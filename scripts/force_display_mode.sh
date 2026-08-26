#!/bin/bash
# Force kiosk panel to DISPLAY_WIDTH x DISPLAY_HEIGHT (default 1024x600 landscape).
# Survives missing EDID modes by falling back to wlr-randr --custom-mode.
set -euo pipefail

DISPLAY_WIDTH="${DISPLAY_WIDTH:-1024}"
DISPLAY_HEIGHT="${DISPLAY_HEIGHT:-600}"
DISPLAY_ROTATION="${DISPLAY_ROTATION:-normal}"
TARGET_MODE="${DISPLAY_WIDTH}x${DISPLAY_HEIGHT}"
LOG="${KIOSK_DISPLAY_LOG:-${HOME:-/home/rle}/kiosk_display.log}"
RETRIES="${DISPLAY_FORCE_RETRIES:-8}"
RETRY_SLEEP="${DISPLAY_FORCE_RETRY_SLEEP:-1}"

mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG" 2>/dev/null || true; }

ensure_wayland_env() {
  if [[ -z "${XDG_RUNTIME_DIR:-}" ]]; then
    export XDG_RUNTIME_DIR="/run/user/$(id -u)"
  fi
  if [[ -z "${WAYLAND_DISPLAY:-}" ]]; then
    for cand in wayland-0 wayland-1; do
      if [[ -S "${XDG_RUNTIME_DIR}/${cand}" ]]; then
        export WAYLAND_DISPLAY="$cand"
        break
      fi
    done
  fi
}

wayland_outputs() {
  # Print enabled output names first, then any other named outputs.
  wlr-randr 2>/dev/null | awk '
    /^[^ ]/ { name=$1 }
    /Enabled: yes/ { print name; seen[name]=1 }
    END {
      # nothing else here; second pass below
    }
  '
  wlr-randr 2>/dev/null | awk '
    /^[^ ]/ { print $1 }
  ' | awk 'NF && !seen[$0]++'
}

current_mode_of() {
  local output="$1"
  wlr-randr 2>/dev/null | awk -v want="$output" '
    /^[^ ]/ { cur=($1==want) }
    cur && /\(current\)/ {
      if (match($0, /[0-9]+x[0-9]+/)) {
        print substr($0, RSTART, RLENGTH)
        exit
      }
    }
  '
}

apply_one_wayland() {
  local output="$1"
  # Prefer advertised mode; many 7" HDMI panels omit 1024x600 from EDID.
  if wlr-randr --output "$output" --mode "$TARGET_MODE" --transform "$DISPLAY_ROTATION" 2>/dev/null; then
    return 0
  fi
  if wlr-randr --output "$output" --custom-mode "$TARGET_MODE" --transform "$DISPLAY_ROTATION" 2>/dev/null; then
    return 0
  fi
  # Refresh rate variants some compositors accept
  if wlr-randr --output "$output" --custom-mode "${TARGET_MODE}@60" --transform "$DISPLAY_ROTATION" 2>/dev/null; then
    return 0
  fi
  if wlr-randr --output "$output" --custom-mode "${TARGET_MODE}@59.852" --transform "$DISPLAY_ROTATION" 2>/dev/null; then
    return 0
  fi
  return 1
}

verify_wayland() {
  local output mode ok=1
  local -a outs=()
  mapfile -t outs < <(wayland_outputs | awk 'NF && !seen[$0]++')
  ((${#outs[@]})) || return 1
  for output in "${outs[@]}"; do
    mode="$(current_mode_of "$output" || true)"
    if [[ "$mode" == "$TARGET_MODE" ]]; then
      log "verify ok output=$output mode=$mode"
      ok=0
    else
      log "verify miss output=$output mode=${mode:-unknown} want=$TARGET_MODE"
    fi
  done
  return "$ok"
}

apply_wayland_mode() {
  command -v wlr-randr >/dev/null 2>&1 || return 1
  ensure_wayland_env
  [[ -n "${WAYLAND_DISPLAY:-}" ]] || return 1
  [[ -S "${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}" ]] || return 1

  local -a outs=()
  mapfile -t outs < <(wayland_outputs | awk 'NF && !seen[$0]++')
  ((${#outs[@]})) || return 1

  local output applied=1
  for output in "${outs[@]}"; do
    if apply_one_wayland "$output"; then
      log "applied wayland output=$output mode=$TARGET_MODE transform=$DISPLAY_ROTATION"
      applied=0
    else
      log "apply failed wayland output=$output mode=$TARGET_MODE"
    fi
  done
  ((applied == 0)) || return 1
  verify_wayland
}

apply_x11_mode() {
  command -v xrandr >/dev/null 2>&1 || return 1
  [[ -n "${DISPLAY:-}" ]] || return 1

  local output
  output="$(xrandr --query 2>/dev/null | awk '/ connected/{print $1; exit}')"
  [[ -n "$output" ]] || return 1

  if ! xrandr --query 2>/dev/null | grep -Eq "(^| )${TARGET_MODE}( |$)"; then
    local gtf_line
    gtf_line="$(cvt "$DISPLAY_WIDTH" "$DISPLAY_HEIGHT" 60 2>/dev/null | awk '/Modeline /{$1=""; print substr($0,2)}' || true)"
    if [[ -n "$gtf_line" ]]; then
      # shellcheck disable=SC2086
      xrandr --newmode ${gtf_line} 2>/dev/null || true
      xrandr --addmode "$output" "$TARGET_MODE" 2>/dev/null || true
    fi
  fi

  xrandr --output "$output" --mode "$TARGET_MODE" --rotate "$DISPLAY_ROTATION" 2>/dev/null || return 1
  log "applied x11 output=$output mode=$TARGET_MODE"
  return 0
}

main() {
  log "force_display_mode start want=${TARGET_MODE} rotation=${DISPLAY_ROTATION}"
  local i
  for ((i = 1; i <= RETRIES; i++)); do
    if apply_wayland_mode || apply_x11_mode; then
      log "force_display_mode success attempt=${i}"
      exit 0
    fi
    log "force_display_mode retry=${i}/${RETRIES}"
    sleep "$RETRY_SLEEP"
  done
  log "force_display_mode FAILED want=${TARGET_MODE}"
  exit 1
}

main "$@"
