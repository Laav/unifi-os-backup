# Security policy

## Supported versions

Security fixes are provided for the latest tagged release. Operators should test and deploy updates promptly, especially after UniFi OS or Microsoft Graph behavior changes.

## Reporting a vulnerability

Do not open a public issue containing credentials, tokens, backup data, internal URLs, tenant identifiers, or exploit details. Use the repository owner's private vulnerability-reporting channel (GitHub Security Advisories is recommended). Include the affected version, impact, reproduction steps using fictitious data, and any proposed mitigation.

Rotate affected UniFi credentials, Graph client secrets, webhook/ntfy/storage tokens, and HMAC secrets before sharing sanitized diagnostics. Never attach a real `.unifi`, `.unifi.age`, age identity, or private recipient configuration file.

## Scope

Reports about secret disclosure, path traversal, unsafe retention, TLS bypass, command injection, permission failures, token leakage, and systemd sandbox escapes are in scope. Availability of undocumented UniFi endpoints is a compatibility issue unless it causes unsafe behavior.
