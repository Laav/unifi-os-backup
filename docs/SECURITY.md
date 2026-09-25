# Security design

## Trust boundaries

The root service reads local secrets, talks to a configured UniFi HTTPS origin and optionally Microsoft identity/Graph, Azure Blob or S3-compatible storage, and ntfy, then writes sensitive backups. Root, the configuration owner, the configured services, and the host CA trust store are trusted boundaries.

## Controls

- Secrets are outside Git in root:root 0600 files under a 0700 directory.
- `umask 077`, `mktemp`, traps, a private systemd `/tmp`, and mode 0600 protect transient material.
- Password JSON and OAuth form encoding are done by Python; secret values are streamed on stdin.
- Graph authorization is read by curl from a temporary header file, not exposed in `ps` arguments.
- Azure SAS, S3 signing material, signed URLs, and ntfy bearer tokens are likewise kept in root-only configuration and mode-0600 temporary files rather than command-line values.
- Normal TLS validation is mandatory. A private CA is explicit; insecure TLS is unsupported.
- HTTP status, TOKEN cookie, minimum size, Content-Type, and leading HTML/JSON content are checked before publish.
- The destination temporary file shares the final filesystem so `mv` is atomic.
- Fixed filename matching, absolute-path checks, non-negative bounded retention, a minimum-count floor, and a non-root-directory guard constrain deletion.
- `flock` serializes runs.
- systemd denies capabilities and writes outside the configured default backup path while allowing outbound network and CA reads.

## Residual risks

- Root can read every secret and backup; harden and patch the host.
- Another root process can inspect process memory, stdin, or temporary files.
- SHA256 detects accidental change but provides no authenticity unless hashes are stored through an independently protected channel.
- Undocumented UniFi endpoints can change without notice.
- A syntactically plausible `.unifi` file might still be unrestorable. Conduct periodic restore drills.
- Client secrets are supported for initial compatibility; certificate or workload-identity authentication would reduce shared-secret risk but is not implemented.
- The status/Prometheus files are intentionally world-readable for local monitoring agents and therefore contain no credentials. They do contain filenames, hashes, sizes, and timestamps.
- Remote object storage exposes sensitive controller backups to another security boundary. Provider-side encryption does not replace least privilege, immutability, or client-side encryption requirements in higher-risk environments.

## Operational recommendations

- Use a long, unique UniFi password and rotate it.
- Use least privilege and test whether a non-Super-Admin role can download system backups on every upgrade.
- Encrypt the backup filesystem or host volume at rest.
- Replicate to a separate failure domain with a prefix-scoped, write-only identity and provider lifecycle/immutability controls.
- Alert on failed systemd units and on missing expected weekly files.
- Treat emailed `.unifi` attachments as sensitive and apply mailbox retention/DLP controls.
- Restore-test the newest backup regularly.
