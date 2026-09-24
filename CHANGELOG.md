# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- Reworked the success email as a minimal, table-based HTML layout for predictable rendering in Outlook and other mail clients.

## [1.0.0] - 2026-09-24

### Added

- Defensive UniFi OS controlplane login and system-backup download workflow.
- Atomic files, content checks, SHA256, retention and non-overlapping runs.
- Optional Microsoft Graph `Mail.Send` delivery for small attachments.
- Hardened systemd service and weekly persistent timer.
- Safe install, update and uninstall scripts plus shell-based tests.
