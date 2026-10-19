# extensions —— 配套 pi 扩展

配合本仓四个 zhishiku skill 的 pi（coding agent harness）扩展。
每个文件职责独立，**可单独启用或关掉**，不做隐式耦合。

## 安装

把需要的 `.ts` 复制到你的 harness 扩展目录：

```bash
# pi 默认扩展目录
cp extensions/*.ts ~/.pi/agent/extensions/
```

重启会话后生效。

## 路径配置（不硬编码用户名）

所有扩展共用 `_paths.ts` 解析路径，优先级：**环境变量 > `~` 推导**。

| 环境变量 | 默认值 | 含义 |
|---|---|---|
| `ZHISHIKU_ROOT` | `~/.zhishiku` | 知识库数据根（caiji_wei / tilian_wei / gengxin_wei / resume） |
| `PI_AGENT_DIR` | `~/.pi/agent` | harness 配置根 |
| `PI_SKILLS_DIR` | `<PI_AGENT_DIR>/skills` | skill 目录（缺口板 `zhishiku-chuli/xinxi.txt` 在这下面） |
| `TEMP_CLEAN_ROOTS` | `~/Desktop:~/Downloads:/tmp` | `temp-script-cleaner` 允许清理的目录，`:` 分隔 |

数据和 skill 放在别处时，`export` 对应变量即可，不用改源码。

## 各扩展职责

| 文件 | 管什么 | 挂载事件 |
|---|---|---|
| `_paths.ts` | 共用路径解析（不是扩展，被其它文件 import） | — |
| `zhishiku-domain.ts` | 按领域注入铁律 / 流程表 / 工具清单；`/domain` 命令与 `zhishiku_domain` 工具 | `before_agent_start` |
| `zhishiku-guard.ts` | 续跑条注入、压缩前快照重建、无标记时拦空采 | `before_agent_start` / `session_before_compact` / `tool_call` |
| `dangerous-op-guard.ts` | 危险命令（`rm -rf`、`dd of=/dev/*`、`mkfs`、`git push -f`）与保护路径覆盖前确认 | `tool_call` |
| `snapshot-manager.ts` | 快照统一台账 + 生命周期 + 过期候选列表 | `session_start` / `agent_end` |
| `temp-script-cleaner.ts` | 收尾时列本会话写的临时脚本（`probe*` / `tmp*` / `vfy*` …），确认后删 | `tool_call` / `agent_settled` |
| `logic-checker.ts` | 规则/流程自洽性抽查 | — |

## zhishiku-domain

- 判定顺序：显式 `/domain` 锁定 > 题目关键字（≥2 分）> 续跑条 > cwd
- 三路入口：自动判定 / 命令 `/domain` / 工具 `zhishiku_domain`
- 只注入索引，不注正文；正文按 `tieuli.txt` / `liucheng_biao/` 路径 read

## zhishiku-guard

- 每轮从磁盘重读 `resume/current.md` 与缺口板，注入阶段/标记/下次动作
- 缺口板 `caiji标记` 为 0 时读 `zhishiku-caiji/SKILL.md` 会被 **block**（拦空采）
- 压缩前快照续跑条到 `resume/done/`，压缩后按磁盘重建
- 只读不写知识库；写库仍归 skill

## snapshot-manager

- 台账：`<数据根>/_snapshots/INDEX.md`（树形）+ `index.json`
- 扫四类：`gengxin_wei/*/_snap/`、`resume/done/`、`_bak_*`、`skill *.bak-*`
- 命令：`/snapshot` 看统计、`/snapshot md` 看完整台账、`/snapcheck` 列过期候选
- **只列不删**：清理要 `/snapcheck --delete` 且确认
- 生命周期表在扩展内 `LIFECYCLE` 常量，改了要同步上表

## 注意

- 扩展是**只读**的守卫；写库（caiji / tilian / gengxin）仍由 skill 的脚本完成。
- 非 TUI 模式没有确认对话框，`dangerous-op-guard` 默认**拦截**而不是放行。
