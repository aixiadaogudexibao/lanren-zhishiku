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

```powershell
git clone <你的仓库 URL> lanren-zhishiku
cd lanren-zhishiku
.\install.ps1
```

```bash
git clone <你的仓库 URL> lanren-zhishiku
cd lanren-zhishiku
bash install.sh
```

然后**新开**一轮 pi 会话。触发：

| 说法 | 效果 |
|---|---|
| **使用知识库系统** | 只用知识库处理**当前**这一请求 |
| **开启知识库系统模式** | 之后每个任务都走知识库，直到关闭 |
| 关闭知识库系统模式 | 恢复普通处理 |

`install` 会：

1. 从 `xinxi.txt.example` 生成带本机路径的 `xinxi.txt`（已 gitignore）
2. 把四个 skill 链到 `~/.pi/agent/skills/`（默认符号链接；可用 `-Mode Copy` / `--copy`）

同名 skill 已存在时默认**跳过**。确认要用本仓库替换时再加 `-Force` / `--force`。

## 目录

```text
lanren-zhishiku/
├── install.ps1 / install.sh
├── docs/architecture.md
├── examples/domain-skeleton/     # 空领域骨架（无真实知识）
├── zhishiku-caiji/               # 采集层
├── zhishiku-tilian/              # 提炼层
├── zhishiku-gengxin/             # 回注 / 知识容器
└── zhishiku-chuli/               # 处理层（入口）
```

数据根（运行后产生，默认不进 git）：

- `zhishiku-caiji/caiji_wei/<领域>/`
- `zhishiku-tilian/tilian_wei/<领域>/`
- `zhishiku-gengxin/gengxin_wei/<领域>/`

新建领域可复制示例：

```bash
cp -a examples/domain-skeleton zhishiku-gengxin/gengxin_wei/your-domain
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
*_win:   C:/.../lanren-zhishiku/...
*_linux: /media/xi/系统/Users/.../lanren-zhishiku/...
```

仓库挪目录后重新跑一次 `install`（或手改三份 `xinxi.txt`）。

## 本地模型

Ollama 等本地小模型**不要**参与 caiji / tilian / gengxin 写库；只允许只读辅助 `zhishiku-chuli`（详见 chuli 的「本地模型边界」）。

## 推到 GitHub（本地已整理好时）

本机先有提交后：

1. 在 GitHub 网页 New repository → 名 `lanren-zhishiku` → Public → **不要**勾选初始化 README  
2. 本地：

```bash
cd /path/to/lanren-zhishiku   # 或 C:/Users/xi/zhishiku
git remote add origin git@github.com:<USER>/lanren-zhishiku.git
git push -u origin main
```

## License

MIT — 见 [LICENSE](LICENSE)。
