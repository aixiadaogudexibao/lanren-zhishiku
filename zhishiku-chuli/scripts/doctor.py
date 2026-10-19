#!/usr/bin/env python3
"""zhishiku 全链体检 + 交叉检验

为什么需要：
  一条链的状态分散在 5 个文件里：
    缺口板 chuli/xinxi.txt  →  biao_xin(dai/hui)  →  tilian_wei/suoyin  →  gengxin_wei/*  →  yongfa/shengming
  单看任何一个都说不出「断在哪」，跨会话尤其容易丢链。

本脚本做两件事：
  1. 索引：把各段的状态集中列出来（哪个案例在哪一步）
  2. 交叉检验：找互相矛盾的地方（标了没采、采了没清标、提炼了没回注…）

只读，不写任何文件。

用法：
  python3 doctor.py                      # 全部领域
  python3 doctor.py --domain ctf-pwn     # 单领域
  python3 doctor.py --strict             # 有 ✗ 就返回非零
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta
import os
from pathlib import Path

# 路径解析：环境变量优先，其次 ~ 推导；源码不硬编码用户名
_HOME = Path(os.path.expanduser("~"))
_AGENT = Path(os.environ.get("PI_AGENT_DIR") or (_HOME / ".pi" / "agent"))
KM_ROOT = Path(os.environ.get("ZHISHIKU_ROOT") or (_HOME / ".zhishiku"))
SKILLS_DIR = Path(os.environ.get("PI_SKILLS_DIR") or (_AGENT / "skills"))
RESUME = KM_ROOT / "resume/current.md"
GAPBOARD = SKILLS_DIR / "zhishiku-chuli" / "xinxi.txt"
CAIJI = KM_ROOT / "caiji_wei"
TILIAN = KM_ROOT / "tilian_wei"
GENGXIN = KM_ROOT / "gengxin_wei"

# flag 语义（来自 zhishiku-caiji）
FLAG_MEAN = {0: "待采集", 1: "采集中", 2: "归档中(可恢复)", 4: "已归档", 8: "已交付"}
STALE_DAI_DAYS = 7


# ─────────────────────────── 读盘 ───────────────────────────

def read(p: Path, limit: int = 1 << 20) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def domains() -> list[str]:
    try:
        return sorted(d.name for d in GENGXIN.iterdir() if d.is_dir() and not d.name.startswith(("_", ".")))
    except OSError:
        return []


# ─────────────────────────── 各段状态 ───────────────────────────

def gap_tasks() -> list[dict]:
    """缺口板里 caiji标记=1 且未闭的任务"""
    raw = read(GAPBOARD, 1 << 18)
    out = []
    for block in re.split(r"^-{3,}$", raw, flags=re.M):
        if not re.search(r"^任务[：:]", block, re.M):
            continue
        g = lambda k: (re.search(rf"^{k}[：:]\s*(.*)$", block, re.M) or [None, ""])[1].strip()
        status, mark = g("状态"), g("采集标记")
        if re.search(r"已采清|^闭$|暂定", status) or mark != "1":
            continue
        out.append({"domain": g("领域"), "task": g("任务"), "status": status,
                    "summary": g("标记摘要"), "path": g("原路径")})
    return out


def paused_keys() -> set[tuple[str, str]]:
    """暂定任务的 (领域, 标识) 集合；标识匹配任务名里的案例号或题名片段"""
    out = set()
    for t in paused_tasks():
        out.add((t["domain"], t["task"]))
    return out


def is_paused_case(domain: str, cid: str) -> bool:
    for d, task in paused_keys():
        if d != domain:
            continue
        if cid in task:
            return True
    return False


def paused_tasks() -> list[dict]:
    """缺口板里 状态=暂定 的任务：每次扫描都必须报给用户"""
    raw = read(GAPBOARD, 1 << 18)
    out = []
    for block in re.split(r"^-{3,}$", raw, flags=re.M):
        if not re.search(r"^任务[：:]", block, re.M):
            continue
        g = lambda k: (re.search(rf"^{k}[：:]\s*(.*)$", block, re.M) or [None, ""])[1].strip()
        if g("状态") != "暂定":
            continue
        out.append({
            "domain": g("领域"), "task": g("任务"),
            "note": g("备注"), "updated": g("更新"),
        })
    return out


def all_gap_tasks() -> list[dict]:
    """缺口板全部任务节（含已闭，用于与续跑条/磁盘交叉校验）"""
    raw = read(GAPBOARD, 1 << 18)
    out = []
    for block in re.split(r"^-{3,}$", raw, flags=re.M):
        if not re.search(r"^任务[：:]", block, re.M):
            continue
        g = lambda k: (re.search(rf"^{k}[：:]\s*(.*)$", block, re.M) or [None, ""])[1].strip()
        out.append({
            "task": g("任务"), "domain": g("领域"), "path": g("原路径"),
            "status": g("状态"), "mark": g("caiji标记") or g("采集标记"),
            "updated": g("更新"), "note": g("备注"),
        })
    return out


def deliverables_ok(path_str: str) -> tuple[bool, str]:
    """pwn/CTF 交付物：exp* 与 wp* 至少各一个"""
    if not path_str or path_str in ("-", "未知"):
        return True, "无路径"
    p = Path(path_str)
    d = p if p.is_dir() else p.parent
    if not d.is_dir():
        return False, f"目录不存在：{d}"
    # 递归两层找：原题目录常把 exp 放在 PWN附件/ 之类的子目录
    def _find(pred, depth: int = 2) -> bool:
        if depth < 0:
            return False
        try:
            for f in d.iterdir():
                if f.is_file() and pred(f):
                    return True
                if f.is_dir() and not f.name.startswith(".") and _find_in(f, pred, depth - 1):
                    return True
        except OSError:
            return False
        return False

    def _find_in(nd, pred, depth: int) -> bool:
        try:
            for f in nd.iterdir():
                if f.is_file() and pred(f):
                    return True
                if f.is_dir() and not f.name.startswith(".") and depth > 0 and _find_in(f, pred, depth - 1):
                    return True
        except OSError:
            return False
        return False

    has_exp = _find(lambda f: f.name.startswith("exp") and f.suffix == ".py")
    has_wp = _find(lambda f: f.name in ("wp_agent.md", "wp.md"))
    if has_exp and has_wp:
        return True, "exp+wp"
    miss = []
    if not has_exp:
        miss.append("exp")
    if not has_wp:
        miss.append("wp")
    return False, f"缺 {'/'.join(miss)}"


def biao(domain: str) -> dict:
    """解析 biao_xin.txt → {'dai':[(id,flag)], 'hui':[(id,flag)]}"""
    raw = read(CAIJI / domain / "biao_xin.txt")
    res = {"dai": [], "hui": []}
    cur = None
    for line in raw.splitlines():
        t = line.strip()
        if t in ("[dai]", "[hui]"):
            cur = t[1:-1]
            continue
        if not cur or not t or t.startswith("#"):
            continue
        parts = [x.strip() for x in t.split("|")]
        if len(parts) >= 3 and parts[1].isdigit():
            res[cur].append((parts[1], int(parts[2]) if parts[2].isdigit() else -1))
    return res


def tilian_ids(domain: str) -> set[str]:
    raw = read(TILIAN / domain / "suoyin.txt")
    return set(re.findall(r"^(\d{4})\s*\|", raw, re.M))


def tilian_no_output(domain: str) -> set[str]:
    """suoyin 里登记为「压测/无新产出」的案例：有登记即合法，不要求回注"""
    raw = read(TILIAN / domain / "suoyin.txt")
    out = set()
    for m in re.finditer(r"^(\d{4})\s*\|([^|]*)\|", raw, re.M):
        if re.search(r"压测|无新产出|无需新建卡|无需产出", m.group(2)):
            out.add(m.group(1))
    return out


def gengxin_cases(domain: str) -> set[str]:
    """gengxin 里出现过的案例号（来自条目的「来源」行）"""
    root = GENGXIN / domain
    ids: set[str] = set()
    if not root.is_dir():
        return ids
    for p in root.rglob("*.txt"):
        if "_snap" in p.parts:
            continue
        for m in re.finditer(rf"{re.escape(domain)}/(\d{{4}})", read(p, 1 << 16)):
            ids.add(m.group(1))
    return ids


def dai_age(domain: str, cid: str) -> int | None:
    p = CAIJI / domain / "biao/dai" / cid
    try:
        return (datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)).days
    except OSError:
        return None


def resume_state() -> dict:
    raw = read(RESUME, 8192)
    g = lambda k: (re.search(rf"^{k}[：:]\s*(.+)$", raw, re.M) or [None, ""])[1].strip()
    return {
        "领域": g("领域"), "阶段": g("阶段"), "题目": g("题目"),
        "采集标记": g("采集标记"), "版本": g("版本"), "写者": g("写者")[:8],
        "心跳": g("心跳"), "下次动作": g("下次动作"),
    }


# ─────────────────────────── 渲染 ───────────────────────────

OK, WARN, BAD = "✓", "⚠", "✗"


def section(title: str) -> None:
    print()
    print(f"## {title}")


def main() -> int:
    ap = argparse.ArgumentParser(description="zhishiku 全链体检")
    ap.add_argument("--domain")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    ds = [args.domain] if args.domain else domains()
    if not ds:
        print("未找到领域", file=sys.stderr)
        return 1

    problems: list[str] = []
    warns: list[str] = []

    # ── 1. 续跑条 ──
    r = resume_state()
    section("续跑条")
    if not r["阶段"]:
        print(f"{WARN} 无续跑条")
        warns.append("无续跑条")
    else:
        hb = r["心跳"]
        stale = False
        if hb:
            m = re.match(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})", hb)
            if m:
                t = datetime(*map(int, m.groups()))
                mins = int((datetime.now() - t).total_seconds() // 60)
                stale = mins > 30
        tag = f"{WARN} 心跳 {hb}（已 {mins} 分钟）" if stale else f"{OK} 心跳 {hb}"
        print(f"{tag}")
        print(f"  v{r['版本'] or '?'} · 写者 {r['写者'] or '-'} · 阶段 {r['阶段']} · {r['题目'] or '-'}")
        print(f"  下次动作：{r['下次动作'] or '-'}")
        if stale:
            warns.append(f"续跑条心跳过期（{mins} 分钟）")

    # ── 2. 缺口板 ──
    section("缺口板（caiji标记=1 未闭）")
    gaps = gap_tasks()
    if not gaps:
        print(f"{OK} 无未闭缺口")
    for g in gaps:
        dom = g["domain"] or "?"
        if args.domain and dom != args.domain:
            continue
        print(f"{WARN} [{dom}] {g['task']} — {g['status']}")
        if g["summary"] not in ("", "-"):
            print(f"    摘要：{g['summary']}")

    # ── 2.5 暂定任务（MUST 每次点名）──
    section("暂定任务（挂起，不问不动；此处只点名）")
    paused = paused_tasks()
    if args.domain:
        paused = [t for t in paused if t["domain"] == args.domain]
    if not paused:
        print(f"{OK} 无暂定任务")
    else:
        for t in paused:
            age = ""
            if t["updated"]:
                m = re.match(r"(\d{4})-(\d{2})-(\d{2})", t["updated"])
                if m:
                    try:
                        days = (datetime.now() - datetime(*map(int, m.groups()))).days
                        age = f"，已挂 {days} 天"
                    except ValueError:
                        pass
            print(f"{WARN} [{t['domain'] or '?'}] {t['task'] or '?'}{age}")
            if t["note"]:
                print(f"    恢复点：{t['note']}")
        print(f"  → 共 {len(paused)} 项暂定；需用户提及才处理，不自动开工")
        warns.append(f"暂定任务 {len(paused)} 项（需用户提及才处理）")

    # ── 2.6 缺口板 ↔ 续跑条 ↔ 磁盘 交叉校验 ──
    section("缺口板交叉校验")
    tasks = all_gap_tasks()
    if args.domain:
        tasks = [t for t in tasks if t["domain"] == args.domain]
    r_stage = r.get("阶段", "")
    r_title = r.get("题目", "")
    xcheck: list[str] = []

    for t in tasks:
        # a) 状态「进行中」但续跑条已闭，且题目对得上 → 不一致
        if t["status"] == "进行中" and r_stage in ("闭", "C5"):
            if t["task"] and (t["task"][:9] in r_title or r_title[:9] in t["task"]):
                xcheck.append(f"[{t['domain']}] 「{t['task']}」标进行中，但续跑条已是 {r_stage}")
        # b) 状态未闭但交付物齐全 → 可能忘了关节
        if t["status"] in ("进行中", "已交付待采"):
            ok, why = deliverables_ok(t["path"])
            if ok and why == "exp+wp":
                xcheck.append(f"[{t['domain']}] 「{t['task']}」交付物已齐全({why})，状态仍是「{t['status']}」")
        # c) pwn/CTF 已闭但交付物不全
        if t["status"] in ("闭", "已采清") and re.search(r"pwn|ctf", t["domain"] or ""):
            ok, why = deliverables_ok(t["path"])
            if not ok:
                xcheck.append(f"[{t['domain']}] 「{t['task']}」已闭但交付物不全（{why}）")

    if xcheck:
        print(f"{BAD} 发现 {len(xcheck)} 处不一致：")
        for c in xcheck:
            print(f"  - {c}")
        problems.extend(c)
    else:
        print(f"{OK} 缺口板与磁盘一致")

    # ── 3. 各领域案例索引 ──
    for dom in ds:
        if not (CAIJI / dom / "biao_xin.txt").exists():
            continue
        section(f"{dom} · 案例索引")
        b = biao(dom)
        til = tilian_ids(dom)
        til_no = tilian_no_output(dom)
        gen = gengxin_cases(dom)

        # biao_xin ↔ biao/{dai,hui} 目录一致性
        for sect in ("dai", "hui"):
            listed = {c for c, _ in b[sect]}
            dpath = CAIJI / dom / "biao" / sect
            on_disk = {x.name for x in dpath.iterdir() if x.is_dir()} if dpath.is_dir() else set()
            if listed - on_disk:
                c = f"biao_xin [{sect}] 有 {sorted(listed - on_disk)} 但目录不存在"
                print(f"  {BAD} {c}")
                problems.append(f"[{dom}] {c}")
            if on_disk - listed:
                c = f"biao/{sect}/ 有 {sorted(on_disk - listed)} 但 biao_xin 未登记"
                print(f"  {BAD} {c}")
                problems.append(f"[{dom}] {c}")

        if b["dai"]:
            for cid, flag in b["dai"]:
                age = dai_age(dom, cid)
                why = FLAG_MEAN.get(flag, f"flag={flag}")
                paused_case = is_paused_case(dom, cid)
                stale = age is not None and age >= STALE_DAI_DAYS and not paused_case
                tag = WARN if stale else OK
                age_s = f"滞留 {age} 天" if age is not None else "目录缺失"
                if paused_case:
                    age_s += "（暂定，不催）"
                print(f"{tag} dai/{cid} flag={flag}({why}) {age_s}")
                if stale:
                    warns.append(f"[{dom}] 案例 {cid} 在 dai 滞留 {age} 天（{why}）")
                if flag == 2:
                    problems.append(f"[{dom}] 案例 {cid} flag=2 崩溃恢复标记未完成归档")
                if age is None:
                    problems.append(f"[{dom}] 案例 {cid} 在 biao_xin 但 biao/dai/{cid} 目录不存在")

        done = [c for c, _ in b["hui"]]
        print(f"  hui：{len(done)} 个，最近 {', '.join(done[-5:]) if done else '-'}")

        # ── 交叉检验 ──
        checks = []
        for cid, flag in b["dai"]:
            if flag == 4:
                checks.append(f"案例 {cid} 在 [dai] 但 flag=4（已归档）")

        gap_ids = {g["task"] for g in gaps if g["domain"] == dom}
        for cid, _ in b["dai"]:
            pass

        all_hui = set(done)
        for cid in sorted(all_hui):
            if cid not in til:
                checks.append(f"案例 {cid} 已归档(hui) 但 tilian 无对应稿")
            elif cid not in gen and cid not in til_no:
                checks.append(f"案例 {cid} tilian 有稿但 gengxin 未见回注")

        for cid in sorted(til - all_hui):
            checks.append(f"tilian 有案例 {cid} 但 caiji 未归档（不在 hui）")

        for cid in sorted(gen - all_hui):
            if cid.isdigit():
                checks.append(f"gengxin 引用了 caiji 未归档的案例 {cid}")

        # 链条矩阵：一眼看清每个案例走到哪一段
        all_ids = sorted({c for c, _ in b["dai"]} | all_hui | til | gen)
        if all_ids:
            print("  链条：案例 caiji  tilian  gengxin")
            for cid in all_ids[-8:]:
                in_hui = cid in all_hui
                in_dai = any(c == cid for c, _ in b["dai"])
                mark = lambda ok: "  ✓   " if ok else "  ·   "
                row = (
                    f"  {cid}  "
                    + ("dai  " if in_dai else ("hui  " if in_hui else "—    "))
                    + mark(cid in til)
                    + mark(cid in gen or cid in til_no)
                )
                print(row)

        if checks:
            print(f"  {BAD} 交叉检验：")
            for c in checks:
                print(f"    - {c}")
            problems.extend(f"[{dom}] {c}" for c in checks)
        else:
            print(f"  {OK} 交叉检验通过")

    # ── 4. 汇总 ──
    section("汇总")
    if not problems and not warns:
        print(f"{OK} 全链一致，无异常")
        return 0
    if problems:
        print(f"{BAD} 必须处理 {len(problems)} 项：")
        for p in problems:
            print(f"  - {p}")
    if warns:
        print(f"{WARN} 需留意 {len(warns)} 项：")
        for w in warns:
            print(f"  - {w}")
    return 2 if (args.strict and problems) else 0


if __name__ == "__main__":
    sys.exit(main())
