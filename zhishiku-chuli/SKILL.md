---
name: zhishiku-chuli
description: Use when 用户说「使用知识库系统」或「开启知识库系统模式」，要用已积累的知识库处理某领域的用户请求（按执行流 / 错误处理 / 指令表执行）；遇到未记录情况时自动采集、扫描其他 skill 辅助解决、并回注更新知识库。
metadata:
  version: "1.6.0"
---

# 知识库处理层（zhishiku-chuli）

## 概述

本 skill 是知识库系统的**处理层**（入口 / 编排器）。

前面三个（`zhishiku-caiji` / `zhishiku-tilian` / `zhishiku-gengxin`）构成**知识库层**；本 skill 用知识库层的产物去处理用户请求，并在遇到**未记录情况**时反哺知识库，形成闭环。

## 触发词与模式

| 说法 | 含义 |
|---|---|
| **使用知识库系统** | 单次：用知识库处理**这一个**请求 |
| **开启知识库系统模式** | 持续：**所有任务**都用知识库系统处理，直到用户说「关闭知识库系统模式」 |
| 关闭知识库系统模式 / 退出知识库系统 | 恢复正常处理（不再强制走知识库） |

- 听到「使用知识库系统」→ 对**当前这一个**请求走本 skill 的处理流程。
- 听到「开启知识库系统模式」→ 进入持续模式：**之后每个用户任务**都先走本 skill（查领域知识 → 遇到未记录就调 caiji 采集 → 自动回注）。
- 模式是**会话级**的：新会话默认关闭，需用户重新开启。
- 模式开启期间，不得绕过本 skill 直接用通用能力处理任务。

## 系统全貌（四层）

```text
知识库层：  zhishiku-caiji（采集） ─▶ zhishiku-tilian（提炼） ─▶ zhishiku-gengxin（容器）
                                                                        │
                                                              读知识    │    ▲ 回注
                                                                        ▼    │
处理层：                        zhishiku-chuli（处理用户请求） ───────────────┘
                                          │
                                          └─ 遇到未记录情况 ─▶ 调用 caiji 采集 ─▶ tilian ─▶ gengxin
                                                               （自动更新知识库）
```

## 边界（何时用 / 何时不用）

| 需求 | 用哪个 |
|---|---|
| 小任务队列 / 每日任务 / 执行次数 | `planing-biao` |
| 长跑项目 / 需求 / issue / 迭代 | `chang-plan` |
| 采集执行过程 | `zhishiku-caiji` |
| 把案例提炼成知识 | `zhishiku-tilian` |
| 按领域回注 / 维护容器 | `zhishiku-gengxin` |
| **用知识库处理某领域的用户任务** | **本 skill** |

## 输入

- **用户请求**：某领域的一个任务。
- **领域知识库**：`gengxin_wei/<领域>/`
  - `liucheng.txt` 执行流**总览**（入门分诊 + 树形；怎么走）
  - `liucheng_biao/<标号>.txt` 执行流**卡片**（时机/条件/做法/下一跳；怎么做）
  - `cuowu.txt` 错误处理（会怎么错、怎么修）
  - `zhiling.txt` 命令速查（具体指令）
  - `tieuli.txt` / `yuanze.txt` / `bianjie.txt`（铁律 / 原则 / 边界）
  - `tools/<工具名>.txt` 领域专用工具使用规范（如 `tools/libcsearch.txt`）
  - `liucheng_jiu_shupai.txt` 若存在：旧竖排备份，**仅**当总览指向「尚未卡片化」时按需翻阅

知识库根来源：读 `zhishiku-gengxin/xinxi.txt`（键 `gengxin_wei`）。该文件含两行路径 `gengxin_wei_win` / `gengxin_wei_linux`，**按当前运行环境选**：Windows 取 `_win`（`C:/...`），Linux/WSL 取 `_linux`（`/media/xi/...`）；两行指向同一个文件夹。旧单行 `gengxin_wei: <路径>` 则按当前 OS 判断是否可访问，不可访问则询问用户。

## 领域

- 从用户请求判断领域，并**匹配 `gengxin_wei/` 下已有领域文件夹**（列 `gengxin_wei/suoyin.txt`）。
- 无匹配 → **询问用户**：属于哪个领域 / 是否新建领域库。
- 领域确定后不得中途更换。

## 处理协议

```text
- [ ] 1. 确定领域
- [ ] 2. 载入领域知识（总览 + 按需卡片，勿整目录塞进上下文）
- [ ] 3. 拆解用户请求为大步骤
- [ ] 4. 逐步处理（分诊 → 树选枝 → 打开当前卡片 / 指令表 / 错误处理）
- [ ] 5. 遇到未记录情况 → 调用 caiji 采集
- [ ] 6. 结束后按需自动更新（tilian → gengxin）
- [ ] 7. IoT 领域 → 样本交接 ai_iot（见下「IoT 样本交接」）
- [ ] 8. 报告
- [ ] 9. 交付物：在原题目目录留下 exp.py 与 wp（仅 pwn/CTF）
```

**1. 确定领域**：判断请求属于哪个领域，匹配已有领域库；无匹配就问用户。

**2. 载入知识（控制上下文）**：
- **必读**：`tieuli.txt` 要点、`liucheng.txt` 的「读法 + 入门分诊」；按任务类型只精读**命中的那一棵树**。
- **按需读**：当前步骤的 `liucheng_biao/<标号>.txt`（一次一卡）；`zhiling.txt` / `cuowu.txt` 相关段；`yuanze`/`bianjie` 在需要裁决时读。
- **禁止**：把整个 `liucheng_biao/` 或整份旧 `liucheng_jiu_shupai.txt` 无差别全文灌进上下文。
- 若存在 `tools/`，列出工具名，**按需**打开对应规范。

**3. 拆解请求**：把用户请求拆成有序的大步骤。

**4. 逐步处理**，每步按顺序查：

- **执行流（树形）**：
  1. 用 `liucheng.txt` **入门分诊**表，按题面条件选树（堆/栈/格式化…）。
  2. 在命中树上沿主路径走；遇 `├─/└─` 分叉，用题面对照行内 **〔条件〕** 选枝。
  3. 打开当前标号卡片 `liucheng_biao/<标号>.txt`，核对 **时机 / 条件**；不满足则走卡片「不满足时」或回到树分叉。
  4. 按卡片「做什么」执行，参数用实际值填充；完成后跟「下一跳」进下一卡。
  5. 总览写「尚未卡片化 / 见 jiu_shupai」时，**只翻** `liucheng_jiu_shupai.txt` 对应小节，不读全文件。
- `zhiling.txt`：取规范指令，填入参数后执行。
- `cuowu.txt`：预判可能出现的错误，按其「处理」提前规避或即时补救。
- `tieuli.txt` / `bianjie.txt`：遵守铁律，不越边界。
- `tools/<工具名>.txt`：任务需要某个专用工具时，读对应规范并照做。
  - **打靶机 / pwn 题需要「泄漏 libc 后确定版本」时 → 必读 `tools/libcsearch.txt`**，用 LibcSearcher 反查；多解必须 `add_condition` 消歧后再算 `system` / `str_bin_sh`；不得直接把泄漏地址当基址或跳过版本确认。
  - **领域为 `ai_iot` / IoT 固件相关时 → 必读 `tools/yangben-jiaojie.txt`**（样本交接规范），并在收尾时执行「7 IoT 样本交接」。

**5. 未记录情况（触发采集 + 扫描 skill 求助 + 回到主流程）**

判定为「未记录」的情形：

- 分诊选不进任何树，且 `liucheng_jiu_shupai` 也无对应节；
- 树上无匹配分叉 / 无对应标号卡片，且条件对不上；
- `zhiling.txt` 里没有需要的指令；
- 出现 `cuowu.txt` 未记录的错误；
- 与铁律冲突、需要新做法。

动作（顺序固定，不得跳步）：

1. **立即调用 `zhishiku-caiji`**，为本任务新建一个案例（**同领域**）。把「从缺口那一步起」的步骤作为该案例的大步骤分化。
2. **扫描所有可用 skill，找能辅助解决当前缺口的**：
   - 扫描方式：读 skill 索引 `skills.jsonl`（含每个 skill 的 name / description / triggers；也可用 `skill-manager` 的查询脚本）。索引路径按当前 OS 选：Windows 为 `C:\Users\xi\.pi\agent\skill-index\skills.jsonl`，Linux/WSL 为 `/media/xi/系统/Users/xi/.pi/agent/skill-index/skills.jsonl`；索引不可用时，列出 skills 根目录（Windows `C:\Users\xi\.pi\agent\skills\`，Linux `/media/xi/系统/Users/xi/.pi/agent/skills/`）下每个 `SKILL.md` 的 frontmatter `description`。
   - 按当前问题的关键词匹配（如 pwn / 堆 / 格式化串 / IDA / 浏览器 / 固件 …），列出候选。
   - 选最匹配的一个（或几个）→ **读取并遵循它的流程**来解决缺口。
   - **没有匹配的 skill** → 才用通用能力处理，并在报告里注明「无 skill 可辅助」。
3. **缺口解决后，回到原 chuli 执行流**，继续按知识库处理后续步骤——**不得停在别的 skill 里**。
4. 全程**从缺口起，每条指令都按 caiji 的采集节奏如实记录**（执行一条 → 写一个 `->` 块）。
5. 缺口之前的步骤已在知识库中，不必重采。

**6. 结束后自动更新**

- 若本轮触发了采集 → **自动**继续 `zhishiku-tilian` 提炼 → `zhishiku-gengxin` 回注，闭合缺口。
- 未触发采集 → 直接报告。

**7 IoT 样本交接（仅领域 `ai_iot` / IoT 固件相关时）**

知识库体系把**知识**与**样本实体**分开：知识（方法论/案例/容器）由 caiji/tilian/gengxin 管；**样本实体（固件/题包/rootfs/qemu/环境根）由 ai_iot 样本库管**。处理完 IoT 任务后，按领域工具规范 `tools/yangben-jiaojie.txt`（源规范 `samples/交接规范.md`）执行交接，顺序固定：

1. **落样本**：未校验 → `<ai_iot根>/samples/incoming/`；已校验 → `samples/curated/<vendor>-<product>-<version>/`（含 `source.txt`、`sha256.txt`）。
2. **建/用环境根**：`<环境根>/cases/CASE-XXXX/`（`ai_iot_huanjing`），放 `firmware/unpack/exp/work`，写 `README.md`。
3. **登记**：往 `samples/registry.txt` 哨兵处追加一行：`ai_iot/<案例id> | <样本名> | <sha256> | <来源> | <样本路径> | <环境根> | curated | <YYYY-MM-DD>`。
4. **回填 metadata**：对应案例 `entries/CASE-XXXX/metadata.json` 的 `sample.path` / `lab.env_root` / `lab.rootfs` / `lab.binary` 写实际路径。

固定路径（唯一权威）：
- 知识库根 `ai_iot`：`/media/xi/软件/ai_iot`
- 环境根：`/media/xi/软件/ai_iot_huanjing/cases/CASE-XXXX`
- 样本区：`/media/xi/软件/ai_iot/samples`（`incoming` / `curated` / `registry.txt`）

边界：大文件只留环境根，知识库语义只存**路径引用**；ai_iot 不再承担方法论（已在 `gengxin_wei/ai_iot`）；幂等（同案例更新 registry 同行）。

**8. 报告**：领域 / 用到了哪些知识 / 缺口几处 / 是否已采集并回注 / **IoT 领域则加：样本是否已交接 ai_iot（样本路径 ↔ 环境根 ↔ ai_iot/<案例id>）**。

**9. 交付物（仅 pwn / CTF）**：若本次是 pwn/CTF 题，在**原题目目录**写下 `exp.py` 和 `wp.md`（见下）。

## 交付物：exp.py 与 wp（仅 pwn / CTF 时）

当任务属于 **pwn / CTF 漏洞利用类**（领域如 `ctf-pwn`，或题目就是 CTF 二进制/Web 题）时，**每次完成后必须**在原题目目录留下两份产物：

1. **`exp.py`** —— 可复现的利用脚本（能直接跑、拿到 shell 或读到 flag）。
2. **`wp.md`** —— 简明 writeup：漏洞点 / 利用思路 / 关键 gadget 与偏移 / 踩过的坑 / 最终 PoC 怎么跑。

规则：

- 写到**原题目所在目录**（不是知识库目录，也不是别处）。
- 若该目录**已有 `exp.py` / `wp.md`**（很可能是用户自己的）→ **不得覆盖**：本次产物改写作 `exp_agent.py` / `wp_agent.md`，并在报告里说明。
- **只在 pwn/CTF 题触发**；普通运维、写脚本、排查故障等任务**不写** `exp.py`/`wp.md`。
- 没跑通也要写 `wp.md`（记录卡在哪一步、下一步思路）；但 `exp.py` 只在**真能跑通**时才作为最终版。

### exp.py 的写法（硬要求）

代码要**平铺、能一眼读完**，**不得过度封装**：

- **不要**把整段流程包进 `def main()/def build()/def exploit()/def pwn()` 之类的函数里。
- **只在两种地方用函数**：
  1. **交互辅助**：`def s(a)`, `def sl(a)`, `def sla(a,b)`, `def get_addr()` 这类收发封装；
  2. **反复调用的部分**：菜单操作 `def add(idx,size,data)`, `def delete(idx)`, `def show(idx)`, `def edit(...)`（会被调很多次）。
- 其余（payload 组装、偏移、一次性 gadget 调用、stage 拼接）**直接写在主流程里**，按执行顺序平铺。
- 目标：**从上到下就是利用过程**，读到哪行就知道在干什么。

## 本地模型边界（Ollama 等，防污染）

**目的**：本地小模型（如 `qwen3:8b`）上下文短、易胡写，禁止参与会**写入/改写知识库**的链路，避免污染案例与容器。

| 角色 | 本地模型 | 说明 |
|---|---|---|
| **本 skill（chuli）** | **允许** | 仅作只读副脑：解释库内条目、草稿思路、对照 `cuowu`；**不得**直接改任何知识库文件 |
| **领域 `ctf-pwn`** / skill `ctf-pwn-workflow` | **允许** | 解题辅助、读库、写题目目录下的 `exp.py`/`wp.md`；**不得**写 `caiji_wei` / `tilian_wei` / `gengxin_wei` |
| **`zhishiku-caiji`** | **禁止** | 采集必须是真实指令与原始输出，禁止本地模型代写 `->` 块或总结代替结果 |
| **`zhishiku-tilian`** | **禁止** | 提炼与归属判定不得交给本地模型，防止错归类、无来源写入 |
| **`zhishiku-gengxin`** | **禁止** | 回注/合并/标过期只按本协议由主 agent 执行，禁止本地模型改容器 |
| 其他领域（如 `python-env`）| **默认禁止** | 未单列放行的领域，使用本地模型时不得走知识库写路径 |

硬规则：

1. **会话一旦启用本地模型**（Ollama / 本地 OpenAI 兼容端点等）：本轮知识库相关工作**只允许** `zhishiku-chuli` + `ctf-pwn`（领域或 `ctf-pwn-workflow`）。
2. 启用本地模型期间：**不得调用** `zhishiku-caiji` / `zhishiku-tilian` / `zhishiku-gengxin`，也不得「顺手」写其数据根下任何文件。
3. 若 chuli 在本地模型模式下命中**未记录缺口**：
   - **不要**用本地模型填库或假装已采集；
   - 报告「缺口 + 需主 agent / 云端模型再开 caiji」；
   - 或**明确关闭本地模型模式**后，再由主 agent 走 caiji → tilian → gengxin。
4. 本地模型**只读** `gengxin_wei/ctf-pwn/` 的六文件；输出若要落盘，只许题目目录（`exp.py` / `wp.md` 等），不许知识库目录。
5. 默认本地模型名：`qwen3:8b`（或用户指定的同级 ≤8B）；**禁止**为知识库任务拉起 14B+ 占满内存。

## 铁律（MUST）

0. **模式开启期间，所有任务都走本 skill，不得绕过**；单次触发只管当次请求。
1. **只用知识库里有的执行流与指令**；缺口**必须触发采集**，不得默默划过。
2. **出现未记录情况必须调用 caiji**——这是知识库增长的唯一入口。
3. **缺口处必须扫描所有可用 skill，优先求助能辅助的领域 skill**，而不是直接裸推；求助后**必须回到本 skill 的主流程**。
4. 采集期间**严格遵守 caiji 的规则**（如实、逐条、不攒写、失败也记）。
5. **不直接改知识库**；回注只由 `zhishiku-gengxin` 做。
6. **领域必须属于已有库**；不确定就问用户。
7. 不得因缺口而放弃任务，也不得**臆造**知识库里没有的知识。
8. **pwn/CTF 题完成后，必须在原题目目录留下 `exp.py` 与 `wp.md`**（已有同名文件先备份）；非 pwn/CTF 不触发。
9. **启用本地模型时：仅 chuli + ctf-pwn 可用；caiji / tilian / gengxin 一律禁用**（详见「本地模型边界」），防止污染 skill 与知识库。

## 为什么会想略过缺口（必须识破的借口）

| 借口 | 现实 |
|---|---|
| 这个缺口太小，不值得采集 | 小缺口正是知识增长点；不采永远是缺口 |
| 先把任务做完，回头再采集 | 回头就记不清原始输出了；必须在缺口**当时**开采集 |
| 知识库没有，我随便试一个命令 | 试可以，但试的过程必须被采集，否则白试 |
| 采集太麻烦，我直接总结一下 | 总结 = 污染；caiji 要的是原始输出 |
| 缺口我用通用能力解决了，就不用采了吧 | 解决了更要采——下次它就变成「已记录」 |
| 缺口我自己会，不用去找别的 skill | 找 skill 是为了复用已验证的方法，也给知识库留更好的样本 |
| 我直接硬解更快 | 硬解容易错且不会沉淀；先扫 skill，再动手 |
| 采集会打断任务节奏 | 中断只是缺口，不是污染；不采才是真损失 |

## 红旗（出现任意一条，立即停下修正）

- 我遇到了知识库没有的步骤，但没打算采集。
- 我准备「做完再补记」。
- 我用总结代替采集原始输出。
- 我改了知识库里的文件（应该由 gengxin 做）。
- 我在缺口处反复试错，却没有采集。
- **我遇到缺口，没扫描其他 skill 就直接硬解**。
- **我求助了别的 skill，但没回到 chuli 主流程**。
- 我把领域猜成别的库了。
- **本地模型开着，却调用了 caiji / tilian / gengxin，或让本地模型写知识库文件**。
- **本地模型模式下用本地模型「总结」冒充采集结果，或直接改 gengxin_wei**。

## 启动自检

处理前：

- 领域库存在，且 `liucheng.txt` / `cuowu.txt` / `zhiling.txt` 至少有一个非空。
- 若 `liucheng.txt` 为树形总览：确认读法/分诊可读；需要执行时能打开对应 `liucheng_biao/<标号>.txt`。
- 引用的知识条目能对上（`来源` 可读）。

触发采集时：

- `zhishiku-caiji` 可用；不可用 → 报告「未采集」，任务继续但注明缺口仍在。
- 已扫描其他 skill；选中的 skill 已读并遵循；缺口解决后已回到主流程。

处理后：

- 若触发过采集，确认缺口已进入 `gengxin_wei/<领域>/` 对应文件（回注完成）。

## 示例

请求：「在 Windows 上装个 python 环境跑个脚本」。

```text
1. 领域 → python-env（已存在库）
2. 载入 python-env 的知识
3. 命中 liucheng 分诊/树 → 打开当前标号卡片，按「做什么」逐条执行
   - 指令表取 `<解释器> --version; echo "exit=$?"`
   - cuowu.txt 预判「解释器不可用」：python3 可能失败 → 备选 python
4. 全程有知识，无需采集
5. 报告：领域 python-env / 用 3 条知识 / 缺口 0
```

另一个请求命中缺口：

```text
执行到某步，出现 cuowu.txt 未记录的「权限被拒」错误
  → 判为未记录情况
  → 立即调用 zhishiku-caiji 建案例（领域 python-env），从该步起如实采集
  → 扫描所有 skill，按关键词「权限 / 提权 / sudo」匹配，选中匹配的那个
  → 读取并遵循它排查解决，全程逐条记录
  → 缺口解决，回到 chuli 主流程继续（不停在别的 skill 里）
  → 结束后自动 tilian → gengxin
  → 下次再遇到「权限被拒」，cuowu.txt 里已有记录
```

## 常见错误

| 错误 | 后果 | 纠正 |
|---|---|---|
| 遇到缺口不采集 | 知识库永不增长，缺口永远在 | 缺口必须触发 caiji |
| 「做完再补记」 | 原始输出丢失，样本报废 | 缺口当时就开采集 |
| 用总结代替采集 | 采样污染 | 照抄真实 stdout / 报错 |
| 直接改知识库 | 绕过 gengxin 的安全规则 | 回注交给 gengxin |
| 领域猜错 | 用错库、知识进错地方 | 不确定就问用户 |
| 采集时攒着写 | 数据失真 | 遵守 caiji 的采集节奏 |
| 缺口处放弃任务 | 任务失败 | 缺口用通用能力继续，同时采集 |
| 缺口不扫 skill、直接硬解 | 重复造轮子、采样质量差 | 先扫所有 skill，优先求助匹配的 |
| 求助其他 skill 后不返回主流程 | 脱离知识库系统、后续不采集 | 缺口解决后必须回到 chuli 主流程 |
| 臆造知识库没有的知识 | 知识失真 | 只用库里有的，缺口靠采集补 |
| 本地模型参与 caiji/tilian/gengxin | 案例与容器被胡写污染 | 本地模型仅 chuli+ctf-pwn；写库必须关本地模型后由主 agent 走原链路 |
| 本地模型把输出写入 gengxin_wei/caiji_wei | skill/知识库被污染 | 本地模型只许读 ctf-pwn 库；落盘仅题目目录 |
