#!/usr/bin/env python3
"""实战使用 + 生命周期（yongfa.txt / shengming.txt）—— zhishiku-gengxin 用。

两个数据文件（都在 <数据根>/<领域>/ 下）：

    yongfa.txt      实战使用日志，append-only，末尾 ★ 哨兵。由本脚本追加。
    shengming.txt   生命周期表，**维护型**（非 append-only），可从 yongfa.txt 重建。

用法
----
    # 1) 只读报告（默认）
    python3 yongfa.py <数据根>/<领域> [--all]

    # 2) 推进一个轮次 —— chuli 每处理完一个任务调一次
    python3 yongfa.py <领域> --tick --date 2026-09-27 [--case ctf-pwn/0013] \
                        [--used KEY=结果[:备注],...] [--life 3]

    # 3) 用户裁决（生命周期归零、已询问用户之后）
    python3 yongfa.py <领域> --refresh KEY[,KEY...]   # 用户不同意 → 生命周期刷新回满值
    python3 yongfa.py <领域> --expire  KEY[,KEY...]   # 用户同意   → 状态置「已裁决:过期」

生命周期规则
------------
- 每个知识条目的生命周期是**倒计时**，满值 L（默认 3）。
- 单位是「轮次」：chuli 处理完一个任务 = 一轮。
- 本轮用到的键 → 生命周期 = L；本轮没用的键 → 生命周期 -1。
- 库里存在但表里没有的键（新建 / 首次见到）→ 初始化为 L。
- 生命周期降到 0 → 状态「待裁决」→ **必须询问用户**，绝不自动删。
  - 用户同意已无用 → `--expire`，状态「已裁决:过期」；由 gengxin 下次回注时在条目里落 `[候选过期]`。
  - 用户不同意 → `--refresh`，生命周期刷新回 L，继续观察。

退出码：0 正常 / 1 非法行或悬空引用 / 2 用法或路径错。
"""
import re
import sys
from datetime import date as _date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RESULTS = {"成": 1, "败": 2}          # 结果只有两态
ST_ACTIVE = "活跃"
ST_JUDGE = "待裁决"
ST_EXPIRED = "已裁决:过期"
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}$")
DEF_LIFE = 3
ZERO_LIMIT = 40
JUDGE_LIMIT = 20


# ---------------------------------------------------------------- 读取工具
def txt(p: Path) -> str:
    """读文本（换行已归一，适合解析/校验）。"""
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def read_raw(p: Path) -> str:
    """读文本且**保留原行尾**（Path.read_text 会把 CRLF 归一成 LF，
    用它读再写回，会把 CRLF 的 yongfa.txt 静默改成 LF）。"""
    return p.read_bytes().decode("utf-8", errors="replace") if p.exists() else ""


# 哨兵行：必须容忍 CRLF——`^★[ \t]*$` 在 re.M 下匹配不了 `★\r`，
# 会让 CRLF 的 yongfa.txt 完全无法追加。
SENTINEL_RE = re.compile(r"^★[ \t]*\r?$", re.M)


def parse_log(path: Path):
    """yongfa.txt -> (used, bad)；used[key] = [用, 成, 败]。"""
    used, bad = {}, []
    for n, line in enumerate(txt(path).splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#") or s == "★":
            continue
        f = [x.strip() for x in s.split("|")]
        if len(f) != 5:
            bad.append((n, s, f"字段数={len(f)}（应为 5）"))
            continue
        d, key, res, _cid, _note = f
        if not DATE_RE.match(d):
            bad.append((n, s, f"日期不合法: {d!r}"))
            continue
        if res not in RESULTS:
            bad.append((n, s, f"结果不合法: {res!r}（只能是 成/败）"))
            continue
        if not key:
            bad.append((n, s, "键为空"))
            continue
        c = used.setdefault(key, [0, 0, 0])
        c[0] += 1
        c[RESULTS[res]] += 1
    return used, bad


def lib_keys(d: Path):
    """库里现存、可被实战引用的键。"""
    keys = set()
    lb = d / "liucheng_biao"
    if lb.is_dir():
        for f in sorted(lb.glob("*.txt")):
            if not f.name.startswith("00_"):
                keys.add(f"liucheng_biao/{f.stem}")
    tb = d / "tools"
    if tb.is_dir():
        for f in sorted(tb.glob("*.txt")):
            keys.add(f"tools/{f.stem}")
    for m in re.findall(r"^##\s+(\S.*?)\s*$", txt(d / "cuowu.txt"), re.M):
        keys.add(f"cuowu/{m}")
    for line in txt(d / "zhiling.txt").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        op = s.split("|")[0].strip()
        if op:
            keys.add(f"zhiling/{op}")
    return keys


def read_shengming(d: Path):
    """-> (meta, rows)；rows[key] = [生命周期(int), 最后使用, 状态]。"""
    meta = {"轮次": 0, "满值": DEF_LIFE}
    rows = {}
    p = d / "shengming.txt"
    for line in txt(p).splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            m = re.match(r"#\s*(轮次|满值)\s*[:：]\s*(\d+)", s)
            if m:
                meta[m.group(1)] = int(m.group(2))
            continue
        f = [x.strip() for x in s.split("|")]
        if len(f) != 4:
            continue
        key, life, last, st = f
        try:
            rows[key] = [int(life), last, st]
        except ValueError:
            continue
    return meta, rows


def write_shengming(d: Path, meta, rows):
    head = [
        "# 生命周期表（**维护型**，非 append-only；可从 yongfa.txt 重建）",
        f"# 轮次：{meta['轮次']}",
        f"# 满值：{meta['满值']}",
        "# 键 | 生命周期 | 最后使用 | 状态",
    ]
    body = [
        f"{k} | {v[0]} | {v[1]} | {v[2]}"
        for k, v in sorted(rows.items())
    ]
    (d / "shengming.txt").write_text(
        "\n".join(head + body) + "\n", encoding="utf-8", newline="\n"
    )


def append_log(d: Path, lines):
    """向 yongfa.txt 的 ★ 哨兵处追加；不读全文（只做一次替换）。"""
    p = d / "yongfa.txt"
    t = read_raw(p)
    nl = "\r\n" if "\r\n" in t else "\n"
    cnt = len(SENTINEL_RE.findall(t))
    if cnt != 1:
        print(f"[错误] {p} 的 ★ 哨兵数={cnt}（应为 1），先修复再追加", file=sys.stderr)
        return False
    if not lines:
        return True
    block = nl.join(lines)
    t = SENTINEL_RE.sub(lambda m: block + nl + m.group(0), t, count=1)
    p.write_text(t, encoding="utf-8", newline="")
    return True


def parse_used(specs):
    """['K=成', 'K=败:原因'] -> [(k, 结果, 备注)]"""
    out = []
    for raw in specs:
        for item in raw.split(","):
            item = item.strip()
            if not item:
                continue
            if "=" not in item:
                return None, f"--used 项缺 '='：{item!r}"
            k, rest = item.split("=", 1)
            if ":" in rest:
                res, note = rest.split(":", 1)
            else:
                res, note = rest, "-"
            k, res, note = k.strip(), res.strip(), note.strip()
            if res not in RESULTS:
                return None, f"结果不合法：{res!r}（只能是 成/败）"
            if "|" in k or "|" in note:
                return None, "键或备注里不得含 '|'"
            out.append((k, res, note or "-"))
    return out, None


# ---------------------------------------------------------------- 动作
def do_tick(d: Path, args):
    if "--date" not in args:
        print("--tick 需要 --date YYYY-MM-DD", file=sys.stderr)
        return 2
    dt = args[args.index("--date") + 1]
    if not DATE_RE.match(dt):
        print(f"日期格式应为 YYYY-MM-DD：{dt!r}", file=sys.stderr)
        return 2
    case = args[args.index("--case") + 1] if "--case" in args else "-"

    used_specs = [args[i + 1] for i, a in enumerate(args) if a == "--used"]
    used, err = parse_used(used_specs)
    if err:
        print(err, file=sys.stderr)
        return 2
    used = used or []
    used_keys = {k for k, _r, _n in used}

    meta, rows = read_shengming(d)
    if "--life" in args:
        meta["满值"] = int(args[args.index("--life") + 1])
    L = meta["满值"]
    meta["轮次"] += 1

    # 1) 追加使用行
    lines = [f"{dt} | {k} | {r} | {case} | {n}" for k, r, n in used]
    if lines and not append_log(d, lines):
        return 2

    # 2) 应用生命周期
    keys = lib_keys(d) | set(rows) | used_keys
    just_zero = []
    for k in sorted(keys):
        if k in used_keys:
            rows[k] = [L, dt, ST_ACTIVE]
            continue
        if k not in rows:
            rows[k] = [L, "-", ST_ACTIVE]        # 新建 / 首次见到
            continue
        life, last, st = rows[k]
        if st == ST_EXPIRED:                     # 已裁决过期：冻结
            continue
        life = max(0, life - 1)
        st = ST_JUDGE if life == 0 else ST_ACTIVE
        rows[k] = [life, last, st]
        if life == 0:
            just_zero.append(k)

    write_shengming(d, meta, rows)

    print(f"轮次 {meta['轮次']}（满值 {L}）· 本轮用到 {len(used_keys)} 条 · 更新 {len(rows)} 条")
    if lines:
        for l in lines:
            print(f"  + {l}")
    if just_zero:
        print(f"\n⚠ 生命周期归零 {len(just_zero)} 条 —— **必须询问用户**：")
        for k in just_zero:
            print(f"  {k}")
        print("\n  用户同意已无用 → python3 yongfa.py <领域> --expire  <键>")
        print("  用户不同意     → python3 yongfa.py <领域> --refresh <键>")
        print("  （绝不自动删；同意后也只标 [候选过期]，由 gengxin 下次回注落地）")
    else:
        print("  无键归零。")
    return 0


def do_set(d: Path, args, flag, new_status, life):
    vals = []
    for i, a in enumerate(args):
        if a == flag:
            vals += [x.strip() for x in args[i + 1].split(",") if x.strip()]
    if not vals:
        print(f"{flag} 需要键列表", file=sys.stderr)
        return 2
    meta, rows = read_shengming(d)
    L = meta["满值"]
    missing = [k for k in vals if k not in rows]
    for k in vals:
        last = rows.get(k, [0, "-", ""])[1]
        if new_status == ST_EXPIRED:
            rows[k] = [0, last, ST_EXPIRED]
        else:
            rows[k] = [L, last, ST_ACTIVE]     # 用户不同意 → 刷新回满值
    write_shengming(d, meta, rows)
    verb = "标记为已裁决:过期" if new_status == ST_EXPIRED else f"生命周期刷新回 {L}"
    print(f"{verb}：{len(vals)} 条")
    for k in vals:
        print(f"  {k}")
    if missing:
        print(f"  （其中 {len(missing)} 条原本不在生命周期表里，已补建）")
    return 0


def do_report(d: Path, args):
    log = d / "yongfa.txt"
    if not log.exists():
        print(f"缺 {log}（应先建 表头 + ★ 哨兵）", file=sys.stderr)
        return 2
    used, bad = parse_log(log)
    keys = lib_keys(d)
    meta, rows = read_shengming(d)
    L = meta["满值"]

    print(f"领域 {d.name} · 实战使用统计")
    print(f"  日志行 {sum(v[0] for v in used.values())} · 涉及键 {len(used)} · 库内键 {len(keys)}")

    print("\n[用过]")
    if used:
        for k in sorted(used, key=lambda x: (-used[x][0], x)):
            u, w, f = used[k]
            flag = "  << 成0败>=2，失败证据充分" if w == 0 and f >= 2 else ""
            print(f"  {k} | 用{u} 成{w} 败{f}{flag}")
    else:
        print("  （无）")

    print(f"\n[生命周期] 满值 {L} · 轮次 {meta['轮次']}")
    if not rows:
        print("  （生命周期表未建立；chuli 跑完第一个轮次后生成）")
    else:
        judge = sorted(k for k, v in rows.items() if v[2] == ST_JUDGE)
        exp = sorted(k for k, v in rows.items() if v[2] == ST_EXPIRED)
        near = sorted(k for k, v in rows.items() if v[2] == ST_ACTIVE and v[0] <= 1)
        print(f"  待裁决 {len(judge)} · 已裁决过期 {len(exp)} · 观察中(≤1) {len(near)}"
              f" · 活跃 {sum(1 for v in rows.values() if v[2] == ST_ACTIVE)}")
        if judge:
            print(f"  待裁决（**必须询问用户**，汇总成一次问，别逐条连问）：")
            for k in judge[:JUDGE_LIMIT]:
                print(f"    {k} | 生命周期 0 | 最后使用 {rows[k][1]}")
            if len(judge) > JUDGE_LIMIT:
                print(f"    ...（还有 {len(judge) - JUDGE_LIMIT} 项）")
        if exp:
            print("  已裁决:过期（等 gengxin 下次回注落 [候选过期]）：")
            for k in exp:
                print(f"    {k} | 最后使用 {rows[k][1]}")
        if near:
            print(f"  观察中（生命周期 ≤ 1，共 {len(near)} 项）：")
            for k in near[:10]:
                print(f"    {k} | 生命周期 {rows[k][0]} | 最后使用 {rows[k][1]}")
            if len(near) > 10:
                print(f"    ...（还有 {len(near) - 10} 项）")

    zero = sorted(keys - set(used))
    show_all = "--all" in args
    limit = len(zero) if show_all else ZERO_LIMIT
    print(f"\n[零使用] {len(zero)} 项（先查树是否挂上，别直接删）")
    for k in zero[:limit]:
        print(f"  {k}")
    if len(zero) > limit:
        print(f"  ...（还有 {len(zero) - limit} 项，加 --all 看全量）")

    ghost = sorted(set(used) - keys)
    if ghost:
        print("\n[警告] 悬空引用：日志里有、库里已无此键")
        for k in ghost:
            print(f"  {k}")

    orphan = sorted(set(rows) - keys)
    if orphan:
        print("\n[警告] 生命周期表里有、库里已无此键（应由 gengxin 清理）")
        for k in orphan:
            print(f"  {k}")

    if bad:
        print("\n[错误] 非法行")
        for n, s, why in bad:
            print(f"  L{n} {why}: {s[:80]}")

    if not bad and not ghost and not orphan:
        print("\n✅ 日志格式与引用全部通过")
    return 1 if (bad or orphan) else 0


def main():
    args = sys.argv[1:]
    pos = [a for a in args if not a.startswith("--")]
    # 去掉 flag 的取值（--date X / --case X / --life X / --used X）
    skip = set()
    for i, a in enumerate(args):
        if a in ("--date", "--case", "--life", "--used") and i + 1 < len(args):
            skip.add(i + 1)
    pos = [a for i, a in enumerate(args)
           if not a.startswith("--") and i not in skip]
    d = Path(pos[0] if pos else ".").resolve()
    if not d.is_dir():
        print(f"不是目录: {d}", file=sys.stderr)
        return 2

    if "--tick" in args:
        return do_tick(d, args)
    if "--refresh" in args:
        return do_set(d, args, "--refresh", ST_ACTIVE, None)
    if "--expire" in args:
        return do_set(d, args, "--expire", ST_EXPIRED, None)
    return do_report(d, args)


if __name__ == "__main__":
    sys.exit(main())
