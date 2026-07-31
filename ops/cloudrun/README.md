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
| Runtime identity | `axom-flood-publisher@<your-gcp-project>.iam.gserviceaccount.com` |
| Scheduler identity | `axom-flood-scheduler@<your-gcp-project>.iam.gserviceaccount.com` |
| Deploy-key secret | `axom-flood-github-deploy-key` |

The runtime service account can read only the deploy-key secret. The scheduler
identity can invoke only the CWC job. The GitHub deploy key can write only to
`Shady-2096/Axom-floods`.

The job clones a fresh `main`, installs the locked Python environment, runs
`axom-flood cwc --backfill-hours 12`, rebuilds the content-hashed PWA bundle,
and pushes a data commit only after both steps succeed.

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
  --set-env-vars AXOM_GITHUB_REPOSITORY=Shady-2096/Axom-floods \
  --cpu 1 \
  --memory 1Gi \
  --task-timeout 20m \
  --max-retries 1 \
  --tasks 1
```

The billing account has an INR 100 monthly budget alert filtered to this
project. A Google Cloud budget is an alert, not a hard spending cap.
