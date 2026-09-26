# Encryption at rest

Completed backups can optionally be encrypted with [`age`](https://github.com/FiloSottile/age). Encryption is disabled by default and does not change existing installations until explicitly enabled.

The design uses public recipients on the backup host. The private recovery identity should be generated, protected, and tested on a separate recovery system. The backup host rejects recipient files containing common age/private-key markers.

## Enable age encryption

Install `age` from the Ubuntu package or another independently verified source:

```bash
sudo apt-get update
sudo apt-get install -y age
```

Generate an identity on a separate recovery host:

```bash
umask 077
age-keygen -o unifi-backup-identity.txt
age-keygen -y unifi-backup-identity.txt > unifi-backup-recipient.txt
```

Copy only `unifi-backup-recipient.txt` to the backup host:

```bash
sudo install -o root -g root -m 0600 \
  unifi-backup-recipient.txt /etc/unifi-backup/age-recipients.txt
sudoedit /etc/unifi-backup/unifi-backup.env
```

```bash
ENCRYPTION_TYPE="age"
AGE_RECIPIENTS_FILE="/etc/unifi-backup/age-recipients.txt"
```

The official age CLI supports one or more public recipients through `--recipients-file`; see the [age documentation](https://github.com/FiloSottile/age/blob/main/doc/age.1.html). Do not copy an `AGE-SECRET-KEY` identity to the backup server.

## Result and restore test

A completed artifact becomes:

```text
unifi_os_backup_2026-09-26_03-00-00.unifi.age
unifi_os_backup_2026-09-26_03-00-00.unifi.age.json
```

Decrypt only on an isolated recovery host:

```bash
age --decrypt \
  --identity unifi-backup-identity.txt \
  --output restored.unifi \
  unifi_os_backup_2026-09-26_03-00-00.unifi.age
sha256sum restored.unifi
```

Compare the result with `encryption.plaintext_sha256` in the JSON sidecar, then perform a real restore test in a non-production UniFi environment. An encrypted file and checksum do not prove application-level restorability.

## Security boundary

- The downloaded plaintext exists temporarily as a root-only mode-0600 file while UniFi generates/transfers it and while `age` reads it.
- After successful encryption and atomic publication, that temporary plaintext is removed and only `.unifi.age` remains as the completed backup.
- Normal deletion cannot guarantee physical erasure on SSDs, copy-on-write filesystems, snapshots, or storage with journaling. Use encrypted host storage when protection of transient data or deleted blocks is required.
- Losing every matching identity makes the backup permanently unrecoverable. Maintain independently protected, tested recovery copies.
- Remote storage and Graph mail receive the encrypted artifact when encryption is enabled.
