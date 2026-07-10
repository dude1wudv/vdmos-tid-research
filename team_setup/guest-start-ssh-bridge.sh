#!/usr/bin/env bash
set -euo pipefail

mode="start"
if [[ "${1:-}" == "--check" ]]; then
  mode="check"
  shift
fi
iface="${1:-ens33}"

if command -v ip >/dev/null 2>&1; then
  ip_cmd="$(command -v ip)"
elif [[ -x /sbin/ip ]]; then
  ip_cmd="/sbin/ip"
else
  echo "ip command not found" >&2
  exit 1
fi

if [[ "$mode" == "start" ]]; then
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Run start mode with sudo: sudo bash $0 $iface" >&2
    exit 1
  fi
  systemctl enable --now NetworkManager
  if ! nmcli -t -f DEVICE,STATE dev status | grep -q "^${iface}:connected$"; then
    nmcli dev connect "$iface"
  fi
  systemctl enable --now sshd
  if systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --add-service=ssh >/dev/null
    firewall-cmd --reload >/dev/null
  fi
fi

echo "=== interface ==="
if command -v nmcli >/dev/null 2>&1; then
  nmcli -f DEVICE,TYPE,STATE,CONNECTION dev status | sed -n "1p;/^${iface}[[:space:]]/p"
fi
"$ip_cmd" -br -4 addr show dev "$iface" || true

echo "=== route ==="
"$ip_cmd" route | sed -n '1,5p'

echo "=== sshd ==="
systemctl is-enabled sshd 2>/dev/null || true
systemctl is-active sshd 2>/dev/null || true

if command -v ss >/dev/null 2>&1; then
  listen_output="$(ss -lnt)"
elif [[ -x /usr/sbin/ss ]]; then
  listen_output="$(/usr/sbin/ss -lnt)"
else
  listen_output="$(netstat -lnt 2>/dev/null || true)"
fi
printf '%s\n' "$listen_output" | grep -E '(^|[[:space:]])([^[:space:]]*:)?22[[:space:]]' || true

echo "=== sentaurus ==="
sdevice_path="$(command -v sdevice 2>/dev/null || true)"
if [[ -z "$sdevice_path" && -x /usr/synopsys/sentaurus/W-2024.09/bin/sdevice ]]; then
  sdevice_path="/usr/synopsys/sentaurus/W-2024.09/bin/sdevice"
fi
printf '%s\n' "${sdevice_path:-missing}"

fail=0
"$ip_cmd" -o -4 addr show dev "$iface" | grep -q 'inet ' || { echo "$iface has no IPv4 address" >&2; fail=1; }
systemctl is-active --quiet sshd || { echo "sshd is not active" >&2; fail=1; }
printf '%s\n' "$listen_output" | grep -Eq '([^[:space:]]*:)?22[[:space:]]' || { echo "TCP 22 is not listening" >&2; fail=1; }
[[ -n "$sdevice_path" ]] || { echo "sdevice not found" >&2; fail=1; }

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi

echo "SSH bridge ready: Windows VMware NAT/DHCP -> VM $iface -> sshd:22"
