# Public-source publication checklist

[Documentation index](README.md) · [Contributing](../CONTRIBUTING.md) · [Release procedure](RELEASING.md)

Use this checklist before pushing public source. For a software release, also complete the permanent [RELEASING.md](RELEASING.md) procedure. Editorial documentation commits follow normal review and may be pushed without changing versions or creating tags/releases.

## Review source and identity

1. Confirm the intended checkout, branch and canonical origin: `Laav/unifi-os-backup`. Preserve unrelated work and history; do not reinitialize or force-reset an existing repository.
2. Review the intended diff, staged files, ignored paths and relevant history for secrets/personal data. Never upload real backups, email exports, configuration, journals, cookies, private identities, tenant IDs, mailboxes or internal hostnames.
3. Keep examples synthetic and validate screenshots separately. A public-source scanner is useful but does not replace human review. Credentials found in committed history must be revoked/rotated; deleting the current file is insufficient.
4. Use a suitable public commit identity and retain LF endings/executable Git modes. Inspect modes with `git ls-files --stage`; do not broadly stage ignored/private files to fix a test.

## Validate and push

Run the checks appropriate to the change from [TESTING.md](TESTING.md). Documentation checks include links/anchors, examples, configuration-reference consistency and whitespace/privacy review. Software releases require the full local/native Ubuntu matrix, including systemd and security regressions.

Commit only intended changes and push through the authorized branch/PR workflow. Verify the exact remote commit and its CI results. Do not infer tag/release authorization from permission to update documentation. Do not modify a published tag or old release archive to include newer edits.

## Release-specific checks

For an authorized software release, use a new SemVer, factual release notes, an immutable annotated tag and passing final-source/tag CI. Review public raw installer/archive contents, installation on disposable Ubuntu and an isolated restore drill. Do not claim live integrations were tested when only fixtures/mocks ran.

Where repository settings and organizational tooling permit, enable secret scanning/push protection, security alerts, private vulnerability reporting, branch protection and required CI. Use trusted signatures and independently distributed checksums when available; an annotated tag alone is not a signature. Generated GitHub source archives are sufficient release artifacts; never attach operational data.
