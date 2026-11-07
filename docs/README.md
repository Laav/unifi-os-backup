# Documentation

Use the [repository overview](../README.md) for capabilities and a quick start. This index groups the operational guides by task. Guides describe the current source; [published releases](https://github.com/Laav/unifi-os-backup/releases) and [CHANGELOG.md](../CHANGELOG.md) contain version history. Consult the documentation in your selected tag when running an older release.

## Start and operate

| Task | Guide |
|---|---|
| Install with automatic dependencies; remove or purge | [Installation](INSTALL.md) |
| Create a dedicated local UniFi identity | [Service account](UNIFI-ACCOUNT.md) |
| Configure everything through the terminal | [Configuration wizard](CONFIGURE.md) |
| Understand files, permissions and manual changes | [Configuration architecture](CONFIGURATION.md) |
| Look up every supported field/default/dependency | [Generated configuration reference](CONFIGURATION-REFERENCE.md) |
| Run backups, review schedules and inspect logs | [Operations](OPERATIONS.md) |
| Update safely or roll back | [Updating](UPGRADING.md) |
| Diagnose failures and compatibility changes | [Troubleshooting](TROUBLESHOOTING.md) and [exit codes](EXIT-CODES.md) |

## Protect and recover backups

| Task | Guide |
|---|---|
| Encrypt artifacts with public recipients | [age encryption](ENCRYPTION.md) |
| Select age/count/minimum or GFS retention | [Local retention](RETENTION.md) |
| Configure Azure Blob or S3 credentials | [Object storage](STORAGE.md) |
| Manage independent cloud/filesystem destinations | [Multiple destinations](MULTI-TARGET.md) |
| Inspect/request provider protection | [Immutability](IMMUTABILITY.md) |
| Recheck local integrity or decryption | [Verification](VERIFICATION.md) |
| Recheck remote bytes and process replication failures | [Remote verification and retries](RETRIES.md) |
| Prepare verified files for a manual UniFi restore | [Disaster recovery](DISASTER-RECOVERY.md) |

## Monitor and notify

| Task | Guide |
|---|---|
| Monitor freshness, JSON logs, Prometheus or SNMP/Auvik | [Monitoring](MONITORING.md) |
| Email a supported-size backup through Microsoft Graph | [Graph mail](MICROSOFT-GRAPH.md) |
| Send status/failure/recovery notifications through ntfy | [Notifications](NOTIFICATIONS.md) |
| Integrate a generic signed HTTPS event receiver | [Webhooks](WEBHOOKS.md) |
| Understand per-backup identity and status | [Metadata](METADATA.md) |
| Inspect the installation's combined inventory | [Catalog](CATALOG.md) |
| Detect size, timing or repeated-failure anomalies | [Anomaly analysis](ANOMALIES.md) |
| Compare explicit normalized exports without disclosing values | [Configuration diffing](CONFIG-DIFF.md) |

## Security, development and evidence

- [Security policy](../SECURITY.md): supported security fixes and private reporting.
- [Security design](SECURITY.md): trust boundaries, controls and residual risks.
- [Contributing](../CONTRIBUTING.md): source/documentation workflow and checks.
- [Testing](TESTING.md): reproducible checks and infrastructure limitations.
- [Configuration audit](CONFIGURATION-AUDIT.md) and [validation record](CONFIGURATION-VALIDATION.md): dated design/testing evidence, rather than installation instructions.
- [Release procedure](RELEASING.md) and [publication checklist](PUBLISHING.md): maintainer versioning, privacy review and authorized publication.

Keep credentials, real backups and private configuration journals out of issues, examples, screenshots and Git. Examples use synthetic values; replace them privately through the configuration manager or a protected editor.
