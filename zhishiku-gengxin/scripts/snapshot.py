#!/usr/bin/env python3
"""回注快照 / 回滚（zhishiku-gengxin 用）。

回注是**覆盖式**的写操作：一旦把错误的条目合并进知识容器，靠人工比对是找不回来的。
所以 gengxin 的协议要求**回注前先拍快照**，出问题时按快照回滚。

用法：
    python3 snapshot.py <数据根>/<领域> --take [--note "回注 ctf-pwn/0013"]
    python3 snapshot.py <领域> --list
    python3 snapshot.py <领域> --rollback <快照名> [--yes]
    python3 snapshot.py <领域> --prune [--keep 5]

约定
----
- 快照放在 <领域>/_snap/<YYYYMMDD-HHMMSS>/，内含每个文件的副本 + `MANIFEST.txt`（路径 / 字节数 / sha256）。
- `_snap/` 自身不进快照，也不被 yongfa.py / validate.py 当作知识文件（它们只扫领域根那几层）。
- **回滚前会自动再拍一份** `_snap/<旧名>-preRollback/`，所以回滚本身也是可逆的。
- 回滚会把「当前有、快照里没有」的文件移到 `_snap/<快照名>/_orphan-<时间戳>/`，而不是删掉。

退出码：0 成功 / 1 快照不存在或校验失败 / 2 用法或路径错。
"""
import hashlib
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SNAP_DIR = "_snap"
MANIFEST = "MANIFEST.txt"
KEEP_DEFAULT = 5


# ------------------------------------------------------------------ 工具
def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def domain_files(d: Path):
    """领域内需要快照的文件（跳过 _snap/ 自身）。"""
    for p in sorted(d.rglob("*")):
        if not p.is_file():
            continue
        if p.relative_to(d).parts[0] == SNAP_DIR:
            continue
        yield p


def read_manifest(snap: Path):
    """-> [(rel, size, sha)]"""
    mf = snap / MANIFEST
    out = []
    if not mf.is_file():
        return out
    for line in mf.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        rel, size, sha = parts
        out.append((rel, int(size), sha))
    return out


def dsize(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


# ------------------------------------------------------------------ 动作
def do_take(d: Path, args):
    note = ""
    if "--note" in args:
        note = args[args.index("--note") + 1]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snap = d / SNAP_DIR / stamp
    if snap.exists():
        print(f"快照已存在（同一秒内重复调用？）：{snap}", file=sys.stderr)
        return 2
    snap.mkdir(parents=True)

    rows, total = [], 0
    for f in domain_files(d):
        rel = f.relative_to(d).as_posix()
        dst = snap / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        size = f.stat().st_size
        total += size
        rows.append(f"{rel}\t{size}\t{sha256(f)}")

    header = [
        "# zhishiku 回注快照（gengxin 用；回滚请看 snapshot.py --rollback）",
        f"# 快照名：{stamp}",
        f"# 时间：{datetime.now().isoformat(timespec='seconds')}",
        f"# 文件数：{len(rows)}   总字节：{total}",
        f"# 备注：{note or '-'}",
        "# 路径<TAB>字节数<TAB>sha256",
    ]
    (snap / MANIFEST).write_text("\n".join(header + rows) + "\n",
                                 encoding="utf-8", newline="\n")
    print(f"已拍快照 {stamp}：{len(rows)} 个文件 / {total} 字节")
    if note:
        print(f"  备注：{note}")
    print(f"  路径：{snap}")
    print(f"  回滚：python3 snapshot.py \"{d}\" --rollback {stamp}")
    return 0


def do_list(d: Path):
    base = d / SNAP_DIR
    snaps = sorted([p for p in base.iterdir() if p.is_dir()]) if base.is_dir() else []
    if not snaps:
        print("（无快照）")
        return 0
    print(f"{d.name} 的快照（{len(snaps)} 个）：")
    for s in snaps:
        mf = read_manifest(s)
        note = ""
        mfp = s / MANIFEST
        if mfp.is_file():
            m = re.search(r"^# 备注：(.+)$", mfp.read_text(encoding="utf-8", errors="replace"), re.M)
            if m and m.group(1).strip() != "-":
                note = f"  {m.group(1)}"
        print(f"  {s.name}  文件 {len(mf)}  {dsize(s)} 字节{note}")
    return 0


def do_rollback(d: Path, args, auto_yes=False):
    if "--rollback" not in args:
        return 2
    name = args[args.index("--rollback") + 1]
    snap = d / SNAP_DIR / name
    if not snap.is_dir():
        print(f"快照不存在：{snap}", file=sys.stderr)
        return 1

    rows = read_manifest(snap)
    if not rows:
        print(f"{snap}/{MANIFEST} 缺失或为空，拒绝回滚", file=sys.stderr)
        return 1

    # 先校验快照自身完整（防止拿一个坏快照去覆盖好的现状）
    broken = [rel for rel, size, sha in rows
              if not (snap / rel).is_file() or (snap / rel).stat().st_size != size
              or sha256(snap / rel) != sha]
    if broken:
        print(f"快照自身不完整（{len(broken)} 个文件校验失败），拒绝回滚：", file=sys.stderr)
        for b in broken[:10]:
            print(f"  {b}", file=sys.stderr)
        return 1

    if not auto_yes:
        print(f"即将把 {d.name} 回滚到快照 {name}（{len(rows)} 个文件）。")
        print("回滚前会自动再拍一份 preRollback 快照。确认请加 --yes。")
        return 0

    # 1) 回滚前保护：把现状再拍一份
    pre = d / SNAP_DIR / f"{name}-preRollback"
    if not pre.exists():
        pre.mkdir(parents=True)
        for f in domain_files(d):
            rel = f.relative_to(d).as_posix()
            dst = pre / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
        print(f"已拍回滚前快照：{pre.name}")

    # 2) 恢复快照里的文件
    restored = 0
    for rel, _size, _sha in rows:
        src, dst = snap / rel, d / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.is_file() or sha256(dst) != _sha:
            shutil.copy2(src, dst)
            restored += 1

    # 3) 快照里没有、当前有的文件 → 移到 _orphan（不删）
    keep = {rel for rel, _s, _h in rows}
    orphans = [f.relative_to(d).as_posix() for f in domain_files(d) if f.relative_to(d).as_posix() not in keep]
    if orphans:
        orph = snap / f"_orphan-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        for rel in orphans:
            dst = orph / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(d / rel), str(dst))
        print(f"移出 {len(orphans)} 个快照里没有的文件 → {orph.relative_to(d).as_posix()}/")

    print(f"已回滚到 {name}：恢复/覆盖 {restored} 个，移出 {len(orphans)} 个。")
    print("  （可再回滚到 preRollback 撤销本次操作）")
    return 0


def do_prune(d: Path, args):
    keep = KEEP_DEFAULT
    if "--keep" in args:
        keep = int(args[args.index("--keep") + 1])
    base = d / SNAP_DIR
    if not base.is_dir():
        print("（无快照）")
        return 0
    snaps = sorted(p for p in base.iterdir() if p.is_dir())
    doomed = snaps[:-keep] if keep > 0 else snaps
    for s in doomed:
        shutil.rmtree(s)
        print(f"删除旧快照 {s.name}")
    print(f"保留 {len(snaps) - len(doomed)} 个（上限 {keep}）")
    return 0


# ------------------------------------------------------------------ main
def main():
    args = sys.argv[1:]
    skip = {i + 1 for i, a in enumerate(args) if a in ("--note", "--keep", "--rollback")}
    pos = [a for i, a in enumerate(args) if not a.startswith("--") and i not in skip]
    d = Path(pos[0] if pos else ".").resolve()
    if not d.is_dir():
        print(f"不是目录：{d}", file=sys.stderr)
        return 2

    if "--take" in args:
        return do_take(d, args)
    if "--list" in args:
        return do_list(d)
    if "--rollback" in args:
        return do_rollback(d, args, auto_yes="--yes" in args)
    if "--prune" in args:
        return do_prune(d, args)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
