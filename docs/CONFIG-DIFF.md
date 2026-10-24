# Configuration diffs and format capability

The tested local `.unifi` sample has no recognized ZIP/GZIP/age envelope. Ubiquiti's [backup documentation](https://help.ui.com/hc/en-us/articles/360008976393-Backups-and-Migration-in-UniFi) describes backup and UI restore but provides no stable public native container/extraction contract. This release therefore does **not** claim native `.unifi` or embedded `.unf` semantic parsing. It fails with exit 69 (`unsupported`) when a hash-bound normalized export is absent. No encryption keys or format guesses are embedded.

`unifi-backup-diff --old FILE --new FILE`, `--latest-two`, or `--backup-id-old ID --backup-id-new ID` compares explicit normalized configuration snapshots. An independently reviewed exporter can place a root-only `<backup-filename>.config.json` companion beside a backup:

```json
{
  "schema": "unifi-backup-config/v1",
  "backup_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "categories": {
    "networks": [{"id": "stable-network-id", "vlan": 120}],
    "wifi": [{"id": "stable-wlan-id", "security": "wpa3"}]
  }
}
```

This is this project's **adapter schema**, not an asserted UniFi file format. A companion must match the actual artifact SHA256; direct `.config.json` inputs are explicitly operator-supplied exports. The tool validates backup bytes before consuming a companion. It never guesses how to generate one from opaque native bytes.

Supported category names are networks, firewall, nat, port_forwarding, vpn, wifi, dhcp, dns, admins and security, when provided by that exporter. Objects need unique stable string IDs. Added/removed/modified/optional unchanged statuses are deterministic. Common volatile timestamps are ignored. Unknown categories are reported as unsupported; malformed objects fail explicitly.

Output never contains source values, arbitrary field names, raw object IDs, passwords, tokens, SSIDs or network addresses. Object IDs become opaque hashes; only category, change kind, field count and `[REDACTED]` are emitted. There is no show-secrets option. `--summary`, `--category firewall`, `--unchanged` and `--json` adjust output without exposing values.

`DIFF_ENABLED=true` enables an optional automatic latest-two comparison; unsupported snapshots or failed comparisons are reported without blocking the backup. `config-diff.json` holds the last redacted result. Native extraction remains a documented capability limitation until a reliable supported format contract is available.
