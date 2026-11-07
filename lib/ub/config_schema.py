"""Declarative, dependency-free configuration metadata. Never contains secrets."""
from dataclasses import dataclass

from core import Failure, boolean, integer


@dataclass(frozen=True)
class Setting:
    name: str
    default: str = ''
    kind: str = 'text'
    description: str = ''
    group: str = 'advanced'
    choices: tuple = ()
    low: int = 0
    high: int = 1000000
    sensitive: bool = False
    depends: str = 'always'
    status: str = 'active'

    def validate(self, values):
        if self.name not in values:
            return
        value = values[self.name]
        if self.kind == 'bool':
            boolean(values, self.name, self.default == 'true')
        elif self.kind == 'int':
            if len(value) > 20:
                raise Failure(self.name + ': integer exceeds the supported range', 78)
            integer(values, self.name, self.default, self.low, self.high)
        elif self.choices and value not in self.choices:
            raise Failure(self.name + ': choose ' + ', '.join(self.choices), 78)
        if '\0' in value:
            raise Failure(self.name + ': NUL bytes are not supported', 78)


def field(name, default='', kind='text', description='', group='advanced', **kw):
    return Setting(name, str(default), kind, description or name.replace('_', ' ').capitalize(), group, **kw)


MAIN = [
    field('UNIFI_URL', kind='origin', group='connection', description='UniFi OS HTTPS origin, optionally with port; no credentials or path.'),
    field('UNIFI_USERNAME', 'uni-bck', group='connection', sensitive=True, description='Dedicated local service account; do not use a daily administrator account.'),
    field('UNIFI_PASSWORD', group='connection', sensitive=True, description='Service-account password. Blank input keeps an existing password.'),
    field('UNIFI_CA_CERT', kind='certificate', group='connection', description='Optional trusted PEM CA chain. TLS verification is never disabled.'),
    field('BACKUP_DIR', '/var/backups/unifi', 'directory', group='backup', description='Private local backup directory; systemd also needs explicit write access.'),
    field('RETENTION_MODE', 'legacy', group='retention', choices=('legacy', 'gfs'), description='Legacy age/count rules or union of GFS period tiers, minimum floor and retry pins.'),
    field('ENCRYPTION_TYPE', 'none', group='encryption', choices=('none', 'age'), description='Optional age recipient encryption. Losing recovery identities loses encrypted backups permanently.'),
    field('AGE_RECIPIENTS_FILE', '/etc/unifi-backup/age-recipients.txt', 'private_path', group='encryption', depends='ENCRYPTION_TYPE=age', description='Public recipients only; never place private recovery identities on the backup host.'),
    field('LOG_FORMAT', 'text', group='monitoring', choices=('text', 'json'), description='Human-readable journald messages or structured newline-delimited JSON.'),
    field('STATUS_FILE', '/var/lib/unifi-backup/status.json', 'path', group='monitoring', description='Monitoring state; must end in status.json under BACKUP_DIR or /var/lib/unifi-backup.'),
    field('CATALOG_FILE', '/var/lib/unifi-backup/catalog.json', 'path', group='monitoring', description='Central catalog; must end in catalog.json under BACKUP_DIR or /var/lib/unifi-backup.'),
    field('LOCK_FILE', '/run/unifi-backup/unifi-backup.lock', 'path', description='Shared operation lock, directly under /run/unifi-backup or BACKUP_DIR.'),
    field('BACKUP_TARGETS', group='destinations', description='Ordered active target IDs. Nonempty overrides legacy remote storage; local backup always remains enabled.'),
    field('BACKUP_TARGET_CONFIG_DIR', '/etc/unifi-backup/targets.d', 'private_directory', group='destinations', description='Private directory containing independent NAME.env target files.'),
    field('REMOTE_STORAGE_TYPE', 'none', group='destinations', choices=('none', 'azure_blob', 's3'), status='legacy', depends='BACKUP_TARGETS is empty', description='Compatible legacy single target. Never activated or migrated automatically.'),
    field('STORAGE_CONFIG_FILE', '/etc/unifi-backup/storage.env', 'private_path', group='destinations', status='legacy', depends='BACKUP_TARGETS is empty and REMOTE_STORAGE_TYPE!=none'),
    field('GRAPH_CONFIG_FILE', '/etc/unifi-backup/graph.env', 'private_path', group='notifications', depends='ENABLE_EMAIL=true'),
    field('NTFY_CONFIG_FILE', '/etc/unifi-backup/ntfy.env', 'private_path', group='notifications', depends='ENABLE_NTFY=true'),
    field('WEBHOOK_CONFIG_FILE', '/etc/unifi-backup/webhook.env', 'private_path', group='notifications', depends='ENABLE_WEBHOOK=true'),
    field('VERIFY_IDENTITY_FILE', kind='private_path', group='verification', sensitive=True, depends='VERIFY_DECRYPT_CHECK=true', description='Existing protected off-host recovery identity reference only. The wizard never creates or edits an identity.'),
    field('RESTORE_STAGING_DIR', '/var/lib/unifi-backup/restore', 'directory', group='recovery', description='Private preparation destination; no automated controller import.'),
]

for name, default, low, high, group, description in [
    ('RETENTION_DAYS', 35, 0, 1000000, 'retention', 'Maximum age in days; zero disables age deletion.'),
    ('RETENTION_COUNT', 0, 0, 1000000, 'retention', 'Maximum backup count; zero disables the count limit.'),
    ('RETENTION_MIN_COUNT', 1, 0, 1000000, 'retention', 'Newest backups always retained despite age/count; pending retries also pin their source.'),
    ('MIN_BACKUP_SIZE', 10000, 1, 1099511627776, 'backup', 'Minimum acceptable downloaded backup size in bytes.'),
    ('CURL_CONNECT_TIMEOUT', 15, 1, 86400, 'backup', 'Connection timeout in seconds.'),
    ('CURL_MAX_TIME', 1800, 1, 86400, 'backup', 'Total request timeout; at least the connection timeout.'),
    ('BACKUP_DOWNLOAD_RETRIES', 1, 0, 3, 'backup', 'Additional fresh-login attempts for transient error-like responses.'),
    ('BACKUP_RETRY_DELAY', 15, 1, 300, 'backup', 'Seconds between backup download retries.'),
    ('STALE_WARNING_HOURS', 192, 1, 1000000, 'monitoring', 'Warning age in hours; match the actual backup schedule.'),
    ('STALE_CRITICAL_HOURS', 216, 1, 1000000, 'monitoring', 'Critical age in hours; must exceed the warning threshold.'),
    ('BACKUP_REQUIRED_TARGETS', 0, 0, 32, 'destinations', 'Minimum successful remote targets; local storage never counts. Every required target must also succeed.'),
    ('RETRY_MAX_ATTEMPTS', 8, 1, 100, 'retry', 'Maximum total attempts including the initial upload.'),
    ('RETRY_BASE_INTERVAL', 300, 1, 604800, 'retry', 'Initial exponential backoff interval in seconds.'),
    ('RETRY_MAX_INTERVAL', 86400, 1, 604800, 'retry', 'Backoff cap in seconds, at least the base interval.'),
    ('RETRY_MAX_AGE_DAYS', 7, 1, 365, 'retry', 'After this age a task becomes dead and releases its retention pin.'),
    ('RETRY_QUEUE_LIMIT', 1000, 1, 100000, 'retry', 'Maximum pending tasks and separately bounded terminal history.'),
    ('RESTORE_MAX_BYTES', 10737418240, 1, 1099511627776, 'recovery', 'Maximum downloaded/decrypted bytes during recovery preparation.'),
    ('ANOMALY_BASELINE', 20, 2, 200, 'analysis', 'Rolling comparable sample window.'),
    ('ANOMALY_MIN_SAMPLES', 5, 2, 200, 'analysis', 'Minimum history before size/duration anomaly decisions.'),
    ('ANOMALY_SIZE_PERCENT', 50, 1, 10000, 'analysis', 'Minimum median-relative size deviation, also requiring the MAD threshold.'),
    ('ANOMALY_DURATION_PERCENT', 200, 1, 10000, 'analysis', 'Minimum median-relative timing increase.'),
    ('ANOMALY_IDENTICAL_COUNT', 0, 0, 200, 'analysis', 'Optional identical-plaintext streak warning; zero disables it.'),
    ('ANOMALY_FAILURE_STREAK', 3, 2, 100, 'analysis', 'Consecutive authentication/download/replication failure threshold.'),
    ('ANOMALY_HISTORY_LIMIT', 200, 30, 10000, 'analysis', 'Maximum persisted operational history entries.'),
]:
    MAIN.append(field(name, default, 'int', description, group, low=low, high=high))
for tier in ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'):
    MAIN.append(field('GFS_' + tier, 0, 'int', 'Distinct UTC ' + tier.lower() + ' periods to retain; tiers form a union.', 'retention', depends='RETENTION_MODE=gfs'))
for name, default, group, description in [
    ('ENABLE_EMAIL', False, 'notifications', 'Enable Graph attachment email; separate protected credentials and Mail.Send consent are required.'),
    ('ENABLE_NTFY', False, 'notifications', 'Enable ntfy notifications.'),
    ('ENABLE_WEBHOOK', False, 'notifications', 'Enable generic HTTPS JSON webhooks.'),
    ('NOTIFY_ON_SUCCESS', False, 'notifications', 'Notify on routine successful runs.'),
    ('NOTIFY_ON_FAILURE', True, 'notifications', 'Notify on failed runs.'),
    ('NOTIFY_ON_RECOVERY', True, 'notifications', 'Notify when a successful run follows failure.'),
    ('NOTIFY_ON_STALE', True, 'notifications', 'Notify on stale-backup transitions and recovery.'),
    ('REMOTE_UPLOAD_REQUIRED', True, 'destinations', 'Legacy upload must succeed when enabled; unused by multi-target policy.'),
    ('VERIFY_ENABLED', False, 'verification', 'Enable post-backup/scheduled integrity checks; scheduled use also needs the timer.'),
    ('VERIFY_DECRYPT_CHECK', False, 'verification', 'Use an existing protected identity for scheduled decryption checks; not required for byte verification.'),
    ('REMOTE_VERIFY_ENABLED', False, 'verification', 'Enable scheduled full remote verification; requires target read access and timer activation.'),
    ('RETRY_ENABLED', False, 'retry', 'Enable the scheduled persistent retry worker; also activate its timer.'),
    ('ANOMALY_ENABLED', False, 'analysis', 'Enable nonblocking post-backup anomaly analysis.'),
    ('DIFF_ENABLED', False, 'analysis', 'Enable nonblocking diffs of normalized exports, not opaque native UniFi containers.'),
]:
    MAIN.append(field(name, str(default).lower(), 'bool', description, group,
                      status='legacy' if name == 'REMOTE_UPLOAD_REQUIRED' else 'active'))

STORAGE = [
    field('STORAGE_CA_CERT', kind='certificate', group='provider', description='Optional trusted PEM CA chain for remote storage.'),
    field('STORAGE_CONNECT_TIMEOUT', 15, 'int', group='provider', low=1, high=86400),
    field('STORAGE_MAX_TIME', 1800, 'int', group='provider', low=1, high=86400),
    field('AZURE_BLOB_BASE_URL', kind='container_url', group='provider', sensitive=True, depends='TARGET_TYPE=azure_blob'),
    field('AZURE_BLOB_SAS_TOKEN', group='provider', sensitive=True, depends='TARGET_TYPE=azure_blob', description='Protected container SAS; the wizard never changes provider permissions.'),
    field('AZURE_BLOB_PREFIX', group='provider', depends='TARGET_TYPE=azure_blob'),
    field('S3_ENDPOINT', kind='origin', group='provider', sensitive=True, depends='TARGET_TYPE=s3'),
    field('S3_REGION', group='provider', depends='TARGET_TYPE=s3'),
    field('S3_BUCKET', group='provider', sensitive=True, depends='TARGET_TYPE=s3'),
    field('S3_PREFIX', group='provider', depends='TARGET_TYPE=s3'),
    field('S3_ACCESS_KEY_ID', group='provider', sensitive=True, depends='TARGET_TYPE=s3'),
    field('S3_SECRET_ACCESS_KEY', group='provider', sensitive=True, depends='TARGET_TYPE=s3'),
    field('S3_SESSION_TOKEN', group='provider', sensitive=True, depends='TARGET_TYPE=s3'),
    field('S3_PATH_STYLE', 'true', 'bool', group='provider', depends='TARGET_TYPE=s3'),
    field('S3_SERVER_SIDE_ENCRYPTION', group='provider', choices=('', 'AES256', 'aws:kms'), depends='TARGET_TYPE=s3'),
    field('S3_SSE_KMS_KEY_ID', group='provider', sensitive=True, depends='S3_SERVER_SIDE_ENCRYPTION=aws:kms'),
]
TARGET = [
    field('TARGET_TYPE', group='target', choices=('filesystem', 's3', 'azure_blob')),
    field('TARGET_REQUIRED', 'false', 'bool', group='target', description='This independent target must succeed, in addition to the global remote quorum.'),
    field('TARGET_VERIFY', 'metadata', group='target', choices=('none', 'exists', 'metadata', 'full'), description='Full downloads and hashes bytes; existence/metadata checks are weaker.'),
    field('TARGET_IMMUTABILITY', 'none', group='target', choices=('none', 'check', 'request'), description='None, read-only existing-policy check, or explicit new-object retention request. Never changes bucket/container policy.'),
    field('TARGET_LOCK_MODE', group='target', description='Default GOVERNANCE for S3, locked for Azure. COMPLIANCE/locked requests may be irreversible.', depends='TARGET_IMMUTABILITY!=none'),
    field('TARGET_LOCK_DAYS', 30, 'int', group='target', low=1, high=36500, depends='TARGET_IMMUTABILITY!=none'),
    field('TARGET_ALLOW_PERMANENT_LOCK', 'false', 'bool', group='target', depends='TARGET_IMMUTABILITY=request', description='Explicit consent to potentially irreversible COMPLIANCE/locked new objects.'),
    field('FILESYSTEM_PATH', kind='directory', group='provider', depends='TARGET_TYPE=filesystem', description='Existing private mounted destination with .unifi-backup-target marker matching the ID.'),
    field('FILESYSTEM_REQUIRE_MOUNT', 'true', 'bool', group='provider', depends='TARGET_TYPE=filesystem'),
    field('RESTORE_MAX_BYTES', 10737418240, 'int', group='provider', low=1, high=1099511627776,
          description='Remote read/download safety limit; inherits main RESTORE_MAX_BYTES unless explicitly overridden in this target.'),
] + STORAGE
GRAPH = [
    field('TENANT_ID', group='graph', sensitive=True), field('CLIENT_ID', group='graph', sensitive=True),
    field('GRAPH_AUTH_METHOD', 'client_secret', group='graph', choices=('client_secret',)),
    field('CLIENT_SECRET', group='graph', sensitive=True),
    field('MAIL_FROM', group='graph', sensitive=True), field('MAIL_TO', group='graph', sensitive=True),
    field('GRAPH_SIMPLE_ATTACHMENT_MAX_BYTES', 2800000, 'int', group='graph', low=1, high=2999999,
          description='Small-attachment limit; keep below 3 MB and account for base64/metadata. Oversized backups stay local.'),
]
NTFY = [
    field('NTFY_BASE_URL', kind='origin', group='ntfy', sensitive=True),
    field('NTFY_TOPIC', group='ntfy', sensitive=True),
    field('NTFY_ACCESS_TOKEN', group='ntfy', sensitive=True),
    field('NTFY_ALLOW_ANONYMOUS', 'false', 'bool', group='ntfy'),
    field('NTFY_CA_CERT', kind='certificate', group='ntfy'),
]
WEBHOOK = [
    field('WEBHOOK_URL', kind='webhook_url', group='webhook', sensitive=True),
    field('WEBHOOK_BEARER_TOKEN', group='webhook', sensitive=True),
    field('WEBHOOK_HMAC_SECRET', group='webhook', sensitive=True),
    field('WEBHOOK_CA_CERT', kind='certificate', group='webhook'),
    field('WEBHOOK_CONNECT_TIMEOUT', 15, 'int', group='webhook', low=1, high=86400),
    field('WEBHOOK_MAX_TIME', 60, 'int', group='webhook', low=1, high=86400),
]
SCOPES = {'main': MAIN, 'storage': STORAGE, 'target': TARGET, 'graph': GRAPH, 'ntfy': NTFY, 'webhook': WEBHOOK}
FILES = {'main': 'unifi-backup.env', 'storage': 'storage.env', 'graph': 'graph.env', 'ntfy': 'ntfy.env', 'webhook': 'webhook.env', 'target': 'targets.d/ID.env'}


def defaults(scope):
    return {s.name: s.default for s in SCOPES[scope]}


def validate_operations(sections):
    """Shared advanced-engine validation; no filesystem/network side effects."""
    c = {**defaults('main'), **sections['main']}
    advanced = ('VERIFY_', 'RETRY_', 'REMOTE_VERIFY_', 'ANOMALY_', 'DIFF_', 'GFS_', 'RESTORE_', 'BACKUP_REQUIRED_TARGETS', 'RETENTION_MODE')
    for s in MAIN:
        if s.name.startswith(advanced):
            s.validate(c)
    if int(c['BACKUP_REQUIRED_TARGETS']) > len(sections) - 1:
        raise Failure('BACKUP_REQUIRED_TARGETS exceeds the active remote target count', 78)
    if int(c['RETRY_BASE_INTERVAL']) > int(c['RETRY_MAX_INTERVAL']):
        raise Failure('RETRY_BASE_INTERVAL exceeds RETRY_MAX_INTERVAL', 78)
    if int(c['ANOMALY_MIN_SAMPLES']) > int(c['ANOMALY_BASELINE']):
        raise Failure('ANOMALY_MIN_SAMPLES exceeds ANOMALY_BASELINE', 78)
    if c['RETENTION_MODE'] == 'gfs' and not any(int(c['GFS_' + t]) for t in ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY')):
        raise Failure('GFS requires at least one nonzero tier', 78)
    for identifier, values in sections.items():
        if identifier == 'main':
            continue
        v = {**defaults('target'), **values}
        for s in TARGET:
            # Provider checks remain in Store; this matches the existing
            # advanced loader's offline policy contract.
            if s.group == 'target' and s.name != 'TARGET_LOCK_MODE':
                s.validate(v)
        if not v['TARGET_TYPE']:
            raise Failure('TARGET_TYPE is required', 78)
        mode = values.get('TARGET_LOCK_MODE') or ('GOVERNANCE' if v['TARGET_TYPE'] == 's3' else 'locked')
        if v['TARGET_IMMUTABILITY'] == 'request' and mode in ('COMPLIANCE', 'locked') and v['TARGET_ALLOW_PERMANENT_LOCK'] != 'true':
            raise Failure('Permanent immutable protection requires explicit target consent', 78)


def reference():
    """Generated inventory: runtime defaults, not fictitious example credentials."""
    rows = ['# Configuration reference', '', 'Generated by `unifi-backup-configure --reference`. Do not edit this table manually.', '',
            'Defaults are runtime defaults, not example credentials. Missing required values are empty. All env files are root-owned 0600 under private 0700 directories. Unknown literal assignments are retained but not managed.', '',
            '| Setting | Source file | Default | Consumers | Validation | Sensitive | Dependency | Status | Description |',
            '|---|---|---|---|---|---|---|---|---|']
    for scope, specs in SCOPES.items():
        for s in specs:
            consumers = {'main': ['bin/unifi-backup', 'lib/unifi-backup-runtime.sh'],
                         'graph': ['bin/unifi-mail-backup'], 'ntfy': ['bin/unifi-backup-notify'],
                         'webhook': ['bin/unifi-backup-notify'], 'storage': ['bin/unifi-backup-upload', 'lib/ub/storage.py'],
                         'target': ['lib/unifi-backup-runtime.sh', 'lib/ub/storage.py', 'lib/ub/policy.py', 'lib/ub/replication.py']}[scope][:]
            if scope == 'main':
                consumers += {'retention': ['lib/ub/retention.py'], 'analysis': ['lib/ub/anomaly.py', 'lib/ub/config_diff.py'],
                              'retry': ['lib/ub/retry_queue.py'], 'verification': ['lib/ub/cli.py', 'lib/ub/verify.py'],
                              'recovery': ['lib/ub/recovery.py'], 'notifications': ['bin/unifi-backup-notify', 'bin/unifi-mail-backup'],
                              'monitoring': ['bin/unifi-backup-monitor', 'bin/unifi-backup-status', 'bin/unifi-backup-catalog'],
                              'destinations': ['lib/ub/replication.py', 'bin/unifi-backup-upload']}.get(s.group, [])
            rule = '/'.join(s.choices) if s.choices else f'{s.low}..{s.high}' if s.kind == 'int' else s.kind
            default = ('inherit main RESTORE_MAX_BYTES' if scope == 'target' and s.name == 'RESTORE_MAX_BYTES' else
                       s.default or ('provider-specific: GOVERNANCE / locked' if s.name == 'TARGET_LOCK_MODE' else '(empty)'))
            activation = {'graph': 'ENABLE_EMAIL=true', 'ntfy': 'ENABLE_NTFY=true', 'webhook': 'ENABLE_WEBHOOK=true',
                          'storage': 'BACKUP_TARGETS is empty and REMOTE_STORAGE_TYPE!=none', 'target': 'ID in BACKUP_TARGETS'}.get(scope, '')
            dependency = activation + ('; ' if activation and s.depends != 'always' else '') + (s.depends if s.depends != 'always' or not activation else '')
            vals = [s.name, FILES[scope], default, ', '.join(consumers), rule,
                    'yes' if s.sensitive else 'no', dependency, 'legacy file' if scope == 'storage' else s.status, s.description]
            rows.append('| ' + ' | '.join(v.replace('|', '\\|').replace('\n', ' ') for v in vals) + ' |')
    rows += ['', 'Public age recipients live in the referenced AGE_RECIPIENTS_FILE (not Bash assignments); the manager rejects private identities and validates public recipients with age before encryption is enabled.', '',
             'Scheduling is a systemd OnCalendar expression in a dedicated timer drop-in, not an engine environment setting. Cross-field, permission, dependency, target and systemd-access rules are evaluated by the shared manager validator; see CONFIGURE.md.', '']
    return '\n'.join(rows)
