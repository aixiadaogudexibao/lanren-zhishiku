<!--
来源：作者本机 SYSTEM.md（常驻提示词）中的 zhishiku 相关段落，已脱敏。
用法：把这几个段落并入你自己的 SYSTEM.md / 常驻提示词。
路径约定：<数据根> = 知识库数据根（默认 ~/.zhishiku）；<skill 根> = ~/.pi/agent/skills。
-->

## Skills 路由（匹配则 read SKILL.md）

**知识库闭环（zhishiku）**

| Skill | 何时 |
|---|---|
| **zhishiku-chuli** | 用户说「使用/开启知识库系统」；按领域执行流处理 |
| **zhishiku-caiji** | chuli 结束后有采集标记；或显式要采集（处理中禁止提前 caiji） |
| **zhishiku-tilian** | 采集归档后提炼 |
| **zhishiku-gengxin** | 提炼后回注容器；或用户要求更新某领域 |
| **zhishiku-github** | 推 lanren-zhishiku 到 GitHub、回填 skill 漂移 |

**编排硬规则**（细文在 AGENTS + 各 skill）：

1. 每轮先看续跑条；阶段≠闭则续跑，禁止无声丢链。
2. 处理中遇未记录 → **只打标继续**，禁止中途 caiji。
3. **无标记** → 直接把结果交给用户；不空跑 caiji/tilian/gengxin。
4. **有标记** → **先交付用户**，再按已通思路 **复现**采集 → tilian → gengxin。
5. 库已覆盖的题 → 可只 `--tick`，不无故开 gengxin。
6. 本地模型可打标做题，**禁止写库**（C2–C4 留给主 agent）。

## 知识库与磁盘真相（chuli 时）

完整续跑规则在 **AGENTS.md**（通常已在 `<project_context>`）；本段只给索引，不是 AGENTS 全文。**何时必须看 AGENTS**：知识库模式；进行中的 `chuli→caiji→tilian→gengxin`；compact / 话题岔开后链可能未闭。若 project_context 缺 AGENTS，继续 zhishiku 前先 read 它。

| 磁盘真相 | 路径 | 管什么 |
|---|---|---|
| AGENTS | ~/.pi/agent/AGENTS.md | 阶段与自检细则 |
| 缺口板 | ~/.pi/agent/skills/zhishiku-chuli/xinxi.txt | 有无缺口、`caiji标记` 0/1（字段名以文件表头为准） |
| 续跑条 | <数据根>/resume/current.md | 链阶段 C0–C5/闭 |

职责索引：① 新消息/compact 后先看续跑条，阶段≠闭则续跑，禁止无声丢链；② 无标记 → 直接交结果，不空跑 caiji/tilian/gengxin；③ 有标记 → 先交付，再 caiji（复现再写）→ tilian → gengxin；④ 阶段切换都更新续跑条，状态在磁盘不在聊天记忆。

数据根：`<数据根>`（默认 `~/.zhishiku/`）

| 目录 | 含义 |
|---|---|
| gengxin_wei/<领域>/ | 可执行知识（liucheng / tools / yuanze …） |
| caiji_wei/ | 采集 |
| tilian_wei/ | 提炼稿 |
| resume/ | 链阶段续跑 |

常见领域：ctf-pwn、ai_iot 等。处理前读该领域 `tieuli` / `liucheng_biao` / 相关 `tools/*.txt`；工具用法以容器内说明为准。

## 扩展（extensions/）

三个职责独立的扩展，各自可单独关掉：

| 文件 | 管什么 | 关键事件 |
|---|---|---|
| `zhishiku-domain.ts` | 按领域注入铁律 / 流程表 / 工具清单 | `before_agent_start` |
| `zhishiku-guard.ts` | 续跑条注入、压缩快照重建、拦空采 | `before_agent_start` / `session_before_compact` / `tool_call` |
| `dangerous-op-guard.ts` | 危险命令 / 覆盖保护路径前确认 | `tool_call` |
| `snapshot-manager.ts` | 快照统一台账 + 生命周期 + 过期清理 | `session_start` / `agent_end` |

**zhishiku-domain**

- 判定顺序：显式 `/domain` 锁定 > 题目关键字（≥2 分）> 续跑条 > cwd
- 三路入口：自动判定 / 命令 `/domain` / 工具 `zhishiku_domain`
- 只注入索引，不注正文；正文按 `tieuli.txt` / `liucheng_biao/` 路径 read

**zhishiku-guard**

- 每轮从磁盘重读 `resume/current.md` 与缺口板，注入阶段/标记/下次动作
- `caiji标记` 为 0 时读 `zhishiku-caiji/SKILL.md` 会被 **block**（拦空采）
- 压缩前快照续跑条到 `resume/done/`，压缩后按磁盘重建
- 只读不写知识库；写库仍归 skill

**snapshot-manager**

- 台账：`<数据根>/_snapshots/INDEX.md`（树形）+ `index.json`
- 扫四类：`gengxin _snap/`、`resume/done/`、`_bak_*`、`skill *.bak-*`
- 命令：`/snapshot` 看统计、`/snapshot md` 看完整台账、`/snapcheck` 列过期候选
- **只列不删**：清理要 `/snapcheck --delete` 且确认
- 生命周期表在扩展内 `LIFECYCLE` 常量，改了要同步 `安全` 说明
