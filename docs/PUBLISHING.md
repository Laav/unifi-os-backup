# Publishing checklist

The source tree is designed to be public, but the final GitHub owner/repository URL is environment-specific and cannot be inferred. Before the first public push:

1. Verify that every canonical repository URL points to `Laav/unifi-os-backup`.
2. Initialize Git if needed and record executable modes:

   ```bash
   git init
   git add .
   git update-index --chmod=+x install.sh update.sh uninstall.sh
   git update-index --chmod=+x bin/*
   git update-index --chmod=+x tests/run.sh tests/test-*.sh tests/fixtures/mock-*
   ```

3. Run `bash tests/run.sh` and ShellCheck on Ubuntu. Let the matrix CI pass on 22.04, 24.04, and 26.04.
4. Review `git diff --cached`, `git status --ignored`, and the complete commit history for secrets. Automated secret scanning supplements but does not replace manual review.
5. Confirm no `.unifi`, `.env`, private key, certificate bundle containing a private key, cookie, token, internal hostname, tenant identifier, real mailbox, or customer data is tracked.
6. Enable GitHub secret scanning, push protection, Dependabot/security alerts where applicable, private vulnerability reporting, branch protection, and required CI.
7. Create a signed initial commit/tag when organizational tooling supports it. Publish SHA256 checksums for release archives through GitHub Releases and, ideally, an independently controlled channel.
8. Download the public raw `install.sh` and a release/archive as an external user, inspect them, test bootstrap installation on a disposable Ubuntu host, then perform a restore drill with a non-production UniFi instance.

Do not add secrets to fix an example or test. If a secret ever enters a commit, revoke/rotate it immediately; deleting the working-tree file is not enough because Git history and forks may retain it.
