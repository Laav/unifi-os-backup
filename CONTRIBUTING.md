# Contributing

Keep changes focused, reviewable and free of production data. Use English in source-facing documentation, examples and interface text. The [documentation index](docs/README.md) is the starting point for operator guides.

## Public-source safety

Use synthetic endpoints, identities and credentials. Never commit a real controller URL, username, password, tenant/client identifier, mailbox, token, cookie, backup, email export or private recovery identity. Configuration and transaction journals belong outside Git. Screenshots must not reveal personal accounts, private hostnames or operational data.

Report vulnerabilities through [SECURITY.md](SECURITY.md). Do not put exploit details or secret-bearing diagnostics in a public issue. A source scanner supplements manual review; it cannot prove that every artifact is safe.

## Code changes

Preserve Bash 4 compatibility, Python standard-library operation, LF line endings and executable Git modes. Respect protected configuration, TLS validation, locking, atomic publication and the distinction between local integrity, replication, notification and actual restoration.

Explain the problem, resulting behavior, compatibility/security consequences and validation. Use synthetic fixtures for meaningful behavior changes. Do not guess undocumented UniFi endpoints or broaden cloud permissions to hide a failure. Security-sensitive changes to authentication, paths/deletion, signing, secrets, encryption, sandboxing, recovery or provider permissions require explicit review.

Run the applicable checks from [TESTING.md](docs/TESTING.md), including the complete Ubuntu matrix for substantive software changes. Do not claim live cloud/controller validation from mocks, or count platform skips as passes.

## Documentation changes

- Keep the README focused on capabilities, installation and navigation. Put version history in CHANGELOG and Releases.
- Describe the current behavior in task-oriented guides; retain dated audit records and archived release notes as historical evidence.
- Keep one generated field inventory in `docs/CONFIGURATION-REFERENCE.md`. Change its schema source and regenerate it when behavior changes; do not hand-edit or duplicate the table.
- Label pinned versions as explicit examples and keep their download/checkout tags consistent. Do not imply the default-branch bootstrap selects a release.
- Verify relative links/anchors, command names/options, fenced examples, privacy and `git diff --check`. Do not execute state-changing examples merely to proofread them.
- Documentation on `main` may be newer than a release archive. Link release-specific claims to the relevant tag/evidence.

Editorial documentation updates can be committed and pushed through the normal review process without changing software versions, tags or published releases. Software behavior changes follow [RELEASING.md](docs/RELEASING.md); publication requires explicit authorization.
