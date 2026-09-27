# lanren-zhishiku 设计规格

日期：2026-03-27  
状态：已批准（方案 A + 扁平四 skill）

## 目标

公开 GitHub 模板仓：clone → install → 新开 pi 会话即可使用知识库四层闭环。  
不含维护者本地领域知识（ctf-pwn / ai_iot / python-env 等）。

## 非目标

- 不打包真实案例 / 提炼产物 / 知识容器内容
- 不改四 skill 的核心协议语义（本次只做可移植包装）
- 本次不 `gh repo create`、不 push（本地 git + 首提交即可）

## 仓库结构

```text
lanren-zhishiku/          # 工作目录现为 C:/Users/xi/zhishiku，远程名 lanren-zhishiku
├── README.md
├── LICENSE                 # MIT
├── CONTRIBUTING.md
├── .gitignore
├── install.ps1 / install.sh
├── docs/
│   ├── architecture.md
│   └── 2026-03-27-lanren-zhishiku-design.md
├── examples/domain-skeleton/   # 空领域六文件骨架
├── zhishiku-caiji/
├── zhishiku-tilian/
├── zhishiku-gengxin/
└── zhishiku-chuli/
```

## 路径可移植性

- 仓内提交 `xinxi.txt.example`（占位符），**不**提交含本机绝对路径的 `xinxi.txt`
- `install` 根据仓库实际位置生成三份 `xinxi.txt`（`_win` + `_linux` 两行）
- Linux 行：若检测到 WSL/`/media/xi/系统` 映射则写入映射路径，否则写入与 win 等价的说明性路径或同一相对解析结果

## 安装行为

1. 默认把四个 skill **符号链接**到 `~/.pi/agent/skills/`（可用 Copy）
2. 目标已存在 → 跳过；`-Force`/`--force` 才替换
3. 从 `.example` 生成/覆盖本包内 `xinxi.txt`
4. 打印触发词与数据根位置

## 示例骨架

`examples/domain-skeleton/` 提供空领域文件头 + 哨兵，无真实知识点。  
用户可复制到 `gengxin_wei/<领域>/` 作为新建领域起点。

## 成功标准

- [ ] 目录与文档齐全，无领域知识文件
- [ ] `git status` 干净且有首提交
- [ ] README 能独立完成：装、用、数据根说明
- [ ] install 脚本可生成 xinxi 且不覆盖未 `--force` 的已有 skill
