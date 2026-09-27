# 架构：四层知识库闭环

```text
知识库层：  zhishiku-caiji（采集） ─▶ zhishiku-tilian（提炼） ─▶ zhishiku-gengxin（容器）
                                                                        │
                                                              读知识    │    ▲ 回注
                                                                        ▼    │
处理层：                        zhishiku-chuli（处理用户请求） ───────────────┘
                                          │
                                          └─ 未记录缺口 ─▶ caiji ─▶ tilian ─▶ gengxin
```

| Skill | 角色 | 数据根 |
|---|---|---|
| `zhishiku-caiji` | 逐条采集「指令 ↔ 原始输出」案例 | `<数据根>/caiji_wei/<领域>/` |
| `zhishiku-tilian` | 案例 → 知识点 / 执行流 / 错误 / 指令表 | `<数据根>/tilian_wei/<领域>/` |
| `zhishiku-gengxin` | 按领域回注到可执行知识容器 | `<数据根>/gengxin_wei/<领域>/` |
| `zhishiku-chuli` | 用容器处理任务；缺口触发采集闭环 | （只读 gengxin，经 xinxi 定位） |

## 领域

一个领域 = 一个文件夹名（如 `python-env`）。四层共用同一领域名，禁止中途改名。

## 数据根

三个 `*_wei` 目录同属**一个数据根**，与 skill 定义（`SKILL.md`）分离。

- 默认：仓库根目录。
- 推荐：`install --data-root <dir>` 放到 harness 与仓库之外，例如 `~/.zhishiku`。

把数据根搬出 harness 目录，是为了避免：

1. **重装覆盖** —— `install --force` / 换版本时不会碰到知识库。
2. **换 harness 丢库** —— 数据不属于任何 harness 的 `skills/` 目录。
3. **多 harness 分裂** —— pi 与 codex 各存一份，导致同一知识库两条分叉。
4. **路径污染样本** —— 采集时执行的命令若引用 harness 路径，`->` 块的「结果」会因 harness 而异，样本失去可移植性。

## 路径约定

每个带数据根的 skill 用 `xinxi.txt`：

```text
<root>_win:   <Windows 绝对路径>
<root>_linux: <Linux/WSL 绝对路径>
```

两行必须指向**同一份**目录。`install` 从 `xinxi.txt.example` 生成。

`install` **不覆盖**已存在且内容不同的 `xinxi.txt`（只警告），避免重跑把知识库指到空目录；要覆盖用 `--force-xinxi` / `-ForceXinxi`。

## 多 harness 同步

`SKILL.md` 的**唯一源是本仓库**，各 harness 的 `skills/` 是副本。

```text
repo/*/SKILL.md --sync.sh--> <harness>/skills/*/SKILL.md
```

`sync.sh` 只做一件事：把源里作为示例出现的 `.pi/agent` 段换成目标 harness 的段（`.codex` 那份读起来就是 `.codex`）。其余逐字节一致，行尾不变。

不同步的两类东西：

- `xinxi.txt` —— 机器/ harness 配置，各副本本就指向同**一个**数据根，无需同步。
- `*_wei/**` —— 活数据，已不在 skills 目录里。

## 哨兵写入

`qingdan.txt`、`buzou/*.txt`、`suoyin.txt`、`rizhi.txt` 等 append-only 文件末尾保留独占一行的 `★`。追加 = 把 `★` 替换为 `新内容\n★`，不读全文。

## 实战使用日志

知识条目有两个**互不替代**的计数：

| 计数 | 含义 | 谁写 | 存在哪 |
|---|---|---|---|
| `命中：N` | **来源支撑数**：多少案例样本印证了这条 | `tilian` 重复提炼时 +1 | 条目自身 |
| 实战使用行 | **实战效果**：用了几次、成/败各几次 | `chuli` 收尾时追加 | `gengxin_wei/<领域>/yongfa.txt` |

`yongfa.txt` 是 append-only（末尾 `★`），键取 `liucheng_biao/<标号>` / `tools/<工具名>` / `cuowu/<错误特征>` / `zhiling/<操作>`。`gengxin` 只读不改。统计用 `zhishiku-gengxin/scripts/yongfa.py <数据根>/<领域>`，输出「用过」与「零使用」两张表。

写入权限：`chuli` 是唯一写 `yongfa.txt` 的角色（且只许追加）；本地模型会话一律不记账。

## 条目生命周期

`yongfa.txt` 回答「用了几次」，`shengming.txt` 回答「多久没人用了」。

`gengxin_wei/<领域>/shengming.txt` 是**维护型状态表**（非 append-only，可从 `yongfa.txt` 重建）：

```text
# 轮次：12
# 满值：3
# 键 | 生命周期 | 最后使用 | 状态
liucheng_biao/H.leak.3 | 3 | 2026-09-27 | 活跃
liucheng_biao/H.old.1 | 0 | 2026-08-01 | 待裁决
```

- 生命周期是倒计时，满值 `L`（默认 3），单位是「轮次」（`chuli` 处理完一个任务 = 一轮）。
- 本轮用到的键 → 回到 `L`；没用到的 → −1；库里新增/首次见到的键 → 初始化为 `L`。
- 降到 `0` → `待裁决` → **必须询问用户**（汇总成一次问）。同意 → `--expire`（冻结，等 gengxin 落 `[候选过期]`）；不同意 → `--refresh`（刷新回 `L`）。
- **空轮次也要记账**，否则生命周期永远不动。

`chuli` 是唯一写入方，且只能经 `zhishiku-gengxin/scripts/yongfa.py --tick` 写；`gengxin` 只读。

## 回注快照

回注是覆盖式写，所以 `gengxin` 的铁律是**无快照不回注**：

```bash
python3 zhishiku-gengxin/scripts/snapshot.py <数据根>/<领域> --take --note "回注 <案例id>"
```

- 快照落在 `<领域>/_snap/<YYYYMMDD-HHMMSS>/`，含逐份副本 + `MANIFEST.txt`（路径 / 字节数 / sha256）。
- 回滚：`--rollback <快照名> --yes`。回滚前**自动再拍一份 preRollback**；「快照里没有」的文件**移到 `_orphan-<时间戳>/` 而不是删**；快照自身校验失败则**拒绝回滚**。
- 清理：`--prune --keep 5`。
- `_snap/` 不是知识目录，`yongfa.py` / `validate.py` 都不扫它。

`rizhi.txt` 的行尾带快照名，便于从日志定位「这次回注能不能回滚」。

## 领域自检

`gengxin_wei/<领域>/validate.py` 是回注收尾的体检脚本（gengxin 协议第 7 步）。它按数据根的相对位置推导 `caiji_wei`，算不得硬编码 harness 路径；并把 stdout 强制为 UTF-8，以便在 Windows 控制台（默认 GBK）也能跑。

## 本地模型边界

Ollama 等本地小模型**只允许**参与只读的 `zhishiku-chuli`（及约定的解题辅助）；**禁止**参与 caiji / tilian / gengxin 写库，防止污染。
