# Contributing

Keep changes small, reviewable, and free of production data. Never commit a real endpoint, username, password, tenant/client identifier, secret, token, certificate private key, email address, cookie, or `.unifi` backup.

Before opening a pull request:

```bash
bash tests/run.sh
shellcheck install.sh update.sh uninstall.sh bin/* tests/*.sh tests/fixtures/mock-*
```

Explain security consequences, compatibility assumptions, and manual tests. Changes to authentication, endpoints, deletion, filesystem paths, curl arguments, systemd hardening, Graph permissions, or secret handling require explicit security review.

Do not add an undocumented UniFi fallback endpoint based on guesswork. Link authoritative documentation where it exists and label observed controlplane behavior as unsupported. Do not broaden Microsoft Graph permissions merely to accommodate an attachment workflow without documenting and reviewing the extra access.

Use LF line endings and preserve Bash 4 compatibility. New behavior should include a dependency-free shell test suitable for Ubuntu 22.04, 24.04, and 26.04.
