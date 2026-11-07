# Validation and infrastructure boundaries

```bash
bash tests/run.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
shellcheck install.sh update.sh uninstall.sh bin/* lib/*.sh tests/*.sh tests/fixtures/mock-*
python3 -m compileall -q lib/ub
git diff --check
```

Configuration-specific coverage additionally includes literal parser/serializer round trips (quotes, dollars, Unicode, multiline and ANSI literals), comment/unknown preservation, inactive integrations, legacy transitions, independent targets/quorum, redacted diagnostics, permissions/symlinks, UI Back/Cancel, missing TTY/dialog, interruption rollback, corrupt preimages, pending recovery, concurrent writers and stale dependency edits. `test-config-lock.sh` exercises shared read-only descriptor locks and pending-reader refusal on Linux.

Reserved-path regression tests reject configuration/key aliases involving manager locks/markers/journals, engine locks, status/catalog files, recipient/identity roles and moved key resources. A disabled integration cannot use a reserved path to bypass planning safety.

`test_configure_tui.py` opens real Linux pseudo-terminals with dialog, checking non-echoed synthetic password entry, option-like input and Escape. `test_configure_install.py` runs fixture copies of actual install/update/uninstall scripts with fixed installation prefixes rewritten into a private temporary tree and a no-op systemctl. It checks preserved config/backups, automatic missing-dialog provisioning during update, and ordinary-removal versus explicit-purge behavior; it never operates on live units or the host's production directories. APT is intercepted, including unexpected calls. `test_dependencies.py` mocks every APT call and covers idempotent provisioning, safe options, opt-out, missing core dependencies, failures and non-TTY behavior. Parser differential tests compare only synthetic literals against real Bash, with secret-redaction assertions on errors. These tests explicitly skip unsupported Windows environments. CI provisions dialog before the Ubuntu matrix runs its PTY tests.

The disposable Ubuntu CI containers initially install analysis/platform tools without dialog/age. A separate integration step copies only `install.sh` into a temporary directory and runs `--dependencies-only`, using real APT to provision the missing application packages. Both executables must then be available before the complete test suite runs. This tests standalone provisioning on every supported Ubuntu version; it does not deploy application configuration, enable units or operate on a production host.

The generated inventory can be checked with `python3 lib/ub/configure.py --reference`; its output must match `docs/CONFIGURATION-REFERENCE.md`. CI also installs the actual CLI/modules, runs installed help/version commands and compares the installed reference output. For production rollout follow the operator checklist in [CONFIGURE.md](CONFIGURE.md) and the release-specific evidence in [CONFIGURATION-VALIDATION.md](CONFIGURATION-VALIDATION.md); an earlier green CI run does not validate newer changes.

The Ubuntu 22.04/24.04/26.04 CI matrix runs the existing Bash suite, new Bash end-to-end operations, standard-library Python tests, real `age` encryption/decryption, ShellCheck, and systemd unit validation. A public-source guard rejects tracked backup/email/credential artifacts and obvious live token/private-key patterns. It supplements manual privacy review.

Synthetic tests cover metadata/hash/size failures; missing metadata; error-page rejection; wrong age identities; independent/partial destinations; conditional upload idempotence; queue persistence/exhaustion/expiry and pins; quorum after partial retry; remote byte mismatches; S3/Azure listing and protected transport; timeout/authentication errors; required immutability without capability; local/cloud/filesystem recovery; dry-run; insufficient disk space; interrupted recovery cleanup; robust anomaly baselines, outliers, size/timing changes and identical hashes; redacted deterministic diffs and unsupported native formats.

Queue-capacity regression tests also verify that repeated rejected tasks cannot grow dead-letter history beyond its configured bound, active retention pins remain intact, and monitoring reflects the bounded queue.

Kernel flock contention and symlinks run on Linux. The Windows development host cannot create test symlinks under its current permissions and has no native Linux flock; those checks are explicitly deferred to CI, not claimed locally. Real age tests generate ephemeral identities and delete them after execution. No production backup, cloud credential, lock/hold mutation, message or controller restore occurs during tests.

Live UniFi restore compatibility, provider IAM/SAS permissions, S3-compatible vendor quirks, real network failure modes, provider WORM/account/versioning/lifecycle setup, and actual Auvik/RMM/Graph delivery require operator acceptance testing in their own environment. Mock protocol success is not a live cloud validation. The opaque native `.unifi` format does not acquire semantic parser support through these tests.
