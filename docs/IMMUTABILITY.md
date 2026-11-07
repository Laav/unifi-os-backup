# Storage immutability

[Documentation index](README.md) · [Multiple destinations](MULTI-TARGET.md) · [Local retention](RETENTION.md)

Target defaults are `TARGET_IMMUTABILITY=none`. `check` requires existing provider protection; `request` requests protection only on newly created objects. `TARGET_LOCK_MODE` is `GOVERNANCE`/`COMPLIANCE` for S3 or `locked`/`unlocked` for Azure. `TARGET_LOCK_DAYS=30` specifies a horizon from artifact creation, not a new rolling extension on each retry. `COMPLIANCE` or Azure `locked` requests additionally require `TARGET_ALLOW_PERMANENT_LOCK=true`.

No command enables bucket versioning, creates container policies, sets legal holds, shortens retention, bypasses governance, overwrites objects or deletes cloud data. Compliance/locked settings can be irreversible; provision and approve them administratively. S3 capability detection reads GetObjectLockConfiguration and GetBucketVersioning. Actual object protection is checked from HeadObject retention headers. Azure checks container properties and blob properties; a version-level request can be attempted explicitly, but success is only recorded after blob headers confirm the mode and future retention horizon. Legal-hold state is reported, never set automatically.

`unifi-backup-storage-policy --check [--target ID] [--file MANAGED_NAME] --json` reports provider capabilities and optional object-level confirmation. `--dry-run` issues read-only inspections only. A required protection setting never silently falls back to ordinary upload. Missing permissions, unsupported S3-compatible operations, absent retention headers or expired policy produce a failed replication result and retry/dead-letter state.

Provider documentation:

- [S3 PutObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html), [HeadObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html), [GetObjectLockConfiguration](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObjectLockConfiguration.html).
- [Azure Put Blob](https://learn.microsoft.com/rest/api/storageservices/put-blob), [Get Blob Properties](https://learn.microsoft.com/rest/api/storageservices/get-blob-properties), [Get Container Properties](https://learn.microsoft.com/rest/api/storageservices/get-container-properties).

Required permissions include S3 GetObjectRetention/GetObjectLegalHold/GetBucketVersioning/GetBucketObjectLockConfiguration, and PutObjectRetention for requests, or the corresponding Azure read/write/immutable-storage SAS permissions. The tool does not manage account capabilities; confirm versioning, lifecycle and WORM support on your exact provider.

## Local grandfather-father-son policy

Local GFS selection, age/count policies, minimum floors and retry pins are documented in [RETENTION.md](RETENTION.md). Configure remote lifecycle independently so it does not expire objects before required immutability or recovery windows. Preview local selection with `sudo unifi-backup-retention --dry-run --json` before applying changes.
