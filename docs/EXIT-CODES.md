# Exit codes

The 1.4 configuration manager follows the same ranges, with 65 for unsafe/unsupported syntax, 69 for missing UI/system tools, 73 for apply failure with completed rollback, 75 for write conflicts/locks or incomplete rollback, 77 for manager ownership/path security violations, and 78 for invalid configuration. Offline JSON validation distinguishes error categories and warnings. Backup/live-helper and monitoring codes retain their existing meanings. See [CONFIGURE.md](CONFIGURE.md).

The commands use the established BSD `sysexits` range where practical. Monitoring status uses the separate Nagios convention documented below.

| Code | Name/category | Typical meaning |
|---:|---|---|
| `0` | success | Requested operation completed |
| `64` | usage | Unknown/missing command-line argument |
| `65` | data error | Invalid managed filename, JSON, or input content |
| `66` | input unavailable | Backup/metadata file missing, empty, unsafe, or unreadable |
| `69` | service unavailable | Missing dependency/helper, DNS/connect/TLS transport failure |
| `70` | internal software error | Internal invariant or logging-field failure |
| `73` | cannot create | Local directory/file/metadata/status creation failure |
| `74` | I/O or validation error | Invalid/empty/small/error-like backup, endpoint/encryption failure, or retention I/O error |
| `75` | temporary/remote failure | Active lock, required Azure/S3 upload failure, Graph send failure, or ntfy/webhook rejection |
| `77` | permission/authentication | UniFi or Graph authentication/authorization failure |
| `78` | configuration | Missing, insecure, unsupported, or inconsistent configuration |
| `129` | signal | SIGHUP |
| `130` | signal | SIGINT |
| `143` | signal | SIGTERM |

New maintenance commands use the same categories. Native-format diff capability errors use 69, corrupted verification uses 74, failed required replication uses 75, and anomaly analysis uses 1 for a warning. JSON reports retain separate local-integrity and replication outcomes. `unifi-backup-restore` prepares files only; success does not mean a controller was restored.

HTTP and curl error categories are included in the sanitized log message and JSON `event`; secrets and response bodies are not logged. systemd exposes the numeric result through `systemctl status unifi-backup.service`.

## Monitoring exit codes

`unifi-backup-status --format text` and `--format json` use:

| Code | State |
|---:|---|
| `0` | OK |
| `1` | WARNING |
| `2` | CRITICAL |
| `3` | UNKNOWN |

`--format snmp` prints this number but exits zero so Net-SNMP can expose the value as a numeric custom OID. `--format prometheus` also exits zero after successful rendering.

`unifi-backup-monitor` returns the same `0`/`1`/`2`/`3` monitoring codes. Its systemd unit declares 1 and 2 as successful service outcomes so WARNING/CRITICAL backup state does not masquerade as a crashed checker; UNKNOWN remains a failed unit run.
