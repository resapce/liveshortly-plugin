#!/usr/bin/env bash
# Find a working Python 3 interpreter and run the given hook script.
# Deliberately NO `set -e` — we must never exit non-zero from a hook launcher
# because Claude Code treats hook failures as errors and may skip subsequent hooks.

probe() {
    "$1" -c 'import sys; print(sys.version_info[0])' 2>/dev/null
}

for cmd in python3 python; do
    v=$(probe "$cmd") || continue
    if [ "$v" = "3" ]; then
        exec "$cmd" "$@"
    fi
done

echo "[liveshortly] ERROR: no Python 3 found (tried python3, python)" >&2
exit 0   # exit 0 so Claude does not treat missing Python as a hook failure
