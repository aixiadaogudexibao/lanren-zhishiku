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
| `zhishiku-caiji` | 逐条采集「指令 ↔ 原始输出」案例 | `caiji_wei/<领域>/` |
| `zhishiku-tilian` | 案例 → 知识点 / 执行流 / 错误 / 指令表 | `tilian_wei/<领域>/` |
| `zhishiku-gengxin` | 按领域回注到可执行知识容器 | `gengxin_wei/<领域>/` |
| `zhishiku-chuli` | 用容器处理任务；缺口触发采集闭环 | （只读 gengxin，经 xinxi 定位） |

## 领域

一个领域 = 一个文件夹名（如 `python-env`）。四层共用同一领域名，禁止中途改名。

## 路径约定

每个带数据根的 skill 用 `xinxi.txt`：

```text
<root>_win:   <Windows 绝对路径>
<root>_linux: <Linux/WSL 绝对路径>
```

两行必须指向**同一份**目录。`install` 从 `xinxi.txt.example` 生成。

## 哨兵写入

`qingdan.txt`、`buzou/*.txt`、`suoyin.txt`、`rizhi.txt` 等 append-only 文件末尾保留独占一行的 `★`。追加 = 把 `★` 替换为 `新内容\n★`，不读全文。

## 本地模型边界

Ollama 等本地小模型**只允许**参与只读的 `zhishiku-chuli`（及约定的解题辅助）；**禁止**参与 caiji / tilian / gengxin 写库，防止污染。
