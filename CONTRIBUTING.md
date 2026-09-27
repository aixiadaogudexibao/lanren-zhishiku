# Contributing

## 可以提交

- 四个 skill 的 `SKILL.md` 改进（协议澄清、防污染规则、可读性）
- `install` 脚本、文档、`examples/domain-skeleton`
- 与平台无关的 bugfix

## 不要提交

- `caiji_wei/**`、`tilian_wei/**`、`gengxin_wei/**` 下的**领域内容**（案例、提炼产物、知识条目）
- 含本机绝对路径的 `xinxi.txt`（只提交 `xinxi.txt.example`）
- 固件、题包、libc、大样本二进制

## 新建领域骨架

复制示例后改名：

```bash
cp -a examples/domain-skeleton gengxin_wei/your-domain
```

再按 `zhishiku-gengxin` 协议填充；真实知识应来自 caiji → tilian → gengxin，不要手搓无来源条目。

## 本地开发

```powershell
.\install.ps1 -Mode Link
# 改 SKILL.md 后新开 pi 会话即可（Link 模式）
```
