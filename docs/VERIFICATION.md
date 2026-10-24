# Integrity verification

`unifi-backup-verify --latest`, `--all`, `--file ABSOLUTE_FILE`, or `--backup-id ID` recheck managed backups against their original JSON metadata. `--json` produces per-file results; `--quiet` uses exit status only. A missing/malformed sidecar, changed bytes, different size, incomplete filename, HTML/JSON error response, or symlink fails safely.

`--decrypt-check --identity /secure/recovery-key.txt` additionally decrypts age ciphertext into a mode-0700 temporary directory, checks the original plaintext hash/size, and cleans it up. The identity must be owned by the operator with no group/other access. It need not remain on the server. Keep recovery identities off-host between checks.

The results distinguish metadata validity, ciphertext/backup hash validity, decryption, limited structure checks, and actual restore testing. `.unifi` is an opaque controlplane format: Ubiquiti documents UI restoration but does not provide a stable public container specification. Only error-page exclusion and the documented age envelope are checked. `structure=limited` never claims parseability; `restore_tested` remains false. Perform manual restore drills.

State is stored atomically in `verification.json`; `unifi_verification.prom` exports result, timestamp, and cumulative failed checks. Hashes/sidecars are not signatures and must be protected independently for authenticity.
