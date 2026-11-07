"""Mockable dialog presentation only. Business rules live in model/schema."""
import gettext
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unicodedata

from core import Failure
from config_schema import SCOPES
from config_model import Model, active_field, calendar, public_recipients
from config_files import fingerprint, read_bytes

_ = gettext.NullTranslations().gettext  # English catalog boundary for future localization.


def screen_text(value):
    return ''.join(c if c in '\n\t' or not unicodedata.category(c).startswith('C') else '?' for c in str(value))


class Dialog:
    def __init__(self):
        if not sys.stdin.isatty() or not sys.stdout.isatty() or os.environ.get('TERM', '') in ('', 'dumb'):
            raise Failure('Interactive setup needs a TTY and TERM (SSH: ssh -t). Use --validate or --inspect for automation.', 69)
        self.program = shutil.which('dialog')
        if not self.program:
            raise Failure('UI dependency dialog is unavailable; rerun the current install.sh or update.sh with automatic dependency provisioning enabled (the default)', 69)

    def widget(self, title, widget, values, extra=False, ok='Next', cancel='Cancel', default_no=False):
        columns, lines = shutil.get_terminal_size()
        if columns < 60 or lines < 18:
            raise Failure('Terminal is too small; resize to at least 60 columns by 18 lines and retry. No configuration was applied.', 69)
        height, width = max(12, lines - 4), max(56, columns - 4)
        tokens = ['--clear', '--erase-on-exit', '--no-collapse', '--backtitle', _('UniFi OS Backup | Configuration'),
                  '--title', screen_text(title), '--ok-label', _(ok), '--cancel-label', _(cancel)]
        if extra:
            tokens += ['--extra-button', '--extra-label', _('Back')]
        if default_no:
            tokens += ['--defaultno']
        tokens += [widget, screen_text(values[0]), str(height), str(width)]
        if widget in ('--menu', '--radiolist', '--checklist'):
            tokens += [str(max(3, height - 10))]
        # Each user-controlled option-like value is explicitly escaped from
        # dialog's option parser, as documented by upstream (not shell quoting).
        for value in values[1:]:
            text = screen_text(value)
            if text.startswith('--'):
                tokens.append('--')
            tokens.append(text)
        def encoded(token):
            return '"' + token.replace('\\', '\\\\').replace('"', '\\"') + '"'
        data = ('\n'.join(encoded(t) for t in tokens) + '\n').encode('utf-8')
        # Anonymous private parameter file; no draft values appear in argv,
        # environment, diagnostic files or a named persistent payload.
        with tempfile.TemporaryFile() as parameters, open('/dev/tty', 'r+b', buffering=0) as tty:
            parameters.write(data); parameters.seek(0)
            environment = {k: v for k, v in os.environ.items() if not k.startswith('DIALOG')}
            environment['DIALOGRC'] = '/dev/null'
            result = subprocess.run([self.program, '--output-fd', '1', '--file', '&' + str(parameters.fileno())],
                                    stdin=tty, stdout=subprocess.PIPE, stderr=tty, pass_fds=(parameters.fileno(),), env=environment, check=False)
        if result.returncode not in (0, 1, 3, 255):
            raise Failure('Terminal UI failed; unapplied edits were discarded', 69)
        return result.returncode, result.stdout.decode('utf-8').rstrip('\n')

    def menu(self, title, prompt, items, extra=False):
        values = [prompt]
        for key, description in items:
            values += [key, description]
        return self.widget(title, '--menu', values, extra, ok='Select', cancel='Cancel')

    def input(self, title, prompt, value='', secret=False):
        return self.widget(title, '--passwordbox' if secret else '--inputbox', [prompt, '' if secret else value], extra=True)

    def choose(self, title, prompt, choices, value):
        values = [prompt]
        for choice in choices:
            values += [choice or '(empty)', choice or _('No provider encryption request'), 'on' if choice == value else 'off']
        code, selected = self.widget(title, '--radiolist', values, extra=True)
        return code, '' if selected == '(empty)' else selected

    def boolean(self, title, prompt, value):
        code, selected = self.widget(title, '--checklist', [prompt, 'enabled', _('Enabled'), 'on' if value == 'true' else 'off'], extra=True)
        return code, 'true' if selected.strip('"') == 'enabled' else 'false'

    def confirm(self, title, prompt):
        code, _value = self.widget(title, '--yesno', [prompt], ok='Yes', cancel='No', default_no=True)
        return code == 0

    def message(self, title, message):
        # msgbox scrolls on supported dialog builds; for long reports a menu
        # offers a scrollable list without storing report files.
        lines = screen_text(message).splitlines() or ['']
        if len(lines) > max(5, shutil.get_terminal_size().lines - 10):
            self.menu(title, _('Scroll with arrow/PageUp/PageDown keys; Select or Cancel returns.'), [(str(i + 1), line or ' ') for i, line in enumerate(lines)])
        else:
            self.widget(title, '--msgbox', [message], ok='Back')


def issue_text(issues):
    return '\n'.join(('WARNING' if issue.warning else 'ERROR') + ' [' + issue.category + '] ' + issue.location + ': ' + issue.message for issue in issues) or _('Configuration is valid.')


class Wizard:
    def __init__(self, model, ui, helper_dir='/usr/local/sbin'):
        self.model, self.ui, self.helper_dir = model, ui, Path(helper_dir)

    def edit_value(self, name, spec):
        value = self.model.values[name][spec.name]
        prompt = _(spec.description) + '\n\n' + spec.name
        if spec.sensitive:
            code, action = self.ui.menu(spec.name, prompt + '\n' + _('Existing values are never displayed.'),
                                        [('keep', _('Keep existing value')), ('replace', _('Replace using masked input')), ('clear', _('Explicitly clear value'))], extra=True)
            if code != 0 or action == 'keep':
                return
            if action == 'clear':
                if self.ui.confirm(_('Clear sensitive value'), _('Clear this value in the in-memory draft?')):
                    self.model.set(name, spec.name, '')
                return
            code, new = self.ui.input(spec.name, prompt + '\n' + _('Blank keeps the existing value.'), secret=True)
            if code == 0 and new:
                self.model.set(name, spec.name, new)
        elif spec.kind == 'bool':
            code, new = self.ui.boolean(spec.name, prompt, value)
            if code == 0:
                self.model.set(name, spec.name, new)
        elif spec.choices or spec.name == 'TARGET_LOCK_MODE':
            choices = spec.choices or (('GOVERNANCE', 'COMPLIANCE') if self.model.values[name]['TARGET_TYPE'] == 's3' else ('locked', 'unlocked'))
            code, new = self.ui.choose(spec.name, prompt, choices, value)
            if code == 0:
                self.model.set(name, spec.name, new)
        else:
            # Multiline literals can be kept or replaced without accidentally
            # flattening a value through a one-line input widget.
            initial = value if '\n' not in value and '\r' not in value else ''
            code, new = self.ui.input(spec.name, prompt + (_('\nMultiline existing value: blank keeps it.') if initial != value else ''), initial)
            if code == 0 and (new or initial == value):
                self.model.set(name, spec.name, new)

    def section(self, name, groups=None, guided=False):
        while True:
            values = self.model.values[name]
            visible = dict(values)
            if name == 'storage':
                visible['TARGET_TYPE'] = self.model.main['REMOTE_STORAGE_TYPE']
            specs = [s for s in SCOPES[self.model.scopes[name]] if (not groups or s.group in groups) and active_field(s, visible, self.model.main)]
            items = [(s.name, ('[set; hidden]' if values[s.name] else '[empty]') if s.sensitive else values[s.name] or '(empty)') for s in specs]
            items += [('next', _('Next section') if guided else _('Return to main menu'))]
            code, key = self.ui.menu(_('Settings: ') + name, _('Select a setting to edit. Changes stay in memory until Review and Finish.'), items, extra=True)
            if code == 3:
                return 'back'
            if code in (1, 255):
                return 'cancel'
            if key == 'next':
                return 'next'
            spec = next((s for s in specs if s.name == key), None)
            if spec:
                try:
                    self.edit_value(name, spec)
                except Failure as exc:
                    self.ui.message(_('Setting was not changed'), str(exc))

    def schedule(self):
        current = self.model.current_schedule()
        prompt = _('Keep existing drop-ins, or explicitly replace the calendar in the manager-owned timer drop-in. No timer is started.')
        prompt += '\n' + (_('Current calendar: ') + current if current else _('Effective schedule not decoded; Keep preserves all existing rules. Packaged default: Sunday 03:00.'))
        code, choice = self.ui.menu(_('Backup schedule'), prompt,
                                    [('keep', _('Keep current schedule')), ('daily', _('Daily at 03:00')), ('weekly', _('Sunday at 03:00')), ('custom', _('Custom systemd calendar'))], extra=True)
        if code != 0:
            return 'back' if code == 3 else 'cancel'
        if choice == 'keep':
            return 'next'
        expression = {'daily': '*-*-* 03:00:00', 'weekly': 'Sun *-*-* 03:00:00'}.get(choice)
        if choice == 'custom':
            code, expression = self.ui.input(_('Custom schedule'), _('Enter a systemd OnCalendar expression. It will be validated with systemd-analyze.'), current or 'Sun *-*-* 03:00:00')
            if code != 0:
                return 'back'
        calendar(expression)
        self.model.schedule = expression
        return 'next'

    def recipients(self):
        path = Path(self.model.main['AGE_RECIPIENTS_FILE'])
        self.model.extra_snapshot.setdefault(path, fingerprint(path))
        data = self.model.recipients if self.model.recipients is not None else read_bytes(path)
        if data and any(line.strip() and not line.lstrip().startswith(b'#') for line in data.splitlines()):
            public_recipients(data, check_age=False)  # Refuse private keys before displaying anything.
        lines = [line for line in (data or b'').decode().splitlines() if line.strip() and not line.lstrip().startswith('#')]
        while True:
            code, choice = self.ui.menu(_('Public age recipients'), _('Only public recipients are accepted. Private identities are never generated, edited or displayed. Losing all recovery keys loses the backups.'),
                                        [('add', _('Add public recipient')), ('remove', _('Remove a public recipient')), ('done', _('Next'))], extra=True)
            if code != 0:
                return
            if choice == 'done':
                proposed = ('\n'.join(lines) + '\n').encode()
                public_recipients(proposed, check_age=False)
                self.model.recipients = proposed
                return
            if choice == 'add':
                code, value = self.ui.input(_('Add public recipient'), _('Paste one public age1... or SSH public recipient. Never paste a private identity.'))
                if code == 0 and value:
                    proposed = ('\n'.join(lines + [value]) + '\n').encode()
                    public_recipients(proposed, check_age=False)
                    lines.append(value)
            elif choice == 'remove' and lines:
                code, value = self.ui.menu(_('Remove recipient'), _('Select the recipient number (values are not displayed).'), [(str(i), _('Public recipient ') + str(i + 1)) for i in range(len(lines))])
                if code == 0:
                    lines.pop(int(value))

    def targets(self):
        while True:
            active = self.model.target_ids()
            names = [name[7:] for name in self.model.values if name.startswith('target:')]
            code, choice = self.ui.menu(_('Backup destinations'), _('Local backups always remain enabled. New targets stay disabled until explicitly enabled. Removing from active use retains credentials and all backups.'),
                                        [('add', _('Add independent target')), ('legacy', _('Legacy single-target settings')), ('policy', _('Active IDs and remote success policy'))] +
                                        [('target:' + name, name + (' [active] ' if name in active else ' [disabled] ') + self.model.values['target:' + name]['TARGET_TYPE']) for name in names] + [('next', _('Next / return'))], extra=True)
            if code != 0:
                return 'back' if code == 3 else 'cancel'
            if choice == 'next':
                return 'next'
            try:
                if choice == 'add':
                    code, identifier = self.ui.input(_('Target ID'), _('Use a unique ID: letters, digits, underscore or hyphen; maximum 64 characters.'))
                    if code != 0:
                        continue
                    code, kind = self.ui.choose(_('Target backend'), _('No remote writes or permissions changes occur during configuration.'), ('azure_blob', 's3', 'filesystem'), 'azure_blob')
                    if code == 0:
                        self.model.add_target(identifier, kind)
                        self.section('target:' + identifier)
                elif choice == 'legacy':
                    self.section('main', {'destinations'})
                    if self.model.main['REMOTE_STORAGE_TYPE'] != 'none':
                        self.section('storage')
                elif choice == 'policy':
                    self.section('main', {'destinations'})
                elif choice.startswith('target:') and choice[7:] in names:
                    choice = choice[7:]
                    code, action = self.ui.menu(_('Target: ') + choice, _('Disable/remove only changes the active ID list. Pending retries need operator review. Cloud objects and credentials are never deleted.'),
                                                [('edit', _('Edit settings')), ('enable', _('Enable target')), ('disable', _('Disable target')), ('remove', _('Remove from active configuration')),
                                                 ('validate', _('Validate locally')), ('test', _('Explicit read-only destination test')), ('capability', _('Explicit read-only immutability inspection'))], extra=True)
                    if code != 0:
                        continue
                    if action == 'edit':
                        self.section('target:' + choice)
                    elif action in ('enable', 'disable', 'remove'):
                        if self.ui.confirm(_('Change active destinations'), _('Apply this change to the draft active target list? Review quorum and pending retries before Finish.')):
                            self.model.activate(choice, action == 'enable')
                    elif action == 'validate':
                        self.ui.message(_('Target validation'), issue_text(self.model.validate_target(choice)))
                    elif action in ('test', 'capability') and self.ui.confirm(_('Live read-only test'), _('Contact this configured provider now? Requires read/list permissions. No upload, deletion, hold or policy mutation will be performed.')):
                        from storage import Store
                        from policy import capability
                        store = Store(choice, self.model.values['target:' + choice])
                        result = capability(store)['supported'] if action == 'capability' else len(store.listing())
                        self.ui.message(_('Read-only test'), _('Capability supported: ') + str(result) if action == 'capability' else _('Managed object count: ') + str(result))
            except Failure as exc:
                self.ui.message(_('Destination action failed'), str(exc))

    def notifications(self):
        while True:
            enabled = [('graph', 'ENABLE_EMAIL'), ('ntfy', 'ENABLE_NTFY'), ('webhook', 'ENABLE_WEBHOOK')]
            items = [('flags', _('Enable integrations and select notification events'))]
            items += [(name, _('Configure ') + name) for name, flag in enabled if self.model.main[flag] == 'true']
            items += [('test', _('Test committed ntfy/webhook settings (explicit send)')), ('next', _('Next / return'))]
            code, choice = self.ui.menu(_('Notifications'), _('Only enabled integrations are shown. Graph email requires application permission and admin consent; this wizard never sends backup attachments.'), items, extra=True)
            if code != 0:
                return 'back' if code == 3 else 'cancel'
            if choice == 'next':
                return 'next'
            if choice == 'flags':
                self.section('main', {'notifications'})
            elif choice in ('graph', 'ntfy', 'webhook'):
                self.section(choice)
            elif choice == 'test':
                self.run_helper('unifi-backup-notify', ['--config', str(self.model.config), '--event', 'success', '--message', 'Explicit configuration test notification'], live=True)

    def run_helper(self, name, args, live=False):
        if live and self.model.plan():
            self.ui.message(_('Apply first'), _('This test uses committed configuration. Review and Finish your changes first.'))
            return
        if live and not self.ui.confirm(_('Explicit network operation'), _('Perform this operation using committed settings now? No real backup will be created.')):
            return
        executable = self.helper_dir / name
        if not executable.is_file():
            self.ui.message(_('Helper unavailable'), _('Install/update the application before running this action.'))
            return
        result = subprocess.run([str(executable), *args], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=300 if live else 30, check=False)
        if name == 'unifi-backup-status':
            lines = [_('Monitoring: ') + {0: 'OK', 1: 'WARNING', 2: 'CRITICAL', 3: 'UNKNOWN'}.get(result.returncode, 'UNKNOWN')]
            data = read_bytes(self.model.main['STATUS_FILE'], private=False)
            if data:
                try:
                    document = json.loads(data)
                    for section, fields in [('last_run', ('completed_timestamp', 'duration_seconds', 'exit_code')),
                                             ('last_success', ('completed_timestamp', 'size_bytes'))]:
                        for key in fields:
                            value = (document.get(section) or {}).get(key)
                            if type(value) is int:
                                lines.append(section + '.' + key + ': ' + str(value))
                except (ValueError, TypeError, AttributeError):
                    lines.append(_('Monitoring state cannot be decoded safely.'))
            self.ui.message(_('Backup status'), '\n'.join(lines))
        else:
            self.ui.message(_('Operation result'), _('Exit code: ') + str(result.returncode) + _('\nDetails are deliberately not copied into configuration diagnostics. For the backup checker, zero means success.'))

    def diagnostics(self):
        code, choice = self.ui.menu(_('Status and diagnostics'), _('No live test runs without an additional confirmation.'),
                                    [('status', _('Read backup monitoring status')), ('local', _('Validate in-memory configuration')), ('login', _('Explicit UniFi login test')), ('timers', _('Manage timer activation (committed settings)'))], extra=True)
        if code != 0:
            return
        if choice == 'local':
            self.ui.message(_('Validation'), issue_text(self.model.validate()))
        elif choice == 'status':
            self.run_helper('unifi-backup-status', ['--status-file', self.model.main['STATUS_FILE'], '--format', 'text', '--warning-age-hours', self.model.main['STALE_WARNING_HOURS'], '--critical-age-hours', self.model.main['STALE_CRITICAL_HOURS']])
        elif choice == 'login':
            self.run_helper('unifi-backup-check', ['--config', str(self.model.config), '--live'], live=True)
        elif choice == 'timers':
            if self.model.plan():
                self.ui.message(_('Apply first'), _('Apply and validate the draft before changing timer state.')); return
            code, timer = self.ui.menu(_('Select timer'), _('Timer activation is a separate explicit operational action, not part of the file transaction.'),
                                       [('backup', _('Backup schedule')), ('monitor', _('Freshness monitor')), ('verify', _('Integrity verification')), ('remote-verify', _('Remote verification')), ('retry', _('Replication retry worker'))])
            if code != 0:
                return
            code, action = self.ui.choose(_('Timer action'), _('Starting a Persistent timer may immediately run an overdue job, including a real backup or remote operation. Check configuration flags first.'), ('keep', 'enable-and-start', 'disable-and-stop', 'restart-if-active'), 'keep')
            flag = {'verify': 'VERIFY_ENABLED', 'remote-verify': 'REMOTE_VERIFY_ENABLED', 'retry': 'RETRY_ENABLED'}.get(timer)
            if action in ('enable-and-start', 'restart-if-active') and (any(not i.warning for i in self.model.validate()) or flag and self.model.main[flag] != 'true'):
                self.ui.message(_('Timer not started'), _('Validate configuration and explicitly enable the corresponding feature flag before starting its timer.'))
                return
            if code == 0 and action != 'keep' and self.ui.confirm(_('Confirm timer operation'), _('Execute the selected systemd timer operation now? It may run a scheduled operation immediately.')):
                unit = 'unifi-backup' + ('' if timer == 'backup' else '-' + timer) + '.timer'
                command = {'enable-and-start': ['enable', '--now'], 'disable-and-stop': ['disable', '--now'], 'restart-if-active': ['try-restart']}[action]
                result = subprocess.run(['systemctl', *command, unit], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
                self.ui.message(_('Timer result'), _('systemctl exit code: ') + str(result.returncode))

    def review(self):
        issues = self.model.validate()
        try:
            plan = self.model.plan()
        except Failure as exc:
            self.ui.message(_('Cannot plan unsafe changes'), issue_text(issues) + '\n' + str(exc))
            return False
        rows = self.model.summary()
        text = [_('Review: no changes have been written.')]
        for row in rows:
            if row['changed']:
                text.append(row['section'] + '/' + row['group'] + ' ' + row['setting'] + ': ' + row['old'] + ' -> ' + row['new'])
        for item in plan:
            text.append(('NEW ' if item['before'] is None else 'UPDATE ') + str(item['path']))
        if not Path(self.model.main['BACKUP_DIR']).exists():
            text.append(_('Create private backup directory: ') + self.model.main['BACKUP_DIR'])
        text += [_('New secret-file parents are private 0700 directories. Rollback journals retain old secrets with 0600 permissions.'),
                 _('systemd: daemon-reload if drop-ins change. Timers are not automatically enabled, started or restarted.'), issue_text(issues)]
        self.ui.message(_('Review proposed changes'), '\n'.join(text))
        if any(not x.warning for x in issues):
            self.ui.message(_('Cannot apply'), _('Resolve validation errors first. Existing configuration is unchanged.'))
            return False
        if not plan:
            self.ui.message(_('No changes'), _('Configuration already matches the draft.'))
            return False
        if self.ui.confirm(_('Finish and apply'), _('Write the reviewed configuration and listed drop-ins now? A private rollback journal will retain previous secrets. No backup or live test will start.')):
            identifier = self.model.apply()
            self.ui.message(_('Configuration applied'), _('Rollback transaction ID: ') + str(identifier) + _('\nRetain this ID privately. Consider explicitly restarting an already-active backup timer after a schedule change.'))
            config, units = self.model.config, self.model.units
            self.model = Model(config, units)
            if self.ui.confirm(_('Local configuration check'), _('Run the existing offline configuration checker now? No network test or real backup.')):
                self.run_helper('unifi-backup-check', ['--config', str(config)])
            return True
        return False

    def guided(self):
        steps = [lambda: self.section('main', {'connection'}, True), lambda: self.section('main', {'backup'}, True),
                 self.schedule, lambda: self.section('main', {'retention'}, True), lambda: self.section('main', {'encryption'}, True),
                 self.targets, self.notifications]
        index = 0
        while 0 <= index < len(steps):
            try:
                action = steps[index]()
            except Failure as exc:
                self.ui.message(_('Section needs attention'), str(exc))
                continue
            if action == 'cancel':
                return
            following = index + (-1 if action == 'back' else 1)
            if following == 5 and self.model.main['ENCRYPTION_TYPE'] == 'age':
                try:
                    self.recipients()
                except Failure as exc:
                    self.ui.message(_('Public recipients need attention'), str(exc))
                    continue
            index = following
        if index == len(steps):
            self.review()

    def edit_existing(self):
        groups = [('connection', _('UniFi connection')), ('backup', _('Local backup / timeouts')), ('retention', _('Retention / GFS')),
                  ('encryption', _('Encryption')), ('destinations', _('Destinations / replication policy')), ('notifications', _('Notifications')),
                  ('monitoring', _('Monitoring / logging')), ('verification', _('Integrity / remote verification')), ('retry', _('Persistent retries')),
                  ('analysis', _('Anomalies / config diff')), ('recovery', _('Recovery preparation')), ('advanced', _('Advanced paths / locking'))]
        while True:
            code, choice = self.ui.menu(_('Edit existing configuration'), _('Choose a category. Current values are loaded; defaults are not reset.'), groups, extra=True)
            if code != 0:
                return
            if choice == 'destinations':
                self.section('main', {'destinations'})
            elif choice == 'notifications':
                self.notifications()
            else:
                self.section('main', {choice})

    def run(self, guided=False):
        if guided:
            self.guided()
        while True:
            code, choice = self.ui.menu(_('Main menu'), _('Keyboard: arrows, Tab/Shift-Tab, Space for checkboxes, Enter. Cancel/Exit never applies an unconfirmed draft.'),
                                        [('guided', _('1. Initial setup / guided configuration')), ('edit', _('2. Edit existing configuration')), ('targets', _('3. Manage backup destinations')),
                                         ('notifications', _('4. Configure notifications')), ('retention', _('5. Schedule and retention')), ('validate', _('6. Validate configuration')),
                                         ('status', _('7. Backup status and diagnostics')), ('exit', _('8. Exit')), ('advanced', _('Monitoring and advanced settings')),
                                         ('recipients', _('Manage public age recipients')), ('finish', _('Review and Finish'))])
            if code in (1, 255) or choice == 'exit':
                dirty = any(self.model.dirty.values()) or self.model.schedule is not None or self.model.recipients is not None
                if not dirty or self.ui.confirm(_('Discard draft and exit'), _('Discard all unapplied changes and exit? Existing configuration remains unchanged.')):
                    return
                continue
            try:
                if choice == 'guided':
                    self.guided()
                elif choice == 'edit':
                    self.edit_existing()
                elif choice == 'targets':
                    self.targets()
                elif choice == 'notifications':
                    self.notifications()
                elif choice == 'retention':
                    self.schedule(); self.section('main', {'retention'})
                elif choice == 'validate':
                    self.ui.message(_('Validation'), issue_text(self.model.validate()))
                elif choice == 'status':
                    self.diagnostics()
                elif choice == 'advanced':
                    self.section('main', {'monitoring', 'verification', 'retry', 'analysis', 'recovery', 'advanced'})
                elif choice == 'recipients':
                    self.recipients()
                elif choice == 'finish':
                    self.review()
            except Failure as exc:
                self.ui.message(_('Operation refused safely'), str(exc))
