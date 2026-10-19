/**
 * zhishiku 续跑守卫 —— 让「续跑条」和「采集标记」从人工自觉变成机器保证
 *
 * 解决两个真实故障：
 *   A. 采集标记丢失：判定有缺口却没写进 xinxi.txt，链断在 C0
 *   B. 压缩后不按 skill：compact 把阶段、标记、题目路径一起丢掉，模型开始自由发挥
 *
 * 分工：
 *   - 扩展保证「已写下的标记不丢」「没标记不会被空跑」
 *   - 该不该打标仍由模型按 chuli skill 判定（扩展不替它判断）
 *
 * 三条原则：
 *   1. 磁盘是唯一真相：每轮从 current.md 重读，不依赖会话记忆
 *   2. 只读不写：本扩展不改任何知识库文件（写由 skill 负责）
 *   3. 读不到就静默跳过：文件缺失不能让会话起不来
 */

import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { isToolCallEventType, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { GAPBOARD, KM_ROOT, RESUME, RESUME_DONE, SKILLS_DIR } from "./_paths.ts";

// ─────────────────────────── 配置 ───────────────────────────

/** 续跑条关键字段 */
const FIELDS = ["领域", "阶段", "题目", "原路径", "采集标记", "caiji", "tilian", "gengxin", "用户已交付", "阻塞", "下次动作"] as const;
const META_FIELDS = ["版本", "写者", "心跳"] as const;
type Field = (typeof FIELDS)[number];
type Resume = Record<Field, string> & { meta: Record<string, string>; _raw: string };

// ─────────────────────────── 读盘 ───────────────────────────

function safeRead(p: string, max = 1 << 18): string {
	try {
		return readFileSync(p, "utf8").slice(0, max);
	} catch {
		return "";
	}
}

function parseResume(): Resume | null {
	const raw = safeRead(RESUME, 8192);
	if (!raw.trim()) return null;
	const out: any = { _raw: raw, meta: {} };
	for (const f of FIELDS) {
		const m = new RegExp(`^${f}[：:]\\s*(.+)$`, "m").exec(raw);
		out[f] = m ? m[1].trim() : "";
	}
	for (const f of META_FIELDS) {
		const m = new RegExp(`^${f}[：:]\\s*(.+)$`, "m").exec(raw);
		if (m) out.meta[f] = m[1].trim();
	}
	if (!out.阶段) return null;
	return out as Resume;
}

function isClosed(r: Resume): boolean {
	return /^(闭|C5|已闭)$/.test(r.阶段);
}

/** 心跳是否过期（阈值 30 分钟） */
function heartbeatState(r: Resume): { expired: boolean; why: string } {
	const hb = r.meta["心跳"] ?? "";
	if (!hb) return { expired: true, why: "无心跳" };
	const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/.exec(hb.trim());
	if (!m) return { expired: true, why: "心跳格式异常" };
	const t = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5])).getTime();
	const mins = Math.floor((Date.now() - t) / 60000);
	if (mins > 30) return { expired: true, why: `心跳已 ${mins} 分钟未更新` };
	return { expired: false, why: `心跳正常（${mins} 分钟前）` };
}

/** 跑 doctor.py，只取「汇总」前的关键行（缓存 60 秒，避免每轮 subprocess） */
let doctorCache = { at: 0, text: "" };
function runDoctor(domain: string): string {
	const now = Date.now();
	if (now - doctorCache.at < 60_000) return doctorCache.text;
	try {
		const { execFileSync } = require("node:child_process");
		const out = execFileSync(
			"python3",
			[join(SKILLS_DIR, "zhishiku-chuli", "scripts", "doctor.py"), "--domain", domain],
			{ encoding: "utf8", timeout: 8000 },
		);
		// 只保留汇总段，控制注入体积
		const idx = out.indexOf("## 汇总");
		const tail = idx >= 0 ? out.slice(idx) : "";
		const text = tail.trim();
		doctorCache = { at: now, text };
		return text;
	} catch (e: any) {
		const text = String(e?.stdout ?? "").slice(-800);
		doctorCache = { at: now, text };
		return text;
	}
}

/** 取本窗口短 ID */
function windowId(ctx: any): string {
	try {
		const id = ctx?.sessionManager?.getSessionId?.() ?? "";
		return String(id).slice(0, 8) || "unknown";
	} catch {
		return "unknown";
	}
}

/** 解析缺口板：返回所有 caiji标记：1 的任务节 */
interface GapTask {
	task: string;
	status: string;
	mark: string;
	summary: string;
	detail: string;
	note?: string;
	domain?: string;
	updated?: string;
}
/** 暂定任务：挂起，每次扫描都要点名，不自动开工 */
function parsePaused(): GapTask[] {
	const raw = safeRead(GAPBOARD, 1 << 18);
	if (!raw.trim()) return [];
	const out: GapTask[] = [];
	for (const b of raw.split(/^---$/m).map((x) => x.trim()).filter(Boolean)) {
		if (!/^任务[：:]/m.test(b)) continue;
		const g = (k: string) => {
			const m = new RegExp(`^${k}[：:]\\s*(.*)$`, "m").exec(b);
			return m ? m[1].trim() : "";
		};
		if (g("状态") !== "暂定") continue;
		out.push({
			task: g("任务"),
			status: "暂定",
			mark: g("caiji标记"),
			summary: g("标记摘要"),
			detail: g("标记明细"),
			note: g("备注"),
			domain: g("领域"),
			updated: g("更新"),
		});
	}
	return out;
}

function parseGapboard(): { tasks: GapTask[]; openCount: number } {
	const raw = safeRead(GAPBOARD, 1 << 18);
	if (!raw.trim()) return { tasks: [], openCount: 0 };
	const blocks = raw.split(/^---$/m).map((b) => b.trim()).filter(Boolean);
	const tasks: GapTask[] = [];
	for (const b of blocks) {
		if (!/^任务[：:]/m.test(b)) continue;
		const g = (k: string) => {
			const m = new RegExp(`^${k}[：:]\\s*(.*)$`, "m").exec(b);
			return m ? m[1].trim() : "";
		};
		const status = g("状态");
		// 注意：缺口板的字段名是「caiji标记」（见 SKILL.md 与 xinxi.txt 表头），
		// 不是续跑条用的「采集标记」。两者名字不同，不要混用。
		const mark = g("caiji标记") || g("采集标记");
		// 已采清 / 闭 / 暂定 不算未闭缺口
		if (/已采清|^闭$|暂定/.test(status)) continue;
		if (mark !== "1") continue;
		tasks.push({
			task: g("任务"),
			status,
			mark,
			summary: g("标记摘要"),
			detail: g("标记明细"),
		});
	}
	return { tasks, openCount: tasks.length };
}

// ─────────────────────────── 渲染 ───────────────────────────

function renderResume(r: Resume): string {
	return [
		`## 续跑条（磁盘真相 · 每轮重读 · 勿靠记忆）`,
		``,
		`| 字段 | 值 |`,
		`|---|---|`,
		`| 领域 | ${r.领域 || "-"} |`,
		`| 阶段 | **${r.阶段}** |`,
		`| 题目 | ${r.题目 || "-"} |`,
		`| 版本 / 写者 | v${r.meta["版本"] || "?"} / ${(r.meta["写者"] || "-").slice(0, 8)} |`,
		`| 采集标记 | ${r.采集标记 || "0"} |`,
		`| 用户已交付 | ${r.用户已交付 || "否"} |`,
		`| caiji / tilian / gengxin | ${r.caiji || "-"} / ${r.tilian || "-"} / ${r.gengxin || "-"} |`,
		`| 阻塞 | ${r.阻塞 || "无"} |`,
		`| 下次动作 | ${r.下次动作 || "-"} |`,
		``,
		`阶段含义：C0 处理中 · C1 已交付 · C2 采集 · C3 提炼 · C4 回注 · C5 收尾 · 闭`,
	].join("\n");
}

function renderGaps(tasks: GapTask[]): string {
	const lines = [`## 缺口板：${tasks.length} 个未闭采集标记`];
	for (const t of tasks) {
		lines.push(`- **${t.task || "未命名"}**（状态 ${t.status || "?"}）`);
		if (t.summary && t.summary !== "-") lines.push(`  - 摘要：${t.summary}`);
		if (t.detail && t.detail !== "-") lines.push(`  - 明细：${t.detail.slice(0, 300)}`);
	}
	lines.push(`- 明细文件：\`${GAPBOARD}\``);
	return lines.join("\n");
}

// ─────────────────────────── 扩展主体 ───────────────────────────

export default function zhishikuGuard(pi: ExtensionAPI) {
	let alertedMissingMark = false;
	/** 本轮是否碰过 wp 搜索（tools/wp-search.txt 或 wp 搜索命令） */
	let usedWpThisRound = false;

	pi.on("session_start", async (_e, ctx) => {
		const r = parseResume();
		if (!r) {
			ctx.ui.notify("zhishiku: 无续跑条，按普通任务处理", "info");
			return;
		}
		if (isClosed(r)) {
			ctx.ui.notify(`zhishiku: 链已闭（${r.题目 || "-"}）`, "info");
			return;
		}
		const gaps = parseGapboard();
		const paused = parsePaused();
		if (paused.length) {
			ctx.ui.notify(
				`zhishiku: ${paused.length} 项暂定（挂起，需你提及才处理）：` +
					paused.map((t) => `[${t.domain || "?"}] ${t.task || "?"}`).join("；"),
				"warning",
			);
		}
		const me = windowId(ctx);
		const owner = (r.meta["写者"] ?? "").slice(0, 8);
		const ver = r.meta["版本"] ?? "?";
		const hb = heartbeatState(r);
		const ownerTag =
			!owner || owner === me
				? `你是 owner（${me}）`
				: `owner=${owner}${hb.expired ? "（心跳过期，可 takeover）" : ""}`;
		ctx.ui.notify(
			`zhishiku: 窗口 ${me} · v${ver} · ${r.阶段} · ${r.题目 || "-"} · ${ownerTag} · 未闭标记 ${gaps.openCount}`,
			hb.expired && owner !== me ? "warning" : "info",
		);
	});

	// ── 核心：每轮注入续跑条 + 缺口摘要 ──
	pi.on("before_agent_start", async (event, _ctx) => {
		const r = parseResume();
		if (!r || isClosed(r)) return;

		const gaps = parseGapboard();
		const parts = [renderResume(r)];
		if (gaps.tasks.length) parts.push(renderGaps(gaps.tasks));
		const paused = parsePaused();
		if (paused.length) {
			const lines = [`## 暂定任务：${paused.length} 项（挂起 · 用户提及才处理 · 不自动开工）`];
			for (const t of paused) {
				lines.push(`- [${t.domain || "?"}] ${t.task || "?"}（更新 ${t.updated || "-"}）`);
				if (t.note) lines.push(`  - 恢复点：${t.note}`);
			}
			lines.push(`- **本轮如非用户提及上述任务，不要主动开工、不要催问；只需知道它们存在。**`);
			parts.push(lines.join("\n"));
		}
		// 交付物不全：摆到模型面前，避免报「已交付」却只有 exp
		const miss = missingDeliverables(r);
		if (miss) {
			parts.push(
				[
					"## 交付物不全（pwn/CTF 必须双份）",
					"",
					`- ${miss}`,
					"- `exp_agent.py`：能跑通的利用脚本",
					"- `wp_agent.md`：简明 writeup（漏洞点/思路/gadget 与偏移/踩坑/PoC 怎么跑）；**没跑通也要写**，记录卡在哪、下一步思路",
					"- 只有 exp 没 wp = 交付未完成，不得报「已交付」；两份都写原题目目录，不碰用户的 exp.py / wp.md",
				].join("\n"),
			);
		}

		// 全链体检汇总（只读，含交叉检验异常）
		if (r.领域) {
			const doc = runDoctor(r.领域);
			if (doc && doc.includes("✗")) parts.push(`## 体检异常\n\n${doc}`);
		}

		// systemPrompt 每轮重算（不落历史）；message 负责跨压缩可见
		return {
			systemPrompt: `${event.systemPrompt}\n\n${parts.join("\n\n")}`,
			message: {
				customType: "zhishiku-resume",
				display: true,
				content: [
					`[zhishiku 续跑条 · ${new Date().toISOString().slice(0, 16).replace("T", " ")}]`,
					`领域 ${r.领域 || "-"} · 阶段 ${r.阶段} · 题目 ${r.题目 || "-"}`,
					`采集标记 ${r.采集标记 || "0"} · 已交付 ${r.用户已交付 || "否"}`,
					`下次动作：${r.下次动作 || "-"}`,
					gaps.openCount ? `未闭采集标记 ${gaps.openCount} 条，明细见 ${GAPBOARD}` : "",
				]
					.filter(Boolean)
					.join("\n"),
			},
		};
	});

	// ── 压缩前：把续跑条快照落盘，压缩后仍能重建 ──
	pi.on("session_before_compact", async (event, ctx) => {
		const r = parseResume();
		if (!r || isClosed(r)) return; // 不拦压缩，只做备份

		try {
			mkdirSync(RESUME_DONE, { recursive: true });
			const stamp = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 12);
			const dest = join(RESUME_DONE, `${stamp}-precompact-${r.领域 || "unknown"}.md`);
			copyFileSync(RESUME, dest);
			// 轮转：precompact 类快照只留最近 KEEP_PRECOMPACT 份，防止 done/ 无限膨胀
			rotatePrecompact();
			ctx.ui.notify(`zhishiku: 压缩前已快照续跑条（${r.阶段}）`, "info");
		} catch {
			// 快照失败不影响压缩
		}
		return; // 不接管摘要，交给默认压缩
	});

	// ── 压缩后：立即重注入，防止上一轮上下文被摘要替代后失忆 ──
	pi.on("session_compact", async (_event, ctx) => {
		const r = parseResume();
		if (!r || isClosed(r)) return;
		pi.sendMessage({
			customType: "zhishiku-resume",
			display: true,
			content: [
				`[压缩后重建 · 磁盘真相]`,
				renderResume(r),
			].join("\n\n"),
		});
		ctx.ui.notify(`zhishiku: 压缩完成，已按磁盘重建续跑条（${r.阶段}）`, "info");
	});

	// ── 拦空采：缺口板没有 caiji标记：1 时读 caiji skill 直接拒 ──
	pi.on("tool_call", async (event, ctx) => {
		if (isToolCallEventType("read", event)) {
			const p = String(event.input.path ?? "");
			if (!p.includes("zhishiku-caiji/SKILL.md")) return;

			const r = parseResume();
			const gaps = parseGapboard();
			if (gaps.openCount === 0) {
				ctx.ui.notify("zhishiku: 缺口板无 caiji标记：1，已拦下空采", "warning");
				return {
					block: true,
					reason:
						`缺口板 ${GAPBOARD} 里没有 caiji标记：1 的任务节，禁止空跑 caiji。\n` +
						`先把缺口写进对应任务节（任务/状态/caiji标记：1/标记明细），再开采集。`,
				};
			}
			ctx.ui.notify(`zhishiku: 采集标记 ${gaps.openCount} 条，允许 caiji`, "info");
		}
	});

	// ── 事后提醒：碰了 chuli skill 但没写缺口板 ──
	pi.on("tool_call", async (event, ctx) => {
		if (!isToolCallEventType("read", event)) return;
		const p = String(event.input.path ?? "");
		if (p.includes("zhishiku-chuli/SKILL.md")) {
			alertedMissingMark = false;
			ctx.ui.notify("zhishiku: 进入 chuli，缺口须写 xinxi.txt", "info");
		}
		// 读过 wp 检索规范 → 本轮用过 wp（收尾需回答「缺口已查」）
		if (p.includes("tools/wp-search.txt")) {
			usedWpThisRound = true;
		}
	});

	// ── 抓 wp 检索动作（curl 搜索 / mcporter exa / gh search）──
	pi.on("tool_call", async (event) => {
		if (!isToolCallEventType("bash", event)) return;
		const cmd = String(event.input.command ?? "");
		if (/writeup|wp-search|web_search_exa|gh search|duckduckgo|google\.com\/search/i.test(cmd)) {
			usedWpThisRound = true;
		}
	});

	pi.on("agent_end", async (_event, ctx) => {
		if (alertedMissingMark) return;
		const board = safeRead(GAPBOARD, 1 << 18);
		if (!board.trim()) return;
		const r = parseResume();
		// 阶段 C0 且缺口板无任何进行中节 → 提醒可能漏打标
		if (r && r.阶段 === "C0" && !/状态[：:]\s*进行中/m.test(board)) {
			alertedMissingMark = true;
			ctx.ui.notify("zhishiku: 阶段 C0 但缺口板无进行中任务，检查是否漏写采集标记", "warning");
		}
	});

	pi.on("session_shutdown", async () => {
		usedWpThisRound = false;
	});
	/** precompact 快照轮转：只保留最近 N 份（按文件名时间戳排序） */
	function rotatePrecompact(keep = 5): void {
		try {
			const names = readdirSync(RESUME_DONE)
				.filter((n) => n.includes("-precompact-"))
				.sort(); // 文件名以 YYYYMMDDHHMM 开头，字典序即时间序
			const drop = names.slice(0, Math.max(0, names.length - keep));
			for (const n of drop) {
				try {
					unlinkSync(join(RESUME_DONE, n));
				} catch {
					/* 单个失败不阻塞 */
				}
			}
		} catch {
			/* 目录读不到就跳过 */
		}
	}

	/** 检查 pwn/CTF 交付物双份是否齐全；返回缺失说明（null=齐全或不适用） */
	function missingDeliverables(r: Resume): string | null {
		if (!r.原路径) return null;
		if (!/ctf-pwn|pwn|ctf/i.test(r.领域 || "")) return null;
		const dir = r.原路径.replace(/\/[^/]+$/, "");
		const hasExp = existsSync(join(dir, "exp_agent.py"));
		const hasWp = existsSync(join(dir, "wp_agent.md"));
		if (hasExp && hasWp) return null;
		const miss: string[] = [];
		if (!hasExp) miss.push("exp_agent.py");
		if (!hasWp) miss.push("wp_agent.md");
		return `目录 ${dir} 缺 ${miss.join("、")}`;
	}

	// ── 交付物完整性：收尾提醒 ──
	pi.on("agent_settled", async (_event, ctx) => {
		const r = parseResume();
		if (!r) return;
		const miss = missingDeliverables(r);
		if (!miss) return;
		ctx.ui.notify(
			`zhishiku: pwn/CTF 交付物不全（${miss}）\n` +
				`规则：两份都要写；没跑通也要写 wp 记录卡点。只有 exp 没 wp = 交付未完成。`,
			"warning",
		);
	});

	pi.on("agent_settled", async (_event, ctx) => {
		const r = parseResume();
		if (!r) return;
		if (r.阶段 === "C5") {
			ctx.ui.notify("zhishiku: 阶段 C5，记得 yongfa.py --tick 后把阶段写闭", "info");
		}
		if (r.阶段 === "C5" || r.阶段 === "C1") {
			const root = join(KM_ROOT, "gengxin_wei", r.领域 || "");
			ctx.ui.notify(
				`zhishiku: 交付报告需带技术卡执行流 — python3 ${join(SKILLS_DIR, "zhishiku-chuli", "scripts", "show_flow.py")} ${root} --date <YYYY-MM-DD>`,
				"info",
			);
		}

		// wp 专项：用过 wp 但收尾仍是标记 0 → 提醒复查缺口
		if (usedWpThisRound && (r.采集标记 || "0") === "0" && (r.阶段 === "C0" || r.阶段 === "C1")) {
			ctx.ui.notify(
				"zhishiku: 本轮用过 wp，收尾须回答「缺口已查：有/无」；wp 复现成功而库无卡 → 必须 caiji标记：1",
				"warning",
			);
		}
	});
}
