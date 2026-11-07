# Configuration manager review and rollout record

Date: 2026-11-07. The original 1.4.1 implementation record below starts at `196bab3` (published v1.3.0). The current 1.4.2 patch validation is recorded separately here. Publication was explicitly authorized. No production server configuration has been changed.

## 1.4.2 patch review

Starting release: v1.4.1, commit `23f4be2`. A literal dollar inside double quotes was incorrectly classified as shell expansion. The parser now distinguishes literal dollars from expansion syntax and reports only a safe basename, line and setting on failure. Real shell expressions are still refused. No user configuration was read, executed or rewritten to diagnose this issue; the exact contents of a reported production configuration are unknown.

Installer/updater share one self-contained dependency provisioner in `install.sh`, so the standalone bootstrap also works when Git is missing. Missing dependencies, including dialog/age, are provisioned before application deployment. Existing configuration separation, default values, service hardening, storage/notification behavior and scheduled backup interfaces remain unchanged. No migration is needed. `--no-install-deps` supports managed/offline hosts. APT package changes are not transactional or rolled back; no general upgrade, repository modification or package removal is requested.

Local Windows validation: **77 Python cases, 63 pass and 14 explicit Linux-only skips**; the Bash suite succeeds with its documented Linux-only branches skipped. ShellCheck 0.11, Bash syntax, Python compilation, whitespace and personal-reference checks pass. The six additional dependency tests/skips are the synthetic Bash comparison plus five root-Linux provisioning methods; the previous eight platform skips remain. Native Ubuntu CI is the release gate for every skipped case.

New regressions cover safe literal dollars against real Bash, refusal of actual expansion, diagnostics without secret values, missing dialog/Git/age, opt-out versus missing core dependencies, idempotence, APT failure, no-TTY/help behavior, and lifecycle updates that stop before replacing binaries on provisioning failure. Every unit/lifecycle-test APT call is mocked/intercepted; none installs packages or accesses a production server. Separately, each disposable Ubuntu CI container runs a standalone copy of the actual installer with `--dependencies-only` to provision dialog/age through real APT before running the suite. This integration step deploys no application/configuration files or units.

Operator test: fetch the new tag and run its updater on an isolated host with dialog absent, confirm automatic provisioning, check both CLI versions, run offline validation and open the UI over SSH. Repeat with a representative private configuration containing literal special characters; cancellation must preserve its bytes. Genuine unsupported expressions should identify only the file/line/setting. Check APT repository failures before deployment and `--no-install-deps` on a pre-provisioned host. Then follow the environment-specific production acceptance steps below; live authentication, backup creation and remote tests remain opt-in.

Verified native evidence: [implementation CI](https://github.com/Laav/unifi-os-backup/actions/runs/42380772634) at `0bca30f`, then [standalone APT integration CI](https://github.com/Laav/unifi-os-backup/actions/runs/42380875849) at `4576a70`, both successful on **Ubuntu 22.04, 24.04 and 26.04**. Each version passes **all 77 Python tests without skips**, **all 16 Bash scripts**, real age/dialog, lifecycle preservation and failed-deployment checks, ShellCheck, systemd verification and installed 1.4.2 CLI/reference checks. The second run also confirms actual installation of both dialog and age via the copied standalone installer on all three versions. Final documentation/source and the immutable release tag receive separate CI before publication.

## Architecture and compatibility review

- [Audit/findings](CONFIGURATION-AUDIT.md), [generated 124-row scoped inventory](CONFIGURATION-REFERENCE.md), [operator walkthrough](CONFIGURE.md).
- One optional dialog interface; declarative schema/model/validation separated from literal parsing, transactional persistence and presentation. Existing backup/storage/recovery protocols are retained.
- Separate secret and per-target files remain justified; no mandatory file-layout migration. Unknown literals/comments survive. Unsupported executable syntax is refused, not sourced by the manager.
- Existing advanced-engine validation now calls the shared schema. Existing Bash/provider validators remain compatibility/security boundaries rather than being replaced wholesale.
- Packaged units/timers are unchanged. New overrides use dedicated owned filenames and keep existing administrator overrides and hardening.

## Changed-file map

Added: `bin/unifi-backup-configure`; `lib/ub/config_schema.py`, `config_files.py`, `config_model.py`, `config_transaction.py`, `config_ui.py`, `configure.py`; `tests/test-config-lock.sh`, `test_configure.py`, `test_configure_install.py`, `test_configure_tui.py`; `docs/CONFIGURATION-AUDIT.md`, `CONFIGURATION-REFERENCE.md`, `CONFIGURE.md`, this review record and `docs/releases/v1.4.1.md`.

Updated: `install.sh`, `update.sh`, `uninstall.sh`; shared Bash common/runtime libraries; main backup, mail, upload, notify and monitor readers; `lib/ub/cli.py` and `core.py`; metadata-version assertion; CI's optional dialog test dependency; `.gitignore`; README, CHANGELOG, CONTRIBUTING and configuration/install/upgrade/security/exit-code/troubleshooting/testing/releasing documentation.

Removed: no application files, configuration templates, backup data, integrations or packaged units. The duplicated manual configuration table is replaced by the generated reference.

## Local and automated Linux validation

Windows development host, working Python 3.14, Git Bash, ShellCheck 0.11 and a real age binary. The first baseline attempt used an incomplete Python installation on PATH and failed before application tests; rerunning with the working interpreter established a successful baseline. No machine-wide Python configuration was changed.

- Baseline: original 25 Python cases (24 pass, 1 Windows symlink skip) and all original 15 Bash test scripts pass.
- Final Python suite: 69 cases, 61 pass, 8 explicitly skipped on this Windows host.
- Final Bash suite: successful; original 15 scripts execute, the additional Linux-only configuration-flock script reports SKIP. The existing operation test's kernel-flock branch is also Linux-only.
- Real age encryption/decryption tests pass locally with ephemeral test keys; the wizard itself never creates private keys.
- ShellCheck, Bash syntax, Python compilation, generated-reference consistency and `git diff --check` pass.
- Public-source guard and known-personal-reference scan pass. Tests use synthetic values and private temporary trees only.

The eight local Python skips are existing-engine symlink enforcement; configuration POSIX permissions/symlinks; protected POSIX/systemd path policy; actual systemd unit/drop-in verification; three real dialog pseudo-terminal tests; and actual lifecycle-script sandbox execution requiring the root Linux CI container.

After publication authorization, the implementation was pushed and tested by the full Ubuntu 22.04/24.04/26.04 matrix. The [successful implementation CI run](https://github.com/Laav/unifi-os-backup/actions/runs/42376036010) validates commit `ab829a7`:

- All **67 Python cases pass without skips on each Ubuntu version**, including all eight cases deferred on Windows.
- All **16 Bash test scripts pass**, including actual kernel flock contention and pending-transaction reader refusal.
- Real dialog PTYs test masked input, Escape and option-like values; fresh/repeated install, update, ordinary removal and purge execute in the private lifecycle sandbox.
- Real age, permissions/symlinks, generated systemd units/drop-ins, ShellCheck, installed help/version and installed generated-reference comparison pass.

The first Linux run found an installation assumption: `/usr/local/sbin` was not initialized in the minimal lifecycle fixture. Installer/updater now explicitly create executable/unit destination directories before deploying helpers; the full matrix passed after this fix. No test was disabled to obtain that result. The final release source and annotated tag are additionally gated by CI before GitHub Release publication; consult their [Actions results](https://github.com/Laav/unifi-os-backup/actions).

Before publication, two additional path-role tests reproduced unsafe references to configuration locks, state/catalog files, recipient/key files and transaction journals. Validation/planning now refuse these overlaps, including disabled integrations and references moved within a draft. The [successful hardened-source CI run](https://github.com/Laav/unifi-os-backup/actions/runs/42377189638) validates commit `f466278`: all **69 Python tests and 16 Bash scripts pass without skips on Ubuntu 22.04, 24.04 and 26.04**, including both new regressions, real dialog/lifecycle/systemd checks and the installed 1.4.1 CLI. The previously created v1.4.0 tag remains immutable and has no published GitHub Release; v1.4.1 contains this hardening. Final documentation/source and tag CI are separate publication gates.

CI runs on x86-64 Ubuntu containers, not real UniFi/cloud infrastructure or a human SSH session. Native ARM64 execution, a visual SSH walkthrough, provider IAM/SAS/WORM setup, real Graph/Auvik/notification delivery and an actual controller restore remain environment-specific acceptance checks. Passing a PTY test is not a claim that every terminal emulator/layout has been visually reviewed.

## Security/recovery review

Read locks precede sourcing. Services open the pre-created configuration lock read-only; apply acquires exclusive configuration and operation locks. File/ancestor/symlink/mode/owner checks, bounded UTF-8 literals, private staging, durable preimages and per-file atomic replacement protect changes. A pending marker prevents updated readers from using an interrupted transaction. Signals roll back; power loss/SIGKILL needs explicit recovery. Preimage corruption or later edits cause safe refusal, not overwrite. Filesystem-wide atomicity across multiple files is not claimed.

Sensitive settings never appear in review/export values or dialog arguments. Existing secrets are not prefilled; public recipients reject private identities. No provider permissions, remote data, live controller or scheduled operation is changed during configuration save. Journal retention intentionally retains old credentials; protect and prune completed records through an approved administrator process. Independent installations/manual editors/older readers require external coordination.

## Required operator acceptance before production

1. On disposable Ubuntu 22.04/24.04/26.04, run the complete checks from TESTING.md. Require the real dialog PTY, Linux read-lock, sandbox lifecycle and systemd/drop-in tests to execute, not skip. Review executable Git modes before committing/publishing.
2. Install the reviewed tree noninteractively, then run `sudo unifi-backup-configure`. Repeat with `install.sh --configure`. Confirm SSH navigation, resize handling, hidden secret input, Back/Next, Cancel/no writes, explicit Finish and no-op repeat apply.
3. Import private **synthetic** copies of representative existing configurations, custom comments, custom file paths and administrator overrides. Test disabled integrations, legacy storage and independent targets without changing production credentials. Confirm unsupported shell syntax refuses rewriting.
4. Review `systemctl cat` and effective ExecStart, calendars and ReadWritePaths. Confirm custom backup/mount paths work with unchanged ProtectSystem/ProtectHome. Verify no timer activates on Finish; explicitly approve any Persistent timer activation after tests.
5. Simulate a writer conflict, failed second replacement, termination and pending recovery. Confirm readers refuse pending state, rollback restores preimages and later edits are never overwritten. Preserve a private independent config/override backup before a rollout.
6. Only with separate operator approval, test UniFi login, read-only provider access/capabilities and a deliberate ntfy/webhook test. Graph attachment delivery remains a separate explicit mailer test. Then create one deliberate backup, verify it and complete an isolated restore drill.

Do not skip the environment-specific acceptance checks merely because automated tests pass. Keep v1.3.0 available for an application rollback, finish/recover any pending transaction first, disable/remove the newer manager entry point when returning to old readers, and review owned overrides separately. Publication follows the authorized release procedure and passing final-source/tag CI.
