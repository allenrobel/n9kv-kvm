#!/usr/bin/env bash
#
# Kill all running nexus9000v VMs.
#
# NOTE: these VMs are launched as raw qemu-system-x86_64 processes (see
# nexus9000v-ovs.py / nexus9000v-linux-bridge.py), NOT as libvirt domains,
# so "virsh destroy" does not apply -- they don't appear in "virsh list".
# We therefore match the QEMU processes the same way list_n9kv.sh does and
# kill them by PID.
#
# Usage:
#   ./kill_n9kv.sh          # graceful TERM
#   ./kill_n9kv.sh -9       # force KILL
#   ./kill_n9kv.sh -n       # dry-run: show what would be killed

SIGNAL=TERM
DRY_RUN=0

for arg in "$@"; do
    case "$arg" in
        -9|--kill)    SIGNAL=KILL ;;
        -n|--dry-run) DRY_RUN=1 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

# grep -v grep avoids matching this pipeline's own grep process.
# PID is field 2 of "ps -ef"; the switch name follows the "-name" QEMU flag.
# Emit "PID name" per line (name defaults to "?" if -name is absent).
MATCHES=$(ps -ef | grep manufacturer=Cisco,product=Nexus9000 | grep -v grep \
    | awk '{ name="?"; for (i=1;i<=NF;i++) if ($i=="-name") name=$(i+1); print $2, name }')

if [ -z "$MATCHES" ]; then
    echo "No nexus9000v processes found."
    exit 0
fi

while read -r pid name; do
    [ -z "$pid" ] && continue
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "Would kill $name (PID $pid, SIG$SIGNAL)"
    else
        echo "Killing $name (PID $pid, SIG$SIGNAL)"
        sudo kill -"$SIGNAL" "$pid"
    fi
done <<< "$MATCHES"
