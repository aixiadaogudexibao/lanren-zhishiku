# lanren-zhishiku

面向 [pi](https://github.com/) 等 agent 运行时的**知识库系统 skill 模板**：采集 → 提炼 → 回注 → 用知识处理任务。

本仓库是**公开模板**，不含作者本地领域知识。clone 后安装即可从零积累自己的库。

```text
zhishiku-caiji（采集） ─▶ zhishiku-tilian（提炼） ─▶ zhishiku-gengxin（容器）
                                                              │
                                                    读知识    │    ▲ 回注
                                                              ▼    │
                        zhishiku-chuli（处理用户请求） ───────────────┘
```

## 快速开始

拿到发布包（zip）或 clone 后，**最省事的是双击**：

```text
Windows    双击 install.cmd        （数据根用 %USERPROFILE%\.zhishiku）
Linux/mac  bash install.sh --copy --data-root ~/.zhishiku
```

也可手动跑：

```powershell
git clone https://github.com/aixiadaogudexibao/lanren-zhishiku.git lanren-zhishiku
cd lanren-zhishiku
.\install.ps1 -DataRoot $env:USERPROFILE\.zhishiku
```

```bash
git clone https://github.com/aixiadaogudexibao/lanren-zhishiku.git lanren-zhishiku
cd lanren-zhishiku
bash install.sh --copy --data-root ~/.zhishiku
```

包内 `QUICKSTART.txt` 是一页纸说明。

然后**新开**一轮会话。触发：

| 说法 | 效果 |
|---|---|
| **使用知识库系统** | 只用知识库处理**当前**这一请求 |
| **开启知识库系统模式** | 之后每个任务都走知识库，直到关闭 |
| 关闭知识库系统模式 | 恢复普通处理 |

`install` 会：

1. 从 `xinxi.txt.example` 生成带本机路径的 `xinxi.txt`（已 gitignore）
2. 把四个 skill 链到 `~/.pi/agent/skills/`（默认符号链接；可用 `-Mode Copy` / `--copy`）

同名 skill 已存在时默认**跳过**。确认要用本仓库替换时再加 `-Force` / `--force`。

`xinxi.txt` 已存在且内容不同时，`install` **不会覆盖**，只警告并保留原文件（避免一次重跑把知识库悄悄指到空目录）。确实要覆盖再加 `-ForceXinxi` / `--force-xinxi`。

## 多 harness / 统一数据根

同一台机器上如果有多个 agent 运行时（例如 pi 与 codex），**让它们共用一份知识库**，别各存一份：

```bash
# 数据放到 harness 与仓库之外，重装/换 harness 都不丢
bash install.sh --data-root ~/.zhishiku
```

```powershell
.\install.ps1 -DataRoot $env:USERPROFILE\.zhishiku
```

再把其它 harness 的 `xinxi.txt` 也指到同一个目录即可。目录长这样：

```text
~/.zhishiku/
├── caiji_wei/<领域>/     采集的案例
├── tilian_wei/<领域>/    提炼出的知识
└── gengxin_wei/<领域>/   回注后的知识容器
```

### 改完 skill 后同步到各 harness

本仓库的 `SKILL.md` 是**唯一源**。改完后：

```bash
bash sync.sh           # 同步到 ~/.pi/agent/skills 与 ~/.codex/skills
bash sync.sh --check   # 只看漂移，不写盘（有漂移退出码 1）
```

`sync.sh` 会按目标 harness 替换示例路径里的 `.pi/agent` 段（`.codex` 装的那份读起来就是 `.codex`），其余逐字节一致；行尾保持不变。它**只写 SKILL.md**，绝不碰 `xinxi.txt` 和 `*_wei/` 数据。

## 扩展与提示词（可选）

`install.sh` / `install.ps1` 默认**只装四个 skill**——那已经够用了：agent 读 `SKILL.md` 按流程走。

想让日常使用更省事，再加两个开关。两者都**默认关闭**。

### `--with-extensions` / `-WithExtensions`

把 `extensions/*.ts` 复制到 `<agent>/extensions/`（默认 `~/.pi/agent/extensions/`）。
装上后每轮自动做这些事：

| 文件 | 干什么 |
|---|---|
| `zhishiku-domain.ts` | 按题目关键字 / 续跑条自动判定领域，注入该领域铁律与流程表 |
| `zhishiku-guard.ts` | 每轮重读续跑条与缺口板；无采集标记时拦空采 |
| `snapshot-manager.ts` | 快照统一台账（`/snapshot`、`/snapcheck`） |
| `dangerous-op-guard.ts` | `rm -rf`、`dd of=/dev/*` 等危险命令前确认 |
| `temp-script-cleaner.ts` | 收尾时列出本会话写的 `probe*` / `tmp*` 临时脚本 |
| `logic-checker.ts` | 规则自洽性抽查 |

> `dangerous-op-guard` 会在 `rm -rf` 前弹窗，所以默认不装，避免悄悄改变别人的环境。

扩展不硬编码用户名，路径按 `ZHISHIKU_ROOT` / `PI_AGENT_DIR` / `PI_SKILLS_DIR` 解析，没设就按 `~` 推导。详见 `extensions/README.md`。

### `--with-prompts` / `-WithPrompts`

把 `docs/prompts/AGENTS.zhishiku.md` **追加**到 `<agent>/AGENTS.md`。
这里面是续跑条规则（C0–C5 阶段、磁盘真相、中断恢复），不追加的话 agent 不会主动维护续跑条。

安全做法：

- **只追加，不覆盖**；已有文件先备份成 `AGENTS.md.bak-<时间>`
- 写入带 `<!-- lanren-zhishiku:auto-appended -->` 标记，重跑不会重复追加

`docs/prompts/SYSTEM.zhishiku.md`（技能路由、扩展说明）需要**手动合并**，因为不同人的 `SYSTEM.md` 结构差别大。

### 一条命令装全

```bash
bash install.sh --copy --data-root ~/.zhishiku --with-extensions --with-prompts
```

```powershell
.\install.ps1 -Mode Copy -DataRoot $env:USERPROFILE\.zhishiku -WithExtensions -WithPrompts
```

## 目录

```text
lanren-zhishiku/
├── install.cmd                   # Windows 双击即装
├── QUICKSTART.txt                # 一页纸说明（包里第一个看这个）
├── install.ps1 / install.sh
├── sync.sh                       # 仓库 → 各 harness 同步 SKILL.md 与 scripts/
├── pack.sh                       # 打 zip 发布包（从 HEAD 导出）
├── .gitattributes                # .sh/.py 必须 LF；.ps1/.cmd 用 CRLF
├── tests/selftest.py             # 静态一致性 + 脚本行为 + 领域自检
├── docs/architecture.md
├── docs/prompts/                 # 可选提示词（AGENTS / SYSTEM 的 zhishiku 段落）
├── extensions/                   # 可选 pi 扩展（护栏 / 领域注入 / 快照台账）
├── examples/domain-skeleton/     # 空领域骨架（无真实知识）
├── zhishiku-caiji/               # 采集层
├── zhishiku-tilian/              # 提炼层
├── zhishiku-gengxin/             # 回注 / 知识容器（含 scripts/）
└── zhishiku-chuli/               # 处理层（入口）
```

`zhishiku-gengxin/scripts/` 里是两个回注用的工具（都由 `sync.sh` 一起同步到各 harness）：

| 脚本 | 干什么 |
|---|---|
| `yongfa.py` | 实战使用记账 + 条目生命周期（`--tick` / `--refresh` / `--expire`），回注前看它的报告 |
| `snapshot.py` | 回注前拍快照、出问题按快照回滚（`--take` / `--list` / `--rollback` / `--prune`） |

## 自测

```bash
python3 tests/selftest.py        # 期望 “失败 0”
python3 tests/selftest.py -v     # 逐条打印（218 项）
python3 tests/selftest.py --keep # 保留沙箱目录排错
```

沙箱在临时目录，不碰仓库与真实数据根；会顺便体检真实领域库（若 `xinxi.txt` 指向的目录存在）。

覆盖范围：

| # | 段 | 查什么 |
|---|---|---|
| 1 | 静态一致性 | frontmatter、跨 skill 引用、文件样例块的 `★` 不重复、tilian 声明即有小节 |
| 2 | `yongfa.py` 用法 | 参数校验、非法结果、缺 `★` 等 |
| 3 | `--tick` 记账 | 生命周期回落/预警/冻结、空轮次也衰减 |
| 4 | 异常 | 悬空引用、非法行计数、截断与 `--all` |
| 5 | 行尾与编码 | CRLF / LF 两种日志都能追加，且保持原行尾 |
| 6 | `snapshot.py` | 拍摄/列表/回滚三重保险、坏快照拒回滚、`--prune` |
| 7 | 真实数据根 | 跑各领域 `validate.py` 与 `yongfa.py` |
| 8 | 端到端 | 用户纠正块的 5 段结构能被下游接受 |
| 9 | 契约 | 枚举出的键 ↔ `--used` 接受的键 一致 |
| 10 | 破坏矩阵 | 对 `validate.py` 逐项注入错误，每项都要被抓到 |
| 11 | install / sync | `--data-root` 三种写法、防覆盖守卫、漂移检测、不碰数据 |
| 12 | 仓库契约 | 孤儿脚本、占位符、行尾（`.sh` 必须 LF）、`.gitattributes`、gitignore |

> 跑 11 段需要 git-bash。自测会自动找 `C:\Program Files\Git\bin\bash.exe`；**不能用 System32 的 `bash.exe`**——那是 WSL 的 bash，`uname -s` 报 Linux，路径全错。

数据根（运行后产生，默认不进 git）。不指定 `--data-root` 时是仓库根下的 `caiji_wei/` `tilian_wei/` `gengxin_wei/`：

- `<数据根>/caiji_wei/<领域>/`
- `<数据根>/tilian_wei/<领域>/`
- `<数据根>/gengxin_wei/<领域>/`

新建领域可复制示例：

```bash
cp -a examples/domain-skeleton <数据根>/gengxin_wei/your-domain
```

## 四个 skill 各自做什么

| Skill | 何时用 |
|---|---|
| `zhishiku-chuli` | 用已有知识处理任务；缺口自动采集并回注 |
| `zhishiku-caiji` | 把一次解决过程逐条采成案例轨迹 |
| `zhishiku-tilian` | 案例 → 知识点 / 执行流 / 错误处理 / 指令表 |
| `zhishiku-gengxin` | 按领域把提炼结果写入知识容器 |

更细的协议见各目录 `SKILL.md`；总览见 [`docs/architecture.md`](docs/architecture.md)。

## 路径说明

`xinxi.txt` 使用双行路径，Windows / Linux 指向同一文件夹：

```text
*_win:   C:/.../.zhishiku/caiji_wei
*_linux: /mnt/c/Users/<你>/.zhishiku/caiji_wei   # 挂载前缀不同用 --linux-prefix
```

数据根换了位置（例如仓库挪了目录，或改用 `--data-root`）时，重跑一次 `install` 并加 `--force-xinxi`；或手改三份 `xinxi.txt`（`zhishiku-caiji` / `zhishiku-tilian` / `zhishiku-gengxin` 各一份）。`zhishiku-chuli` 没有 `xinxi.txt`，它从 gengxin 那份读取数据根。

## 本地模型

Ollama 等本地小模型**不要**参与 caiji / tilian / gengxin 写库；只允许只读辅助 `zhishiku-chuli`（详见 chuli 的「本地模型边界」）。

## License

MIT — 见 [LICENSE](LICENSE)。
