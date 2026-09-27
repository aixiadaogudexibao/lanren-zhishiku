#!/usr/bin/env bash
# Install lanren-zhishiku skills into the pi skills directory and write xinxi.txt.
#
# Usage:
#   bash install.sh
#   bash install.sh --copy
#   bash install.sh --force
#   bash install.sh --skip-xinxi
#   bash install.sh --data-root ~/.zhishiku       # one data root shared by all harnesses
#   bash install.sh --linux-prefix /media/u/系统   # C: 在 Linux 侧的挂载前缀（默认 /mnt/c）
#   bash install.sh --force-xinxi                  # overwrite an existing xinxi.txt
#   SKILLS_ROOT=/path bash install.sh

set -euo pipefail

SRC_ROOT="$(cd "$(dirname "$0")" && pwd)"
# Linux 侧 C: 盘的前缀。默认用 WSL 标准 /mnt/c；
# 若你的盘挂到别处（例：C: -> /media/<你>/系统），用 --linux-prefix 或
# 环境变量 ZHISHIKU_LINUX_C_PREFIX 覆盖，否则生成的 _linux 路径在别的机器上对不上。
LINUX_C_PREFIX="${ZHISHIKU_LINUX_C_PREFIX:-/mnt/c}"

MODE=link
FORCE=0
SKIP_XINXI=0
SKIP_LINK=0
FORCE_XINXI=0
DATA_ROOT=""
SKILLS_ROOT="${SKILLS_ROOT:-$HOME/.pi/agent/skills}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --copy) MODE=copy; shift ;;
    --link) MODE=link; shift ;;
    --force) FORCE=1; shift ;;
    --skip-xinxi) SKIP_XINXI=1; shift ;;
    --skip-link|--xinxi-only) SKIP_LINK=1; shift ;;
    --skills-root) SKILLS_ROOT="$2"; shift 2 ;;
    --data-root) DATA_ROOT="$2"; shift 2 ;;
    --linux-prefix) LINUX_C_PREFIX="$2"; shift 2 ;;
    --force-xinxi) FORCE_XINXI=1; shift ;;
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

NAMES=(zhishiku-caiji zhishiku-tilian zhishiku-gengxin zhishiku-chuli)

# Windows 风格反斜杠路径可以照原样写（C:\Users\<用户>\.zhishiku），一律先归一成正斜杠。
# 不要用 ${v//\\//}：它在 bash 5.3 上根本不替换反斜杠（版本间行为不一致）。
# bash 5.2+ 的 patsub_replacement 还会把替换串里的 `&` 当成匹配文本，一并关掉。
shopt -u patsub_replacement 2>/dev/null || true

norm_path() {
  printf '%s' "$1" | tr '\134' '/'
}

to_win_style() {
  # /c/Users/<用户>/...      (git-bash)  -> C:/Users/<用户>/...
  # /mnt/c/Users/<用户>/...  (WSL)       -> C:/Users/<用户>/...
  # <--linux-prefix>/...                -> C:/...
  local p="$1"
  if [[ "$p" =~ ^/([a-zA-Z])/(.*)$ ]]; then
    local d
    d="$(echo "${BASH_REMATCH[1]}" | tr '[:lower:]' '[:upper:]')"
    echo "${d}:/${BASH_REMATCH[2]}"
    return
  fi
  if [[ "$p" =~ ^/mnt/([a-zA-Z])/(.*)$ ]]; then
    local d
    d="$(echo "${BASH_REMATCH[1]}" | tr '[:lower:]' '[:upper:]')"
    echo "${d}:/${BASH_REMATCH[2]}"
    return
  fi
  if [[ "$p" == "${LINUX_C_PREFIX%/}"/* ]]; then
    echo "C:/${p#${LINUX_C_PREFIX%/}/}"
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
      printf '%s' "${LINUX_C_PREFIX%/}/${rest}"
    else
      echo "/mnt/$(echo "$d" | tr '[:upper:]' '[:lower:]')/${rest}"
    fi
    return
  fi
  echo "$p"
}

# $1/$2 = the directory that CONTAINS the three *_wei dirs
#          (repo root by default, or --data-root)
write_xinxi() {
  local root_win="$1"
  local root_linux="$2"
  local dir key example out text old
  for pair in "zhishiku-caiji:caiji_wei" "zhishiku-tilian:tilian_wei" "zhishiku-gengxin:gengxin_wei"; do
    dir="${pair%%:*}"; key="${pair##*:}"
    example="$SRC_ROOT/$dir/xinxi.txt.example"
    out="$SRC_ROOT/$dir/xinxi.txt"
    if [[ ! -f "$example" ]]; then
      echo "warn: missing $example" >&2
      continue
    fi
    # 用 bash 参数扩展而不是 sed：路径里可能含 \ & | 等 sed 元字符，
    # 例如把路径里的 \U 当成转义，作者曾因此生成 C:SERSXI.ZHISHIKU 这种乱码。
    text="$(cat "$example")"
    text="${text//\{\{DATA_WIN\}\}/$root_win/$key}"
    text="${text//\{\{DATA_LINUX\}\}/$root_linux/$key}"
    if [[ -f "$out" ]]; then
      old="$(cat "$out")"
      if [[ "$old" != "$text" && "$FORCE_XINXI" -eq 0 ]]; then
        echo "warn: $out already points somewhere else; keeping it." >&2
        echo "      (rerun with --force-xinxi to overwrite with: $root_win/$key)" >&2
        continue
      fi
    fi
    printf '%s\n' "$text" >"$out"
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

# --data-root: keep the knowledge data outside any harness/repo dir so it is
# shared by every harness and survives reinstalls. See docs/architecture.md.
DATA_ROOT="$(norm_path "$DATA_ROOT")"
SKILLS_ROOT="$(norm_path "$SKILLS_ROOT")"
if [[ -n "$DATA_ROOT" ]]; then
  # 先把任何写法（/c/... 、C:\... 、C:/...）转成 Windows 形式，再由它推出 Linux 形式。
  REPO_WIN="$(to_win_style "$(norm_path "$DATA_ROOT")")"
  REPO_LINUX="$(to_linux_style "$REPO_WIN")"
fi

# Three independent data roots live side by side under one parent dir.
DATA_PARENT_LOCAL="${DATA_ROOT:-$SRC_ROOT}"
# --data-root 可以指向还不存在的目录，先建出来
[[ -n "$DATA_ROOT" ]] && mkdir -p "$DATA_PARENT_LOCAL" 2>/dev/null || true
if [[ -d "$DATA_PARENT_LOCAL" ]]; then
  mkdir -p "$DATA_PARENT_LOCAL"/caiji_wei \
           "$DATA_PARENT_LOCAL"/tilian_wei \
           "$DATA_PARENT_LOCAL"/gengxin_wei 2>/dev/null || true
fi

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
echo "  data roots : ${DATA_ROOT:-$SRC_ROOT}"
echo "  skills root: $SKILLS_ROOT"
echo "  triggers   : 「使用知识库系统」 / 「开启知识库系统模式」"
echo "reopen the pi session to load skills."
