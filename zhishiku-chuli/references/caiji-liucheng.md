# 有标记时的 caiji 流程

> 从 `SKILL.md` 拆出；主文件只留摘要与指针。

## 有标记时的 caiji 方式（MUST）

1. **用户侧结果已交付之后**，再开 caiji（exp/wp 等按第 10 步该写的已写、结论已给用户）。
2. **caiji 输入**：读 `xinxi.txt` 该任务节的 `标记明细`（方案 A：层 / 类型码 / 何时 / 反证 / 差在 / 当时判断 / 如何越过 / 用户原话）+ 领域 + 题目/原路径；不要靠聊天回忆拼标记。旧节缺层字段时按 caiji 降级规则整段采。
3. 新建案例（同领域）；大步骤分化覆盖**明细里的缺口段**（及为说清缺口所必需的前后文）；**有 `层` 时按层收窄**（参数层只采布局/条件变体），不必重采整题里库已覆盖的成功老路。
4. **按已跑通的思路复现再采集**：边复现边按 caiji 节奏写 `->` 块（执行一条 → 写一块）。优先复现「标记中的新路径 / 纠错路径」。
5. **禁止**用回忆/总结事后填 `结果`；复现跑不出来 → 在案例里标「未采集/复现失败」并写清原因，不得编造 stdout。
6. 用户纠正类标记：复现时仍要落 `位置：用户纠正` 块，`结果` 用 `xinxi.txt` 明细里保存的用户原话。
7. 本地模型模式：仍**禁止**写 caiji；在**已交付用户结果**的前提下报告「有标记未采集（本地模型）」；`xinxi.txt` **保留** `caiji标记：1` 与明细，供主 agent 后续补采；关本地模型后再走 caiji。
8. caiji 案例归档后 → **自动** `zhishiku-tilian` → `zhishiku-gengxin` 闭合缺口。
9. 标记已用于开采或已声明无法采集后：更新 `xinxi.txt`——该任务 `caiji标记：0` 或 `状态：已采清`/`闭`，避免重复开案；无其它进行中节 → `当前：无`。

**7. 收尾记账：实战使用 + 生命周期（一条命令）**

收尾时跑一次 `yongfa.py` 的 `--tick`。它同时完成两件事：把本轮用到的键追加进 `yongfa.txt`，并推进 `shengming.txt` 的生命周期。

```bash
python3 <skill 目录>/zhishiku-gengxin/scripts/yongfa.py <数据根>/<领域> \
  --tick --date <YYYY-MM-DD> [--case <领域>/<编号>] \
  --used "<键>=成" --used "<键>=败:<败因>"
```

- **键**：`liucheng_biao/<标号>` / `tools/<工具名>` / `cuowu/<错误特征>` / `zhiling/<操作>`。
- **并列择一**：本轮若因「多节点同时满足」而用 `--pick` 裁过，把**胜出键**计入 `--used`；候选里没用上的**不记**。
- **结果**：只有 `成` / `败` 两态（判不准就记 `败`，别留中间态）。
- **案例id**：本轮**完成后**因标记开过 caiji → `--case <领域>/<编号>`；否则省略（脚本写 `-`）。
- 只记**真用到的**键；「翻过但没用上」的不写。
- **本轮没用到任何知识，也要跑一次**（不传 `--used`）。空轮次必须记账，否则生命周期不会倒计时，「零使用」永远是 0 信息。
- **不要手改** `yongfa.txt` / `shengming.txt`：`★` 哨兵与生命周期都由脚本处理。

跑完读输出：

- **出现「生命周期归零」→ 汇总成一次询问用户**（列前 10 条 + 总数）：
  > 「生命周期归零 N 条。全部标记过期 / 全部保留刷新 / 只处理其中某几条？」
  - 答「同意已无用」→ 对那几条执行 `... --expire "<键>,<键>"`
  - 答「不同意 / 保留」→ 执行 `... --refresh "<键>,<键>"`，**生命周期刷新回满值**
  - **用户没答复就不写任何裁决**，停在 `待裁决`，下次再问。
- 没有归零 → 什么都不用问。

格式与判读见 `zhishiku-gengxin` 的「实战使用日志」与「条目生命周期」。这是本 skill **唯一**被允许写 `gengxin_wei/` 的地方：`yongfa.txt` 与 `shengming.txt`，且**只能经由脚本写**。

**7.1 收尾展示：本轮技术卡与执行流（MUST，交付时给用户看）**

`--tick` 写完后，立刻跑一次展示脚本，把本轮用到的 `liucheng_biao` 卡按卡内「下一跳」串成 `->` 链：

```bash
python3 <本 skill 目录>/scripts/show_flow.py <数据根>/<领域> \
  --date <YYYY-MM-DD> [--case <领域>/<编号>]
# 或直接指定卡片：
#   --keys liucheng_biao/H.cat.1,liucheng_biao/H.cat.2
```

输出形如：

```text
## 本轮使用技术卡
- ✔ H.cat.1  → H.cat.2
- ✔ H.cat.2  → H.cat.3

## 执行流
H.cat.1 -> H.cat.2 -> H.cat.3

## 未连入主链（本轮用到，但上下游不在本轮）
- C.while_crossbuf.1
```

规则：

- **写进交付给用户的收尾报告**，与领域、采集标记、`--tick` 结果并列；无卡就写「本轮未用技术卡」，不要略掉这一节。
- `->` 只表达**卡内已写明的下一跳**，不凭题目顺序自行编链；链断就是断，不补全。
- 「未连入主链」如实列出（下游卡未在本轮用到，不算失败）。
- 只在 `liucheng_biao` 内连线；`jishu/` / `silu/` / `tools/` 仍照常记 `--tick`，但不进这条 `->` 链。
- 脚本只读，不改任何文件；不要为凑链去改卡片的「下一跳」。

**7.2 全链体检与交叉检验（`doctor.py`，开工与收尾都可跑）**

状态散在 5 个文件里（缺口板 / biao_xin / tilian suoyin / gengxin / 续跑条），单看任一都答不出「断在哪」。用一条命令集中查看并交叉校验：

```bash
python3 <本 skill 目录>/scripts/doctor.py              # 全部领域
python3 <本 skill 目录>/scripts/doctor.py --domain ctf-pwn
python3 <本 skill 目录>/scripts/doctor.py --strict     # 有 ✗ 时返回非零
```

输出分四段：

| 段 | 内容 |
|---|---|
| **续跑条** | 版本 / 写者 / 心跳是否过期 / 阶段 / 下次动作 |
| **缺口板** | `caiji标记=1` 且未闭的任务 |
| **案例索引** | 每领域 `dai`/`hui` 概况 + **链条矩阵**（案例 → caiji → tilian → gengxin 三列打勾） |
| **汇总** | `✗` 必须处理、`⚠` 需留意 |

交叉检验规则（脚本自动判定）：

| 判定 | 含义 |
|---|---|
| 案例在 `hui` 但 tilian 无稿 | **归档了没提炼** |
| 案例 tilian 有稿但 gengxin 未见 | **提炼了没回注** |
| tilian 有案例但 caiji 不在 `hui` | 提炼跑在采集前 / 编号错 |
| gengxin 引用未归档案例 | 幽灵引用 |
| `dai` 停留 ≥7 天 | 采集断在半路 |
| `flag=2` | 崩溃恢复标记未收尾 |
| 续跑条心跳 >30 分钟 | owner 可能已放弃 |

使用时机：

- **开工**：`--domain <领域>`，确认上一条链断在哪，避免从头重开。
- **收尾**：全量跑一次；`✗` 项要么当场修，要么在报告里写明留待处理。
- 只读，不改任何文件；不要为了让它变绿去手改 `biao_xin.txt`，那要走 caiji 的归档流程。

**8 IoT 样本交接（仅领域 `ai_iot` / IoT 固件相关时）**

知识库体系把**知识**与**样本实体**分开：知识（方法论/案例/容器）由 caiji/tilian/gengxin 管；**样本实体（固件/题包/rootfs/qemu/环境根）由 ai_iot 样本库管**。处理完 IoT 任务后，按领域工具规范 `tools/yangben-jiaojie.txt`（源规范 `samples/交接规范.md`）执行交接，顺序固定：

1. **落样本**：未校验 → `<ai_iot根>/samples/incoming/`；已校验 → `samples/curated/<vendor>-<product>-<version>/`（含 `source.txt`、`sha256.txt`）。
2. **建/用环境根**：`<环境根>/cases/CASE-XXXX/`（`ai_iot_huanjing`），放 `firmware/unpack/exp/work`，写 `README.md`。
3. **登记**：往 `samples/registry.txt` 哨兵处追加一行：`ai_iot/<案例id> | <样本名> | <sha256> | <来源> | <样本路径> | <环境根> | curated | <YYYY-MM-DD>`。
4. **回填 metadata**：对应案例 `entries/CASE-XXXX/metadata.json` 的 `sample.path` / `lab.env_root` / `lab.rootfs` / `lab.binary` 写实际路径。

固定路径（唯一权威）：
- 知识库根 `<ai_iot根>`：由该领域自行约定（作者的取值写在 `tools/yangben-jiaojie.txt` 里）
- 环境根：`<环境根>/cases/CASE-XXXX`
- 样本区：`<ai_iot根>/samples`（`incoming` / `curated` / `registry.txt`）

边界：大文件只留环境根，知识库语义只存**路径引用**；ai_iot 不再承担方法论（已在 `gengxin_wei/ai_iot`）；幂等（同案例更新 registry 同行）。

**9. 报告**：领域 / 用到了哪些知识 / **并列择一用了哪个键（若发生）** / **门槛缺失/待补（若有）** / **采集标记几条（摘要）** / 完成后是否已 caiji 并回注 / **IoT 领域则加：样本是否已交接 ai_iot（样本路径 ↔ 环境根 ↔ ai_iot/<案例id>）**。

**10. 交付物（仅 pwn / CTF）**：若本次是 pwn/CTF 题，在**原题目目录**写下 `exp_agent.py` 和 `wp_agent.md`（见下）。

