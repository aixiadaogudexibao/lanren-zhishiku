#!/usr/bin/env bash
# 打发布包（zip 一键包）。
#
#   bash pack.sh              -> dist/lanren-zhishiku-<日期>.zip
#   bash pack.sh /tmp/out     -> 指定输出目录
#   STAMP=v1 bash pack.sh     -> 指定后缀
#
# 从 git HEAD 导出，所以先 commit 再打包；工作区有未提交改动时会警告。
set -euo pipefail

cd "$(dirname "$0")"
NAME="lanren-zhishiku"
OUTDIR="${1:-dist}"
STAMP="${STAMP:-$(date +%Y%m%d)}"
OUT="$OUTDIR/${NAME}-${STAMP}.zip"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "不是 git 仓库，无法用 git archive 导出。" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "!! 工作区有未提交改动 —— zip 只含 HEAD 的内容，与当前文件不一致。" >&2
  echo "   先 git commit 再打包（若你确实要导 HEAD，忽略此警告）。" >&2
  echo >&2
fi

mkdir -p "$OUTDIR"
rm -f "$OUT"
git archive --format=zip --prefix="${NAME}/" -o "$OUT" HEAD

COUNT="$(python -c 'import sys,zipfile;print(len(zipfile.ZipFile(sys.argv[1]).namelist()))' "$OUT")"
SIZE="$(wc -c <"$OUT" | tr -d ' ')"
echo "已生成 $OUT"
echo "  条目 $COUNT 个 · $SIZE 字节"
echo "  解压后目录名：${NAME}/"

# 关键文件自检：包必须包含一键入口与四个 skill
for f in install.cmd install.ps1 install.sh sync.sh QUICKSTART.txt \
         tests/selftest.py zhishiku-gengxin/scripts/yongfa.py \
         zhishiku-caiji/SKILL.md zhishiku-tilian/SKILL.md \
         zhishiku-gengxin/SKILL.md zhishiku-chuli/SKILL.md; do
  if ! python -c 'import sys,zipfile;z=zipfile.ZipFile(sys.argv[1]);sys.exit(0 if "'"$NAME"'/"+"'"$f"'" in z.namelist() else 1)' "$OUT"; then
    echo "!! 包里缺少 $f" >&2
    exit 1
  fi
done
echo "  自检：关键文件齐备 ✅"

if python -c 'import sys,zipfile;z=zipfile.ZipFile(sys.argv[1]);sys.exit(0 if any("/xinxi.txt" == n[len("'"$NAME"'"):] for n in z.namelist()) else 1)' "$OUT"; then
  echo "!! 包里混进了 xinxi.txt（本机路径，不该发布）" >&2
  exit 1
fi
echo "  自检：无本机 xinxi.txt ✅"
