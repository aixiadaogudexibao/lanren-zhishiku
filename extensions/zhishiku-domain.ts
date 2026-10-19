/**
 * zhishiku-domain —— 按领域加载知识库上下文
 *
 * 作用：
 *   1. 扫描 <知识库根>/gengxin_wei/<领域>/，自动发现已有领域
 *   2. 每轮开工前判断当前任务属于哪个领域（显式 > 续跑条 > cwd > 提示词关键字）
 *   3. 命中后把该领域的「铁律 + 流程表清单 + 工具清单」注入系统提示
 *   4. /domain 手动切换；zhishiku_domain 工具供模型主动查询
 *
 * 只注入「索引级」信息（清单），正文仍由模型按路径 read，避免把 6KB 铁律每轮全灌。
 */

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { basename, join } from "node:path";
import { Type } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { GAPBOARD, GENGXIN, KM_ROOT, RESUME } from "./_paths.ts";

// ─────────────────────────── 配置 ───────────────────────────

/** 领域识别信号：cwd 片段 / 提示词关键字 */
const SIGNALS: Record<string, { cwd: string[]; words: string[] }> = {
	"ctf-pwn": {
		cwd: ["/pwn", "/ctf", "nss", "强网杯", "长城杯", "羊城杯", "hackthebox", "靶场"],
		words: ["pwn", "堆", "栈溢出", "格式化字符串", "fmtstr", "format string", "heap", "堆溢出", "uaf", "rop", "ret2", "shellcode", "tcache", "fastbin", "libc", "one_gadget", "canary", "checksec", "glibc", "pwntools", "exp.py"],
	},
	"chrome-v8": {
		cwd: ["chrome-v8", "chromium", "v8", "electron", "livehime", "bilibili", "直播姬", "cef"],
		words: ["v8", "chrome", "chromium", "electron", "cef", "bytecode", "snapshot", "js引擎", "javascript引擎", "turboFan", "maglev"],
	},
	ai_iot: {
		cwd: ["ai_iot", "firmware", "固件", "router", "iot", "samples", "rootfs"],
		words: ["固件", "firmware", "路由器", "iot", "binwalk", "固件解包", "qemu", "mips", "armel", "rootfs", "upnp", "嵌入式"],
	},
};

/** 注入上限，防止上下文爆炸 */
const MAX_TIEULI = 1400;
const MAX_LIUCHENG_LIST = 60;
const MAX_TOOLS_LIST = 20;

// ─────────────────────────── 类型 ───────────────────────────

interface DomainInfo {
	name: string;
	root: string;
	tieuliBytes: number;
	liuchengCount: number;
	toolCount: number;
	jishuCount: number;
}

interface DomainCard {
	domain: string;
	tieuli: string[];
	/** 流程表按技术前缀聚合：{ "H": {count, sample}, ... } */
	liuchengGroups: Array<{ prefix: string; count: number; sample: string[] }>;
	liuchengTotal: number;
	tools: string[];
	paths: Record<string, string>;
	reason: string;
}

// ─────────────────────────── 磁盘工具 ───────────────────────────

function safeRead(p: string, max = 1 << 20): string {
	try {
		return readFileSync(p, "utf8").slice(0, max);
	} catch {
		return "";
	}
}

function safeLs(p: string): string[] {
	try {
		return readdirSync(p).sort();
	} catch {
		return [];
	}
}

function fileSize(p: string): number {
	try {
		return statSync(p).size;
	} catch {
		return 0;
	}
}

/** 扫描所有领域（以 gengxin_wei/<领域>/ 为准） */
function scanDomains(): DomainInfo[] {
	return safeLs(GENGXIN)
		.filter((n) => !n.startsWith(".") && !n.startsWith("_"))
		.map((name) => {
			const root = join(GENGXIN, name);
			try {
				if (!statSync(root).isDirectory()) return null;
			} catch {
				return null;
			}
			if (!existsSync(join(root, "tieuli.txt"))) return null; // 必须有铁律才算完整领域
			return {
				name,
				root,
				tieuliBytes: fileSize(join(root, "tieuli.txt")),
				liuchengCount: safeLs(join(root, "liucheng_biao")).filter((f) => f !== "00_说明.txt").length,
				toolCount: safeLs(join(root, "tools")).filter((f) => !f.startsWith("_")).length,
				jishuCount: safeLs(join(root, "jishu")).length,
			};
		})
		.filter((d): d is DomainInfo => d !== null);
}

/** 读该领域铁律（截断到 MAX_TIEULI） */
function loadTieuli(root: string): string[] {
	const raw = safeRead(join(root, "tieuli.txt"), MAX_TIEULI * 4);
	const out: string[] = [];
	let used = 0;
	for (const line of raw.split("\n")) {
		const t = line.trim();
		if (!t || t.startsWith("#") || t.startsWith("来源：") || t.startsWith("命中：")) continue;
		if (used + t.length > MAX_TIEULI) {
			out.push("…（更多铁律见 tieuli.txt）");
			break;
		}
		out.push(t.replace(/^[-*]\s*/, ""));
		used += t.length;
	}
	return out;
}

function buildCard(domain: string, reason: string): DomainCard | null {
	const root = join(GENGXIN, domain);
	if (!existsSync(root)) return null;
	const allCards = safeLs(join(root, "liucheng_biao")).filter((f) => f !== "00_说明.txt");
	// 按前缀（H./S./K./E./C./... ）聚合：只报"有哪些方向 + 各多少个 + 2~3 个样例"
	// 完整清单让模型自己 ls，避免每轮灌上千字符
	const groups = new Map<string, string[]>();
	for (const f of allCards) {
		const base = f.replace(/\.txt$/, "");
		const m = /^([A-Za-z]+)\./.exec(base);
		const key = m ? m[1] : "其它";
		if (!groups.has(key)) groups.set(key, []);
		groups.get(key)!.push(base);
	}
	const liuchengGroups = [...groups.entries()]
		.sort((a, b) => b[1].length - a[1].length)
		.map(([prefix, list]) => ({ prefix, count: list.length, sample: list.slice(0, 3) }));

	const tools = safeLs(join(root, "tools"))
		.filter((f) => !f.startsWith("_") && f.endsWith(".txt"))
		.slice(0, MAX_TOOLS_LIST);
	return {
		domain,
		tieuli: loadTieuli(root),
		liuchengGroups,
		liuchengTotal: allCards.length,
		tools,
		paths: {
			root,
			tieuli: join(root, "tieuli.txt"),
			liucheng: join(root, "liucheng.txt"),
			liucheng_biao: join(root, "liucheng_biao"),
			tools: join(root, "tools"),
			jishu: join(root, "jishu"),
			cuowu: join(root, "cuowu.txt"),
			zhiling: join(root, "zhiling.txt"),
			yongfa: join(root, "yongfa.txt"),
		},
		reason,
	};
}

// ─────────────────────────── 领域判定 ───────────────────────────

/** 从续跑条读「领域：xxx」 */
function domainFromResume(): string | null {
	const raw = safeRead(RESUME, 4096);
	const m = /^领域[：:]\s*(\S+)/m.exec(raw);
	if (!m) return null;
	const stage = /^阶段[：:]\s*(\S+)/m.exec(raw);
	const stageVal = stage?.[1] ?? "";
	if (stageVal === "闭") return null; // 链已闭，不算强信号
	return m[1].trim();
}

/** 打分式关键字匹配 */
function domainFromText(text: string, domains: string[]): { domain: string; score: number } | null {
	const low = text.toLowerCase();
	let best: { domain: string; score: number } | null = null;
	for (const d of domains) {
		const sig = SIGNALS[d];
		if (!sig) continue;
		let score = 0;
		for (const w of sig.words) if (low.includes(w.toLowerCase())) score += 2;
		if (score > 0 && (!best || score > best.score)) best = { domain: d, score };
	}
	return best;
}

/** cwd 路径匹配 */
function domainFromCwd(cwd: string, domains: string[]): string | null {
	const low = cwd.toLowerCase();
	let best: { d: string; n: number } | null = null;
	for (const d of domains) {
		const sig = SIGNALS[d];
		if (!sig) continue;
		let n = 0;
		for (const seg of sig.cwd) if (low.includes(seg.toLowerCase())) n++;
		if (n > 0 && (!best || n > best.n)) best = { d, n };
	}
	return best?.d ?? null;
}

/** 综合判定：显式 > 提示词 > 续跑条 > cwd
 *  续跑条只说明上一条链停在哪，不应压过当前题目话题；
 *  题目关键字命中说明用户正在谈别的领域。
 */
function resolveDomain(
	prompt: string,
	cwd: string,
	explicit: string | null,
	domains: string[],
): { domain: string | null; reason: string } {
	if (explicit && domains.includes(explicit)) return { domain: explicit, reason: "显式指定" };
	const byText = domainFromText(prompt, domains);
	if (byText && byText.score >= 2) return { domain: byText.domain, reason: `关键字(${byText.score})` };
	const fromResume = domainFromResume();
	if (fromResume && domains.includes(fromResume)) return { domain: fromResume, reason: "续跑条（无题目关键字时）" };
	if (byText) return { domain: byText.domain, reason: `弱关键字(${byText.score})` };
	const byCwd = domainFromCwd(cwd, domains);
	if (byCwd) return { domain: byCwd, reason: "cwd 路径" };
	return { domain: null, reason: "未命中" };
}

// ─────────────────────────── 渲染 ───────────────────────────

function renderCard(c: DomainCard): string {
	const L = (s: string) => s; // 占位，方便以后改格式
	const lines: string[] = [];
	lines.push(`## zhishiku 领域已加载：${c.domain}（依据：${c.reason}）`);
	lines.push("");
	lines.push(`领域根：\`${c.paths.root}\``);
	lines.push("");
	if (c.tieuli.length) {
		lines.push("**铁律（先用这些排查，命中就照做）**");
		for (const t of c.tieuli) lines.push(`- ${t}`);
		lines.push("");
	}
	if (c.liuchengGroups.length) {
		const g = c.liuchengGroups
			.map((x) => `${x.prefix}(${x.count})${x.sample.length ? `:${x.sample.join("/")}` : ""}`)
			.join("  ");
		lines.push(`**流程表 liucheng_biao/ 共 ${c.liuchengTotal} 个，按技术前缀分布：**`);
		lines.push(g);
		lines.push(`（要具体卡名：ls \`${c.paths.liucheng_biao}\` 或 rg 关键词）`);
		lines.push("");
	}
	if (c.tools.length) {
		lines.push(`**工具说明 tools/**：${c.tools.map((f) => f.replace(/\.txt$/, "")).join(" · ")}`);
		lines.push("");
	}
	lines.push(
		[
			"**取用纪律**",
			`- 正文按路径 read：\`${c.paths.tieuli}\` / \`${c.paths.liucheng}\` / \`${c.paths.cuowu}\` / \`${c.paths.zhiling}\``,
			`- 处理前先 read \`${c.paths.tieuli}\` 与相关 \`liucheng_biao\`；工具用法以容器内说明为准`,
			`- 缺口记 \`${GAPBOARD}\`；阶段记 \`${RESUME}\``,
		].join("\n"),
	);
	return lines.join("\n");
}

// ─────────────────────────── 扩展主体 ───────────────────────────

export default function zhishikuDomain(pi: ExtensionAPI) {
	let explicitDomain: string | null = null;
	let lastCardHash = "";

	const domainsOf = () => scanDomains().map((d) => d.name);

	pi.on("session_start", async (_event, ctx) => {
		const ds = scanDomains();
		if (ds.length === 0) {
			ctx.ui.notify(`zhishiku: 未在 ${GENGXIN} 下找到领域（需含 tieuli.txt）`, "warning");
			return;
		}
		// 续跑条只是候选信号，不写进 explicitDomain（否则会盖掉后续的题目关键字）
		const resumed = domainFromResume();
		if (resumed && ds.some((d) => d.name === resumed)) {
			ctx.ui.notify(`zhishiku: 续跑条领域 = ${resumed}（${ds.length} 个领域可用）`, "info");
		} else {
			ctx.ui.notify(`zhishiku: ${ds.length} 个领域 [${ds.map((d) => d.name).join(", ")}]`, "info");
		}
	});

	pi.on("before_agent_start", async (event, _ctx) => {
		const domains = domainsOf();
		const { domain, reason } = resolveDomain(event.prompt ?? "", event.systemPromptOptions?.cwd ?? process.cwd(), explicitDomain, domains);
		if (!domain) return;

		const card = buildCard(domain, reason);
		if (!card) return;

		const hash = `${domain}|${reason}|${card.tieuli.length}`;
		if (hash === lastCardHash) return; // 同一领域同一依据不重复灌
		lastCardHash = hash;

		return {
			systemPrompt: `${event.systemPrompt}\n\n${renderCard(card)}`,
		};
	});

	// ── /domain 命令 ──
	pi.registerCommand("domain", {
		description: "查看/切换 zhishiku 领域（/domain 列全部，/domain ctf-pwn 锁定）",
		getArgumentCompletions: (prefix) => {
			const names = domainsOf().filter((n) => n.startsWith(prefix));
			return names.length ? names.map((n) => ({ value: n, label: n })) : null;
		},
		handler: async (args, ctx) => {
			const ds = scanDomains();
			const arg = (args ?? "").trim();
			if (!arg) {
				const items = ds.map((d) => `${d.name}  (ti:${d.tieuliBytes}B lc:${d.liuchengCount} tools:${d.toolCount} jishu:${d.jishuCount})`);
				const picked = await ctx.ui.select(`zhishiku 领域（当前：${explicitDomain ?? "自动"}）`, ["自动（按信号判定）", ...items]);
				if (!picked) return;
				if (picked.startsWith("自动")) {
					explicitDomain = null;
					ctx.ui.notify("zhishiku: 已切回自动判定", "info");
				} else {
					explicitDomain = picked.split(/\s+/)[0];
					ctx.ui.notify(`zhishiku: 已锁定 ${explicitDomain}`, "info");
				}
				return;
			}
			if (arg === "auto" || arg === "自动") {
				explicitDomain = null;
				ctx.ui.notify("zhishiku: 已切回自动判定", "info");
				return;
			}
			if (!ds.some((d) => d.name === arg)) {
				ctx.ui.notify(`zhishiku: 无此领域 ${arg}；可选 ${ds.map((d) => d.name).join(", ")}`, "error");
				return;
			}
			explicitDomain = arg;
			ctx.ui.notify(`zhishiku: 已锁定 ${arg}`, "info");
		},
	});

	// ── 查询工具 ──
	pi.registerTool({
		name: "zhishiku_domain",
		label: "zhishiku 领域",
		description: "查看或切换 zhishiku 领域，返回该领域铁律/流程表/工具清单与路径。切换后本轮系统提示会带上该领域卡片。",
		parameters: Type.Object({
			domain: Type.Optional(Type.String({ description: "领域名；省略则列出全部，'auto' 恢复自动判定" })),
		}),
		async execute(_id, params, _signal, _onUpdate, ctx) {
			const ds = scanDomains();
			if (!params.domain) {
				const lines = ds.map((d) => `- ${d.name}: tieuli ${d.tieuliBytes}B, liucheng_biao ${d.liuchengCount}, tools ${d.toolCount}, jishu ${d.jishuCount}`);
				const cur = explicitDomain ?? domainFromResume() ?? "自动";
				return {
					content: [{ type: "text", text: `当前领域：${cur}\n\n${lines.join("\n")}` }],
					details: { domains: ds.map((d) => d.name), current: cur },
				};
			}
			if (params.domain === "auto") {
				explicitDomain = null;
				return { content: [{ type: "text", text: "已切回自动判定" }], details: { current: "auto" } };
			}
			if (!ds.some((d) => d.name === params.domain)) {
				return { content: [{ type: "text", text: `无此领域：${params.domain}。可选：${ds.map((d) => d.name).join(", ")}` }], details: { ok: false } };
			}
			explicitDomain = params.domain;
			const card = buildCard(params.domain, "工具切换");
			return {
				content: [{ type: "text", text: card ? renderCard(card) : `已切到 ${params.domain}` }],
				details: { current: explicitDomain },
			};
		},
	});
}
