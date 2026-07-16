#!/usr/bin/env bash
# Atomic, fail-closed single-core SDevice lease manager. Linux VM only (flock required).
set -euo pipefail

usage() {
    echo "usage: $0 {acquire|bind|release|status} [options]" >&2
    exit 64
}
fail() { echo "error=$1" >&2; exit 1; }
require_uint() { [[ ${2:-} =~ ^[0-9]+$ ]] || fail "invalid_${1}"; }
require_token() { [[ ${1:-} =~ ^[a-f0-9]{32}$ ]] || fail "invalid_token"; }
require_root() { [[ ${1:-} =~ ^/[A-Za-z0-9_./-]+$ ]] || fail "invalid_lease_root"; }
require_run_dir() { [[ ${1:-} =~ ^/[A-Za-z0-9_./-]+$ ]] || fail "invalid_remote_run_dir"; }
require_core_list() { [[ ${1:-} =~ ^[0-9]+(,[0-9]+)*$ ]] || fail "invalid_reserved_cores"; }

command=${1:-}
[[ "$command" =~ ^(acquire|bind|release|status)$ ]] || usage
shift || true
lease_root=''
reserved_cores=''
max_managed_slots=''
lock_timeout_seconds=''
remote_run_dir=''
owner_pid=''
token=''
core=''
while [[ $# -gt 0 ]]; do
    case "$1" in
        --lease-root|--reserved-cores|--max-managed-slots|--lock-timeout-seconds|--remote-run-dir|--owner-pid|--token|--core)
            [[ $# -ge 2 ]] || usage
            key=${1#--}; key=${key//-/_}; printf -v "$key" '%s' "$2"; shift 2 ;;
        *) usage ;;
    esac
done

case "$command" in
    acquire)
        require_root "$lease_root"; require_core_list "$reserved_cores"; require_uint max_managed_slots "$max_managed_slots"
        require_uint lock_timeout_seconds "$lock_timeout_seconds"; require_run_dir "$remote_run_dir"; require_uint owner_pid "$owner_pid"
        (( owner_pid > 0 )) || fail invalid_owner_pid ;;
    bind)
        require_root "$lease_root"; require_token "$token"; require_uint core "$core"; require_uint owner_pid "$owner_pid"
        (( owner_pid > 0 )) || fail invalid_owner_pid ;;
    release)
        require_root "$lease_root"; require_token "$token"; require_uint core "$core" ;;
    status)
        require_root "$lease_root"; lock_timeout_seconds=${lock_timeout_seconds:-20}; require_uint lock_timeout_seconds "$lock_timeout_seconds" ;;
esac

lock_timeout_seconds=${lock_timeout_seconds:-20}
umask 077
mkdir -p "$lease_root"
chmod 700 "$lease_root"
exec 9>"$lease_root/.lock"
flock -w "$lock_timeout_seconds" 9 || fail lock_timeout
leases_dir="$lease_root/leases"
mkdir -p "$leases_dir"
chmod 700 "$leases_dir"

read_lease_value() {
    local file=$1 wanted=$2 line key value
    while IFS= read -r line || [[ -n "$line" ]]; do
        key=${line%%=*}; value=${line#*=}
        [[ "$key" == "$wanted" ]] && { printf '%s' "$value"; return 0; }
    done < "$file"
    return 1
}

pid_exists() { [[ $1 =~ ^[1-9][0-9]*$ ]] && kill -0 "$1" 2>/dev/null; }
cleanup_stale_leases() {
    local file pid
    shopt -s nullglob
    for file in "$leases_dir"/*.lease; do
        pid=$(read_lease_value "$file" owner_pid || true)
        # A lease is stale only when its recorded owner PID no longer exists. No TTL reclaim.
        if ! pid_exists "$pid"; then rm -f -- "$file"; fi
    done
    shopt -u nullglob
}

range_contains() {
    local wanted=$1 item start end
    IFS=',' read -r -a items <<< "$2"
    for item in "${items[@]}"; do
        if [[ "$item" == *-* ]]; then
            start=${item%-*}; end=${item#*-}
            (( wanted >= start && wanted <= end )) && return 0
        elif [[ "$item" == "$wanted" ]]; then
            return 0
        fi
    done
    return 1
}

case "$command" in
    acquire)
        cleanup_stale_leases
        online=$(getconf _NPROCESSORS_ONLN) || fail online_core_probe_failed
        require_uint online_cores "$online"; (( online > 0 )) || fail online_core_probe_failed
        declare -A blocked=() lease_cores=()
        IFS=',' read -r -a reserved <<< "$reserved_cores"
        for c in "${reserved[@]}"; do (( c < online )) || fail reserved_core_out_of_range; blocked[$c]=reserved; done
        managed_count=0
        shopt -s nullglob
        for file in "$leases_dir"/*.lease; do
            c=$(read_lease_value "$file" core || true); require_uint lease_core "$c"
            (( c < online )) || fail corrupt_lease_core
            lease_cores[$c]=1; blocked[$c]=managed; managed_count=$((managed_count + 1))
        done
        shopt -u nullglob
        (( managed_count < max_managed_slots )) || fail managed_slot_limit

        # All current SDevice processes not represented by a lease are unmanaged and excluded.
        while IFS= read -r pid; do
            [[ "$pid" =~ ^[1-9][0-9]*$ ]] || continue
            is_managed=0
            shopt -s nullglob
            for file in "$leases_dir"/*.lease; do
                lease_pid=$(read_lease_value "$file" owner_pid || true)
                [[ "$lease_pid" == "$pid" ]] && { is_managed=1; break; }
            done
            shopt -u nullglob
            (( is_managed )) && continue
            affinity=$(taskset -pc "$pid" 2>/dev/null | sed -n 's/.*: //p' | tail -n 1) || fail unmanaged_affinity_probe_failed
            [[ "$affinity" =~ ^[0-9,-]+$ ]] || fail unmanaged_affinity_invalid
            for ((c=0; c<online; c++)); do
                if range_contains "$c" "$affinity"; then blocked[$c]=unmanaged; fi
            done
        done < <(pgrep -x sdevice || true)

        selected=''
        for ((c=0; c<online; c++)); do
            [[ -z ${blocked[$c]+x} ]] && { selected=$c; break; }
        done
        [[ -n "$selected" ]] || fail no_safe_core_available
        token=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
        require_token "$token"
        file="$leases_dir/$token.lease"
        {
            printf 'core=%s\n' "$selected"
            printf 'token=%s\n' "$token"
            printf 'owner_pid=%s\n' "$owner_pid"
            printf 'remote_run_dir=%s\n' "$remote_run_dir"
            printf 'created_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        } > "$file"
        printf 'action=acquire\ncore=%s\ntoken=%s\nlease_file=%s\nowner_pid=%s\n' "$selected" "$token" "$file" "$owner_pid" ;;
    bind)
        file="$leases_dir/$token.lease"
        [[ -f "$file" ]] || fail lease_not_found
        expected_core=$(read_lease_value "$file" core || true)
        [[ "$expected_core" == "$core" ]] || fail core_mismatch
        stored_token=$(read_lease_value "$file" token || true)
        [[ "$stored_token" == "$token" ]] || fail token_mismatch
        tmp="$file.tmp.$$"
        sed '/^owner_pid=/d' "$file" > "$tmp"
        printf 'owner_pid=%s\n' "$owner_pid" >> "$tmp"
        mv -f -- "$tmp" "$file"
        printf 'action=bind\ncore=%s\ntoken=%s\nowner_pid=%s\n' "$core" "$token" "$owner_pid" ;;
    release)
        file="$leases_dir/$token.lease"
        [[ -f "$file" ]] || fail lease_not_found
        expected_core=$(read_lease_value "$file" core || true)
        stored_token=$(read_lease_value "$file" token || true)
        [[ "$expected_core" == "$core" ]] || fail core_mismatch
        [[ "$stored_token" == "$token" ]] || fail token_mismatch
        rm -f -- "$file"
        printf 'action=release\ncore=%s\ntoken=%s\nreleased=true\n' "$core" "$token" ;;
    status)
        cleanup_stale_leases
        online=$(getconf _NPROCESSORS_ONLN) || fail online_core_probe_failed
        printf 'action=status\nonline_cores=%s\nlease_count=' "$online"
        lease_count=0
        shopt -s nullglob
        for file in "$leases_dir"/*.lease; do lease_count=$((lease_count + 1)); done
        printf '%s\n' "$lease_count"
        for file in "$leases_dir"/*.lease; do
            printf 'lease=%s core=%s owner_pid=%s remote_run_dir=%s\n' "$(basename "$file")" "$(read_lease_value "$file" core)" "$(read_lease_value "$file" owner_pid)" "$(read_lease_value "$file" remote_run_dir)"
        done
        shopt -u nullglob ;;
esac