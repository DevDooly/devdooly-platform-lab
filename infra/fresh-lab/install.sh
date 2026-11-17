#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C
exec python3 "$(dirname -- "$0")/install.py" "$@"
