# Google Cloud data publisher

The operational CWC refresh runs as a Cloud Run Job in Google Cloud's Mumbai
region. It does not depend on a laptop, VM, or GitHub-hosted access to the
official source.

## Deployed resources

| Resource | Value |
| --- | --- |
| Project | `<your-gcp-project>` |
| Region | `asia-south1` (Mumbai) |
| CWC job | `axom-flood-cwc-publisher` |
| Schedule | `axom-flood-cwc-every-2h` at minute 17 every two hours, Asia/Kolkata |
| Rainfall job | `axom-flood-rainfall-publisher` |
| Schedule | `axom-flood-rainfall-every-2h` at minute 47 every two hours, Asia/Kolkata |
| Runtime identity | `axom-flood-publisher@<your-gcp-project>.iam.gserviceaccount.com` |
| Scheduler identity | `axom-flood-scheduler@<your-gcp-project>.iam.gserviceaccount.com` |
| Deploy-key secret | `axom-flood-github-deploy-key` |
| Earthdata secret | `axom-flood-earthdata-token` |

The runtime service account can read only the deploy-key and Earthdata secrets.
The scheduler identity can invoke only these jobs. The GitHub deploy key can
write only to `Shady-2096/axom-flood`, the public repository the site is built
from. (`Shady-2096/Axom-floods` was the private predecessor and is
decommissioned.)

The CWC job clones a fresh `main`, installs the locked Python environment, runs
`axom-flood cwc --backfill-hours 12`, rebuilds the content-hashed PWA bundle,
and pushes a data commit only after both steps succeed.

The rainfall job is separate on purpose. River level is what people came for and
rainfall is context, so a NASA outage, an expired Earthdata token, or a slow
archive must never be able to hold up a gauge reading. It is also a different
shape of work: CWC is one request, rainfall is 144.

Two jobs now write to the same branch, so `publish_changes` rebases once and
retries if the remote moved while a run was working. The schedules are staggered
half an hour apart, and the jobs touch different files — the CWC job writes the
content bundle, the rainfall job writes its own artifact and pointer — so the
rebase is clean. It never force-pushes; a genuine conflict fails the run, and the
next execution starts from a fresh clone.

## Connectivity result

The no-write probe was executed in both Indian Cloud Run regions on 2026-07-28:

- CWC passed in Mumbai and Delhi. Mumbai returned the Kampur reading from the
  real latest-level endpoint in 6.5 seconds.
- The ASDMA form GET timed out after 45 seconds in both Mumbai and Delhi.

Therefore only CWC is scheduled on Google Cloud. The image contains a `daily`
mode for the complete pipeline, but it must not be scheduled unless an
India-reachable ASDMA transport has first passed the same no-write gate.

## Operations

Inspect recent executions:

```sh
gcloud run jobs executions list \
  --job axom-flood-cwc-publisher \
  --region asia-south1 \
  --project <your-gcp-project>
```

Read job logs:

```sh
gcloud run jobs logs read axom-flood-cwc-publisher \
  --region asia-south1 \
  --project <your-gcp-project>
```

Start an immediate refresh:

```sh
gcloud run jobs execute axom-flood-cwc-publisher \
  --region asia-south1 \
  --project <your-gcp-project> \
  --wait
```

Pause or resume the two-hour schedule:

```sh
gcloud scheduler jobs pause axom-flood-cwc-every-2h \
  --location asia-south1 \
  --project <your-gcp-project>

gcloud scheduler jobs resume axom-flood-cwc-every-2h \
  --location asia-south1 \
  --project <your-gcp-project>
```

Redeploy the image after changing this directory:

```sh
gcloud run jobs deploy axom-flood-cwc-publisher \
  --source ops/cloudrun \
  --region asia-south1 \
  --project <your-gcp-project> \
  --command /opt/axom-cloudrun/run-job.sh \
  --args cwc \
  --service-account \
  axom-flood-publisher@<your-gcp-project>.iam.gserviceaccount.com \
  --set-secrets GITHUB_DEPLOY_KEY=axom-flood-github-deploy-key:latest \
  --set-env-vars AXOM_GITHUB_REPOSITORY=Shady-2096/axom-flood \
  --cpu 1 \
  --memory 1Gi \
  --task-timeout 20m \
  --max-retries 1 \
  --tasks 1
```

## Setting up the rainfall job

Three steps, run once. The first two need values only the owner has.

**1. Store the Earthdata token.** It is a bearer token from Earthdata → Generate
Token, and the current one expires **2026-10-05**. Reading it from a file keeps
it out of shell history:

```sh
gcloud secrets create axom-flood-earthdata-token \
  --replication-policy automatic \
  --project <your-gcp-project>

gcloud secrets versions add axom-flood-earthdata-token \
  --data-file=/path/to/token.txt \
  --project <your-gcp-project>
```

Add a version the same way when it expires. The job reads `:latest`, so a new
version is picked up on the next run with no redeploy.

**2. Let the runtime identity read it:**

```sh
gcloud secrets add-iam-policy-binding axom-flood-earthdata-token \
  --member serviceAccount:axom-flood-publisher@<your-gcp-project>.iam.gserviceaccount.com \
  --role roles/secretmanager.secretAccessor \
  --project <your-gcp-project>
```

**3. Deploy the job and its schedule:**

```sh
gcloud run jobs deploy axom-flood-rainfall-publisher \
  --source ops/cloudrun \
  --region asia-south1 \
  --project <your-gcp-project> \
  --command /opt/axom-cloudrun/run-job.sh \
  --args rainfall \
  --service-account \
  axom-flood-publisher@<your-gcp-project>.iam.gserviceaccount.com \
  --set-secrets GITHUB_DEPLOY_KEY=axom-flood-github-deploy-key:latest,EARTHDATA_TOKEN=axom-flood-earthdata-token:latest \
  --set-env-vars AXOM_GITHUB_REPOSITORY=Shady-2096/axom-flood \
  --cpu 1 \
  --memory 1Gi \
  --task-timeout 30m \
  --max-retries 1 \
  --tasks 1
```

```sh
gcloud scheduler jobs create http axom-flood-rainfall-every-2h \
  --location asia-south1 \
  --project <your-gcp-project> \
  --schedule "47 */2 * * *" \
  --time-zone Asia/Kolkata \
  --uri "https://asia-south1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/<your-gcp-project>/jobs/axom-flood-rainfall-publisher:run" \
  --http-method POST \
  --oauth-service-account-email \
  axom-flood-scheduler@<your-gcp-project>.iam.gserviceaccount.com
```

Minute 47, against the CWC job's minute 17. Half an hour apart, and a rainfall
run takes about six minutes, so the two never overlap.

### Why 30 minutes of task timeout for a six-minute job

A cold run fetches all 144 half hours serially, which measured 327 seconds on
2026-08-07 at a median of 2 seconds a granule. The first ten requests take 20-30
seconds each before the archive warms up, so a bad day is several times the good
one, and GES DISC serialises us anyway — concurrency does not work, a second
connection is left in `SYN_SENT` forever. Twenty minutes would be cutting it
close on a slow day for no saving.

### Optional: stop refetching everything

Cloud Run clones the repository into a fresh temporary directory each execution,
so the subset cache is thrown away and every run refetches all 144 granules. That
works, and it is what the schedule above does.

A bucket mounted at the cache path turns a run into the four granules that are
actually new. Set `RAINFALL_SUBSET_DIR` to the mount point and add the volume:

```sh
gcloud storage buckets create gs://<your-bucket> \
  --location asia-south1 \
  --project <your-gcp-project>
```

then add to the deploy above:

```sh
  --set-env-vars AXOM_GITHUB_REPOSITORY=Shady-2096/axom-flood,RAINFALL_SUBSET_DIR=/mnt/imerg \
  --add-volume name=imerg,type=cloud-storage,bucket=<your-bucket> \
  --add-volume-mount volume=imerg,mount-path=/mnt/imerg
```

The runtime identity needs `roles/storage.objectAdmin` on the bucket. This is an
optimisation and never a correctness question: an empty cache costs time, never
accuracy. Cached subsets are named by the set of grid cells they were cut to, so
promoting a circle to an analysis boundary invalidates them and the next run
refetches — which is the intended behaviour, not a fault.

## Operating the rainfall job

Same commands as the CWC job with the name swapped. To publish immediately:

```sh
gcloud run jobs execute axom-flood-rainfall-publisher \
  --region asia-south1 \
  --project <your-gcp-project> \
  --wait
```

The job fails loudly and publishes nothing when the token is missing or expired.
That is the intended behaviour: the site keeps showing the previous artifact,
which is dated in its own copy, rather than a rainfall number nobody stands
behind.

The billing account has an INR 100 monthly budget alert filtered to this
project. A Google Cloud budget is an alert, not a hard spending cap.
