# Security design

## Trust boundaries

The root service reads local secrets, talks to a configured UniFi HTTPS origin and optionally Microsoft identity/Graph, then writes sensitive backups. Root, the configuration owner, the UniFi server, the host CA trust store, and (when enabled) Microsoft 365 are trusted boundaries.

## Controls

- Secrets are outside Git in root:root 0600 files under a 0700 directory.
- `umask 077`, `mktemp`, traps, a private systemd `/tmp`, and mode 0600 protect transient material.
- Password JSON and OAuth form encoding are done by Python; secret values are streamed on stdin.
- Graph authorization is read by curl from a temporary header file, not exposed in `ps` arguments.
- Normal TLS validation is mandatory. A private CA is explicit; insecure TLS is unsupported.
- HTTP status, TOKEN cookie, minimum size, Content-Type, and leading HTML/JSON content are checked before publish.
- The destination temporary file shares the final filesystem so `mv` is atomic.
- Fixed filename matching, absolute-path checks, positive retention, and a non-root-directory guard constrain deletion.
- `flock` serializes runs.
- systemd denies capabilities and writes outside the configured default backup path while allowing outbound network and CA reads.

## Residual risks

- Root can read every secret and backup; harden and patch the host.
- Another root process can inspect process memory, stdin, or temporary files.
- SHA256 detects accidental change but provides no authenticity unless hashes are stored through an independently protected channel.
- Undocumented UniFi endpoints can change without notice.
- A syntactically plausible `.unifi` file might still be unrestorable. Conduct periodic restore drills.
- Client secrets are supported for initial compatibility; certificate or workload-identity authentication would reduce shared-secret risk but is not implemented.

## Operational recommendations

- Use a long, unique UniFi password and rotate it.
- Use least privilege and test whether a non-Super-Admin role can download system backups on every upgrade.
- Encrypt the backup filesystem or host volume at rest.
- Replicate to a separate failure domain using a reviewed mechanism.
- Alert on failed systemd units and on missing expected weekly files.
- Treat emailed `.unifi` attachments as sensitive and apply mailbox retention/DLP controls.
- Restore-test the newest backup regularly.
