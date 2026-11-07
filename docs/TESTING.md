# Testing and validation boundaries

[Documentation index](README.md) · [Contributing](../CONTRIBUTING.md) · [Recorded evidence](CONFIGURATION-VALIDATION.md)

## Run the software checks

Use an isolated Ubuntu environment matching [the CI workflow](../.github/workflows/ci.yml). The complete matrix covers Ubuntu 22.04, 24.04 and 26.04. Some filesystem/lifecycle tests require root; real dialog tests require Linux pseudo-terminal support. Do not use a production backup host as a disposable CI environment.

```bash
bash tests/run.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
shellcheck install.sh update.sh uninstall.sh bin/* lib/*.sh tests/*.sh tests/fixtures/mock-*
python3 -m compileall -q lib/ub tests
git diff --check
```

CI additionally installs the actual CLI/modules in its container, validates units with `systemd-analyze verify`, runs installed help/version commands and compares the installed generated reference. To inspect the generated reference without a TTY or configuration:

```bash
python3 lib/ub/configure.py --reference | cmp - docs/CONFIGURATION-REFERENCE.md
```

Require relevant native tests to execute before a software release. Windows or non-root skips are explicit infrastructure limits; they are not passes. Historical counts and exact successful commits are kept in [CONFIGURATION-VALIDATION.md](CONFIGURATION-VALIDATION.md), rather than maintained as a changing test-count promise here.

## Configuration and lifecycle coverage

- Parser/serializer round trips cover quotes, literal dollars, Unicode, multiline/ANSI literals, actual expansion refusal, comment/unknown preservation and redacted diagnostics. A differential test sources only synthetic fixtures in real Bash; the configuration manager never sources files.
- Model tests cover missing/disabled integrations, legacy transitions, independent destinations/quorum, path roles, permissions, symlinks, aliases involving locks/state/keys, schedules and generated systemd drop-ins.
- Transaction tests cover Back/Cancel, missing TTY/UI dependency, concurrent writers, changed dependencies, interruption rollback, corrupt preimages, pending recovery and refusal to overwrite later edits.
- `test-config-lock.sh` checks actual Linux shared read-only locks, contention and pending-reader refusal.
- `test_configure_tui.py` uses real dialog pseudo-terminals for masked synthetic entry, option-like values and Escape.
- `test_configure_install.py` rewrites only fixed prefixes in fixture copies of the actual lifecycle scripts. It operates in a temporary tree with mocked systemctl/APT, checks preserved config/backups, missing-dialog provisioning, deployment refusal on APT failure, ordinary removal and explicit purge. It does not touch production paths or live units.

## Dependency provisioning coverage

`test_dependencies.py` intercepts every APT call. It covers missing dialog/Git/age, safe options, idempotence, opt-out versus missing core tools, failures and no-TTY/help behavior. Regular unit/lifecycle tests never install host packages.

Separately, disposable CI containers initially install analysis/platform tools without dialog/age. CI copies only `install.sh` into a temporary directory and runs `--dependencies-only` with real APT. Both tools must become available before the complete suite executes. This tests the actual standalone provisioner on each Ubuntu release without deploying application configuration or activating units.

## Backup, storage and recovery coverage

Synthetic fixtures and mock transports cover metadata/hash/size failures, error-page exclusion, wrong age identities, independent/partial destinations, conditional-write idempotence, persistent retries, quorum after retry, bounded dead-letter history, retention pins, remote byte mismatches and provider listing/transport failures.

Further cases cover required immutability without capability, local/cloud/filesystem recovery, dry-run, insufficient disk space, interrupted staging cleanup, anomaly baselines/outliers/timing/identical hashes, redacted deterministic diffs and unsupported native formats. Real age tests create temporary identities and remove them afterward.

A public-source guard rejects tracked operational artifacts and obvious live token/private-key patterns. It supplements a manual privacy review. Tests use synthetic data; no production controller restore, Graph delivery, cloud credential or real lock/hold mutation is part of the ordinary suite.

## Documentation-only checks

Check relative paths/anchors, fenced example syntax, command/options against installed help or source, generated-reference consistency, privacy and `git diff --check`. Never run backup, purge, rollback, upload, notification or package-management examples just to proofread them. Existing CI still runs on documentation commits; no version bump or new release is needed for editorial changes.

## Operator acceptance

Live UniFi compatibility/restoration, provider IAM/SAS/WORM/lifecycle configuration, vendor-specific S3 behavior, real network failures, native ARM64 execution and actual Auvik/RMM/Graph/notification delivery require environment-specific acceptance. A mock protocol success does not validate cloud permissions; a real age round trip does not validate a controller restore.

On an isolated machine, walk through fresh/existing configuration, masked edits, Back/Cancel, explicit Finish, custom paths/calendars, locking and recovery before rollout. Then explicitly test the intended controller, destinations and notifications, create/verify one backup and complete an isolated restore drill. Use [CONFIGURE.md](CONFIGURE.md) and [DISASTER-RECOVERY.md](DISASTER-RECOVERY.md) as the operator walkthroughs.
