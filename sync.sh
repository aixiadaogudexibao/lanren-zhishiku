#!/usr/bin/env bash
# Sync skill definitions from this repo (the single source of truth) into one or
# more harness skills directories.
#
#   repo/*/SKILL.md   --sync-->   <target-root>/*/SKILL.md
#
# Per-target rewrite: the source uses `.pi/agent` as the canonical harness
# segment inside example paths (e.g. `C:/Users/<user>/.pi/agent/skills/...`). Each
# target gets its own segment substituted in, so a `.codex` install reads
# `.codex`. Byte-for-byte identical otherwise (line endings preserved).
#
# NOT synced on purpose:
#   - xinxi.txt  -> machine/harness config; every copy points at ONE shared data
#                   root, so there is nothing to sync. See docs/architecture.md.
#   - *_wei/**   -> live knowledge data, lives outside the skills dirs entirely.
#
# Usage:
#   bash sync.sh                 # sync to every default target below
#   bash sync.sh --check         # report drift only, write nothing (exit 1 if drifted)
#   bash sync.sh --target ~/.codex/skills
#   bash sync.sh --target ~/.pi/agent/skills --target /some/other/skills
#   bash sync.sh --source-segment .pi/agent

set -euo pipefail

SRC_ROOT="$(cd "$(dirname "$0")" && pwd)"
SOURCE_SEGMENT=".pi/agent"
CHECK=0
TARGETS=()

# git-bash / WSL 的 /c/... 、/mnt/c/... 在交给原生 Windows python 前显式换成 C:/...。
# 不能依赖 MSYS 的自动路径改写：它对 env 和 argv 的行为不一致（实测同一个值
# 走 env 会被改写、走 argv 不会），曾导致 --target /c/... 全部被当成“未安装”。
to_win() {
  local p="$1" d
  if [[ "$p" =~ ^/([a-zA-Z])/(.*)$ ]]; then
    d="$(echo "${BASH_REMATCH[1]}" | tr '[:lower:]' '[:upper:]')"
    printf '%s' "${d}:/${BASH_REMATCH[2]}"
  elif [[ "$p" =~ ^/mnt/([a-zA-Z])/(.*)$ ]]; then
    d="$(echo "${BASH_REMATCH[1]}" | tr '[:lower:]' '[:upper:]')"
    printf '%s' "${d}:/${BASH_REMATCH[2]}"
  else
    printf '%s' "$p"
  fi
}

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) SRC_ROOT="$(to_win "$SRC_ROOT")" ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK=1; shift ;;
    --target) TARGETS+=("$2"); shift 2 ;;
    --source-segment) SOURCE_SEGMENT="$2"; shift 2 ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  for d in "$HOME/.pi/agent/skills" "$HOME/.codex/skills"; do
    [[ -d "$d" ]] && TARGETS+=("$d")
  done
fi

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo "no targets found (looked for ~/.pi/agent/skills and ~/.codex/skills)" >&2
  echo "pass one explicitly: bash sync.sh --target <skills-root>" >&2
  exit 1
fi

rc=0
for target in "${TARGETS[@]}"; do
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) target="$(to_win "$target")" ;;
  esac
  SRC_ROOT="$SRC_ROOT" SOURCE_SEGMENT="$SOURCE_SEGMENT" \
  TARGET="$target" CHECK="$CHECK" HOME="$HOME" \
  python - <<'PY' || rc=1
import os
import pathlib
import re


def winify(p: pathlib.Path) -> pathlib.Path:
    """git-bash 传进来的 /c/Users/... 或 WSL 的 /mnt/c/... 换成 C:/Users/...
    （原生 Windows python 认不了 /c/...）。Linux 上不做任何转换。
    """
    if os.name != "nt":
        return p
    s = str(p)
    m = re.match(r"^/([A-Za-z])/(.*)$", s) or re.match(r"^/mnt/([A-Za-z])/(.*)$", s)
    if m:
        return pathlib.Path(f"{m.group(1).upper()}:/{m.group(2)}")
    return p

src_root = pathlib.Path(os.environ["SRC_ROOT"])
src_seg = os.environ["SOURCE_SEGMENT"]
target = winify(pathlib.Path(os.environ["TARGET"]))
check = os.environ["CHECK"] == "1"
home = os.environ["HOME"]


def segment_for(t: pathlib.Path) -> str:
    """harness 段 = 从目标往上**最近的以 . 开头的祖先目录**到目标之间那段路径。

    ~/.pi/agent/skills    -> .pi/agent
    ~/.codex/skills       -> .codex
    /tmp/x/.codex/skills  -> .codex

    不用 relative_to(HOME)：目标不在 HOME 下时会取出一长串无关的中间路径（曾把
    AppData/Local/Temp/x/.codex 整段当成 harness 段写进示例路径）。
    """
    parts = list(t.resolve().parts)
    for i in range(len(parts) - 2, -1, -1):
        if parts[i].startswith("."):
            return "/".join(parts[i:-1])
    return t.resolve().parent.name          # 没有 dot 祖先 → 退化为父目录名


seg = segment_for(target).replace("\\", "/")

print(f"==> {target}   (segment: {seg})")

names = sorted(
    p.name for p in src_root.iterdir()
    if p.is_dir() and (p / "SKILL.md").is_file()
)

def rels_for(n):
    """Everything that must be mirrored for one skill: SKILL.md + scripts/**."""
    out = ["SKILL.md"]
    sc = src_root / n / "scripts"
    if sc.is_dir():
        out += [f"scripts/{f.name}" for f in sorted(sc.iterdir()) if f.is_file()]
    return out

drift = False
wrote = 0
for n in names:
    if not (target / n).is_dir():
        print(f"  skip (not installed): {n}")
        continue
    for rel in rels_for(n):
        src = src_root / n / rel
        dst = target / n / rel
        with open(src, encoding="utf-8", newline="") as fh:
            text = fh.read()
        src_seg_bs = src_seg.replace("/", "\\")
        seg_bs = seg.replace("/", "\\")
        rendered = text.replace(src_seg, seg).replace(src_seg_bs, seg_bs)
        old = None
        if dst.is_file():
            with open(dst, encoding="utf-8", newline="") as fh:
                old = fh.read()
        if old == rendered:
            print(f"  ok      {n}/{rel}")
            continue
        if check:
            print(f"  DRIFT   {n}/{rel}")
            drift = True
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(dst, "w", encoding="utf-8", newline="") as fh:
                fh.write(rendered)
            print(f"  wrote   {n}/{rel}")
            wrote += 1

if check and drift:
    raise SystemExit(1)
print(f"  ({wrote} written)")
PY
done

echo
if [[ "$CHECK" -eq 1 ]]; then
  [[ "$rc" -eq 0 ]] && echo "all targets in sync." || echo "drift detected. run 'bash sync.sh' to fix."
else
  echo "done."
fi
exit "$rc"
