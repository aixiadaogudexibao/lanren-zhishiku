#!/usr/bin/env python3
"""执行流展示：把本轮用到的技术卡按「下一跳」串成 a -> b -> c

用法：
  python3 show_flow.py <领域根> --date 2026-10-18 [--case <领域>/<编号>]
  python3 show_flow.py <领域根> --keys liucheng_biao/H.cat.1,liucheng_biao/H.cat.2

说明：
  - 读 yongfa.txt 里指定日期（及可选案例）的 liucheng_biao/* 记录
  - 按卡片正文的「## 下一跳」建立图，从入口卡出发做最长可连链
  - 不在链上的卡单独列出（本轮用了但连不上）
  - 只读，不改任何文件
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FIELD_NEXT = "## 下一跳"
FIELD_TITLE = re.compile(r"^#\s+([A-Za-z0-9_.\-]+)\s*[·:：]?")


def parse_card(path: Path) -> tuple[str, list[str], list[str]]:
    """返回 (卡名, 下一跳候选列表, 其它候选说明)"""
    text = path.read_text(encoding="utf-8", errors="ignore")
    name = path.stem

    m = FIELD_TITLE.search(text)
    if m:
        name = m.group(1).rstrip(".")

    nexts: list[str] = []
    notes: list[str] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() != FIELD_NEXT:
            continue
        # 取该节直到下一个 ## 或空行后的非 -> 行
        for j in range(i + 1, len(lines)):
            cur = lines[j].strip()
            if cur.startswith("## "):
                break
            if not cur:
                continue
            # 提取 `X.y` 形式的卡号（含反引号）
            for cid in re.findall(r"`?([A-Za-z][A-Za-z0-9_]*\.[A-Za-z0-9_]+(?:\.[0-9]+)?)`?", cur):
                if re.match(r"^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z0-9_]+", cid) and cid not in nexts:
                    nexts.append(cid)
            if "结束" in cur or "交 flag" in cur:
                notes.append("结束")
        break
    return name, nexts, notes


def load_used(domain_root: Path, date: str | None, case: str | None) -> list[str]:
    yf = domain_root / "yongfa.txt"
    if not yf.exists():
        return []
    used: list[str] = []
    for line in yf.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip() or line.strip() == "★" or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        d, key, result = parts[0], parts[1], parts[2]
        if date and d != date:
            continue
        if case and len(parts) > 3 and parts[3] not in ("-", case):
            continue
        if not key.startswith("liucheng_biao/"):
            continue
        if result != "成":
            continue
        used.append(key.split("/", 1)[1])
    return used


def build_chain(cards: dict[str, list[str]], used: list[str]) -> tuple[list[str], list[str]]:
    """在 used 内做最长可连链；返回 (链, 剩余)"""
    used_set = set(used)
    if not used_set:
        return [], []

    # 找入口：used 中不被任何其它 used 卡指向的
    pointed: set[str] = set()
    for u in used_set:
        for n in cards.get(u, []):
            if n in used_set:
                pointed.add(n)
    entries = [u for u in used if u not in pointed] or [used[0]]

    best: list[str] = []

    def walk(cur: str, path: list[str]) -> None:
        nonlocal best
        if len(path) > len(best):
            best = list(path)
        for n in cards.get(cur, []):
            if n in used_set and n not in path:
                walk(n, path + [n])

    for e in entries:
        walk(e, [e])
        if len(best) == len(used_set):
            break

    chain = best
    rest = [u for u in used if u not in chain]
    return chain, rest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("domain_root")
    ap.add_argument("--date")
    ap.add_argument("--case")
    ap.add_argument("--keys", help="逗号分隔的 liucheng_biao/*；给了就不读 yongfa.txt")
    args = ap.parse_args()

    root = Path(args.domain_root)
    lb = root / "liucheng_biao"
    if not lb.is_dir():
        print(f"[错误] 无 liucheng_biao 目录：{lb}", file=sys.stderr)
        return 1

    if args.keys:
        used = [k.split("/", 1)[-1] for k in args.keys.split(",") if k.strip()]
    else:
        used = load_used(root, args.date, args.case)

    if not used:
        print("本轮未记录 liucheng_biao 技术卡（yongfa 无成功记录）。")
        return 0

    cards: dict[str, list[str]] = {}
    for name in used:
        p = lb / f"{name}.txt"
        if p.exists():
            _, nxt, _ = parse_card(p)
            cards[name] = nxt
        else:
            cards[name] = []

    chain, rest = build_chain(cards, used)

    print("## 本轮使用技术卡")
    print()
    for u in used:
        nxt = cards.get(u, [])
        mark = "✔" if nxt else "·"
        print(f"- {mark} {u}" + (f"  → {', '.join(nxt)}" if nxt else ""))
    print()

    print("## 执行流")
    print()
    if len(chain) >= 2:
        print(" -> ".join(chain))
    elif chain:
        print(f"{chain[0]}（无下一跳记录，或下一跳未在本轮使用）")
    else:
        print("（无可连接链）")

    if rest:
        print()
        print("## 未连入主链（本轮用到，但上下游不在本轮）")
        print()
        for r in rest:
            nxt = cards.get(r, [])
            print(f"- {r}" + (f"  → {', '.join(nxt)}（未使用）" if nxt else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
