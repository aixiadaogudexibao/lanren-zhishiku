#!/usr/bin/env python3
"""校验五个 zhishiku-* skill 的版本号是否一致

规则（见 ~/.zhishiku/总览.md「版本号规则」）：
  五个 skill 共用套件版本号，不再各自独立演进。

用法：
  python3 check_versions.py              # 只检查，不一致返回非零
  python3 check_versions.py --set 6.1.0  # 五个一起改成指定版本
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 脚本在 <skills>/zhishiku-chuli/scripts/ 下；向上找到包含全部 zhishiku-* 的目录
def _find_skills_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "zhishiku-chuli" / "SKILL.md").exists():
            return parent
    return here.parents[2]


SKILLS_DIR = _find_skills_dir()
NAMES = ["zhishiku-chuli", "zhishiku-caiji", "zhishiku-tilian", "zhishiku-gengxin", "zhishiku-github"]
VER_RE = re.compile(r'^\s+version:\s*"([^"]+)"', re.M)


def read_ver(p: Path) -> str | None:
    try:
        m = VER_RE.search(p.read_text(encoding="utf-8")[:600])
    except OSError:
        return None
    return m.group(1) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", dest="new_ver", help="把五个 skill 一起改成该版本")
    args = ap.parse_args()

    paths = {n: SKILLS_DIR / n / "SKILL.md" for n in NAMES}

    if args.new_ver:
        if not re.fullmatch(r"\d+\.\d+\.\d+", args.new_ver):
            print(f"[错误] 版本号格式应为 X.Y.Z：{args.new_ver}", file=sys.stderr)
            return 1
        for n, p in paths.items():
            if not p.exists():
                print(f"[跳过] 不存在：{p}", file=sys.stderr)
                continue
            s = p.read_text(encoding="utf-8")
            if not VER_RE.search(s):
                print(f"[错误] {n} 无 version 行", file=sys.stderr)
                return 1
            p.write_text(VER_RE.sub(f'  version: "{args.new_ver}"', s, count=1), encoding="utf-8")
            print(f"✓ {n:18} → {args.new_ver}")
        return 0

    vers = {}
    for n, p in paths.items():
        if not p.exists():
            vers[n] = None
            print(f"✗ {n:18} 文件不存在")
            continue
        v = read_ver(p)
        vers[n] = v
        print(f"{'✓' if v else '✗'} {n:18} {v or '无 version'}")

    got = {v for v in vers.values() if v}
    if len(got) == 1 and all(vers.values()):
        print(f"\n✓ 版本一致：{got.pop()}")
        return 0
    print(f"\n✗ 版本不一致：{sorted(got)}", file=sys.stderr)
    print("  规则见 ~/.zhishiku/总览.md「版本号规则」；用 --set X.Y.Z 五个一起改。", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
