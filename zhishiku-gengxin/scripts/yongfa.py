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
    python3 yongfa.py <领域> --tick --date 2026-09-27 [--case <领域>/<案例号>] \
                        [--used KEY=结果[:备注],...] [--life 10]

    # 3) 用户裁决（生命周期归零、已询问用户之后）
    python3 yongfa.py <领域> --refresh KEY[,KEY...]   # 用户不同意 → 生命周期刷新回满值
    python3 yongfa.py <领域> --expire  KEY[,KEY...]   # 用户同意   → 状态置「已裁决:过期」

    # 4) 并列候选择一（决策树「多个节点同时满足」时）
    python3 yongfa.py <领域> --pick KEY1,KEY2[,...]
    #    门槛：成次数 > 用次数 > 生命周期 > 命中 > 输入（分诊表）顺序

    # 5) 数据卫生
    python3 yongfa.py <领域> --gc-orphan [--apply]
        # 默认干跑：列出「生命周期表有、库里已无」的孤儿键；加 --apply 才删除
    python3 yongfa.py <领域> --normalize-report
        # 报告空白折叠后可合并的同义键（日志悬空键 → 库内键）

生命周期规则
------------
- 每个知识条目的生命周期是**倒计时**，满值 L（默认 10）。
- 单位是「轮次」：chuli 处理完一个任务 = 一轮。
- 本轮用到的键 → 生命周期 = L；本轮没用的键 → 生命周期 -1。
- 库里存在但表里没有的键（新建 / 首次见到）→ 初始化为 L。
- 生命周期降到 0 → 状态「待裁决」→ **必须询问用户**，绝不自动删。
  - 用户同意已无用 → `--expire`，状态「已裁决:过期」；由 gengxin 下次回注时在条目里落 `[候选过期]`。
  - 用户不同意 → `--refresh`，生命周期刷新回 L，继续观察。
- `--tick` 只推进**库内键**；表里的孤儿键不参与倒计时（先 --gc-orphan）。
- `--used` 的键必须能落到库内键（允许空白差异，自动归一）；对不上 → 拒绝本轮写入。

退出码：0 正常 / 1 非法行或悬空引用 / 2 用法或路径错。
"""
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RESULTS = {"成": 1, "败": 2}          # 结果只有两态
ST_ACTIVE = "活跃"
ST_JUDGE = "待裁决"
ST_EXPIRED = "已裁决:过期"
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}$")
DEF_LIFE = 10                         # 原 3 太紧，空轮次易误伤低频坑
ZERO_LIMIT = 40
JUDGE_LIMIT = 20
# 超长键几乎肯定是污染（曾出现整库拼接进一行）
MAX_KEY_LEN = 240


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


def norm_key(k: str) -> str:
    """空白折叠：用于同义键对齐（one_gadget约束 ↔ one_gadget 约束）。"""
    return re.sub(r"\s+", "", (k or "").strip())


def is_junk_key(k: str) -> bool:
    """明显污染：超长，或含大量拉丁补区乱码且几乎无 CJK。"""
    if not k or len(k) > MAX_KEY_LEN:
        return True
    moji = sum(1 for c in k if "\u00c0" <= c <= "\u00ff" or c in "£´¶¸º»¼½¾")
    cjk = sum(1 for c in k if "\u4e00" <= c <= "\u9fff")
    return moji >= 3 and cjk == 0


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


def build_canon_map(keys):
    """norm_key → 库内规范键。同一 norm 多条时取最短（通常空格更可读）。"""
    buckets = {}
    for k in keys:
        buckets.setdefault(norm_key(k), []).append(k)
    out = {}
    for n, ks in buckets.items():
        ks = sorted(ks, key=lambda x: (len(x), x))
        out[n] = ks[0]
    return out


def resolve_key(raw: str, canon_map: dict, lib: set):
    """把用户/日志键解析成库内键。成功 → (canon, None)；失败 → (None, reason)。"""
    k = (raw or "").strip()
    if not k:
        return None, "键为空"
    if is_junk_key(k):
        return None, f"键疑似污染（过长或乱码）: {k[:60]}…"
    if k in lib:
        return k, None
    n = norm_key(k)
    if n in canon_map:
        return canon_map[n], None
    return None, f"库中无此键（空白归一后仍无）: {k}"


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

    lib = lib_keys(d)
    canon_map = build_canon_map(lib)
    resolved = []
    bad_used = []
    for k, r, n in used:
        ck, why = resolve_key(k, canon_map, lib)
        if ck is None:
            bad_used.append((k, why))
        else:
            if ck != k:
                print(f"  · 键归一：{k} → {ck}")
            resolved.append((ck, r, n))
    if bad_used:
        print("[错误] --used 含库外/污染键，本轮拒绝写入：", file=sys.stderr)
        for k, why in bad_used:
            print(f"  {why}", file=sys.stderr)
        print("  先核对 cuowu ## 标题 / 卡片名 / zhiling 操作列；或改用库内规范键。",
              file=sys.stderr)
        return 2

    used_keys = {k for k, _r, _n in resolved}

    meta, rows = read_shengming(d)
    if "--life" in args:
        meta["满值"] = int(args[args.index("--life") + 1])
    # 旧表满值过紧时，tick 若未显式 --life，抬到当前默认（只升不降）
    if "--life" not in args and meta.get("满值", 0) < DEF_LIFE:
        print(f"  · 满值 {meta.get('满值')} → {DEF_LIFE}（默认已放宽，避免空轮误伤）")
        meta["满值"] = DEF_LIFE
    L = meta["满值"]
    meta["轮次"] += 1

    # 1) 追加使用行（写规范键）
    lines = [f"{dt} | {k} | {r} | {case} | {n}" for k, r, n in resolved]
    if lines and not append_log(d, lines):
        return 2

    # 2) 应用生命周期——只碰库内键；孤儿不倒计时、不扩表
    orphans = sorted(set(rows) - lib)
    just_zero = []
    for k in sorted(lib):
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

    print(f"轮次 {meta['轮次']}（满值 {L}）· 本轮用到 {len(used_keys)} 条 · 库内 {len(lib)} 条")
    if lines:
        for l in lines:
            print(f"  + {l}")
    if orphans:
        print(f"\n⚠ 生命周期表有 {len(orphans)} 条库外孤儿（本轮未倒计时）。"
              f"清理：python3 yongfa.py <领域> --gc-orphan --apply")
    if just_zero:
        print(f"\n⚠ 生命周期归零 {len(just_zero)} 条 —— **必须询问用户**：")
        for k in just_zero:
            print(f"  {k}")
        print("\n  用户同意已无用 → python3 yongfa.py <领域> --expire  <键>")
        print("  用户不同意     → python3 yongfa.py <领域> --refresh <键>")
        print("  （绝不自动删；同意后也只标 [候选过期]，由 gengxin 下次回注落地）")
    else:
        print("  无库内键归零。")
    return 0


def do_set(d: Path, args, flag, new_status, life):
    vals = []
    for i, a in enumerate(args):
        if a == flag:
            vals += [x.strip() for x in args[i + 1].split(",") if x.strip()]
    if not vals:
        print(f"{flag} 需要键列表", file=sys.stderr)
        return 2
    lib = lib_keys(d)
    canon_map = build_canon_map(lib)
    meta, rows = read_shengming(d)
    L = meta["满值"]
    resolved, missing = [], []
    for raw in vals:
        ck, why = resolve_key(raw, canon_map, lib)
        if ck is None:
            # 允许对表内孤儿直接 expire/refresh（清理场景）
            if raw in rows:
                resolved.append(raw)
            else:
                missing.append((raw, why))
        else:
            resolved.append(ck)
    if missing and not resolved:
        for raw, why in missing:
            print(why, file=sys.stderr)
        return 2
    for k in resolved:
        last = rows.get(k, [0, "-", ""])[1]
        if new_status == ST_EXPIRED:
            rows[k] = [0, last, ST_EXPIRED]
        else:
            rows[k] = [L, last, ST_ACTIVE]
    write_shengming(d, meta, rows)
    verb = "标记为已裁决:过期" if new_status == ST_EXPIRED else f"生命周期刷新回 {L}"
    print(f"{verb}：{len(resolved)} 条")
    for k in resolved:
        print(f"  {k}")
    if missing:
        print(f"  （跳过 {len(missing)} 条无法解析的键）")
    return 0


def do_gc_orphan(d: Path, args):
    """删除 shengming 里库外孤儿 / 污染键。默认干跑，--apply 才写盘。"""
    lib = lib_keys(d)
    meta, rows = read_shengming(d)
    orphan = sorted(set(rows) - lib)
    junk_in_lib = sorted(k for k in rows if k in lib and is_junk_key(k))
    # 也清表内乱码孤儿
    junk_orphan = [k for k in orphan if is_junk_key(k)]
    clean_orphan = [k for k in orphan if not is_junk_key(k)]
    print(f"领域 {d.name} · 孤儿回收预览")
    print(f"  库内键 {len(lib)} · 表内 {len(rows)} · 孤儿 {len(orphan)}"
          f"（乱码/超长 {len(junk_orphan)} · 其它 {len(clean_orphan)}）")
    if junk_orphan:
        print("\n[乱码/超长孤儿] 建议直接删")
        for k in junk_orphan[:30]:
            print(f"  {k[:100]}{'…' if len(k) > 100 else ''} | {rows[k]}")
        if len(junk_orphan) > 30:
            print(f"  ...还有 {len(junk_orphan) - 30} 条")
    if clean_orphan:
        print("\n[其它孤儿] 库里已无对应条目（标题改名/删条后残留）")
        for k in clean_orphan:
            print(f"  {k} | {rows[k]}")
    if junk_in_lib:
        print("\n[警告] 库内键本身像污染（请先修 cuowu/zhiling，不在此删除）")
        for k in junk_in_lib:
            print(f"  {k}")
    if not orphan:
        print("\n无孤儿。")
        return 0
    if "--apply" not in args:
        print("\n干跑结束。确认后加 --apply 删除上述孤儿键（不改 yongfa.txt / 不改知识正文）。")
        return 0
    for k in orphan:
        del rows[k]
    write_shengming(d, meta, rows)
    print(f"\n已删除孤儿 {len(orphan)} 条。表内剩余 {len(rows)}。")
    return 0


def do_normalize_report(d: Path, args):
    """报告：日志悬空键能否空白归一到库内键；表内同 norm 重复。"""
    lib = lib_keys(d)
    canon_map = build_canon_map(lib)
    used, bad = parse_log(d / "yongfa.txt")
    meta, rows = read_shengming(d)

    print(f"领域 {d.name} · 键归一报告")
    ghosts = sorted(set(used) - lib)
    mapped, unmapped = [], []
    for g in ghosts:
        ck, why = resolve_key(g, canon_map, lib)
        if ck:
            mapped.append((g, ck, used[g]))
        else:
            unmapped.append((g, why, used[g]))
    print(f"\n[日志悬空 → 可归一] {len(mapped)}")
    for g, ck, st in mapped:
        print(f"  {g} → {ck} | 用{st[0]} 成{st[1]} 败{st[2]}")
    print(f"\n[日志悬空 → 无法归一] {len(unmapped)}")
    for g, why, st in unmapped:
        print(f"  {g} | 用{st[0]} 成{st[1]} 败{st[2]} | {why}")

    # 表内：同一 norm 多条
    buckets = {}
    for k in rows:
        buckets.setdefault(norm_key(k), []).append(k)
    dups = {n: ks for n, ks in buckets.items() if len(ks) > 1}
    print(f"\n[生命周期表同义重复] {len(dups)} 组")
    for n, ks in sorted(dups.items()):
        print(f"  {ks}")

    # 库内同 norm
    lib_buckets = {}
    for k in lib:
        lib_buckets.setdefault(norm_key(k), []).append(k)
    lib_dups = {n: ks for n, ks in lib_buckets.items() if len(ks) > 1}
    print(f"\n[库内同义键] {len(lib_dups)} 组（需改标题/卡片名才能彻底合并）")
    for n, ks in sorted(lib_dups.items()):
        print(f"  {ks}")

    if bad:
        print("\n[错误] 日志非法行")
        for n, s, why in bad:
            print(f"  L{n} {why}: {s[:80]}")
    return 0


def read_hit(d: Path, key: str) -> int:
    """条目里的「命中：N」= 来源支撑数；没有则 0。仅卡片/工具文件带此字段。"""
    if key.startswith("liucheng_biao/"):
        p = d / "liucheng_biao" / (key.split("/", 1)[1] + ".txt")
    elif key.startswith("tools/"):
        p = d / "tools" / (key.split("/", 1)[1] + ".txt")
    else:
        return 0
    m = re.search(r"命中\s*[:：]\s*(\d+)", txt(p))
    return int(m.group(1)) if m else 0


def do_pick(d: Path, args):
    """决策树「多个节点同时满足」时的确定性择一。

    排序门槛（自上而下）：成次数 → 用次数 → 生命周期 → 命中 → 输入顺序。
    输入顺序即分诊表/树的书写顺序，用作最后兜底（等价于「默认取第一个」）。
    """
    vals = []
    for i, a in enumerate(args):
        if a == "--pick" and i + 1 < len(args):
            vals += [x.strip() for x in args[i + 1].split(",") if x.strip()]
    if not vals:
        print("--pick 需要候选键列表，如 --pick liucheng_biao/H.cat.1,liucheng_biao/H.cat.2",
              file=sys.stderr)
        return 2
    lib = lib_keys(d)
    canon_map = build_canon_map(lib)
    used, _bad = parse_log(d / "yongfa.txt")
    # 把日志按规范键聚合
    used_n = {}
    for k, st in used.items():
        ck, _ = resolve_key(k, canon_map, lib)
        ck = ck or k
        c = used_n.setdefault(ck, [0, 0, 0])
        c[0] += st[0]
        c[1] += st[1]
        c[2] += st[2]
    _meta, rows = read_shengming(d)
    cand = []
    for idx, raw in enumerate(vals):
        k, why = resolve_key(raw, canon_map, lib)
        if k is None:
            print(f"[警告] 候选无法解析，仍参与排序：{why}")
            k = raw
        u, w, fl = used_n.get(k, [0, 0, 0])
        life, _last, st = rows.get(k, [0, "-", "活跃"])
        cand.append({"key": k, "order": idx, "u": u, "w": w, "f": fl,
                     "life": life, "st": st, "hit": read_hit(d, k)})
    rank = sorted(cand, key=lambda c: (-c["w"], -c["u"], -c["life"], -c["hit"], c["order"]))
    win = rank[0]
    print("并列候选择一（门槛：成 > 用 > 生命周期 > 命中 > 分诊顺序）")
    for c in rank:
        mark = "  ← 胜出" if c is win else ""
        print(f"  {c['key']} | 用{c['u']} 成{c['w']} 败{c['f']} | "
              f"生命周期 {c['life']}({c['st']}) | 命中 {c['hit']}{mark}")
    print(f"\n胜出：{win['key']}")
    if win["w"] == 0:
        print("  ⚠ 胜出项「成」次数为 0：实战证据不足，等价于回退分诊表顺序取第一个。")
    return 0


def do_report(d: Path, args):
    log = d / "yongfa.txt"
    if not log.exists():
        print(f"缺 {log}（应先建 表头 + ★ 哨兵）", file=sys.stderr)
        return 2
    used, bad = parse_log(log)
    keys = lib_keys(d)
    canon_map = build_canon_map(keys)
    meta, rows = read_shengming(d)
    L = meta["满值"]

    # 日志按规范键聚合展示
    used_n = {}
    aliases = {}
    for k, st in used.items():
        ck, _ = resolve_key(k, canon_map, keys)
        if ck:
            c = used_n.setdefault(ck, [0, 0, 0])
            c[0] += st[0]
            c[1] += st[1]
            c[2] += st[2]
            if ck != k:
                aliases.setdefault(ck, []).append(k)
        else:
            used_n[k] = st  # 真悬空，原样保留

    print(f"领域 {d.name} · 实战使用统计")
    print(f"  日志行 {sum(v[0] for v in used.values())} · 涉及键 {len(used)}"
          f"（归一后 {len(used_n)}）· 库内键 {len(keys)}")

    print("\n[用过]")
    if used_n:
        for k in sorted(used_n, key=lambda x: (-used_n[x][0], x)):
            u, w, f = used_n[k]
            flag = "  << 成0败>=2，失败证据充分" if w == 0 and f >= 2 else ""
            alias = f"  (含旧键: {', '.join(aliases[k])})" if k in aliases else ""
            print(f"  {k} | 用{u} 成{w} 败{f}{flag}{alias}")
    else:
        print("  （无）")

    print(f"\n[生命周期] 满值 {L} · 轮次 {meta['轮次']}")
    if not rows:
        print("  （生命周期表未建立；chuli 跑完第一个轮次后生成）")
    else:
        orphan = sorted(set(rows) - keys)
        judge = sorted(k for k, v in rows.items() if v[2] == ST_JUDGE and k in keys)
        exp = sorted(k for k, v in rows.items() if v[2] == ST_EXPIRED and k in keys)
        near = sorted(k for k, v in rows.items()
                      if v[2] == ST_ACTIVE and v[0] <= 1 and k in keys)
        print(f"  待裁决 {len(judge)} · 已裁决过期 {len(exp)} · 观察中(≤1) {len(near)}"
              f" · 活跃(库内) {sum(1 for k, v in rows.items() if v[2] == ST_ACTIVE and k in keys)}"
              f" · 孤儿 {len(orphan)}")
        if orphan:
            print(f"  孤儿（不参与裁决展示；请 --gc-orphan）：{len(orphan)} 条")
        if judge:
            print("  待裁决（**必须询问用户**，汇总成一次问，别逐条连问）：")
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

    zero = sorted(keys - set(used_n))
    show_all = "--all" in args
    limit = len(zero) if show_all else ZERO_LIMIT
    print(f"\n[零使用] {len(zero)} 项（先查树是否挂上，别直接删）")
    for k in zero[:limit]:
        print(f"  {k}")
    if len(zero) > limit:
        print(f"  ...（还有 {len(zero) - limit} 项，加 --all 看全量）")

    ghost = sorted(k for k in used_n if k not in keys)
    if ghost:
        print("\n[警告] 悬空引用：日志里有、库里已无此键（且空白归一失败）")
        for k in ghost:
            print(f"  {k}")

    orphan = sorted(set(rows) - keys)
    if orphan:
        print("\n[警告] 生命周期表里有、库里已无此键 → python3 yongfa.py <领域> --gc-orphan [--apply]")
        for k in orphan[:15]:
            print(f"  {k[:100]}{'…' if len(k) > 100 else ''}")
        if len(orphan) > 15:
            print(f"  ...还有 {len(orphan) - 15} 条")

    if bad:
        print("\n[错误] 非法行")
        for n, s, why in bad:
            print(f"  L{n} {why}: {s[:80]}")

    if not bad and not ghost and not orphan:
        print("\n✅ 日志格式与引用全部通过")
    return 1 if (bad or orphan or ghost) else 0


def main():
    args = sys.argv[1:]
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
    if "--pick" in args:
        return do_pick(d, args)
    if "--refresh" in args:
        return do_set(d, args, "--refresh", ST_ACTIVE, None)
    if "--expire" in args:
        return do_set(d, args, "--expire", ST_EXPIRED, None)
    if "--gc-orphan" in args:
        return do_gc_orphan(d, args)
    if "--normalize-report" in args:
        return do_normalize_report(d, args)
    return do_report(d, args)


if __name__ == "__main__":
    sys.exit(main())
