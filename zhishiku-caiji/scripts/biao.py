#!/usr/bin/env python3
"""biao_xin.txt 机械操作（禁止手改 order / flag / 节位置）

biao_xin.txt 是该领域案例的生命周期权威：
    # order | id | flag
    [dai]
    1|0026|1
    [hui]
    1|0001|12
    ...

手改最容易错的三件事：order 重排、flag 改值、[dai]↔[hui] 移动。
本脚本把它们固化成命令，并保证：
  - order 在每个节内始终从 1 连续递增
  - flag 按语义校验（见下表）
  - 移动时同时搬目录，避免表和磁盘不一致

flag 语义（来自 zhishiku-caiji）：
  0  待采集    1  采集中    2  归档中（崩溃恢复）    4  已归档
  8  可选附加位「无需用户确认即可交付」：flag = 必要状态 + 8
  合法取值只有：0 1 2 4 8 9 10 12

用法：
  python3 biao.py <领域根> show
  python3 biao.py <领域根> add <id> [--flag 0]
  python3 biao.py <领域根> set-flag <id> <flag>
  python3 biao.py <领域根> move <id> --to hui          # 同时搬目录
  python3 biao.py <领域根> order <id> <n>              # 调整顺序
  python3 biao.py <领域根> check                       # 校验一致性

领域根例：~/.zhishiku/caiji_wei/ctf-pwn
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# 合法取值只有 0 1 2 4 8 9 10 12（8 是可选附加位：flag = 必要状态 + 8）
LEGAL_FLAGS = {0, 1, 2, 4, 8, 9, 10, 12}
FLAG_MEAN = {
    0: "待采集", 1: "采集中", 2: "归档中", 4: "已归档",
    8: "待采集+可直交", 9: "采集中+可直交", 10: "归档中+可直交", 12: "已归档+可直交",
}
SECTIONS = ("dai", "hui")


class Biao:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "biao_xin.txt"
        if not self.path.exists():
            raise SystemExit(f"[错误] 缺 biao_xin.txt：{self.path}")
        self.data: dict[str, list[tuple[str, int]]] = {s: [] for s in SECTIONS}
        self._parse()

    def _parse(self) -> None:
        cur = None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            t = line.strip()
            if t in ("[dai]", "[hui]"):
                cur = t[1:-1]
                continue
            if not cur or not t or t.startswith("#"):
                continue
            parts = [x.strip() for x in t.split("|")]
            if len(parts) >= 3 and parts[1].isdigit():
                self.data[cur].append((parts[1], int(parts[2]) if parts[2].isdigit() else 0))

    def save(self) -> None:
        out = ["# order | id | flag"]
        for s in SECTIONS:
            out.append(f"[{s}]")
            for i, (cid, fl) in enumerate(self.data[s], 1):
                out.append(f"{i}|{cid}|{fl}")
            out.append("")
        # 去掉最后一个多余空行
        while out and out[-1] == "":
            out.pop()
        self.path.write_text("\n".join(out) + "\n", encoding="utf-8")

    # ── 查询 ──
    def find(self, cid: str) -> tuple[str, int] | None:
        for s in SECTIONS:
            for i, (c, fl) in enumerate(self.data[s]):
                if c == cid:
                    return s, i
        return None

    def ids(self, sect: str) -> list[str]:
        return [c for c, _ in self.data[sect]]

    def next_id(self) -> str:
        allids = [c for s in SECTIONS for c in self.ids(s)]
        n = max((int(x) for x in allids if x.isdigit()), default=0)
        return f"{n + 1:04d}"

    # ── 修改 ──
    def add(self, cid: str, flag: int = 0, sect: str = "dai") -> None:
        if self.find(cid):
            raise SystemExit(f"[错误] 案例 {cid} 已存在")
        self.data[sect].append((cid, flag))
        self._sort_numeric(sect)

    def _sort_numeric(self, sect: str) -> None:
        self.data[sect].sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0)

    def set_flag(self, cid: str, flag: int) -> None:
        pos = self.find(cid)
        if not pos:
            raise SystemExit(f"[错误] 找不到案例 {cid}")
        s, i = pos
        self.data[s][i] = (cid, flag)

    def move(self, cid: str, to: str, with_dir: bool = True, flag_after: int = 4) -> None:
        pos = self.find(cid)
        if not pos:
            raise SystemExit(f"[错误] 找不到案例 {cid}")
        s, i = pos
        if s == to:
            print(f"（{cid} 已在 [{to}]）")
            return

        src_dir = self.root / "biao" / s / cid
        dst_dir = self.root / "biao" / to / cid
        if with_dir:
            if not src_dir.is_dir():
                raise SystemExit(f"[错误] 源目录不存在：{src_dir}")
            if dst_dir.exists():
                raise SystemExit(f"[错误] 目标已存在：{dst_dir}")

        # 步骤 1：标 flag=2（归档中，崩溃恢复标记）
        self.data[s][i] = (cid, 2)
        self.save()

        # 步骤 2：搬目录
        if with_dir:
            dst_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_dir), str(dst_dir))

        # 步骤 3：移到目标节，flag 改 4
        self.data[s].pop(i)
        self.data[to].append((cid, flag_after))
        self._sort_numeric(to)
        self.save()

    def reorder(self, cid: str, n: int) -> None:
        pos = self.find(cid)
        if not pos:
            raise SystemExit(f"[错误] 找不到案例 {cid}")
        s, i = pos
        item = self.data[s].pop(i)
        n = max(1, min(n, len(self.data[s]) + 1))
        self.data[s].insert(n - 1, item)

    # ── 校验 ──
    def check(self) -> list[str]:
        errs: list[str] = []
        for s in SECTIONS:
            seen: set[str] = set()
            for cid, fl in self.data[s]:
                if cid in seen:
                    errs.append(f"[{s}] 重复 id：{cid}")
                seen.add(cid)
                if fl not in LEGAL_FLAGS:
                    errs.append(f"[{s}] {cid} 非法 flag={fl}（合法：0 1 2 4 8 9 10 12）")
                d = self.root / "biao" / s / cid
                if not d.is_dir():
                    errs.append(f"[{s}] {cid} 有索引但目录不存在：{d}")
            on_disk = {x.name for x in (self.root / "biao" / s).iterdir() if x.is_dir()} if (self.root / "biao" / s).is_dir() else set()
            for extra in sorted(on_disk - seen):
                errs.append(f"[{s}] 目录 {extra} 未登记在 biao_xin")
        # dai 里有 flag=4 的（应该在 hui）
        for cid, fl in self.data["dai"]:
            if fl == 4:
                errs.append(f"[dai] {cid} flag=4（已归档）但仍在 dai")
        return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="biao_xin.txt 机械操作")
    ap.add_argument("root", help="领域根目录")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("show")
    p.set_defaults(fn=lambda b, a: cmd_show(b))

    p = sub.add_parser("add")
    p.add_argument("id", nargs="?")
    p.add_argument("--flag", type=int, default=0)
    p.set_defaults(fn=lambda b, a: (b.add(a.id or b.next_id(), a.flag), b.save(), print(f"✓ 已加入 [dai]：{a.id or '(自动编号)'}")))

    p = sub.add_parser("set-flag")
    p.add_argument("id")
    p.add_argument("flag", type=int)
    p.set_defaults(fn=lambda b, a: (b.set_flag(a.id, a.flag), b.save(), print(f"✓ {a.id} flag → {a.flag}")))

    p = sub.add_parser("move")
    p.add_argument("id")
    p.add_argument("--to", required=True, choices=list(SECTIONS))
    p.add_argument("--no-dir", action="store_true", help="只改表，不搬目录")
    p.set_defaults(fn=lambda b, a: (b.move(a.id, a.to, not a.no_dir), print(f"✓ {a.id} → [{a.to}]")))

    p = sub.add_parser("order")
    p.add_argument("id")
    p.add_argument("n", type=int)
    p.set_defaults(fn=lambda b, a: (b.reorder(a.id, a.n), b.save(), print(f"✓ {a.id} 移到第 {a.n} 位")))

    p = sub.add_parser("check")
    p.set_defaults(fn=None)

    args = ap.parse_args()
    b = Biao(Path(args.root))

    if args.cmd == "check":
        errs = b.check()
        if errs:
            print(f"✗ {len(errs)} 处问题：")
            for e in errs:
                print(f"  - {e}")
            return 2
        print("✓ biao_xin 与目录一致")
        return 0

    args.fn(b, args)
    return 0


def cmd_show(b: Biao) -> None:
    print(f"# {b.path}")
    for s in SECTIONS:
        print(f"\n[{s}] {len(b.data[s])} 项")
        for cid, fl in b.data[s]:
            print(f"  {cid}  flag={fl:<2} {FLAG_MEAN.get(fl, '?')}")


if __name__ == "__main__":
    sys.exit(main())
