/**
 * 危险操作确认 —— 删除 / 覆盖 / 系统级改动前先问用户
 *
 * 为什么需要：
 *   模型在排障时常顺手 rm -rf、git reset --hard、sudo、覆盖笔记库文件。
 *   一次误操作可能毁掉知识库或未提交的 exp。这里在工具真正执行前拦一道。
 *
 * 设计原则：
 *   1. 只拦「明显不可逆」的操作，正常读写一律放行，避免确认疲劳
 *   2. 非 TUI 模式（print/json/rpc）没有对话框，默认「拦」而不是「放」
 *   3. 每条规则都带明确 reason，用户和模型都能看到为什么被拦
 */

import { isToolCallEventType, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { homedir } from "node:os";

/** 家目录前缀；用于「删到家目录」判定，不写死用户名 */
const HOME = homedir();

// ─────────────────────────── 规则表 ───────────────────────────

interface Rule {
	id: string;
	test: (cmd: string) => boolean;
	reason: string;
	/** 这条命令想达到什么目的 + 会破坏什么，供用户判断是否放行 */
	purpose: string;
}

const BASH_RULES: Rule[] = [
	{
		id: "rm-rf",
		// rm 带 -r/-R 且带 -f，或直接 rm -rf
		test: (c) => /\brm\s+(-[a-zA-Z]*[rR][a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*[rR]|-[rR]\s+-f|-f\s+-[rR])/.test(c) || /\brm\s+-rf?\b/.test(c),
		reason: "递归强制删除，不可恢复",
		purpose: "删除整个目录树且不确认；一旦路径写错或变量为空（如 `rm -rf $DIR/` 而 DIR 未定义），会清掉当前目录乃至更大范围，无回收站",
	},
	{
		id: "rm-important",
		// 普通 rm 放行；只有删到知识库/笔记/家目录/源码等关键位置才问
		test: (c) =>
			/\brm\s+(-\S+\s+)*/.test(c) &&
			(/[\\/]\.zhishiku|\.pi[\\/]agent|[\\/]Desktop[\\/]|\.ssh|\/etc\/|\/usr\/|\/home\/|[A-Z]:\\Users\\/i.test(c) ||
				c.includes(HOME) ||
				/\brm\s+(-\S+\s+)*(\*|\.\s*$)/.test(c)),
		reason: "删除关键路径或通配符批量删除",
		purpose: "删到知识库/笔记/家目录/系统目录，或用通配符批量删；历史案例与未提交成果可能只存在这里",
	},
	{
		id: "dd-write",
		test: (c) => /\bdd\b[^|;]*\bof=\/dev\//.test(c),
		reason: "dd 直写块设备，可能毁盘",
		purpose: "把数据直接写到磁盘设备节点，绕过文件系统；of= 写错会覆盖分区表或整个盘",
	},
	{
		id: "mkfs",
		test: (c) => /\bmkfs(\.[a-z0-9]+)?\b/.test(c),
		reason: "格式化文件系统",
		purpose: "重建文件系统元数据；该分区原有内容全部失效",
	},
	{
		id: "disk-write",
		test: (c) => /(>|of=)\s*\/dev\/(sd|nvme|vd|hd|mmcblk)/.test(c),
		reason: "直接写物理磁盘",
		purpose: "重定向写到 /dev/sd* 等设备，等价于覆盖磁盘原始扇区",
	},
	{
		id: "git-destructive",
		test: (c) => /\bgit\s+(reset\s+--hard|clean\s+-[a-zA-Z]*f|push\s+.*(--force|-f)\b|checkout\s+--\s+\.)/.test(c),
		reason: "git 破坏性操作，可能丢失未提交改动",
		purpose: "reset --hard 丢弃工作区改动、clean -f 删未跟踪文件、push -f 覆盖远端历史；这些都无法从本地恢复",
	},
	{
		id: "chmod-777-root",
		test: (c) => /\bchmod\s+(-R\s+)?[0-7]*777\s+\/(\s|$)/.test(c),
		reason: "对根目录递归 777",
		purpose: "把根目录下所有文件改成所有人可写可执行，破坏系统权限模型",
	},
	{
		id: "kill-all",
		test: (c) => /\bkill(all)?\s+-9?\s*-1\b/.test(c) || /\bpkill\s+-9\s+/.test(c),
		reason: "批量杀进程",
		purpose: "kill -1 / pkill -9 会杀掉当前用户的大量进程，可能中断正在跑的任务或采集",
	},
	{
		id: "truncate-important",
		test: (c) => /(>|truncate\s+-s\s*0)\s*[^|;]*\.zhishiku|>\s*[^|;]*resume\/current\.md/.test(c),
		reason: "覆盖知识库 / 续跑条",
		purpose: "把状态文件清空或覆盖；续跑条/缺口板是跨会话唯一真相，丢了无法恢复记录",
	},
	{
		id: "shutdown",
		test: (c) => /\b(shutdown|reboot|halt|poweroff)\b/.test(c),
		reason: "关机 / 重启",
		purpose: "会中断所有正在运行的进程，包括未保存的采集与调试会话",
	},
];

/** write / edit 覆盖时的保护路径 */
const PROTECTED_PATHS: Array<{ re: RegExp; reason: string; purpose: string }> = [
	{
		re: /\.zhishiku\/(gengxin_wei|caiji_wei|tilian_wei)\//,
		reason: "知识库容器",
		purpose: "这是可执行知识本体（铁律/执行流/卡片/案例）。整文件覆盖会丢条目或破坏 ★ 哨兵；写入只应由 gengxin 的脚本流程做",
	},
	{
		re: /\.zhishiku\/resume\/current\.md$/,
		reason: "续跑条状态文件",
		purpose: "记录当前链阶段（C0–C5）与写者；多窗口共享。直接 write 会抹掉版本号/写者/心跳，导致其他窗口误判或覆盖，应走 resume_lock.py",
	},
	{
		re: /zhishiku-chuli\/xinxi\.txt$/,
		reason: "缺口板（采集标记真相）",
		purpose: "记录每个任务的 caiji标记 0/1 与缺口明细，是判断该不该开采集的唯一依据；整文件覆盖会丢掉未采任务",
	},
	{
		re: /(^|\/)\.ssh\//,
		reason: "SSH 密钥目录",
		purpose: "存放私钥与 known_hosts；覆盖或误改会导致无法登录、或把私钥内容写出去",
	},
	{
		re: /(^|\/)\.pi\/agent\/(SYSTEM|AGENTS|APPEND_SYSTEM)\.md$/,
		reason: "常驻提示词",
		purpose: "定义每轮行为规则（工作准则/知识库流程/删除确认）；误改会让所有会话按错误规则运行",
	},
	{
		re: /(^|\/)\.pi\/agent\/settings\.json$/,
		reason: "pi 配置",
		purpose: "记录已加载 skills/主题等；写坏会导致启动异常或资源加载不全",
	},
];

/** 允许直接覆盖的例外（这些就是正常业务流） */
const PROTECTED_ALLOW: RegExp[] = [
	/\/resume\/(done|current\.md\.bak)/, // 续跑条归档 / 备份
	/\.bak$/, // 备份文件
	/_bak\//, // 备份目录
];

/**
 * 推断「AI 为什么执行这条命令」——从命令形态 + 路径特征 + 本轮用户原话
 * 返回一句人话，让用户在确认框里判断这是正常操作还是跑偏了
 */
function inferMotivation(cmd: string, lastUserPrompt: string): string {
	const c = cmd.trim();
	const hints: string[] = [];

	// ── 命令形态 ──
	const shapes: Array<[RegExp, string]> = [
		[/\brm\s+.*(-rf?|-[a-zA-Z]*[rR][a-zA-Z]*f)/, "清理目录/删除文件"],
		[/\brm\s+/, "删除文件"],
		[/\bgit\s+reset\s+--hard/, "把仓库回退到某个提交（丢弃工作区改动）"],
		[/\bgit\s+clean\s+.*-f/, "清掉未跟踪文件"],
		[/\bgit\s+push\s+.*(-f|--force)/, "强推覆盖远端历史"],
		[/\bgit\s+checkout\s+--\s+\./, "丢弃某文件的本地改动"],
		[/\bdd\b.*of=\/dev\//, "把镜像/数据写到磁盘设备"],
		[/\bmkfs/, "格式化分区"],
		[/\bshutdown|\breboot|\bpoweroff/, "关机或重启"],
		[/\bp?kill(all)?\s+-?9?\s*-?1/, "杀掉大量进程"],
		[/\bchmod\s+(-R\s+)?[0-7]*777/, "放开权限"],
	];
	for (const [re, desc] of shapes) {
		if (re.test(c)) {
			hints.push(desc);
			break;
		}
	}

	// ── 路径特征 ──
	if (/\.zhishiku\/(gengxin_wei|caiji_wei|tilian_wei)/.test(c)) hints.push("目标是知识库容器");
	if (/resume\/current\.md/.test(c)) hints.push("目标是续跑条（多窗口共享状态）");
	if (/xinxi\.txt/.test(c)) hints.push("目标是缺口板（采集标记来源）");
	return hints.length ? hints.join("；") : "命令形态未识别出明确意图";
}

/** 从路径特征推断目的（write/edit 用） */
function inferWriteMotivation(path: string): string {
	const p = path;
	if (/\.zhishiku\/(gengxin_wei|caiji_wei|tilian_wei)/.test(p)) {
		return "想直接改知识库容器内容（正常应走 gengxin 回注流程）";
	}
	if (/resume\/current\.md$/.test(p)) {
		return "想直接改续跑条（正常应走 resume_lock.py 的 commit/patch）";
	}
	if (/xinxi\.txt$/.test(p)) {
		return "想改缺口板（通常是为了打/清 caiji标记 或补明细）";
	}
	if (/\.ssh\//.test(p)) return "想改 SSH 配置或密钥";
	if (/SYSTEM|AGENTS|APPEND_SYSTEM/.test(p)) return "想改常驻提示词规则";
	if (/settings\.json$/.test(p)) return "想改 pi 配置";
	return "想覆盖受保护文件";
}

function isTemp(path: string): boolean {
	return path.startsWith("/tmp/") || path.startsWith("/var/tmp/") || path.startsWith("/dev/shm/");
}

// ─────────────────────────── 扩展主体 ───────────────────────────

export default function dangerousOpGuard(pi: ExtensionAPI) {
	/** 用户在本次会话里已放行过的规则（避免同一操作反复问） */
	const allowedOnce = new Set<string>();
	/** 本轮用户原话，用于推断「AI 为什么这么做」 */
	let lastUserPrompt = "";

	pi.on("input", async (event) => {
		if (event.source === "extension") return { action: "continue" };
		lastUserPrompt = (event.text ?? "").slice(0, 600);
		return { action: "continue" };
	});

	async function ask(ctx: any, title: string, detail: string, key: string): Promise<boolean> {
		// 非交互模式没有对话框：默认拦，并说明原因
		if (!ctx.hasUI) {
			return false;
		}
		if (allowedOnce.has(key)) return true;

		const ok = await ctx.ui.confirm(`⚠ ${title}`, detail);
		if (ok) allowedOnce.add(key);
		return ok;
	}

	pi.on("tool_call", async (event, ctx) => {
		// ── bash ──
		if (isToolCallEventType("bash", event)) {
			const cmd = String(event.input.command ?? "");
			if (!cmd.trim()) return;

			for (const rule of BASH_RULES) {
				if (!rule.test(cmd)) continue;

				const preview = cmd.length > 300 ? cmd.slice(0, 300) + " …" : cmd;
				const ok = await ask(
					ctx,
					`拦住危险命令：${rule.id}`,
					[
						`**危险点**：${rule.reason}`,
						`**会破坏什么**：${rule.purpose}`,
						`**AI 想干什么**：${inferMotivation(cmd, lastUserPrompt)}`,
						lastUserPrompt ? `**你本轮的要求**：${lastUserPrompt.slice(0, 160)}` : "",
						"",
						"```bash",
						preview,
						"```",
						"",
						"允许执行？",
					]
						.filter(Boolean)
						.join("\n"),
					`bash:${rule.id}`,
				);
				if (!ok) {
					return {
						block: true,
						reason:
							`已拦下危险命令。\n危险点：${rule.reason}\n会影响：${rule.purpose}\n` +
							`推测的意图：${inferMotivation(cmd, lastUserPrompt)}\n` +
							`如确需执行，先用一句话说明「要做什么、为什么非这样做不可」，再请用户确认。`,
					};
				}
				break; // 一条命令只问一次
			}
			return;
		}

		// ── write / edit 覆盖受保护文件 ──
		for (const toolName of ["write", "edit"] as const) {
			if (!isToolCallEventType(toolName, event)) continue;
			const p = String((event.input as any).path ?? "");
			if (!p || isTemp(p)) return;
			if (PROTECTED_ALLOW.some((re) => re.test(p))) return;

			const hit = PROTECTED_PATHS.find((x) => x.re.test(p));
			if (!hit) return;

			const ok = await ask(
				ctx,
				`覆盖受保护文件：${hit.reason}`,
				[
					`**保护原因**：${hit.purpose}`,
					`**AI 想干什么**：${inferWriteMotivation(p)}`,
					lastUserPrompt ? `**你本轮的要求**：${lastUserPrompt.slice(0, 160)}` : "",
					`**路径**：\`${p}\``,
					"",
					"确认写入？",
				]
					.filter(Boolean)
					.join("\n"),
				`write:${hit.reason}`,
			);
			if (!ok) {
				return {
					block: true,
					reason:
						`受保护路径，已拦下。\n保护原因：${hit.purpose}\n推测的意图：${inferWriteMotivation(p)}\n路径：${p}\n` +
						`若确实需要修改，先用一句话说明为什么必须改这里，再请用户确认；并优先走对应脚本（如 resume_lock.py / gengxin 流程）。`,
				};
			}
			return;
		}
	});

	// 会话结束清空放行缓存
	pi.on("session_shutdown", async () => {
		allowedOnce.clear();
	});
}
