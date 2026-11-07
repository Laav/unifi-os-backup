# Updating and rollback

[Documentation index](README.md) · [Installation](INSTALL.md) · [Release history](../CHANGELOG.md)

## Choose the source you intend to install

The updater installs the source in the current checkout. It does not fetch, select or publish a release. Use a reviewed [published tag](https://github.com/Laav/unifi-os-backup/releases) for reproducibility, or deliberately follow `main` for branch updates.

Before updating, review release notes and local changes. Keep an independently protected configuration backup, including referenced external files and administrator drop-ins. Never force a checkout/reset over local changes. Plan updates between backup/configuration jobs; jobs using older binaries must finish before using newer configuration transactions.

## Update to a reviewed release

This example selects `v1.4.2`. Replace the tag with the reviewed release you intend to deploy.

```bash
cd /opt/unifi-os-backup
git status --short
sudo git fetch origin --tags
sudo git switch --detach v1.4.2
sudo ./update.sh
unifi-backup --version
unifi-backup-configure --version
sudo unifi-backup-configure --validate --json
sudo unifi-backup-configure --inspect --json
```

Both version commands should match the selected source. A detached release checkout is expected; it cannot use `git pull` as a tracked branch. Documentation-only commits on `main` do not change the installed software version or alter existing release archives.

## Update an existing main-branch checkout

```bash
cd /opt/unifi-os-backup
git status --short
git branch --show-current
sudo git pull --ff-only
sudo ./update.sh
sudo unifi-backup-configure --validate
```

Use this sequence when the current branch is `main`. To move deliberately from a detached release to the branch, first review local changes, fetch origin and select/create the local branch tracking `origin/main`. Do not use a forced reset to resolve a non-fast-forward update.

## What the updater preserves and changes

The updater replaces installed programs, shared modules and packaged units. It preserves existing main/integration configuration, recipients, independent target files, backup artifacts and operational state. Missing optional configuration examples may be created with fictitious placeholders and mode 0600; existing files are never replaced.

Missing application dependencies, including dialog and age, are provisioned through configured APT repositories before application deployment. No manual `apt install` step is required. `sudo ./update.sh --no-install-deps` opts out for managed/offline hosts. Missing core tools or provisioning failures return 69; APT package changes are not rolled back. See [dependency provisioning](INSTALL.md#prerequisites-and-dependency-provisioning).

The updater does not run the wizard, convert configuration expressions or migrate legacy storage. It reloads systemd, enables the monitor timer and tries to restart already active backup/monitor timers; previously inactive timers are not started. Review persistent timers when scheduling a maintenance window. Verification, remote-verification and retry timers remain independently opt-in.

New defaulted fields do not require copying an entire example over production configuration. Use `sudo unifi-backup-configure` to review supported settings, or compare the [generated field reference](CONFIGURATION-REFERENCE.md) and examples privately before manual edits.

## Validate behavior after updating

Offline validation reports syntax, security, dependency and configuration issues without running network tests or rewriting files. Warnings alone do not make validation fail. Unsupported shell expressions remain refused by the configuration manager even if an older Bash reader accepted them; see [literal assignments](CONFIGURATION.md#manual-configuration-and-trust).

When ready, explicitly test login and create one backup:

```bash
sudo unifi-backup-check --live
sudo systemctl start unifi-backup.service
sudo journalctl -u unifi-backup.service --since "10 minutes ago" --no-pager
sudo unifi-backup-verify --latest --json
```

Check each enabled remote destination and notification independently. Graph HTTP 202 confirms acceptance, not delivery. Repeat login and actual backup creation after every UniFi OS upgrade because the controlplane endpoints can change. Perform recovery drills on isolated infrastructure.

## Existing configuration and migration

No physical configuration-layout migration is required for the terminal manager. It reads existing supported literals, preserves unknown literals/comments and uses current values. It does not reset secrets or activate optional integrations.

- Nonempty `BACKUP_TARGETS` takes precedence over legacy single-target storage. Legacy credentials are not automatically copied, merged or activated. Follow [storage transitions](CONFIGURE.md#storage-mode-transitions) when migrating deliberately.
- Custom file references and administrator overrides remain in place. The wizard creates narrowly scoped owned drop-ins only after review. Changing `BACKUP_DIR` manually also requires reviewing service write access.
- Manager transactions use a shared configuration lock, operation locks and a persistent recovery marker. Older binaries/manual editors do not participate automatically. Do not mix them with active transactions.
- Verification/retry flags and their timers are independent. Review required permissions before enabling reads, listing, full remote verification or immutability requests; legacy upload-only credentials remain usable for their original upload workflow.

For an older installation, review the intervening [changelog](../CHANGELOG.md), [archived release notes](releases/) and [configuration reference](CONFIGURATION-REFERENCE.md). Historical versions remain identified there; unreleased source versions are not invented as published releases. In particular, v1.4.0 is an unpublished source tag, superseded by the published v1.4.1 release.

## Rollback

Application rollback and configuration rollback are separate operations. Preserve configuration, state and backups before either. Complete/recover pending configuration transactions first; never delete a pending marker to make an older reader run.

For application rollback, select the exact previously verified tag, run that checkout's updater and retest. Review its compatibility with current metadata, encrypted artifacts, retry pins, retention policy and drop-ins. Disable incompatible scheduled workers deliberately; older retention must not remove sources needed by a newer retry queue. Historical source-only versions require a reviewed commit, not an invented release tag.

For a completed configuration transaction, use its privately recorded transaction ID:

```bash
sudo unifi-backup-configure --rollback TRANSACTION_ID --yes
```

For an interrupted transaction:

```bash
sudo unifi-backup-configure --recover --yes
```

Use the same custom `--config` path when applicable. Recovery validates preimages/current hashes and refuses to overwrite later operator edits. See [transaction recovery](CONFIGURE.md#transactions-backup-and-recovery-of-configuration) for locking, journal protection and rollback limits.
