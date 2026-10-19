#!/usr/bin/env python3
"""续跑条并发写：单文件 + 版本号 + 写者 + 心跳

为什么需要：
  多个 pi 窗口会同时改 resume/current.md。原来的「整文件覆盖」会让后写的
  把先写的合法推进抹掉（例如 A 窗口推进到 C3，B 窗口按自己的旧印象写回 C2）。

本脚本的三条规则：
  1. 原子写：写临时文件再 os.replace，避免读到半截文件
  2. 版本校验：写前比对版本号，变了就拒写并报冲突（不猜、不自动合并）
  3. 分区职责：owner 写正文；巡检只改单行或往「巡检记录」追加

用法：
  # 看当前状态（含写者、心跳、是否过期）
  python3 resume_lock.py show

  # 认领/更新正文（版本自动 +1）
  python3 resume_lock.py commit --writer <id> --field 阶段=C3 --field 下次动作=...

  # 只改某几行（不整文件覆盖，不递增版本）
  python3 resume_lock.py patch --field 原路径=/xxx/bin

  # 往巡检记录追加（永不覆盖正文）
  python3 resume_lock.py note --writer <id> "原路径少写 bin/ 层级，已修正"

  # 巡检发现 owner 心跳过期，接管
  python3 resume_lock.py takeover --writer <id> [--force]
"""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
import os
from pathlib import Path

# 路径解析：环境变量优先，其次 ~ 推导；源码不硬编码用户名
_HOME = Path(os.path.expanduser("~"))
_AGENT = Path(os.environ.get("PI_AGENT_DIR") or (_HOME / ".pi" / "agent"))
KM_ROOT = Path(os.environ.get("ZHISHIKU_ROOT") or (_HOME / ".zhishiku"))
SKILLS_DIR = Path(os.environ.get("PI_SKILLS_DIR") or (_AGENT / "skills"))
RESUME = KM_ROOT / "resume/current.md"
DONE = KM_ROOT / "resume/done"
LOCK = KM_ROOT / "resume/.current.lock"

# 正文必填字段（顺序即渲染顺序）
BODY_FIELDS = [
    "领域", "阶段", "题目", "原路径", "采集标记", "标记摘要",
    "caiji", "tilian", "gengxin", "用户已交付", "阻塞", "下次动作", "更新",
]
# 头部元字段
META_FIELDS = ["版本", "写者", "心跳"]
NOTE_HEADER = "## 巡检记录"
HEARTBEAT_TIMEOUT_MIN = 30


# ─────────────────────────── 读写 ───────────────────────────

class LockedFile:
    """flock 独占，防止同一时刻两个窗口写坏文件"""

    def __enter__(self):
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(LOCK, "w")
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        try:
            fcntl.flock(self.fh, fcntl.LOCK_UN)
        finally:
            self.fh.close()
        return False


def parse(text: str) -> dict:
    """解析成 {meta:{}, body:{}, notes:[], extra:[]}"""
    meta: dict[str, str] = {}
    body: dict[str, str] = {}
    notes: list[str] = []
    extra: list[str] = []

    in_notes = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip() == NOTE_HEADER:
            in_notes = True
            continue
        if in_notes:
            if line.strip():
                notes.append(line)
            continue
        m = re.match(r"^([^：:]{1,12})[：:]\s*(.*)$", line)
        if not m:
            if line.strip():
                extra.append(line)
            continue
        k, v = m.group(1).strip(), m.group(2).strip()
        if k in META_FIELDS:
            meta[k] = v
        elif k in BODY_FIELDS:
            body[k] = v
        else:
            extra.append(line)
    return {"meta": meta, "body": body, "notes": notes, "extra": extra}


def render(state: dict) -> str:
    meta, body, notes = state["meta"], state["body"], state["notes"]
    out: list[str] = []
    # 元信息在最前，用 --- 与正文隔开
    for k in META_FIELDS:
        if k in meta:
            out.append(f"{k}：{meta[k]}")
    if any(k in meta for k in META_FIELDS):
        out.append("---")
    for k in BODY_FIELDS:
        if k in body:
            out.append(f"{k}：{body[k]}")
    for line in state["extra"]:
        # 过滤历史残留的孤立分隔符与空行，避免每次 render 叠加
        if line.strip() in ("---", ""):
            continue
        out.append(line)
    if notes:
        out.append("")
        out.append(NOTE_HEADER)
        out.extend(notes)
    return "\n".join(out) + "\n"


def read_state() -> dict:
    if not RESUME.exists():
        return {"meta": {}, "body": {}, "notes": [], "extra": []}
    return parse(RESUME.read_text(encoding="utf-8"))


def atomic_write(text: str) -> None:
    """同目录临时文件 + os.replace，保证读者永远看到完整内容"""
    RESUME.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(RESUME.parent), prefix=".current.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, RESUME)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ─────────────────────────── 辅助 ───────────────────────────

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def short_id(writer: str) -> str:
    return (writer or "unknown")[:8]


LEGACY_MARKERS = ("legacy", "unknown", "migrated")


def is_legacy(writer: str) -> bool:
    """迁移/占位写者不算真 owner，可被第一个真实窗口直接接管"""
    w = (writer or "").strip().lower()
    return (not w) or any(w.startswith(m) for m in LEGACY_MARKERS)


def heartbeat_expired(state: dict) -> tuple[bool, str]:
    hb = state["meta"].get("心跳", "")
    if not hb:
        return True, "无心跳字段"
    try:
        t = datetime.strptime(hb.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return True, f"心跳格式异常：{hb}"
    age = datetime.now() - t
    if age > timedelta(minutes=HEARTBEAT_TIMEOUT_MIN):
        mins = int(age.total_seconds() // 60)
        return True, f"心跳已 {mins} 分钟未更新（阈值 {HEARTBEAT_TIMEOUT_MIN}）"
    return False, f"心跳正常（{int(age.total_seconds() // 60)} 分钟前）"


def diff_body(st: dict, incoming: dict[str, str]) -> list[str]:
    """列出将被改动的字段（磁盘值 → 新值），冲突时给用户看差异"""
    out = []
    for k, v in incoming.items():
        old = st["body"].get(k, "")
        if old == v:
            continue
        out.append(f"  {k}: {old!r} → {v!r}")
    return out


def print_conflict(st: dict, incoming: dict[str, str], me: str) -> None:
    """3B：冲突时把双方内容摆出来，而不是只报一句拒绝"""
    owner = (st["meta"].get("写者") or "")[:8] or "无"
    expired, why = heartbeat_expired(st)
    print("", file=sys.stderr)
    print("=" * 56, file=sys.stderr)
    print(f"冲突：磁盘状态 vs 你的写入", file=sys.stderr)
    print("=" * 56, file=sys.stderr)
    print(f"磁盘  版本 {st['meta'].get('版本','?')} · 写者 {owner} · {why}", file=sys.stderr)
    print(f"你是  窗口 {me}", file=sys.stderr)
    print("", file=sys.stderr)
    print("磁盘当前：", file=sys.stderr)
    for k in ("阶段", "题目", "下次动作"):
        if k in st["body"]:
            print(f"  {k}: {st['body'][k]!r}", file=sys.stderr)
    print("", file=sys.stderr)
    changes = diff_body(st, incoming)
    if changes:
        print("你的改动：", file=sys.stderr)
        for c in changes:
            print(c, file=sys.stderr)
    else:
        print("你的改动：无实际差异", file=sys.stderr)
    print("", file=sys.stderr)
    print("下一步：", file=sys.stderr)
    print("  1) 先 `show` 看清对方做到哪", file=sys.stderr)
    print("  2) 若只是纠错 → 用 `patch`（不夺权）", file=sys.stderr)
    print("  3) 若确要接手 → `takeover`（心跳过期）或加 --force", file=sys.stderr)
    print("=" * 56, file=sys.stderr)


KEEP_BACKUPS = 20  # 每类备份只留最近 N 份


def backup_current(tag: str) -> Path | None:
    """写前备份。同 tag 只保留最近 KEEP_BACKUPS 份，防 done/ 无限膨胀。"""
    if not RESUME.exists():
        return None
    DONE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = DONE / f"{stamp}-{tag}.md"
    shutil.copy2(RESUME, dest)
    # 轮转：文件名形如 YYYYMMDD-HHMMSS-<tag>.md，同类按时间序保留最近的
    try:
        same = sorted(p for p in DONE.glob(f"*-{tag}.md"))
        for old_p in same[: max(0, len(same) - KEEP_BACKUPS)]:
            try:
                old_p.unlink()
            except OSError:
                pass
    except OSError:
        pass
    return dest


# ─────────────────────────── 命令 ───────────────────────────

def cmd_show(_args) -> int:
    st = read_state()
    if not st["body"]:
        print("（无续跑条）")
        return 0
    expired, why = heartbeat_expired(st)
    print("## 续跑条")
    print()
    print(f"版本：{st['meta'].get('版本', '?')}   写者：{short_id(st['meta'].get('写者', ''))}")
    print(f"心跳：{st['meta'].get('心跳', '-')}   {'⚠ 过期' if expired else '✓'} {why}")
    print()
    for k in BODY_FIELDS:
        if k in st["body"]:
            print(f"{k}：{st['body'][k]}")
    if st["notes"]:
        print()
        print(NOTE_HEADER)
        for n in st["notes"]:
            print(n)
    return 0


def cmd_commit(args) -> int:
    """owner 推进阶段：版本 +1，写者=自己"""
    with LockedFile():
        st = read_state()
        cur_ver = int(st["meta"].get("版本", "0") or 0)

        incoming = {}
        for spec in args.field or []:
            if "=" in spec:
                k, v = spec.split("=", 1)
                incoming[k.strip()] = v.strip()

        # 版本校验：调用方若给了 --expect-version，必须匹配
        if args.expect_version is not None and args.expect_version != cur_ver:
            print(f"[冲突] 版本不符：磁盘 {cur_ver}，你期望 {args.expect_version}", file=sys.stderr)
            print_conflict(st, incoming, short_id(args.writer))
            return 2

        # 写者校验：不同窗口不能悄悄接管
        owner = st["meta"].get("写者", "")
        if owner and not is_legacy(owner) and short_id(owner) != short_id(args.writer):
            expired, why = heartbeat_expired(st)
            if not expired and not args.force:
                print_conflict(st, incoming, short_id(args.writer))
                return 3
            if expired:
                st["notes"].append(f"- {now_str()} [{short_id(args.writer)}] 接管自 {short_id(owner)}（{why}）")

        backup_current(f"commit-{short_id(args.writer)}")

        for k, v in incoming.items():
            st["body"][k] = v

        st["meta"]["版本"] = str(cur_ver + 1)
        st["meta"]["写者"] = args.writer
        st["meta"]["心跳"] = now_str()
        st["body"]["更新"] = now_str()

        atomic_write(render(st))
        print(f"✓ 已写 版本 {cur_ver} → {cur_ver + 1}，写者 {short_id(args.writer)}")
        return 0


def cmd_patch(args) -> int:
    """只改指定行，不递增版本，不夺 owner（巡检纠错用）"""
    with LockedFile():
        st = read_state()
        changed = []
        for spec in args.field or []:
            if "=" not in spec:
                print(f"[错误] --field 需要 k=v：{spec}", file=sys.stderr)
                return 1
            k, v = spec.split("=", 1)
            k, v = k.strip(), v.strip()
            if k not in BODY_FIELDS:
                print(f"[错误] 未知字段：{k}", file=sys.stderr)
                return 1
            old = st["body"].get(k, "")
            if old == v:
                continue
            st["body"][k] = v
            changed.append(f"{k}: {old!r} → {v!r}")

        if not changed:
            print("（无变化）")
            return 0

        backup_current("patch")
        # 巡检只动单行，不改版本/写者，但记录一笔
        st["notes"].append(f"- {now_str()} [{short_id(args.writer)}] 修正 " + "；".join(changed))
        atomic_write(render(st))
        print("✓ 已修正：")
        for c in changed:
            print(f"  {c}")
        print("（版本不变，owner 未变，已记入巡检记录）")
        return 0


def cmd_note(args) -> int:
    with LockedFile():
        st = read_state()
        st["notes"].append(f"- {now_str()} [{short_id(args.writer)}] {args.text}")
        atomic_write(render(st))
        print("✓ 已追加巡检记录")
        return 0


def cmd_takeover(args) -> int:
    with LockedFile():
        st = read_state()
        owner = st["meta"].get("写者", "")
        if owner and short_id(owner) == short_id(args.writer):
            print("本来就是你的")
            return 0
        expired, why = heartbeat_expired(st)
        if not is_legacy(owner) and not expired and not args.force:
            print(f"[拒绝] {short_id(owner)} {why}；如确需接管加 --force", file=sys.stderr)
            return 3

        backup_current("takeover")
        st["notes"].append(f"- {now_str()} [{short_id(args.writer)}] 接管自 {short_id(owner) or '无'}（{why}）")
        st["meta"]["写者"] = args.writer
        st["meta"]["心跳"] = now_str()
        atomic_write(render(st))
        print(f"✓ 接管完成，写者 → {short_id(args.writer)}")
        return 0


def cmd_beat(args) -> int:
    """只刷新心跳"""
    with LockedFile():
        st = read_state()
        owner = st["meta"].get("写者", "")
        if owner and not is_legacy(owner) and short_id(owner) != short_id(args.writer):
            print(f"[拒绝] 该链属于 {short_id(owner)}", file=sys.stderr)
            return 3
        st["meta"]["写者"] = args.writer
        st["meta"]["心跳"] = now_str()
        atomic_write(render(st))
        print(f"✓ 心跳 → {now_str()}")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="续跑条并发写")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("show", help="显示状态")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("commit", help="推进正文（版本 +1）")
    p.add_argument("--writer", required=True)
    p.add_argument("--field", action="append")
    p.add_argument("--expect-version", type=int)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_commit)

    p = sub.add_parser("patch", help="改单行（版本不变）")
    p.add_argument("--writer", required=True)
    p.add_argument("--field", action="append", required=True)
    p.set_defaults(fn=cmd_patch)

    p = sub.add_parser("note", help="追加巡检记录")
    p.add_argument("--writer", required=True)
    p.add_argument("text")
    p.set_defaults(fn=cmd_note)

    p = sub.add_parser("takeover", help="接管")
    p.add_argument("--writer", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_takeover)

    p = sub.add_parser("beat", help="只刷心跳")
    p.add_argument("--writer", required=True)
    p.set_defaults(fn=cmd_beat)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
