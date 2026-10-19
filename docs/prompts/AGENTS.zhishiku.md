<!--
来源：作者本机 harness 提示词中的 zhishiku 相关段落，已脱敏。
用法：把下面内容并入你自己的 AGENTS.md（或等价的常驻提示词）。
路径约定：<数据根> = 知识库数据根（默认 ~/.zhishiku）；<skill 根> = ~/.pi/agent/skills。
-->

# Agent notes

## zhishiku 流水线：中断恢复（MUST）

目标：避免 `chuli →（有标记才）caiji → tilian → gengxin` 因上下文压缩、话题岔开、会话重载或中途报错而**整链作废**。细节以各 `zhishiku-*/SKILL.md` 为准。

### 阶段（只许前进，不许装没发生过）

```text
C0  chuli 处理中（缺口写入 chuli/xinxi.txt，caiji标记：1；禁止开 caiji）
C1  用户侧结果已交付（xinxi 该任务 caiji标记：0 则可在此结束库务）
C2  caiji标记：1 → caiji 采集/归档中
C3  tilian 提炼中
C4  gengxin 回注中
C5  收尾 --tick（及 IoT 交接若适用）→ 链闭
```

- **无采集标记**（该任务 `caiji标记：0`）：`C0 → C1 → C5（可只 tick）→ 链闭`。**直接把结果交给用户**，禁止空跑 caiji/tilian/gengxin。
- **有采集标记**（该任务 `caiji标记：1`）：`C0 → C1（先交付）→ C2 → C3 → C4 → C5 → 链闭`。交付**不得**等采写库完成。

### 两块磁盘真相

| 文件 | 管什么 |
|---|---|
| `zhishiku-chuli/xinxi.txt`（缺口板） | 各任务节：有无缺口、`caiji标记`、标记明细 |
| `resume/current.md`（续跑条） | 链阶段 C0–C5/闭、下次动作 |

- 判定采不采、续不续 → **以 `xinxi.txt` 该任务节为准**；续跑条「采集标记/摘要」只是摘要，冲突时回修续跑条。
- 打标 = 写 `xinxi.txt`，禁止只放在会话记忆。
- 一块任务一节；有缺口 → 该节 `caiji标记：1`；无缺口 → `0`。

**缺口板路径**：`~/.pi/agent/skills/zhishiku-chuli/xinxi.txt`

> **字段名以该文件表头为准**。注意两个文件的字段名**不同**：
> - 缺口板 `xinxi.txt` 用 **`caiji标记：0|1`**
> - 续跑条 `current.md` 用 **`采集标记：<条数>`**（只是摘要）
>
> 两者名字不一样，脚本/扩展解析时别混用（历史上混用导致过「标记明明是 1 却被判成 0、空采被拦」）。

### 续跑条（防上下文丢失）

凡进入「使用知识库系统」或已在 C0–C4，**每个阶段切换时**更新续跑条。

```text
<数据根>/resume/current.md          # 默认 ~/.zhishiku/resume/current.md
```

Windows 同源：`%USERPROFILE%\.zhishiku\resume\current.md`。目录不存在则创建；`resume/done/` 同理。

#### 多窗口并发（MUST，单文件 + 版本号）

多个窗口会同时改同一份 `current.md`。**禁止用 write 整文件覆盖**，一律走脚本：

```bash
S=<skill 根>/zhishiku-chuli/scripts/resume_lock.py   # 默认 ~/.pi/agent/skills/...

python3 $S show                                              # 看状态（含写者/心跳）
python3 $S commit --writer <window-id> --field 阶段=C3 ...    # owner 推进（版本 +1）
python3 $S patch  --writer <window-id> --field 原路径=/a/bin  # 巡检改单行（不夺权）
python3 $S note   --writer <window-id> "巡检意见"               # 追加巡检记录
python3 $S takeover --writer <window-id>                     # 接管（需心跳过期）
python3 $S beat   --writer <window-id>                       # 只刷心跳
```

**窗口身份**：`ctx.sessionManager.getSessionId()` 取前 8 位（如 `01a14e8c`）。不需要序号，UUID 前段就是唯一短标识。

规则：

| 角色 | 允许的动作 | 禁止 |
|---|---|---|
| **解题窗口（owner）** | `commit` 推进阶段、`beat` 刷心跳 | 不用 write 直接改文件 |
| **巡检窗口** | `patch` 改错行、`note` 留意见 | 改别人合法的阶段推进；整文件覆盖 |
| **任何窗口** | `show` 查看 | 未过期且未 `--force` 时抢占 |

- **冲突优先停手**：`commit` 返回码 2（版本不符）/ 3（写者不是自己）→ 先 `show` 看对方写到哪，不要加 `--force` 硬盖。
- **心跳超时 30 分钟** 可被接管；接管会自动写入巡检记录。
- **巡检纠错不递增版本**：版本号只反映 owner 的阶段推进，避免被纠错动作搅乱。
- 脚本用 `flock` + 临时文件 `os.replace`，不会写出半截文件。

最少字段：

```text
版本：<整数，每次 owner commit +1>
写者：<sessionId 前8位>
心跳：<YYYY-MM-DD HH:MM，超 30 分钟可被接管>
---
领域：<名>
阶段：C0|C1|C2|C3|C4|C5|闭
题目：<可指认名或 ->
原路径：<绝对路径或未知>
采集标记：0|<条数>（与 chuli/xinxi.txt 该任务一致；冲突以 xinxi 为准）
标记摘要：<一句；无则 -；明细在 chuli/xinxi.txt>
caiji：<领域/编号或 ->
tilian：待|中|完|-
gengxin：待|中|完|-
用户已交付：是|否
阻塞：<无|本地模型|等用户|错误一句>
下次动作：<一句可执行下一步>
更新：<YYYY-MM-DD HH:MM>
```

规则：

1. **写续跑条先于长回复收尾**；阶段变了却不更新 = 违规。
2. 链闭 → `阶段：闭`；或把文件移到 `resume/done/YYYYMMDD-HHMM-<领域>.md` 后，把 `current.md` 写成「无进行中 / 阶段：闭」。
3. 续跑条**不是**案例正文：不代替 caiji 的 `->` 块，只指向阶段与磁盘真相。
4. 续跑条**不会**被 Pi 自动注入；必须按下面「每轮开工自检」主动 `read`。

### 每轮开工自检（新用户消息 / 压缩后 / 重载后）

处理新请求前**先看** `resume/current.md`（存在且阶段≠闭时按表续跑）：

| 磁盘/续跑显示 | 动作 |
|---|---|
| 无 current 或阶段=闭 | 按新消息正常处理 |
| 有 `状态：暂定` 的任务 | **只点名一次**（哪些、挂多久、恢复点），**不自动开工、不催**；用户提及才恢复「进行中」 |
| C0，用户又问别的事 | **短答岔问**；**不丢** `xinxi.txt` 标记与续跑；答完默认继续原链，除非用户取消 |
| C0/C1 未交付 | 优先完成用户侧结果交付，再谈库务 |
| C1 且该任务 `caiji标记：1`，caiji 未归档 | **从 C2 续**（caiji 输入 = xinxi 明细），不要重做整题 |
| caiji `flag=1/2` 或 `dai/` 未进 `hui/` | 续 caiji 协议至归档 |
| 已 hui、tilian_wei 无对应稿/未完成 | 续 **tilian** |
| tilian 完、容器未回注 | 续 **gengxin** |
| 回注完、未 `--tick` | 只补 **C5** |
| 本地模型模式且阶段∈{C2,C3,C4} | 不写库；保留续跑条；报告需主 agent 续写库链 |

**禁止**：

- 因岔话题、上下文变短、总结失败，就把进行中的链**当不存在**；
- 不读或丢弃 `xinxi.txt` 里未闭的 `caiji标记：1` 任务节；
- `caiji标记：0` 却「为了完整」重跑整链；
- `caiji标记：1` 已交付却**忘记** C2–C4；
- 不读 `xinxi.txt` / `biao_xin` / `dai|hui` / `tilian_wei` / 续跑条就从头开新案（除非用户明确要求重做）；
- 用回忆补 caiji `结果`（续跑也必须**复现再写**）；用回忆冒充 `xinxi` 明细。

### 与用户岔开时

1. 先更新续跑条 `阻塞：等用户` 或保留 `下次动作`。
2. 回答岔开问题；**不清理** `xinxi.txt` 标记、不把 `阶段` 改成闭。
3. 答完后**主动**用一两句提示「原 zhishiku 链停在 Cx，下一步=…」，并继续执行，除非用户明确取消。
4. 用户说取消 → `阶段：闭` 并注明取消；半成品案例按 caiji 规则保留（缺口可标未采集，不删已有样本）。

### 压缩 / 新会话

- 先读 `resume/current.md` + `zhishiku-chuli/xinxi.txt` + 对应领域 `caiji_wei`/`tilian_wei` 状态，再说话。
- 只凭聊天记忆断定「已经回注完」或「有/无标记」无效；以磁盘、`xinxi.txt` 与续跑条为准。

### 一句话

**结果先给用户；缺口写入 chuli/xinxi（caiji标记：1）；有标记再写库；阶段落盘；打断就短答并续跑；暂定项每轮点名但不自动开工；禁止无声丢链。**
