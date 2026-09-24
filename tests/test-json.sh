#!/usr/bin/env bash
set -Eeuo pipefail
username='uni-bck"admin'
password=$'line 1\nline "2" \\ slash $() `tick`'
actual=$(printf '%s\0%s' "$username" "$password" | python3 -c 'import json,sys; b=sys.stdin.buffer.read().split(b"\0",1); json.dump({"username":b[0].decode(),"password":b[1].decode()},sys.stdout,separators=(",",":"))')
python3 - "$actual" "$username" "$password" <<'PY'
import json,sys
obj=json.loads(sys.argv[1])
assert obj == {"username":sys.argv[2],"password":sys.argv[3]}
PY
echo "PASS: credential JSON escaping"
