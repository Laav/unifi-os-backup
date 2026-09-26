# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [1.2.0] - 2026-09-26

### Added

- Optional age recipient encryption for completed local, remote, and emailed backup artifacts; disabled by default.
- Hourly stale-backup SLA evaluation with transition-only warning, critical, and recovery notifications.
- Generic HTTPS JSON webhooks with protected URLs, optional Bearer authentication, and optional HMAC-SHA256 body signatures.
- Atomic machine-readable central backup catalog generated from validated metadata sidecars.
- Encryption, webhook, catalog, and stale-transition regression tests.

### Changed

- Metadata, status, Graph email, retention, upload filename validation, installers, and monitoring now understand encrypted `.unifi.age` artifacts.

## [1.1.0] - 2026-09-25

### Added

- Optional Azure Blob Storage uploads using `Put Blob` with a protected SAS and overwrite prevention.
- Optional S3/S3-compatible uploads using Signature Version 4, payload hashes, conditional writes, and optional provider-side encryption headers.
- JSON backup metadata sidecars, also included in Microsoft Graph email and remote storage.
- Atomic monitoring state, Prometheus textfile metrics, Nagios/JSON/Prometheus output, and an Auvik-compatible SNMP numeric status.
- Optional token-authenticated ntfy failure, recovery, and success notifications.
- Stable documented exit-code categories and machine-readable JSON event logging.
- Combined retention by age, maximum count, and minimum preserved count.
- A bounded fresh-login retry for transient HTML/JSON-like backup responses.

### Changed

- Reworked the success email as a minimal, table-based HTML layout for predictable rendering in Outlook and other mail clients.

## [1.0.0] - 2026-09-24

### Added

- Defensive UniFi OS controlplane login and system-backup download workflow.
- Atomic files, content checks, SHA256, retention and non-overlapping runs.
- Optional Microsoft Graph `Mail.Send` delivery for small attachments.
- Hardened systemd service and weekly persistent timer.
- Safe install, update and uninstall scripts plus shell-based tests.
