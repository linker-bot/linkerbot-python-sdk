#!/usr/bin/env bash

set -uo pipefail

readonly EXIT_NOT_FOUND=1
readonly EXIT_USAGE=2

interface="can0"
side=""
timeout_ms=500
capture_file=""
error_file=""
dump_pid=""

usage() {
    cat <<'EOF'
Detect a P7 arm without enabling or moving it.

Usage:
  examples/p7_detect.sh --side left|right [--interface can0] [--timeout-ms 500]

Options:
  --side SIDE          Arm side. Required: left or right.
  --interface IFACE    SocketCAN interface (default: can0).
  --timeout-ms MS      Capture timeout in milliseconds (default: 500).
  -h, --help           Show this help.

The script sends only read requests. A complete P7 must respond from all seven
motor IDs: 61-67 for the left arm or 51-57 for the right arm.
EOF
}

cleanup() {
    if [[ -n "${dump_pid}" ]] && kill -0 "${dump_pid}" 2>/dev/null; then
        kill "${dump_pid}" 2>/dev/null || true
        wait "${dump_pid}" 2>/dev/null || true
    fi
    [[ -n "${capture_file}" ]] && rm -f -- "${capture_file}"
    [[ -n "${error_file}" ]] && rm -f -- "${error_file}"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

while (($# > 0)); do
    case "$1" in
        --side)
            [[ $# -ge 2 ]] || { echo "error: --side requires a value" >&2; exit "$EXIT_USAGE"; }
            side="$2"
            shift 2
            ;;
        --interface)
            [[ $# -ge 2 ]] || { echo "error: --interface requires a value" >&2; exit "$EXIT_USAGE"; }
            interface="$2"
            shift 2
            ;;
        --timeout-ms)
            [[ $# -ge 2 ]] || { echo "error: --timeout-ms requires a value" >&2; exit "$EXIT_USAGE"; }
            timeout_ms="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "error: unknown argument: $1" >&2
            usage >&2
            exit "$EXIT_USAGE"
            ;;
    esac
done

if [[ "${side}" != "left" && "${side}" != "right" ]]; then
    echo "error: --side must be left or right" >&2
    exit "$EXIT_USAGE"
fi
if [[ ! "${interface}" =~ ^[[:alnum:]_.:-]+$ ]]; then
    echo "error: invalid SocketCAN interface name: ${interface}" >&2
    exit "$EXIT_USAGE"
fi
if [[ ! "${timeout_ms}" =~ ^[1-9][0-9]*$ ]] || ((timeout_ms > 5000)); then
    echo "error: --timeout-ms must be an integer from 1 to 5000" >&2
    exit "$EXIT_USAGE"
fi

for command_name in ip cansend candump timeout awk; do
    if ! command -v "${command_name}" >/dev/null 2>&1; then
        echo "error: required command not found: ${command_name}" >&2
        exit "$EXIT_USAGE"
    fi
done

if ! link_details=$(ip -details link show dev "${interface}" 2>/dev/null); then
    echo "error: SocketCAN interface ${interface} does not exist" >&2
    exit "$EXIT_USAGE"
fi
if [[ "${link_details}" != *"link/can"* ]]; then
    echo "error: ${interface} is not a CAN interface" >&2
    exit "$EXIT_USAGE"
fi
if ! ip -o link show dev "${interface}" | awk '{print $3}' | grep -Eq '(^|,)UP(,|$)'; then
    echo "error: SocketCAN interface ${interface} is down" >&2
    exit "$EXIT_USAGE"
fi

bitrate=$(awk '
    / bitrate / {
        for (i = 1; i <= NF; i++) {
            if ($i == "bitrate") {
                print $(i + 1)
                exit
            }
        }
    }
' <<<"${link_details}")
if [[ -n "${bitrate}" && "${bitrate}" != "1000000" ]]; then
    echo "error: ${interface} bitrate is ${bitrate}; P7 requires 1000000 bit/s" >&2
    exit "$EXIT_USAGE"
fi

base_id=51
[[ "${side}" == "left" ]] && base_id=61

declare -a motor_ids=()
declare -a control_ids=()
declare -a probe_ids=()
filter="${interface}"
for ((joint = 0; joint < 7; joint++)); do
    motor_id=$((base_id + joint))
    printf -v control_id '%03X' "${motor_id}"
    motor_ids+=("${motor_id}")
    control_ids+=("${control_id}")
    if ((joint < 5)); then
        probe_id="${control_id}"
    else
        printf -v probe_id '%03X' "$((0x600 + motor_id))"
    fi
    probe_ids+=("${probe_id}")
    filter+=",${probe_id}:C00007FF"
done

capture_file=$(mktemp "${TMPDIR:-/tmp}/p7-detect.XXXXXX") || exit "$EXIT_USAGE"
error_file="${capture_file}.err"
outer_timeout_s=$(((timeout_ms + 999) / 1000 + 1))

timeout "${outer_timeout_s}s" \
    candump -L -x -T "${timeout_ms}" "${filter}" \
    >"${capture_file}" 2>"${error_file}" &
dump_pid=$!
sleep 0.05

if ! kill -0 "${dump_pid}" 2>/dev/null; then
    wait "${dump_pid}" 2>/dev/null || true
    echo "error: candump could not monitor ${interface}" >&2
    [[ -s "${error_file}" ]] && sed 's/^/  /' "${error_file}" >&2
    exit "$EXIT_USAGE"
fi

send_failed=0
for ((joint = 0; joint < 5; joint++)); do
    if ! cansend "${interface}" "${control_ids[$joint]}#01"; then
        echo "error: failed to send probe for motor ${motor_ids[$joint]}" >&2
        send_failed=1
    fi
done
for ((joint = 5; joint < 7; joint++)); do
    if ! cansend "${interface}" "${probe_ids[$joint]}#670B000000000476"; then
        echo "error: failed to send probe for motor ${motor_ids[$joint]}" >&2
        send_failed=1
    fi
done

if ((send_failed)); then
    exit "$EXIT_USAGE"
fi

wait_status=0
wait "${dump_pid}" || wait_status=$?
dump_pid=""
if ((wait_status != 0 && wait_status != 124)); then
    echo "error: candump failed while monitoring ${interface}" >&2
    [[ -s "${error_file}" ]] && sed 's/^/  /' "${error_file}" >&2
    exit "$EXIT_USAGE"
fi

declare -A online=()
while IFS= read -r line; do
    [[ "${line}" == *" RX "* ]] || continue
    if [[ "${line}" =~ [[:space:]]([[:xdigit:]]{3})#([[:xdigit:]]*) ]]; then
        frame_id="${BASH_REMATCH[1]^^}"
        frame_data="${BASH_REMATCH[2]^^}"
    else
        continue
    fi

    for ((joint = 0; joint < 5; joint++)); do
        if [[ "${frame_id}" == "${probe_ids[$joint]}" && "${frame_data}" == 01* ]]; then
            online["${joint}"]=1
        fi
    done
    for ((joint = 5; joint < 7; joint++)); do
        printf -v response_pattern '^%02X0B[0-9A-F]{8}00FF$' "${motor_ids[$joint]}"
        if [[ "${frame_id}" == "${probe_ids[$joint]}" && "${frame_data}" =~ ${response_pattern} ]]; then
            online["${joint}"]=1
        fi
    done
done <"${capture_file}"

found=0
echo "P7 ${side} probe on ${interface}:"
for ((joint = 0; joint < 7; joint++)); do
    protocol="V1 register"
    ((joint >= 5)) && protocol="V2 flash"
    if [[ -n "${online[$joint]:-}" ]]; then
        printf '  [OK]      joint %d: motor %d (0x%s, %s)\n' \
            "$((joint + 1))" "${motor_ids[$joint]}" "${control_ids[$joint]}" "${protocol}"
        found=$((found + 1))
    else
        printf '  [MISSING] joint %d: motor %d (0x%s, %s)\n' \
            "$((joint + 1))" "${motor_ids[$joint]}" "${control_ids[$joint]}" "${protocol}"
    fi
done

if ((found == 7)); then
    echo "P7 detected: all 7 motors responded."
    exit 0
fi
if ((found == 0)); then
    echo "P7 not detected: no expected motor responded." >&2
else
    echo "Incomplete P7: ${found}/7 motors responded." >&2
fi
exit "$EXIT_NOT_FOUND"
