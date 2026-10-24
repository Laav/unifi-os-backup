# Deterministic anomaly analysis

`unifi-backup-analyze --latest|--all [--baseline 20] [--json] [--explain]` compares like-for-like controller/plaintext measurements using a rolling median and median absolute deviation. It never calls an external AI service. Results distinguish `cold_start`, `normal` and `anomaly`; warnings never mark a valid backup corrupt.

Defaults require five historical samples out of a twenty-backup window. Size warnings require both a 50% deviation and a deviation beyond six MADs; zero variance still needs the percentage threshold. Available timing stages use a separate 200% increase threshold. Missing durations and encrypted sizes without plaintext metadata are excluded. `ANOMALY_IDENTICAL_COUNT=0` disables identical-hash warnings; an optional positive streak threshold enables them. Repeated authentication/download/replication failures and retry dead letters produce operational warnings.

Enable automatic analysis with `ANOMALY_ENABLED=true`; it is off by default and cannot block backup creation. `ANOMALY_BASELINE`, `ANOMALY_MIN_SAMPLES`, `ANOMALY_SIZE_PERCENT`, `ANOMALY_DURATION_PERCENT`, `ANOMALY_FAILURE_STREAK` and `ANOMALY_HISTORY_LIMIT` control bounded local history. Analysis state/metrics are separate from integrity and replication state. Exit 1 means an anomaly warning, not corrupt backup bytes.
