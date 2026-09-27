#!/usr/bin/env python3
"""zhishiku 自测：静态一致性 + 脚本行为 + 领域自检。

用法：
    python3 tests/selftest.py            # 跑全部
    python3 tests/selftest.py -v         # 打印每个用例
    python3 tests/selftest.py --keep     # 保留沙箱目录（排错用）

只依赖标准库；不改仓库与真实数据根（沙箱在临时目录）。
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PY = sys.executable

# Windows 控制台默认 GBK，中文/符号输出会崩；强制 UTF-8。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
SKILLS = ["zhishiku-caiji", "zhishiku-tilian", "zhishiku-gengxin", "zhishiku-chuli"]
YONGFA = REPO / "zhishiku-gengxin" / "scripts" / "yongfa.py"

VERBOSE = "-v" in sys.argv
KEEP = "--keep" in sys.argv
RESULTS = []


# ------------------------------------------------------------------ 小工具
def run(args, cwd=None, encoding="utf-8"):
    p = subprocess.run([PY] + [str(a) for a in args], cwd=cwd,
                       capture_output=True, text=True,
                       encoding=encoding, errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    if VERBOSE or not ok:
        mark = "ok  " if ok else "FAIL"
        print(f"  [{mark}] {name}" + (f"  <- {detail}" if detail and not ok else ""))
    return ok


def section(title):
    print(f"\n== {title}")


# ------------------------------------------------------------------ 沙箱
HEAD_YONGFA = ("# 实战使用日志（append-only；写入位＝文末的哨兵行）\n"
               "# 日期 | 键 | 结果 | 案例id | 备注\n"
               "# 结果 ∈ 成 / 败\n"
               "★\n")


def make_domain(root: Path, name="dom"):
    d = root / name
    (d / "liucheng_biao").mkdir(parents=True)
    (d / "tools").mkdir()
    (d / "liucheng_biao" / "A.1.txt").write_text(
        "# A.1 · 第一步\n\n## 时机\n- x\n\n## 条件\n- y\n\n## 做什么\n- z\n\n## 下一跳\n- A.2\n\n## 来源\n- dom/0001 buzou/01.txt\n",
        encoding="utf-8")
    (d / "liucheng_biao" / "00_说明.txt").write_text("# 00_说明\n", encoding="utf-8")
    (d / "tools" / "t1.txt").write_text("# t1\n", encoding="utf-8")
    (d / "cuowu.txt").write_text("# 常见错误\n\n## 错误甲\n现象：a\n原因：b\n处理：c\n",
                                 encoding="utf-8")
    (d / "zhiling.txt").write_text("# 命令速查\n操作 | 位置 | 指令（规范形式） | 命中 | 来源\n查版本 | 终端 | xx --version | 1 | dom/0001\n",
                                   encoding="utf-8")
    (d / "yongfa.txt").write_text(HEAD_YONGFA, encoding="utf-8")
    return d


# ------------------------------------------------------------------ 1 静态
def test_static():
    section("1. 静态一致性（四份 SKILL.md）")
    for s in SKILLS:
        p = REPO / s / "SKILL.md"
        if not check(f"{s}: SKILL.md 存在", p.is_file()):
            continue
        t = p.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
        check(f"{s}: frontmatter 合法", bool(m))
        if m:
            fm = m.group(1)
            check(f"{s}: name 与目录一致", f"name: {s}" in fm)
            check(f"{s}: 有 description", "description:" in fm)
            v = re.search(r'version:\s*"([\d.]+)"', fm)
            check(f"{s}: 有 version", bool(v), "缺 metadata.version")
        check(f"{s}: 无 TODO/TBD 残留", not re.search(r"\b(TODO|TBD|FIXME)\b", t))
        check(f"{s}: 认领的 ★ 规则一致",
              ("★" not in t) or ("独占一行" in t or "哨兵" in t), "提到 ★ 但没说哨兵规则")
        # 交叉引用：文中提到的 zhishiku-* 必须是真实目录
        for ref in sorted(set(re.findall(r"zhishiku-[a-z]+", t))):
            check(f"{s}: 引用 {ref} 存在", (REPO / ref).is_dir(), "目录不存在")

    # 引用的脚本/文件确实存在
    g = (REPO / "zhishiku-gengxin" / "SKILL.md").read_text(encoding="utf-8")
    if "scripts/yongfa.py" in g:
        check("gengxin 引用的 scripts/yongfa.py 存在", YONGFA.is_file())
    for f in ["examples/domain-skeleton/yongfa.txt", "sync.sh",
              "install.sh", "install.ps1"]:
        check(f"仓库含 {f}", (REPO / f).exists())
    check("examples 骨架无 ★ 之外的漏项",
          "★" in (REPO / "examples/domain-skeleton/yongfa.txt").read_text(encoding="utf-8"))

    # tilian：输出布局里声明的产出目录，正文必须有对应小节（防“加了目录忘了写规则”）
    t = (REPO / "zhishiku-tilian" / "SKILL.md").read_text(encoding="utf-8")
    lay = re.search(r"## 输出布局（按领域分库）\n\n```text\n(.*?)```", t, re.S)
    if check("tilian: 找到输出布局块", bool(lay)):
        names = [a or b for a, b in re.findall(r"[├└]─ (\w+)/|[├└]─ (\w+)/", lay.group(1))]
        check("tilian: 产出目录 >= 4 个", len(names) >= 4, str(names))
        for name in names:
            check(f"tilian: 产出目录 {name}/ 有对应小节",
                  re.search(rf"^### \d+\. [^\n]*`{name}/", t, re.M) is not None,
                  "布局声明了但正文没有规则小节")

    # 回归：代表单个文件内容的示例块（以 '# ' 开头的 fenced block）里，
    # ★ 不得超过 1 个。历史上 caiji 的 qingdan 表头写成「（★ 是写入位）」
    # 导致文件里出现两个 ★，直接破坏「全文件唯一」与 Edit oldText="★" 的唯一性。
    for s in SKILLS:
        t = (REPO / s / "SKILL.md").read_text(encoding="utf-8")
        for bi, block in enumerate(re.findall(r"```text\n(.*?)```", t, re.S)):
            if not block.startswith("# "):
                continue
            c = block.count("★")
            check(f"{s}: 文件样例块#{bi + 1} 的 ★ 不重复", c <= 1, f"★={c}")


# ------------------------------------------------------------------ 2 用法
def test_usage(sb: Path):
    section("2. yongfa.py 用法与参数校验")
    d = make_domain(sb)
    rc, out = run([YONGFA, d]); check("report 正常退出", rc == 0, out[:200])
    rc, out = run([YONGFA, d, "--tick"]); check("--tick 缺 --date 报错", rc == 2, out[:120])
    rc, out = run([YONGFA, d, "--tick", "--date", "26-09-27"])
    check("--tick 日期格式错报错", rc == 2, out[:120])
    rc, out = run([YONGFA, d, "--tick", "--date", "2026-09-27", "--used", "A.1"])
    check("--used 缺 '=' 报错", rc == 2, out[:120])
    rc, out = run([YONGFA, d, "--tick", "--date", "2026-09-27", "--used", "A.1=也许"])
    check("--used 结果非法报错", rc == 2, out[:120])
    rc, out = run([YONGFA, d, "--tick", "--date", "2026-09-27", "--used", "A.1=成:x|y"])
    check("备注含 '|' 被拒", rc == 2, out[:120])
    rc, out = run([YONGFA, sb / "nope"]); check("不存在的目录报错", rc == 2, out[:120])
    e = sb / "empty"; e.mkdir()
    rc, out = run([YONGFA, e]); check("缺 yongfa.txt 报错", rc == 2, out[:120])


# ------------------------------------------------------------------ 3 记账
def test_tick(sb: Path):
    section("3. --tick 记账与生命周期")
    d = make_domain(sb, "tick")
    rc, out = run([YONGFA, d, "--tick", "--date", "2026-09-01",
                   "--case", "dom/0001", "--used", "liucheng_biao/A.1=成"])
    check("带使用记账成功", rc == 0, out[:200])
    log = (d / "yongfa.txt").read_text(encoding="utf-8")
    check("日志追加了使用行", "2026-09-01 | liucheng_biao/A.1 | 成 | dom/0001 | -" in log, log)
    check("★ 仍唯一", log.count("★") == 1, f"★={log.count('★')}")
    check("★ 仍在最后", log.rstrip().endswith("★"), log[-40:])
    check("生成了 shengming.txt", (d / "shengming.txt").is_file())
    sm = (d / "shengming.txt").read_text(encoding="utf-8")
    check("轮次 1", "# 轮次：1" in sm, sm[:120])
    check("满值 3", "# 满值：3" in sm, sm[:120])
    check("A.1 状态活跃且满值", "liucheng_biao/A.1 | 3 | 2026-09-01 | 活跃" in sm, sm)
    check("未用键已初始化", "tools/t1 | 3 | - | 活跃" in sm, sm)
    check("00_说明 不建键", "00_说明" not in sm, sm)
    check("cuowu 段建键", "cuowu/错误甲" in sm, sm)
    check("zhiling 行建键", "zhiling/查版本" in sm, sm)

    # 空轮次也要衰减
    for day in ("2026-09-02", "2026-09-03", "2026-09-04"):
        rc, out = run([YONGFA, d, "--tick", "--date", day])
        check(f"空轮次 {day} 成功", rc == 0, out[:120])
    sm = (d / "shengming.txt").read_text(encoding="utf-8")
    check("A.1 衰减到 0", "liucheng_biao/A.1 | 0 | 2026-09-01 | 待裁决" in sm, sm)
    check("t1 衰减到 0", "tools/t1 | 0 | - | 待裁决" in sm, sm)
    rc, out = run([YONGFA, d, "--tick", "--date", "2026-09-05"])
    check("归零时提示询问用户", "必须询问用户" in out, out[:200])

    # 再被用过 → 回满值
    rc, out = run([YONGFA, d, "--tick", "--date", "2026-09-06", "--used", "tools/t1=败:记错了"])
    sm = (d / "shengming.txt").read_text(encoding="utf-8")
    check("用过即回满值", "tools/t1 | 3 | 2026-09-06 | 活跃" in sm, sm)

    # 用户不同意 → 刷新
    rc, out = run([YONGFA, d, "--refresh", "liucheng_biao/A.1"])
    sm = (d / "shengming.txt").read_text(encoding="utf-8")
    check("--refresh 刷新回满值", "liucheng_biao/A.1 | 3 | 2026-09-01 | 活跃" in sm, sm)

    # 用户同意 → 过期并冻结
    rc, out = run([YONGFA, d, "--expire", "liucheng_biao/A.1"])
    sm = (d / "shengming.txt").read_text(encoding="utf-8")
    check("--expire 置已裁决:过期", "liucheng_biao/A.1 | 0 | 2026-09-01 | 已裁决:过期" in sm, sm)
    for day in ("2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"):
        run([YONGFA, d, "--tick", "--date", day])
    sm = (d / "shengming.txt").read_text(encoding="utf-8")
    check("已裁决:过期 冻结（不被再降/再问）",
          "liucheng_biao/A.1 | 0 | 2026-09-01 | 已裁决:过期" in sm, sm)


# ------------------------------------------------------------------ 4 异常
def test_anomaly(sb: Path):
    section("4. 异常：悬空引用 / 非法行 / 截断")
    d = make_domain(sb, "bad")
    log = d / "yongfa.txt"
    log.write_text(HEAD_YONGFA.replace("★", "\n".join([
        "2026-09-01 | liucheng_biao/A.1 | 成 | - | -",
        "2026-09-01 | liucheng_biao/GONE | 成 | - | 悬空",
        "2026-09-01 | tools/t1 | 也许 | - | 结果非法",
        "2026-09-01 | tools/t1 | 成 | -",                      # 字段数 4
        "26-09-01 | tools/t1 | 成 | - | -",                     # 日期非法
        "★",
    ])), encoding="utf-8")
    rc, out = run([YONGFA, d])
    check("非法行使退出码=1", rc == 1, f"rc={rc}")
    check("报出悬空引用", "悬空引用" in out, out[:300])
    check("报出非法行", "非法行" in out, out[:300])
    check("非法行计数 3", len(re.findall(r"^  L\d+", out, re.M)) == 3, out[:400])

    # 截断：默认不超过 40 项零使用
    d2 = make_domain(sb, "many")
    for i in range(60):
        (d2 / "liucheng_biao" / f"B.{i}.txt").write_text(
            "# B\n## 时机\n- a\n## 条件\n- b\n## 做什么\n- c\n## 下一跳\n- d\n## 来源\n- x\n",
            encoding="utf-8")
    rc, out = run([YONGFA, d2])
    zeros = out.split("[零使用]")[1]
    listed = len(re.findall(r"^  \w", zeros, re.M))
    check("零使用默认截断到 40", listed <= 41, f"列了 {listed} 行")
    check("截断时给出 --all 提示", "--all" in zeros, zeros[-200:])
    rc, out = run([YONGFA, d2, "--all"])
    check("--all 输出更多", out.count("\n") > zeros.count("\n"), "")

    # 生命周期孤儿键
    d3 = make_domain(sb, "orphan")
    run([YONGFA, d3, "--tick", "--date", "2026-09-01"])
    (d3 / "tools" / "t1.txt").unlink()
    rc, out = run([YONGFA, d3])
    check("生命周期孤儿键被报出", "生命周期表里有" in out and rc == 1, out[:300])


# ------------------------------------------------------------------ 5 行尾
def test_lineendings(sb: Path):
    section("5. 行尾与编码")
    for crlf in (False, True):
        name = "crlf" if crlf else "lf"
        d = make_domain(sb, name)
        body = HEAD_YONGFA.replace("★", "2026-09-01 | tools/t1 | 成 | - | -\n★")
        if crlf:
            body = body.replace("\n", "\r\n")
        (d / "yongfa.txt").write_bytes(body.encode("utf-8"))
        rc, out = run([YONGFA, d])
        check(f"{name}: report 正常", rc == 0, out[:200])
        rc, out = run([YONGFA, d, "--tick", "--date", "2026-09-02", "--used", "tools/t1=成"])
        data = (d / "yongfa.txt").read_bytes().decode("utf-8")
        check(f"{name}: 追加成功且 ★ 唯一", rc == 0 and data.count("★") == 1, data[-80:])
        if crlf:
            check("crlf: 保持 CRLF", "\r\n" in data and data.count("\n") == data.count("\r\n"),
                  f"CRLF={data.count(chr(13)+chr(10))} LF={data.count(chr(10))}")
        # 生命周期表统一 LF
        smb = (d / "shengming.txt").read_bytes()
        check(f"{name}: shengming.txt 为 LF", b"\r\n" not in smb, "混入 CRLF")


# ------------------------------------------------------------------ 6 数据侧
def test_live_data():
    section("7. 真实数据根（存在才跑）")
    xin = REPO / "zhishiku-gengxin" / "xinxi.txt"
    if not xin.is_file():
        print("  (skip) 没有 xinxi.txt")
        return
    t = xin.read_text(encoding="utf-8")
    win = re.search(r"gengxin_wei_win:\s*(\S+)", t)
    lin = re.search(r"gengxin_wei_linux:\s*(\S+)", t)
    root = None
    for m in (win, lin):
        if m and Path(m.group(1)).is_dir():
            root = Path(m.group(1)); break
    if root is None:
        print("  (skip) 当前 OS 找不到 gengxin 数据根")
        return
    check("gengxin 数据根可访问", True)

    # ★ 不变量：append-only 文件里不得出现非哨兵的 ★
    ao_names = {"qingdan.txt", "yongfa.txt", "suoyin.txt", "rizhi.txt"}
    offenders = []
    for f in root.rglob("*.txt"):
        if not (f.name in ao_names or f.parent.name == "buzou"):
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        total = content.count("★")
        sent = len(re.findall(r"^★[ \t]*$", content, re.M))
        if total != sent or sent != 1:
            offenders.append(f"{f.relative_to(root)} (★={total} 哨兵={sent})")
    check("append-only 文件的 ★ 全文件唯一", not offenders,
          "; ".join(offenders[:6]))
    domains = [p for p in root.iterdir() if p.is_dir()]
    check("至少一个领域", bool(domains), str(root))
    for d in sorted(domains):
        vp = d / "validate.py"
        if not vp.is_file():
            print(f"  (skip) {d.name}: 无 validate.py")
            continue
        rc, out = run([vp])
        errs = re.findall(r"✗ (.+)", out)
        check(f"{d.name}: validate 无错误", rc == 0 and not errs, "; ".join(errs)[:200])
        warns = re.findall(r"⚠ (.+)", out)
        if warns:
            print(f"  (warn) {d.name}: {len(warns)} 条警告")
        rc, out = run([YONGFA, d])
        check(f"{d.name}: yongfa.py 无异常", rc == 0, out[:200])


# ------------------------------------------------------------------ 7 端到端
def test_e2e_correction(sb: Path):
    section("8. 端到端：用户纠正块的格式可被下游接受")
    # 按 caiji 规范写一个含纠正块的 buzou，检查 5 段结构完整
    d = make_domain(sb, "e2e")
    buzou = d / "buzou.txt"
    buzou.write_text(
        "执行流：\n"
        "-> 用户纠正：以为要先装 QQ 才能看音乐\n"
        "   位置：用户纠正\n"
        "   指令：agent 判断「本地没有 qq，需先安装再继续」\n"
        "   结果：用户答复：不用装 qq，音乐是网页版，直接开浏览器就行\n"
        "   结论：QQ 与音乐无关，不要臆断依赖顺序\n"
        "★\n", encoding="utf-8")
    blocks = re.findall(
        r"^-> (.+?)\n   位置：(.+?)\n   指令：(.+?)\n   结果：(.+?)\n   结论：(.+?)$",
        buzou.read_text(encoding="utf-8"), re.M)
    check("纠正块可被 5 段正则解析", len(blocks) == 1, str(blocks))
    if blocks:
        op, loc, cmd, res, con = blocks[0]
        check("位置 = 用户纠正", loc == "用户纠正", loc)
        check("结果保留用户原话", res.startswith("用户答复："), res)
        check("指令描述的是 agent 原判断", "agent 判断" in cmd, cmd)
    # 该块落成 cuowu 段后，validate.py 接受
    (d / "cuowu.txt").write_text(
        "# 常见错误\n\n## 臆断步骤依赖顺序\n现象：用户反对 agent 判断「先装 qq 再看音乐」\n"
        "原因：把工具依赖当成先决条件，没有先问清依赖\n处理：先确认各步骤依赖，再决定顺序\n"
        "适用：多步骤任务\n归属：合理化表\n来源：e2e/0001 buzou/01.txt 步骤a\n", encoding="utf-8")
    real = None
    for cand in (REPO / "zhishiku-gengxin" / "xinxi.txt",):
        if cand.is_file():
            m = re.search(r"gengxin_wei_win:\s*(\S+)", cand.read_text(encoding="utf-8"))
            if m and (Path(m.group(1)) / "ctf-pwn" / "validate.py").is_file():
                real = Path(m.group(1)) / "ctf-pwn" / "validate.py"
    if real:
        shutil.copy(real, d / "validate.py")
        (d / "tieuli.txt").write_text("# 铁律\n", encoding="utf-8")
        (d / "yuanze.txt").write_text("# 概述原则\n", encoding="utf-8")
        (d / "bianjie.txt").write_text("# 边界\n", encoding="utf-8")
        (d / "liucheng.txt").write_text("# 执行流\n", encoding="utf-8")
        (d / "suoyin.txt").write_text("# 案例id | 产出条目\n★\n", encoding="utf-8")
        (d / "rizhi.txt").write_text("# 更新日志\n★\n", encoding="utf-8")
        rc, out = run([d / "validate.py"])
        errs = re.findall(r"✗ (.+)", out)
        check("纠正提炼出的 cuowu 段通过 validate", not errs, "; ".join(errs)[:200])
    else:
        print("  (skip) 找不到真实 validate.py 模板")


SNAP = REPO / "zhishiku-gengxin" / "scripts" / "snapshot.py"


# ------------------------------------------------------------------ 6 快照
def test_snapshot(sb: Path):
    section("6. snapshot.py 快照 / 回滚")
    check("snapshot.py 存在", SNAP.is_file())
    if not SNAP.is_file():
        return
    d = make_domain(sb, "snap")
    n_files = sum(1 for p in d.rglob("*") if p.is_file())

    rc, out = run([SNAP, d, "--take", "--note", "单测"])
    check("take 成功", rc == 0, out[:200])
    snaps = sorted((d / "_snap").iterdir()) if (d / "_snap").is_dir() else []
    check("生成了一个快照", len(snaps) == 1, str(snaps))
    snap = snaps[0]
    mf = snap / "MANIFEST.txt"
    check("MANIFEST 存在", mf.is_file())
    rows = [l for l in mf.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    check("MANIFEST 行数 = 领域文件数", len(rows) == n_files, f"{len(rows)} vs {n_files}")
    check("快照不含 _snap 自身", not any("_snap/" in r for r in rows), str(rows))

    rc, out = run([SNAP, d, "--list"])
    check("list 能列出快照", rc == 0 and snap.name in out, out[:200])

    # 改一个文件 + 新增一个文件
    target = d / "liucheng_biao" / "A.1.txt"
    good = target.read_text(encoding="utf-8")
    target.write_text("# A.1 被搞坏了\n", encoding="utf-8")
    extra = d / "liucheng_biao" / "NEW.9.txt"
    extra.write_text("# 新加的\n", encoding="utf-8")

    rc, out = run([SNAP, d, "--rollback", snap.name])
    check("rollback 不带 --yes 只提示", rc == 0 and "--yes" in out, out[:200])
    check("未确认时未改动", target.read_text(encoding="utf-8") == "# A.1 被搞坏了\n")

    rc, out = run([SNAP, d, "--rollback", snap.name, "--yes"])
    check("rollback --yes 成功", rc == 0, out[:300])
    check("被改的文件已恢复", target.read_text(encoding="utf-8") == good)
    check("新文件被移入 _orphan（未删）",
          not extra.exists() and any((snap / p).name == "NEW.9.txt"
                                     for p in snap.rglob("NEW.9.txt")),
          str(list(snap.rglob("NEW.9.txt"))))
    check("回滚前自动拍了 preRollback",
          any(p.name.endswith("-preRollback") for p in (d / "_snap").iterdir()),
          str([p.name for p in (d / "_snap").iterdir()]))

    # 坏快照：篡改快照里的副本 → 必须拒绝回滚
    victim = next(p for p in snap.rglob("*.txt")
                  if p.name != "MANIFEST.txt" and p.parent == snap / "liucheng_biao")
    victim.write_text("# 被篡改\n", encoding="utf-8")
    rc, out = run([SNAP, d, "--rollback", snap.name, "--yes"])
    check("快照自身损坏时拒绝回滚", rc == 1, f"rc={rc} {out[:200]}")

    rc, out = run([SNAP, d, "--rollback", "不存在的快照", "--yes"])
    check("回滚不存在的快照报错", rc == 1, out[:200])

    rc, out = run([SNAP, d, "--prune", "--keep", "1"])
    left = [p for p in (d / "_snap").iterdir() if p.is_dir()]
    check("prune --keep 1 后只剩 1 个", rc == 0 and len(left) == 1, str([p.name for p in left]))

    rc, out = run([sb / "nope", "--take"])
    check("不存在的目录报错", rc == 2, out[:150])


# ------------------------------------------------------------------ 9 契约
def test_key_contract(sb: Path):
    """yongfa.py 枚举出的键 ↔ --used 接受的键 必须一致（否则每次记账都是“悬空引用”）。"""
    section("9. 契约：枚举出的键能被 --tick 接受")
    d = make_domain(sb, "contract")
    rc, out = run([YONGFA, d])
    zero = out.split("[零使用]")[1] if "[零使用]" in out else ""
    keys = re.findall(r"^  (\S.*?)$", zero, re.M)
    keys = [k for k in keys if not k.startswith("...")]
    check("报告能枚举出键", len(keys) >= 4, str(keys[:8]))
    used = ",".join(f"{k}=成" for k in keys[:4])
    rc, out = run([YONGFA, d, "--tick", "--date", "2026-09-01", "--used", used])
    check("枚举出的键拿去记账成功", rc == 0, out[:300])
    check("记账后无悬空引用", "悬空引用" not in out, out[:300])
    rc, out = run([YONGFA, d])
    check("回读无悬空引用", "悬空引用" not in out and rc == 0, out[:300])


# ------------------------------------------------------------------ 10 破坏矩阵
def _validated_domain(sb: Path, name="vdom"):
    """造一个能通过 ctf-pwn/validate.py 的领域（含 caiji 归档使来源不悬空）。"""
    root = sb / name
    d = root / "gengxin_wei" / "ctf-pwn"
    (root / "caiji_wei" / "ctf-pwn" / "biao" / "hui" / "0001").mkdir(parents=True)
    (d / "liucheng_biao").mkdir(parents=True)
    (d / "tools").mkdir()
    (d / "tieuli.txt").write_text(
        "# 铁律\n\n- 要点一\n  来源：ctf-pwn/0001 buzou/01.txt 步骤a\n", encoding="utf-8")
    (d / "yuanze.txt").write_text("# 概述原则\n", encoding="utf-8")
    (d / "bianjie.txt").write_text("# 边界\n", encoding="utf-8")
    (d / "cuowu.txt").write_text(
        "# 常见错误\n\n## 错误甲\n现象：x\n原因：y\n处理：z\n", encoding="utf-8")
    (d / "liucheng.txt").write_text(
        "# 执行流\n\nliucheng_biao/A.1\n", encoding="utf-8")
    (d / "liucheng_biao" / "A.1.txt").write_text(
        "# A.1 · 一步\n\n## 时机\n- a\n\n## 条件\n- b\n\n## 做什么\n- c\n\n## 下一跳\n- d\n\n## 来源\n- ctf-pwn/0001 buzou/01.txt\n",
        encoding="utf-8")
    (d / "zhiling.txt").write_text("# 命令速查\n", encoding="utf-8")
    for f, head in (("suoyin.txt", "# 案例id | 产出条目"), ("rizhi.txt", "# 更新日志"),
                    ("yongfa.txt", "# 实战使用日志")):
        (d / f).write_text(head + "\n★\n", encoding="utf-8")
    real = None
    xin = REPO / "zhishiku-gengxin" / "xinxi.txt"
    if xin.is_file():
        m = re.search(r"gengxin_wei_win:\s*(\S+)", xin.read_text(encoding="utf-8"))
        if m:
            cand = Path(m.group(1)) / "ctf-pwn" / "validate.py"
            if cand.is_file():
                real = cand
    if real is None:
        return d, None
    shutil.copy(real, d / "validate.py")
    return d, d / "validate.py"


def test_validate_matrix(sb: Path):
    section("10. validate.py 破坏矩阵")
    d, vp = _validated_domain(sb)
    if vp is None:
        print("  (skip) 拿不到真实 validate.py 模板")
        return
    rc, out = run([vp])
    check("干净的领域应全通过", rc == 0 and not re.search(r"[✗✓]|⚠|✗", out) or "全部通过" in out,
          out[-300:])

    pristine = sb / "vpristine"
    if pristine.exists():
        shutil.rmtree(pristine)
    shutil.copytree(d, pristine)

    def mut(label, fn, expect, kind="error"):
        shutil.rmtree(d)
        shutil.copytree(pristine, d)
        fn()
        rc, out = run([d / "validate.py"])
        want = "✗" if kind == "error" else "⚠"
        hit = any(expect in ln and want in ln for ln in out.splitlines())
        check(f"矩阵：{label}", hit, f"期望 {want} {expect!r}，实得:\n{out[-400:]}")

    mut("缺 yongfa.txt", lambda: (d / "yongfa.txt").unlink(),
        "缺必备文件: yongfa.txt")
    mut("yongfa 非法行", lambda: (d / "yongfa.txt").write_text(
        "# 实战使用日志\n2026-09-01 | k | 也许 | - | -\n★\n", encoding="utf-8"),
        "yongfa.txt L2 结果不合法")
    mut("suoyin 丢哨兵", lambda: (d / "suoyin.txt").write_text("# 案例id | 产出条目\n", encoding="utf-8"),
        "★ 哨兵数=0")
    mut("suoyin 哨兵重复", lambda: (d / "suoyin.txt").write_text("# x\n★\n★\n", encoding="utf-8"),
        "★ 哨兵数=2")
    mut("liucheng 引用不存在的卡片", lambda: (d / "liucheng.txt").write_text(
        "# 执行流\n\nliucheng_biao/GHOST.9.txt\n", encoding="utf-8"),
        "引用卡片 GHOST.9.txt 不存在")
    mut("shengming 非法状态", lambda: (d / "shengming.txt").write_text(
        "# 轮次：1\n# 满值：3\n# 键 | 生命周期 | 最后使用 | 状态\nk | 2 | - | 乱状态\n", encoding="utf-8"),
        "shengming.txt 状态不合法")
    mut("缺 liucheng_biao 目录", lambda: shutil.rmtree(d / "liucheng_biao"),
        "缺 liucheng_biao/ 目录")
    mut("tieuli 条目缺来源", lambda: (d / "tieuli.txt").write_text(
        "# 铁律\n\n- 要点一\n  来源：ctf-pwn/0001 buzou/01.txt 步骤a\n- 要点二\n", encoding="utf-8"),
        "条目 2 / 来源 1", kind="warn")
    mut("cuowu 段缺三段式", lambda: (d / "cuowu.txt").write_text(
        "# 常见错误\n\n## 错误甲\n现象：x\n原因：y\n处理：z\n\n## 错误乙\n现象：x\n",
        encoding="utf-8"),
        "段落 2 / 原因：", kind="warn")
    mut("树上步号无卡片", lambda: (d / "liucheng.txt").write_text(
        "# 执行流\n\nliucheng_biao/A.1\nH.leak.9\n", encoding="utf-8"),
        "无对应卡片", kind="warn")
    mut("卡片缺字段", lambda: (d / "liucheng_biao" / "A.1.txt").write_text(
        "# A.1\n\n## 时机\n- a\n", encoding="utf-8"),
        "缺字段 条件", kind="warn")
    mut("来源悬空", lambda: (d / "liucheng_biao" / "A.1.txt").write_text(
        "# A.1\n\n## 时机\n- a\n\n## 条件\n- b\n\n## 做什么\n- c\n\n## 下一跳\n- d\n\n## 来源\n- ctf-pwn/9999 buzou/01.txt\n",
        encoding="utf-8"),
        "悬空来源: ctf-pwn/9999", kind="warn")
    shutil.rmtree(pristine, ignore_errors=True)


# ------------------------------------------------------------------ 11 安装/同步
def _fake_repo(base: Path, skills=("zhishiku-caiji", "zhishiku-tilian", "zhishiku-gengxin", "zhishiku-chuli")):
    """造一个最小仓库骨架（install.sh / sync.sh + 各 skill 的 SKILL.md 与 xinxi.txt.example）。"""
    base.mkdir(parents=True, exist_ok=True)
    for f in ("install.sh", "sync.sh"):
        shutil.copy(REPO / f, base / f)
    for n in skills:
        (base / n).mkdir(parents=True, exist_ok=True)
        (base / n / "SKILL.md").write_text(
            f'---\nname: {n}\ndescription: x\nmetadata:\n  version: "1.0.0"\n---\n\n'
            f'# {n}\n\n路径例：`C:/Users/xi/.pi/agent/skills/{n}/x`\n'
            f'与 `C:\\Users\\xi\\.pi\\agent\\skills\\{n}`\n',
            encoding="utf-8")
    for n, key in (("zhishiku-caiji", "caiji_wei"), ("zhishiku-tilian", "tilian_wei"),
                   ("zhishiku-gengxin", "gengxin_wei")):
        (base / n / "xinxi.txt.example").write_text(
            f"{key}_win: {{{{DATA_WIN}}}}\n{key}_linux: {{{{DATA_LINUX}}}}\n", encoding="utf-8")
    (base / "zhishiku-gengxin" / "scripts").mkdir(exist_ok=True)
    (base / "zhishiku-gengxin" / "scripts" / "yongfa.py").write_text(
        '# 路径例 C:/Users/xi/.pi/agent/skills/x\n', encoding="utf-8")
    return base


def _bash_exe():
    """必须用 git-bash，不能用 System32\\bash.exe（那是 WSL 的 bash，uname -s 报 Linux，
    会把 /c/... 路径与 MINGW 分支全弄错）。"""
    cands = [os.environ.get("GIT_BASH"),
             r"C:\Program Files\Git\bin\bash.exe",
             r"C:\Program Files (x86)\Git\bin\bash.exe",
             r"C:\Program Files\Git\usr\bin\bash.exe"]
    for c in cands:
        if c and pathlib.Path(c).is_file():
            return c
    return shutil.which("bash") or "bash"


def _bash(args, cwd=None, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    p = subprocess.run([_bash_exe()] + [str(a) for a in args], cwd=cwd, env=e,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def posix(p):
    """向 git-bash 传路径时必须用 /c/... 形式：原生进程传 C:\\x\\y 给 MSYS bash
    会被吃掉反斜杠（实测变成 C:xy）。"""
    s = str(p).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    return f"/{m.group(1).lower()}/{m.group(2)}" if m else s


def test_install(sb: Path):
    section("11a. install.sh 行为")
    repo = _fake_repo(sb / "irepo")
    droot = sb / "idata"
    skills = sb / "iskills"

    rc, out = _bash(["install.sh", "--copy", "--force-xinxi", "--data-root", posix(droot)],
                    cwd=repo, env={"SKILLS_ROOT": posix(skills)})
    check("install --data-root 成功", rc == 0, out[-300:])
    xin = (repo / "zhishiku-caiji" / "xinxi.txt").read_text(encoding="utf-8") if (repo / "zhishiku-caiji" / "xinxi.txt").is_file() else ""
    check("xinxi 指向 --data-root", str(droot).replace("\\", "/") in xin or str(droot) in xin, xin)
    check("xinxi 无残留占位符", "{{" not in xin, xin)
    check("建了三个数据根", all((droot / k).is_dir() for k in ("caiji_wei", "tilian_wei", "gengxin_wei")),
          str(list(droot.iterdir()) if droot.is_dir() else None))
    check("四个 skill 已复制", all((skills / n / "SKILL.md").is_file()
                                for n in ("zhishiku-caiji", "zhishiku-tilian",
                                          "zhishiku-gengxin", "zhishiku-chuli")),
          str(sorted(p.name for p in skills.iterdir()) if skills.is_dir() else None))

    before = xin
    rc, out = _bash(["install.sh", "--skip-link", "--skip-xinxi"], cwd=repo, env={"SKILLS_ROOT": posix(skills)})
    check("--skip-xinxi 不动 xinxi", rc == 0 and (repo / "zhishiku-caiji" / "xinxi.txt").read_text(encoding="utf-8") == before)

    rc, out = _bash(["install.sh", "--skip-link"], cwd=repo, env={"SKILLS_ROOT": posix(skills)})
    check("默认路径不同时警告并保留", "keeping it" in out or "already points" in out, out[-300:])
    check("警告后 xinxi 未被覆盖",
          (repo / "zhishiku-caiji" / "xinxi.txt").read_text(encoding="utf-8") == before)


def test_sync(sb: Path):
    section("11b. sync.sh 行为")
    repo = _fake_repo(sb / "srepo")
    harness = sb / "sharness" / ".codex" / "skills"
    for n in ("zhishiku-caiji", "zhishiku-tilian", "zhishiku-gengxin", "zhishiku-chuli"):
        (harness / n).mkdir(parents=True)
    (repo / "zhishiku-caiji" / "xinxi.txt").write_text("caiji_wei_win: X\n", encoding="utf-8")

    rc, out = _bash(["sync.sh", "--target", posix(harness), "--source-segment", ".pi/agent"], cwd=repo)
    check("sync 写入成功", rc == 0, out[-300:])
    got = (harness / "zhishiku-caiji" / "SKILL.md").read_text(encoding="utf-8")
    check("harness 段被替换", ".codex/skills" in got and ".pi/agent" not in got, got[:300])
    check("反斜杠写法也替换", ".codex\\skills" in got, got[:400])
    check("同步了 scripts/", (harness / "zhishiku-gengxin" / "scripts" / "yongfa.py").is_file())
    check("未碰 xinxi.txt",
          (repo / "zhishiku-caiji" / "xinxi.txt").read_text(encoding="utf-8") == "caiji_wei_win: X\n")

    rc, out = _bash(["sync.sh", "--target", posix(harness), "--check"], cwd=repo)
    check("--check 同步态返回 0", rc == 0 and "all targets in sync" in out, out[-200:])

    (repo / "zhishiku-chuli" / "SKILL.md").write_text("# 改了\n", encoding="utf-8")
    rc, out = _bash(["sync.sh", "--target", posix(harness), "--check"], cwd=repo)
    check("--check 抓出漂移并返回 1", rc == 1 and "DRIFT" in out, f"rc={rc} {out[-200:]}")
    rc, out = _bash(["sync.sh", "--target", posix(harness)], cwd=repo)
    check("再同步修复漂移", rc == 0)
    rc, out = _bash(["sync.sh", "--target", posix(harness), "--check"], cwd=repo)
    check("修复后 --check 回 0", rc == 0, out[-150:])

    rc, out = _bash(["sync.sh", "--target", posix(sb / "不存在")], cwd=repo)
    check("目标不存在时跳过而非报错", rc == 0, out[-200:])


# ------------------------------------------------------------------ 12 仓库契约
def test_repo_contracts():
    section("12. 仓库静态契约")

    # 12a. 每个 scripts/ 文件都必须在所属 SKILL.md 里被提到
    for skill in SKILLS:
        sdir = REPO / skill / "scripts"
        if not sdir.is_dir():
            continue
        doc = (REPO / skill / "SKILL.md").read_text(encoding="utf-8")
        for f in sorted(sdir.iterdir()):
            if f.is_file():
                check(f"{skill}: scripts/{f.name} 在 SKILL.md 里被引用",
                      f"scripts/{f.name}" in doc, "孤儿脚本")

    # 12b. SKILL.md 里引用的 scripts/xxx.py 必须存在（允许跨 skill 引用，
    #      例：chuli 里写 zhishiku-gengxin/scripts/yongfa.py）
    all_scripts = set()
    for skill in SKILLS:
        sd = REPO / skill / "scripts"
        if sd.is_dir():
            all_scripts |= {f.name for f in sd.iterdir() if f.is_file()}
    for skill in SKILLS:
        doc = (REPO / skill / "SKILL.md").read_text(encoding="utf-8")
        for ref in sorted(set(re.findall(r"scripts/([\w.]+)\.py", doc))):
            check(f"{skill}: 引用的 scripts/{ref}.py 存在", f"{ref}.py" in all_scripts,
                  "在任一 skill 的 scripts/ 下都找不到")

    # 12c. xinxi.txt.example 只含两个已知占位符
    for skill, key in (("zhishiku-caiji", "caiji_wei"), ("zhishiku-tilian", "tilian_wei"),
                       ("zhishiku-gengxin", "gengxin_wei")):
        p = REPO / skill / "xinxi.txt.example"
        if not check(f"{skill}: xinxi.txt.example 存在", p.is_file()):
            continue
        t = p.read_text(encoding="utf-8")
        check(f"{skill}: example 含两个占位符", "{{DATA_WIN}}" in t and "{{DATA_LINUX}}" in t, t)
        check(f"{skill}: example 无未知占位符",
              set(re.findall(r"\{\{(\w+)\}\}", t)) == {"DATA_WIN", "DATA_LINUX"}, t)
        check(f"{skill}: example 键名正确", f"{key}_win:" in t and f"{key}_linux:" in t, t)

    # 12d. 骨架的 append-only 文件哨兵唯一
    sk = (REPO / "examples/domain-skeleton")
    for f in ("yongfa.txt", "suoyin.txt", "rizhi.txt"):
        p = sk / f
        if p.is_file():
            c = p.read_text(encoding="utf-8")
            check(f"骨架 {f}: ★ 恰为 1", c.count("★") == 1 and len(re.findall(r"^★$", c, re.M)) == 1, repr(c))

    # 12f. 行尾与可执行性契约（CRLF 的 .sh 会让 bash 直接跑不起来）
    check(".gitattributes 存在", (REPO / ".gitattributes").is_file())
    for p in sorted(REPO.rglob("*.sh")):
        if ".git" in p.parts:
            continue
        raw = p.read_bytes()
        check(f"{p.relative_to(REPO)} 为 LF", raw.count(b"\r\n") == 0, "含 CRLF，bash 会报 $'\\r'")
        rc, out = _bash(["-n", p])
        check(f"{p.relative_to(REPO)} 语法可解析", rc == 0, out[:200])
    for p in sorted(REPO.rglob("*.py")):
        if ".git" in p.parts or "__pycache__" in p.parts:
            continue
        check(f"{p.relative_to(REPO)} 为 LF", p.read_bytes().count(b"\r\n") == 0, "含 CRLF")
    ps1 = REPO / "install.ps1"
    if ps1.is_file():
        raw = ps1.read_bytes()
        check("install.ps1 带 UTF-8 BOM", raw[:3] == b"\xef\xbb\xbf",
              "无 BOM 时 PowerShell 5.1 在 GBK 代码页下会语法报错")

    # 12g. 一键入口与发布包基础设施
    cmd = REPO / "install.cmd"
    if check("install.cmd 存在", cmd.is_file()):
        raw = cmd.read_bytes()
        check("install.cmd 为 CRLF（cmd.exe 需要）", raw.count(b"\r\n") > 0 and raw.count(b"\n") == raw.count(b"\r\n"),
              f"CRLF={raw.count(bytes([13, 10]))} LF={raw.count(bytes([10]))}")
        check("install.cmd 是纯 ASCII（避免代码页乱码）",
              all(b < 128 for b in raw), "含非 ASCII 字节")
        check("install.cmd 调 install.ps1", b"install.ps1" in raw)
    check("QUICKSTART.txt 存在", (REPO / "QUICKSTART.txt").is_file())
    check("pack.sh 存在", (REPO / "pack.sh").is_file())
    ga = (REPO / ".gitattributes").read_text(encoding="utf-8") if (REPO / ".gitattributes").is_file() else ""
    check(".gitattributes 覆盖 *.cmd", "*.cmd" in ga, ga)
    gi = (REPO / ".gitignore").read_text(encoding="utf-8")
    check(".gitignore 忽略 dist/", "dist/" in gi)

    # 12e. .gitignore：数据根忽略、占位保留（需要 git）
    try:
        def ignored(rel):
            p = subprocess.run(["git", "check-ignore", "-q", rel], cwd=REPO)
            return p.returncode == 0
        check("gitignore 忽略 caiji_wei 内容", ignored("caiji_wei/x.txt"))
        check("gitignore 忽略领域知识文件", ignored("gengxin_wei/ctf-pwn/tieuli.txt"))
        check("gitignore 保留 gengxin_wei/suoyin.txt", not ignored("gengxin_wei/suoyin.txt"))
        check("gitignore 忽略 xinxi.txt", ignored("zhishiku-caiji/xinxi.txt"))
    except OSError:
        print("  (skip) 没有 git")


# ------------------------------------------------------------------ main
def main():
    sb = Path(tempfile.mkdtemp(prefix="zhishiku-selftest-"))
    try:
        test_static()
        test_usage(sb)
        test_tick(sb)
        test_anomaly(sb)
        test_lineendings(sb)
        test_snapshot(sb)
        test_key_contract(sb)
        test_validate_matrix(sb)
        test_install(sb)
        test_sync(sb)
        test_repo_contracts()
        test_live_data()
        test_e2e_correction(sb)
    finally:
        if KEEP:
            print(f"\n沙箱保留在 {sb}")
        else:
            shutil.rmtree(sb, ignore_errors=True)

    fails = [(n, d) for n, ok, d in RESULTS if not ok]
    print(f"\n{'='*60}")
    print(f"共 {len(RESULTS)} 项，通过 {len(RESULTS)-len(fails)}，失败 {len(fails)}")
    for n, d in fails:
        print(f"  FAIL {n}  {d[:200]}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
