#!/usr/bin/env bash
# Install lanren-zhishiku skills into the pi skills directory and write xinxi.txt.
#
# Usage:
#   bash install.sh
#   bash install.sh --copy
#   bash install.sh --force
#   bash install.sh --skip-xinxi
#   SKILLS_ROOT=/path bash install.sh

set -euo pipefail

SRC_ROOT="$(cd "$(dirname "$0")" && pwd)"
MODE=link
FORCE=0
SKIP_XINXI=0
SKIP_LINK=0
SKILLS_ROOT="${SKILLS_ROOT:-$HOME/.pi/agent/skills}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --copy) MODE=copy; shift ;;
    --link) MODE=link; shift ;;
    --force) FORCE=1; shift ;;
    --skip-xinxi) SKIP_XINXI=1; shift ;;
    --skip-link|--xinxi-only) SKIP_LINK=1; shift ;;
    --skills-root) SKILLS_ROOT="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

NAMES=(zhishiku-caiji zhishiku-tilian zhishiku-gengxin zhishiku-chuli)

to_win_style() {
  # /mnt/c/Users/xi/... -> C:/Users/xi/...
  # /media/xi/系统/Users/xi/... -> C:/Users/xi/...
  local p="$1"
  if [[ "$p" =~ ^/mnt/([a-zA-Z])/(.*)$ ]]; then
    local d
    d="$(echo "${BASH_REMATCH[1]}" | tr '[:lower:]' '[:upper:]')"
    echo "${d}:/${BASH_REMATCH[2]}"
    return
  fi
  if [[ "$p" == /media/xi/系统/* ]]; then
    echo "C:/${p#/media/xi/系统/}"
    return
  fi
  # Already windows-ish or unknown: keep as-is for _linux, mirror for _win best-effort
  echo "$p"
}

to_linux_style() {
  local p="$1"
  if [[ "$p" =~ ^([A-Za-z]):/(.*)$ ]]; then
    local d
    d="$(echo "${BASH_REMATCH[1]}" | tr '[:lower:]' '[:upper:]')"
    local rest="${BASH_REMATCH[2]}"
    if [[ "$d" == "C" ]]; then
      echo "/media/xi/系统/${rest}"
    else
      echo "/mnt/$(echo "$d" | tr '[:upper:]' '[:lower:]')/${rest}"
    fi
    return
  fi
  echo "$p"
}

write_xinxi() {
  local repo_win="$1"
  local repo_linux="$2"
  local dir key example out
  for dir in zhishiku-caiji zhishiku-tilian zhishiku-gengxin; do
    example="$SRC_ROOT/$dir/xinxi.txt.example"
    out="$SRC_ROOT/$dir/xinxi.txt"
    if [[ ! -f "$example" ]]; then
      echo "warn: missing $example" >&2
      continue
    fi
    sed -e "s|{{REPO_WIN}}|${repo_win}|g" -e "s|{{REPO_LINUX}}|${repo_linux}|g" "$example" >"$out"
    echo "wrote   $out"
  done
}

# Resolve dual paths from wherever we run
case "$(uname -s)" in
  Linux*)
    REPO_LINUX="$SRC_ROOT"
    REPO_WIN="$(to_win_style "$SRC_ROOT")"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    # Git Bash often gives /c/Users/...
    _p="$SRC_ROOT"
    if [[ "$_p" =~ ^/([a-zA-Z])/(.*)$ ]]; then
      _d="$(echo "${BASH_REMATCH[1]}" | tr '[:lower:]' '[:upper:]')"
      REPO_WIN="${_d}:/${BASH_REMATCH[2]}"
    else
      REPO_WIN="$(to_win_style "$_p")"
    fi
    REPO_LINUX="$(to_linux_style "$REPO_WIN")"
    ;;
  *)
    REPO_LINUX="$SRC_ROOT"
    REPO_WIN="$SRC_ROOT"
    ;;
esac

if [[ "$SKIP_XINXI" -eq 0 ]]; then
  write_xinxi "$REPO_WIN" "$REPO_LINUX"
fi

if [[ "$SKIP_LINK" -eq 1 ]]; then
  echo "skip link/copy (--skip-link)"
else
  mkdir -p "$SKILLS_ROOT"

  for n in "${NAMES[@]}"; do
    src="$SRC_ROOT/$n"
    dst="$SKILLS_ROOT/$n"
    if [[ ! -d "$src" ]]; then
      echo "warn: skip missing source: $src" >&2
      continue
    fi
    if [[ -e "$dst" || -L "$dst" ]]; then
      if [[ "$FORCE" -eq 1 ]]; then
        echo "removing existing: $dst"
        rm -rf "$dst"
      else
        echo "warn: exists, skip (use --force to replace): $dst" >&2
        continue
      fi
    fi
    if [[ "$MODE" == link ]]; then
      ln -s "$src" "$dst"
      echo "linked  $dst  ->  $src"
    else
      cp -a "$src" "$dst"
      echo "copied  $src  ->  $dst"
    fi
  done
fi

echo
echo "done."
echo "  data roots : $SRC_ROOT"
echo "  skills root: $SKILLS_ROOT"
echo "  triggers   : 「使用知识库系统」 / 「开启知识库系统模式」"
echo "reopen the pi session to load skills."
