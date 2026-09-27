# 统一数据根与多 harness 同步

日期：2026-09-27
状态：已实施
关联任务：planing-biao / pk-000
> 本文记录来自作者本机环境；文中的领域名、案例号、条目计数已做脱敏。


## 背景

skill 定义（`SKILL.md`）在仓库里是唯一源，运行时有多个副本；知识数据则住在各运行时自己的 `skills/` 目录下。实测本机情况：

| 位置 | SKILL.md | 数据 |
|---|---|---|
| `~/zhishiku`（仓） | 源 | 空（gitignore） |
| `~/.pi/agent/skills` | 与仓逐字节相同 | 一份（作者的领域库） |
| `~/.codex/skills` | 仅差 harness 前缀 + 行尾 | 另一份（同上，手工镜像） |

## 问题

1. **重装即风险** —— `install --force` 或重新生成 `xinxi.txt` 会把数据根指到空目录，知识库"消失"。
2. **换 harness 丢库** —— 数据住在 harness 目录里，不属于任何持久位置。
3. **多 harness 分裂** —— 同一知识库出现两条分叉，且靠手工镜像保持一致。
4. **路径污染样本** —— 采集时若执行的命令引用 harness 路径，`->` 块的「结果」会因 harness 而异（实例：某案例的 `buzou/NN.txt` 在两侧记录了不同的 `.pi` / `.codex` 路径）。这违反「结果 = 原始输出」的可移植性。

同时发现两个既存缺陷：

- `install.ps1` 为 UTF-8 **无 BOM**，PowerShell 5.1 在 GBK 代码页下按 GBK 解码 → 直接语法错误，脚本根本无法运行。
- `validate.py` 硬编码了 harness 绝对路径，且 `print` emoji 在 Windows GBK 控制台崩溃 → 只在 Linux 可跑。

## 决策

**数据根与 harness 解耦，全机器唯一。**

- 三个 `*_wei/` 同属一个数据根，位于 `<数据根>/{caiji,tilian,gengxin}_wei/`。
- 默认数据根 = 仓库根（克隆即可用）。
- 推荐 `install --data-root <dir>` 把它放到 harness 与仓库之外（本机采用 `~/.zhishiku`）。
- `install` **不覆盖**内容不同的既有 `xinxi.txt`，只警告；要覆盖需显式 `--force-xinxi`。
- `SKILL.md` 由仓库单向同步到各 harness：`sync.sh` 仅替换示例路径中的 harness 段，其余逐字节一致。
- 不同步 `xinxi.txt`（各副本本就指向同一数据根）与 `*_wei/**`（已不在 skills 目录内）。

## 改动清单

- `install.sh` / `install.ps1`：新增 `--data-root` / `-DataRoot`、`--force-xinxi` / `-ForceXinxi`；写入被保护；`install.ps1` 补 UTF-8 BOM 与 `OutputEncoding`。
- `xinxi.txt.example`（3 份）：改为 `{{DATA_WIN}}` / `{{DATA_LINUX}}` 两个占位符。
- `sync.sh`（新增）：`--check` 只读校验；默认目标 `~/.pi/agent/skills`、`~/.codex/skills`。
- 占位文件迁到数据根布局：`{caiji,tilian,gengxin}_wei/.gitkeep`、`gengxin_wei/suoyin.txt`。
- `README.md` / `docs/architecture.md`：新增「多 harness / 统一数据根」与「多 harness 同步」。
- 数据侧（中立根内）：各领域的 `validate.py` 改为相对推导 caiji 路径 + 强制 UTF-8 stdout。

## 非目标

- 不改四层协议语义（采集 / 提炼 / 回注 / 处理的规则一律不动）。
- 不做知识 → skill 的自动生成（维护成本过高，已否决）。
- 不改领域隔离模型。

## 验证

- `bash sync.sh --check` → `all targets in sync`（幂等）。
- 仓 vs `~/.pi`：逐字节相同；仓 vs `~/.codex`：仅差 harness 前缀。
- `bash install.sh --skip-link`（不带 `--force-xinxi`）→ 警告并保住原数据根。
- `python validate.py`：作者两个领域的卡片全部通过（部分悬空来源是外部样本库在 Linux 挂载点，与本次无关）。
