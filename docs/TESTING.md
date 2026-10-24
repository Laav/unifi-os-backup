# Validation and infrastructure boundaries

```bash
bash tests/run.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
shellcheck install.sh update.sh uninstall.sh bin/* lib/*.sh tests/*.sh tests/fixtures/mock-*
python3 -m compileall -q lib/ub
git diff --check
```

The Ubuntu 22.04/24.04/26.04 CI matrix runs the existing Bash suite, new Bash end-to-end operations, standard-library Python tests, real `age` encryption/decryption, ShellCheck, and systemd unit validation. A public-source guard rejects tracked backup/email/credential artifacts and obvious live token/private-key patterns. It supplements manual privacy review.

Synthetic tests cover metadata/hash/size failures; missing metadata; error-page rejection; wrong age identities; independent/partial destinations; conditional upload idempotence; queue persistence/exhaustion/expiry and pins; quorum after partial retry; remote byte mismatches; S3/Azure listing and protected transport; timeout/authentication errors; required immutability without capability; local/cloud/filesystem recovery; dry-run; insufficient disk space; interrupted recovery cleanup; robust anomaly baselines, outliers, size/timing changes and identical hashes; redacted deterministic diffs and unsupported native formats.

Queue-capacity regression tests also verify that repeated rejected tasks cannot grow dead-letter history beyond its configured bound, active retention pins remain intact, and monitoring reflects the bounded queue.

Kernel flock contention and symlinks run on Linux. The Windows development host cannot create test symlinks under its current permissions and has no native Linux flock; those checks are explicitly deferred to CI, not claimed locally. Real age tests generate ephemeral identities and delete them after execution. No production backup, cloud credential, lock/hold mutation, message or controller restore occurs during tests.

Live UniFi restore compatibility, provider IAM/SAS permissions, S3-compatible vendor quirks, real network failure modes, provider WORM/account/versioning/lifecycle setup, and actual Auvik/RMM/Graph delivery require operator acceptance testing in their own environment. Mock protocol success is not a live cloud validation. The opaque native `.unifi` format does not acquire semantic parser support through these tests.
