# Remote verification and retries

`unifi-backup-remote-verify --latest|--all [--target ID] [--full] [--json]` checks existence, size and configured checksum metadata. `--full` downloads the complete object and hashes actual bytes. Metadata matches and upload HTTP success never imply a full byte check. Remote ETags are not hashes.

`unifi-backup-retry` processes due pending tasks from `retry-queue.json`. The shared backup lock serializes backup, retention, verification and retry operations. Atomic persistent state survives a reboot. A task is uniquely keyed by backup ID and target. Replaying a crashed upload requires identical contents before accepting an existing object.

Defaults: 8 total attempts (including initial upload), exponential backoff from 300 seconds, jitter between half and the capped interval, maximum interval 86400 seconds, maximum task age 7 days, and 1000 pending tasks. `--force-due` skips scheduling delay only. It does not reset attempt limits.

Pending tasks pin their local backup and sidecar against retention. Exhausted, expired, invalid-source, removed-target and queue-capacity tasks become explicit dead letters and release that pin. The queue never silently retries corrupt local input. Inspect `retry-queue.json` and alerts before deleting source data; a dead letter means replication is no longer guaranteed. At most the configured number of terminal tasks are retained. Active pins can increase disk usage: monitor free space and queue lag; finite age/attempt/capacity limits bound that risk.

Metrics expose pending/dead uploads, attempts and oldest replication lag in `unifi_retry.prom`. Enable the retry timer explicitly after reviewing target permissions and policy.
