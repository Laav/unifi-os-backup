# Maintainer release procedure

This policy applies permanently to every substantive project release: features, important bug/security fixes, backup/metadata-format changes, installer/updater behavior and other meaningful user-facing changes. Editorial-only documentation changes do not automatically need a new distribution version.

1. Check branch, clean/understood worktree, exact origin URL and maintainer permissions. Fetch origin and tags. Inspect GitHub Releases and tags as well as README, CHANGELOG and CLI versions. Never assume a suggested version is the published version.
2. Choose SemVer: PATCH for compatible fixes, MINOR for compatible new functionality, MAJOR for real breaking changes. Never reuse an existing version/tag/release.
3. Update `bin/unifi-backup`'s VERSION, `lib/ub/core.py`'s VERSION, README, changelog, current documentation and version assertions consistently. Record factual features and limitations only.
4. Run `bash tests/run.sh`, `python3 -m unittest discover -s tests -p 'test_*.py' -v`, ShellCheck on scripts/fixtures, syntax checks, unit verification, privacy/secret review, executable-mode review and `git diff --check`. CI must pass on Ubuntu 22.04, 24.04 and 26.04. Tests requiring infrastructure must be explicitly distinguished from failed tests.
5. Commit only intended changes. Synchronize without destructive resets/force pushes. Push the allowed branch and verify its exact commit plus relevant CI results. Respect branch protection; use a PR when required.
6. Prepare release notes covering features, security, compatibility, upgrade/configuration steps, migrations, limitations and integrations not live-tested. Store the exact multiline text in a file for `gh release create --notes-file`.
7. Recheck that the version is unused, then create an annotated tag for the validated commit:

   ```bash
   git tag -a vX.Y.Z -m 'UniFi OS Backup vX.Y.Z' VALIDATED_COMMIT
   git push origin vX.Y.Z
   git ls-remote origin refs/tags/vX.Y.Z 'refs/tags/vX.Y.Z^{}'
   gh release create vX.Y.Z --repo Laav/unifi-os-backup \
     --verify-tag --title 'UniFi OS Backup vX.Y.Z' --notes-file RELEASE_NOTES.md
   ```

8. Confirm the published release URL, tag target, non-draft/non-prerelease status and Actions results for the branch/tag. GitHub-generated source archives are sufficient; never upload credentials, private keys or backup artifacts.

Do not publish a final release with failed tests, failed available CI, secret exposure or serious unresolved data-safety defects. A justified validation/infrastructure block can leave a documented draft; never claim final publication until GitHub confirms it.

If a release is defective, publish a new fixed version, explain the impact and upgrade path, and mark the prior release appropriately through notes/advisories. Do not retag, rewrite history or substitute other source under the same version.

## Verified starting state for 1.3.0

On 2026-10-24 origin had no Git tags and no published GitHub Releases. README, changelog and executable source all reported 1.2.0 at commit `0d96e1f`. Therefore 1.3.0 is a compatible MINOR increment from the source version and the first published GitHub Release; no previous published release is invented.
