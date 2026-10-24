# Disaster recovery preparation

`unifi-backup-restore` prepares files for a manual UniFi restore. It never changes a controller or calls a speculative restore API.

```bash
sudo unifi-backup-restore --list --json
sudo unifi-backup-restore --latest --output /secure/restore
sudo unifi-backup-restore --backup-id UUID --verify-only --json
sudo unifi-backup-restore --target s3-primary --latest --output /secure/offsite-restore
sudo unifi-backup-restore --date 2026-10-24 --dry-run --json
sudo unifi-backup-restore --latest --identity /secure/recovery-key.txt
```

Selection uses managed filenames and metadata, supports a backup ID/date, and scans independent remote sidecars when `--target` is supplied, even if local backups are lost. Remote discovery needs listing and read permissions. The latest selection skips invalid candidates until a valid backup is found. Explicit ID selection fails rather than substituting another backup.

Every staged artifact is checked against its original size/SHA256. Identity-based decryption checks the recorded plaintext size/hash. Output is mode 0600 in a private mode-0700 directory, never overwrites an existing file, and includes a `.restore.json` report. With no identity, encrypted artifacts remain encrypted and readiness is `verified_encrypted`. Dry-run selects only and writes no backup files. Verification-only leaves no prepared backup. Temporary downloads/decryptions are cleaned up on error.

The report lists origin, backup date/ID, verification levels, known version if present, compatibility warnings, and manual steps. Unknown UniFi versions remain unknown. Verify model/version compatibility and restore in an isolated environment before touching production. A successful preparation is never recorded as a successful application restore test. Hash metadata does not authenticate an attacker-controlled backup: independently protect recovery credentials and original manifests.
