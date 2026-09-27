# 回注快照与可回滚

日期：2026-09-27
状态：已实施
关联任务：`planing-biao` / `C:/Users/xi/zhishiku` / pk-005（对应 G5）

## 背景

`gengxin` 的回注是**覆盖式写**：把提炼结果 diff 合并进 `tieuli.txt` / `cuowu.txt` / `liucheng.txt` / `liucheng_biao/*.txt`。

原有的安全网只有两条，都不够：

1. **「不删条目」铁律** —— 只防删除，不防**改坏**。一次错误合并（比如把两个分支的条件对调）会静默改掉既有内容，而且 `[候选过期]` 之外没有任何变更痕迹。
2. **`rizhi.txt`** —— append-only，只记「做了什么」，**不存旧内容**。知道改错了也回不去。

再叠加生命周期机制（pk-002）：条目的 `[候选过期]` 标记会真的影响后续判断，改错了会持续误导。

对照开源方案（weaver-memory 的 evidence-gated reuse + rollback），缺的是**可回退的证据门槛**：动手前留底、出事后能退回、且退回动作本身也可逆。

## 决策

### 1. 回注前必拍快照（硬约束）

新增铁律 13：**无快照不回注**。动手改领域文件之前必须先跑：

```bash
python3 zhishiku-gengxin/scripts/snapshot.py <数据根>/<领域> --take --note "回注 <领域>/<案例id>"
```

快照失败（磁盘满 / 目录不可写）→ 停下报告，**不得「先改了再说」**。

### 2. 快照布局

```text
<数据根>/<领域>/_snap/<YYYYMMDD-HHMMSS>/
├── MANIFEST.txt          # 路径 <TAB> 字节数 <TAB> sha256
├── tieuli.txt            # 领域文件的逐份副本
├── liucheng_biao/A.1.txt
└── ...
```

- `_snap/` 自身**不进快照**。
- `_snap/` **不是知识目录**：`yongfa.py` 与 `validate.py` 都只扫领域根那几层，不会把副本当成知识条目重复计数。

### 3. 回滚：三重保险

```bash
python3 .../snapshot.py <领域> --rollback <快照名> --yes
```

1. **先校验快照自身**（文件齐、字节数对、sha256 符）。快照坏了就**拒绝回滚**——避免用坏快照覆盖好现状。
2. **回滚前自动再拍一份** `_snap/<快照名>-preRollback/`。所以回滚本身也可逆。
3. **「当前有、快照里没有」的文件移到 `_snap/<快照名>/_orphan-<时间戳>/`，不删**。回滚不应成为误删新知识的途径。

不带 `--yes` 时只打印将要做什么，**不动文件**。

### 4. 保留策略

`--prune --keep 5`（默认留 5 份）。快照是纯副本，领域库本身只有几百 KB，5 份足够覆盖「最近几次回注」的排错窗口。

### 5. `rizhi.txt` 行尾加快照名

```
<日期> | 回注 <领域>/<案例id>：<变更摘要> | 快照 <YYYYMMDD-HHMMSS>
```

这样从日志就能定位「这次回注对应哪个快照、能不能回滚」。

## 改动清单

- `zhishiku-gengxin/scripts/snapshot.py`：新增。`--take` / `--list` / `--rollback` / `--prune`。
- `zhishiku-gengxin/SKILL.md` → 2.9.0：数据布局与骨架加 `_snap/`；协议插入「4. 回注前拍快照」并顺延（原 4–8 → 5–9，原「### 7 回注后自检」→「### 5」，新增「### 4 回注前拍快照」）；回注算法加第 0 步；`rizhi` 行格式加快照名；铁律 13；启动自检；常见错误三条。
- `README.md`：目录加 `tests/` 与 `zhishiku-gengxin/scripts/`，新增「自测」小节。
- `tests/selftest.py`：新增快照/回滚测试段（14 项）。

## 验证

`tests/selftest.py` 覆盖：

- `--take` 生成快照，`MANIFEST` 行数 = 领域文件数，且不含 `_snap/` 自身；
- `--list` 可列出；
- 改一个文件 + 新增一个文件 → `--rollback --yes` 后**被改的恢复**、**新增的进 `_orphan` 且仍存在**、**`preRollback` 已生成**；
- 不带 `--yes` 时**确认未动任何文件**；
- 篡改快照内副本 → **拒绝回滚（rc=1）**；
- 回滚不存在的快照 → rc=1；
- `--prune --keep 1` 后只剩一份；
- 不存在的目录 → rc=2。

全部通过（自测总计 150 项）。
