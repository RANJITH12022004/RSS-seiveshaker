#!/bin/bash
set -euo pipefail

DISPLAY_WIDTH="${DISPLAY_WIDTH:-1024}"
DISPLAY_HEIGHT="${DISPLAY_HEIGHT:-600}"
DISPLAY_ROTATION="${DISPLAY_ROTATION:-normal}"
TARGET_MODE="${DISPLAY_WIDTH}x${DISPLAY_HEIGHT}"

apply_x11_mode() {
  command -v xrandr >/dev/null 2>&1 || return 1
  [[ -n "${DISPLAY:-}" ]] || return 1

  local output
  output="$(xrandr --query 2>/dev/null | awk '/ connected/{print $1; exit}')"
  [[ -n "$output" ]] || return 1

  if ! xrandr --query 2>/dev/null | rg -q "^${TARGET_MODE}\b"; then
    local gtf_line
    gtf_line="$(cvt "$DISPLAY_WIDTH" "$DISPLAY_HEIGHT" 60 2>/dev/null | awk '/Modeline /{$1=""; print substr($0,2)}' || true)"
    if [[ -n "$gtf_line" ]]; then
      xrandr --newmode ${gtf_line} 2>/dev/null || true
      xrandr --addmode "$output" "$TARGET_MODE" 2>/dev/null || true
    fi
  fi

  xrandr --output "$output" --mode "$TARGET_MODE" --rotate "$DISPLAY_ROTATION" 2>/dev/null || true
}

apply_wayland_mode() {
  command -v wlr-randr >/dev/null 2>&1 || return 1
  [[ -n "${WAYLAND_DISPLAY:-}" ]] || return 1

  local output
  output="$(wlr-randr 2>/dev/null | awk '/^[^ ]/{print $1; exit}')"
  [[ -n "$output" ]] || return 1
  wlr-randr --output "$output" --mode "$TARGET_MODE" --transform "$DISPLAY_ROTATION" 2>/dev/null || true
}

apply_x11_mode || apply_wayland_mode || true
