# ASDMA Mac publisher

ASDMA publishes one official Flood Situation Report per report date. This
LaunchAgent checks twice in the evening, at 20:00 and 22:00 local time, and once
when it is loaded after login. Repeated checks are content-idempotent: if the
newest available PDF revision is already committed, nothing is pushed.

This is an opportunistic residential-network path, not an always-on runner. It
does not keep the Mac awake. A scheduled check missed while the machine is
unavailable runs when launchd next loads the agent, but a powered-off Mac cannot
provide guaranteed daily publication.

Each run:

1. clones a fresh public `main` into a temporary directory;
2. installs the locked Python environment;
3. runs the three-day ASDMA lookup with bounded retries;
4. validates the candidate and writes immutable validation/public impact
   artifacts before replacing the current pointer;
5. commits only ASDMA raw, processed, summary, and public impact artifacts;
6. rebases over any concurrent CWC data commit and pushes `main`; and
7. verifies that production serves the exact expected impact revision.

A structurally unfamiliar or invalid candidate is quarantined. Its raw source
and validation evidence are still committed, the prior public pointer remains
unchanged, and the task exits unsuccessfully so the failure is visible. The
ASDMA task does not rebuild the shared CWC content bundle; it publishes through
the stable `data/impact-current.json` pointer to avoid racing the independent
CWC publisher.

The task uses the current macOS user's GitHub credential from Keychain. It does
not use the disabled `axom-india-mac` GitHub Actions runner.

## Operations

Inspect the agent:

```sh
launchctl print gui/$(id -u)/com.axom-flood.asdma-publisher
```

Watch logs:

```sh
tail -f "$HOME/Library/Logs/Axom Flood/asdma-publisher.log"
tail -f "$HOME/Library/Logs/Axom Flood/asdma-publisher.error.log"
```

Run an immediate check:

```sh
launchctl kickstart -k gui/$(id -u)/com.axom-flood.asdma-publisher
```

Stop and disable it without deleting its configuration:

```sh
launchctl disable gui/$(id -u)/com.axom-flood.asdma-publisher
launchctl bootout gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.axom-flood.asdma-publisher.plist"
```
