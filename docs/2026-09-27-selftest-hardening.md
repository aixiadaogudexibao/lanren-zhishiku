# 自测与加固：测试挖出来的 8 个真 bug

日期：2026-09-27
状态：已实施
关联任务：`planing-biao` / `C:/Users/xi/zhishiku`（测试加固，无独立任务号）

## 为什么写这套测试

四层知识库的载体是 prompt + 少量脚本。prompt 部分没法单测，但**能单测的部分一直没测**：两个脚本（`yongfa.py` / `snapshot.py`）、两个装配脚本（`install.sh` / `sync.sh`）、数据侧校验（`validate.py`）、以及四份 SKILL.md 之间的静态契约。

结果第一次认真跑测试就抓出 8 个真问题——其中 3 个是致命的（脚本根本跑不起来 / 数据静默被改），2 个是历史数据已经损坏。

## 测试套件

`tests/selftest.py`，218 项，12 段。沙箱在临时目录，不碰仓库与真实数据根。

设计原则：**每抓到一个 bug，就补一条能再次抓到它的检查**。所以第 10、11、12 段的很多用例是 bug 的化石。

## 抓出来的 bug

### 1. 模板表头注释里带 `★`（致命）

`qingdan.txt` / `yongfa.txt` 的表头写成 `# 大步骤索引（★ 是写入位；一行一个大步骤）`，于是文件里出现**两个 `★`**。

破坏两条硬规则：
- 「`★` 必须全文件唯一」；
- 采集协议写的是 `Edit: oldText = "★"`——两个 `★` 时这个编辑**锚点歧义**，在弱工具上会改到注释里那个、把哨兵弄丢。

真实数据中招 **13 个 `qingdan.txt` + 3 个 `yongfa.txt`**。改模板措辞（不含 `★`）+ 数据迁移（备份 `_migrate_bak-20260927/`）。

### 2. `0007/buzou/04.txt` 里混进工具调用 JSON 碎片（数据已损坏）

该文件整段执行流被写成**一个物理行**、`\n` 全是字面量，尾部是：

```
...结论：交付物齐备\n★", "oldText": "★"}]
```

即一次失败的工具调用把参数片段粘进了数据文件，且哨兵丢失。该案例的数据集实际不可用。

机械修复：砍掉 JSON 碎片、只把「字段标签 / `-> ` / `★`」之前的字面 `\n` 还原为真换行（**保住 `printf ... echo PWNED\n` 里真正的转义**）、哨兵复位。原件备份。

### 3. `H.hook.trig.txt` 正文里有非法 `★`

知识卡片内容含 `★`，同类不一致，改成 `→`。

### 4. CRLF 的 `yongfa.txt` 根本无法追加（致命）

哨兵正则是 `^★[ \t]*$`。CRLF 文件里那一行是 `★\r`，`$` 在 `re.M` 下只匹配 `\n` 之前，所以 `★\r` **匹配不上** → 哨兵数=0 → 脚本拒绝写入。

而真实 `yongfa.txt` 就是 CRLF。修：正则容忍 `\r?`（`^★[ \t]*\r?$`）。

### 5. CRLF 追加后被静默改成 LF（致命）

`Path.read_text()` 会做**通用换行转换**（CRLF→LF）。用它读出全文再写回，等于把整个文件的行尾换掉——违背 append-only 的本意，也制造了无意义的整文件 diff。

修：新增 `read_raw()`（`read_bytes().decode()`）保行尾，只有需要解析/校验的地方才用会归一化的 `txt()`。

### 6. `install.sh` 传 Windows 反斜杠路径会写出乱码（致命）

`--data-root 'C:\Users\xi\.zhishiku'` 生成的 `xinxi.txt` 是：

```
caiji_wei_win: C:SERSXI.ZHISHIKU/CAIJI_WEI
```

原因：路径被塞进 `sed` 的替换串，`\U` 被 GNU sed 解释成「转义序列 → 大写到结尾」，反斜杠被吃掉。修：路径先归一（`tr '\134' '/'`，不用版本间行为不一致的 `${v//\\//}`）+ **弃用 sed**，改用 bash 参数扩展写占位符。

顺带：bash 5.2+ 的 `patsub_replacement` 会把替换串里的 `&` 当成匹配文本（路径含 `&` 时会把 `{{DATA_WIN}}` 又插回去），脚本里显式 `shopt -u patsub_replacement`。

### 7. `--data-root` 指向不存在的目录时不创建它

原逻辑是「父目录存在才建三个 `*_wei`」，于是首次用 `--data-root ~/.zhishiku` 时三个数据根都没建。修：给了 `--data-root` 就先 `mkdir -p` 它。

### 8. 我自己引入的：`install.sh` 被写成 CRLF，bash 直接跑不起来

用 Python 的 `Path.write_text()`（未指定 `newline=""`）打补丁时，Windows 上会把 `\n` 翻译成 `\r\n`。于是：

```
install.sh: line 12: $'\r': command not found
install.sh: line 13: set: pipefail
: invalid option name
```

修：所有 `.sh`/`.py` 归一到 LF，新增 `.gitattributes` 锁定（`*.sh text eol=lf`、`*.py text eol=lf`、`*.ps1 text eol=crlf`），并在自测里加检查：`.sh`/`.py` 不得含 CRLF、`bash -n` 必须通过、`install.ps1` 必须带 UTF-8 BOM。

## 两个测试自身的坑（值得记下）

- **不能用 `System32\bash.exe`**：那是 WSL 的 bash，`uname -s` 报 `Linux`，`MINGW*` 分支不走、`/c/...` 不转换，于是 `--target /c/...` 全被当成「未安装」。自测现在显式找 `C:\Program Files\Git\bin\bash.exe`。
- **不要在同一个文件上混用 Python 补丁和 `edit` 工具**：`edit` 会按它手上的快照回写，把 Python 侧的修改覆盖掉（本次真的发生过一次，导致一条已修好的用例又「失败」）。

## 改动清单

- `tests/selftest.py`：新增（218 项 / 12 段）。
- `.gitattributes`：新增。
- `install.sh`：路径归一、弃用 sed、`shopt -u patsub_replacement`、`mkdir -p $DATA_ROOT`、`to_win_style` 支持 `/c/...`。
- `sync.sh`：bash 侧显式 `to_win()`（不再依赖 MSYS 的 env/argv 改写）；`segment_for` 改为「最近的 `.` 祖先目录」（原来目标不在 `$HOME` 下时会取出一长串无关中间路径）。
- `zhishiku-gengxin/scripts/yongfa.py`：`read_raw()` + CRLF 容忍哨兵正则。
- 数据侧：13 个 `qingdan.txt` 表头、3 个 `yongfa.txt` 表头、1 个损坏的 `buzou/04.txt`、1 个含非法 `★` 的卡片（备份在 `_migrate_bak-20260927/`）。
- 四份 SKILL.md：补「表头/注释里不得出现 `★`」规则。

## 验证

```bash
python3 tests/selftest.py      # 218 项，失败 0
bash sync.sh --check           # all targets in sync
```

真实数据：`ctf-pwn` 56 卡 ✅、`ai_iot` 19 卡 ✅（8 条悬空来源是外部样本库在 Linux 挂载点，与本工作无关）。
