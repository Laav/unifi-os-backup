"""Safe literal-only Bash configuration editing; never sources or evaluates it."""
import hashlib
import os
from pathlib import Path
import re
import stat

from core import Failure, safe_path

LIMIT = 1024 * 1024
KEY = re.compile(r'[A-Z][A-Z0-9_]*')


class Security(Failure):
    def __init__(self, message):
        super().__init__(message, 77)


def checked(path, private=False, directory=False):
    path = Path(path)
    if '..' in path.parts or '\0' in str(path):
        raise Security('Unsafe configuration path')
    try:
        safe_path(path)
    except Failure:
        raise Security('Configuration path must be absolute and contain no symbolic links') from None
    if path == path.parent:
        raise Security('A filesystem root is not a managed destination')
    if os.name != 'nt':
        for parent in path.parents:
            if parent.exists():
                info = parent.stat()
                # A root-owned sticky temporary ancestor is acceptable for
                # private test/config trees, not as the private parent itself.
                if info.st_uid not in (0, os.geteuid()) or (info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX)):
                    raise Security('Unsafe ancestor ownership or write permissions')
    if path.exists():
        info = path.lstat()
        if directory and not stat.S_ISDIR(info.st_mode):
            raise Security('Expected a configuration directory')
        if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
            raise Security('Expected a singly-linked regular configuration file')
        if os.name != 'nt' and (info.st_uid != os.geteuid() or (os.geteuid() == 0 and info.st_gid != 0)):
            raise Security('Configuration must be owned by the operator (root:root in production)')
        if private and os.name != 'nt' and stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600):
            raise Security('Configuration directories require 0700 and files require 0600')
        if not private and os.name != 'nt' and info.st_mode & 0o022:
            raise Security('Managed files/directories cannot be writable by group or others')
    if private and not directory and path.parent.exists():
        checked(path.parent, private=True, directory=True)
    return path


def read_bytes(path, private=True):
    path = checked(path, private=private)
    if not path.exists():
        return None
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > LIMIT:
            raise Failure('Configuration exceeds size limit or is not a regular file', 78)
        content = stream.read(LIMIT + 1)
    if len(content) > LIMIT:
        raise Failure('Configuration exceeds size limit', 78)
    return content


def fingerprint(path, private=True):
    data = read_bytes(path, private)
    if data is None:
        return None
    info = Path(path).stat()
    return [hashlib.sha256(data).hexdigest(), stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid]


def quote(value):
    if not isinstance(value, str) or '\0' in value or len(value.encode('utf-8')) > 65536:
        raise Failure('Unsupported literal configuration value', 78)
    return "'" + value.replace("'", "'\"'\"'") + "'"


def expands(text, position, double_quoted=False):
    """A dollar is literal unless it introduces actual Bash expansion syntax."""
    following = text[position + 1:position + 2]
    if not following:
        return False
    if text.startswith('\\\n', position + 1):
        # Bash removes continuations before expansion. Do not reinterpret a
        # reference split over physical lines as a harmless literal dollar.
        return True
    return bool(re.fullmatch(r'[A-Za-z0-9_@*#?$!{(\[\-]', following)) or (not double_quoted and following == '"')


def literal(text, start):
    """Parse one concatenated shell word. Expansions/operators are forbidden."""
    out, i = [], start
    while i < len(text) and text[i] not in ' \t\n':
        char = text[i]
        if char == "'":
            end = text.find("'", i + 1)
            if end < 0:
                raise Failure('Unterminated literal quote', 65)
            out.append(text[i + 1:end]); i = end + 1
        elif char == '"':
            i += 1
            while i < len(text) and text[i] != '"':
                char = text[i]
                if char == '`' or char == '$' and expands(text, i, double_quoted=True):
                    raise Failure('Shell expansion is unsupported; use literal assignments', 65)
                if char == '\\' and i + 1 < len(text) and text[i + 1] in '$`"\\\n':
                    i += 1
                    if text[i] != '\n':
                        out.append(text[i])
                else:
                    out.append(char)
                i += 1
            if i == len(text):
                raise Failure('Unterminated literal quote', 65)
            i += 1
        elif text.startswith("$'", i):
            i += 2
            data = bytearray()
            while i < len(text) and text[i] != "'":
                if text[i] != '\\':
                    data.extend(text[i].encode('utf-8')); i += 1; continue
                i += 1
                if i == len(text):
                    raise Failure('Incomplete ANSI literal escape', 65)
                escapes = {'n': '\n', 'r': '\r', 't': '\t', 'a': '\a', 'b': '\b', 'e': '\x1b', 'E': '\x1b', 'f': '\f', 'v': '\v', '\\': '\\', "'": "'", '"': '"'}
                if text[i] in escapes:
                    data.extend(escapes[text[i]].encode('utf-8')); i += 1
                else:
                    match = re.match(r'(?:x[0-9a-fA-F]{1,2}|[0-7]{1,3}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8})', text[i:])
                    if not match:
                        raise Failure('Unsupported ANSI literal escape', 65)
                    raw = match.group()
                    code = int(raw[1:], 16) if raw[0] in 'xuU' else int(raw, 8)
                    if code == 0 or code > 0x10ffff or 0xd800 <= code <= 0xdfff:
                        raise Failure('Invalid literal character', 65)
                    if raw[0] in 'uU':
                        data.extend(chr(code).encode('utf-8'))
                    elif code <= 255:
                        data.append(code)
                    else:
                        raise Failure('Unsupported ANSI byte escape', 65)
                    i += len(raw)
            if i == len(text):
                raise Failure('Unterminated ANSI literal', 65)
            try:
                out.append(data.decode('utf-8'))
            except UnicodeError:
                raise Failure('Non-UTF-8 ANSI byte literals cannot be safely managed', 65) from None
            i += 1
        elif char == '\\':
            if i + 1 == len(text):
                raise Failure('Incomplete literal escape', 65)
            i += 1
            if text[i] != '\n':
                out.append(text[i])
            i += 1
        elif char == '$' and expands(text, i) or char in '`;|&<>(){}~\r':
            raise Failure('Shell expressions/operators are unsupported; no rewrite performed', 65)
        else:
            out.append(char); i += 1
    value = ''.join(out)
    quote(value)  # Enforce bounded, NUL-free Unicode values.
    return value, i


class Document:
    def __init__(self, text='', source=None):
        self.source = Path(source).name if source else 'configuration'
        if not re.fullmatch(r'[A-Za-z0-9._-]{1,128}', self.source):
            self.source = 'configuration'
        self.text = text
        if '\0' in text:
            raise self.syntax('Configuration contains NUL bytes', 0)
        self.text, self.values, self.spans = text, {}, {}
        i = 0
        while i < len(text):
            while i < len(text) and text[i] in ' \t\n':
                i += 1
            if i == len(text):
                break
            if text[i] == '#':
                end = text.find('\n', i)
                i = len(text) if end < 0 else end + 1
                continue
            match = re.match(r'(?:export[ \t]+)?([A-Z][A-Z0-9_]*)=', text[i:])
            if not match:
                raise self.syntax('Unsupported shell syntax; only comments and literal assignments can be managed', i)
            key = match.group(1)
            start = i + len(match.group())
            try:
                value, end = literal(text, start)
            except Failure as exc:
                raise self.syntax(str(exc), i, key, exc.code) from None
            self.values[key], self.spans[key] = value, (start, end)
            i = end
            while i < len(text) and text[i] in ' \t':
                i += 1
            if i < len(text) and text[i] == '#':
                end = text.find('\n', i)
                i = len(text) if end < 0 else end
            if i < len(text) and text[i] != '\n':
                raise self.syntax('Multiple shell commands or assignments on one line are unsupported', i, key)

    def syntax(self, message, position, key=None, code=65):
        location = self.source + ': line ' + str(self.text.count('\n', 0, position) + 1)
        if key:
            location += ', setting ' + key
        return Failure(location + ': ' + message + '. Values are hidden; no configuration was executed or rewritten.', code)

    def render(self, values):
        replacements, added = [], []
        for key, value in values.items():
            if not KEY.fullmatch(key):
                raise Failure('Invalid assignment name', 65)
            if self.values.get(key) == value and key in self.values:
                continue
            rendered = quote(value)
            if key in self.spans:
                start, end = self.spans[key]
                replacements.append((start, end, rendered))
            else:
                added.append(key + '=' + rendered + '\n')
        text = self.text
        for start, end, value in sorted(replacements, reverse=True):
            text = text[:start] + value + text[end:]
        if added:
            text += ('\n' if text and not text.endswith('\n') else '') + ''.join(added)
        # Generated content must round-trip before it can leave memory.
        parsed = Document(text, source=self.source)
        if any(parsed.values.get(k) != v for k, v in values.items()):
            raise Failure('Configuration serialization invariant failed', 70)
        data = text.encode('utf-8')
        if len(data) > LIMIT:
            raise Failure('Generated configuration exceeds the supported file size limit', 78)
        return data


def load_document(path):
    data = read_bytes(path)
    try:
        return Document(data.decode('utf-8') if data is not None else '', source=path)
    except UnicodeError:
        raise Failure('Configuration must be valid UTF-8; no rewrite performed', 65) from None
