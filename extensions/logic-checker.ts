/**
 * 自然语言与逻辑检查 —— 在动手前挑出「话说不通」和「自己绕圈」的问题
 *
 * 两类检查：
 *   A. 用户输入侧（input 事件）
 *      - 前后矛盾：同一轮里既要求 A 又要求非 A
 *      - 目标不清：要"优化/修一下/看看"，但没有对象或验收标准
 *      - 覆盖冲突：新的限制把主功能堵死（如"禁止任何写操作"+"把结果存盘"）
 *
 *   B. 自身行为侧（tool_call / tool_result）
 *      - 循环无用功：同一命令重复执行无进展
 *      - 反复失败：同一操作连续失败 3 次仍在重试
 *      - 原地打转：连续多次 read 同一文件却不产出
 *
 * 设计原则：
 *   1. 只提示，不拦（除明显死循环）——判断"有没有矛盾"需要模型和用户参与
 *   2. 提示走 systemPrompt，把结论摆到模型面前，让它自己决定要不要问用户
 *   3. 有置信阈值，不因一个"但是"就报矛盾，避免狼来了
 */

import { createHash } from "node:crypto";
import { type ExtensionAPI } from "@earendil-works/pi-coding-agent";

// ─────────────────────────── 规则 ───────────────────────────

/** 矛盾标记词：出现这些说明用户自己在否定前面的话 */
const CONTRADICT_MARKERS = ["但是不要", "但别", "不过别", "不用", "不需要", "不要", "别用", "禁止", "不能", "except", "but not", "don't", "never"];

/** 模糊动词：只说动词没说对象/标准 */
const VAGUE_VERBS = ["优化一下", "优化下", "改一下", "改改", "修一下", "修下", "看看", "搞一下", "弄一下", "处理一下", "完善一下", "调整一下"];

/** 验收标准词：有这些就算目标清楚 */
const CRITERIA = ["要能", "必须", "至少", "不超过", "通过", "返回", "输出", "格式", "标准", "验收", "测试", "跑通", "flag", "shell"];

/** 绝对限制词：容易把主功能堵死 */
const ABSOLUTE_BANS = ["禁止任何", "不要任何", "一律不许", "完全不能", "永远不要"];

/** 高产出动作：做过这些就算有进展，不算打转 */
const PRODUCTIVE_TOOLS = new Set(["write", "edit"]);
/** 只读动作 */
const READ_TOOLS = new Set(["read", "ls", "grep", "find"]);

// ─────────────────────────── 状态 ───────────────────────────

interface Issue {
	kind: string;
	detail: string;
	hint: string;
}

interface CallRecord {
	id: string; // toolCallId
	fp: string; // 指纹：工具名 + 参数
	tool: string;
	ok: boolean;
	turn: number;
}

// ─────────────────────────── 文本分析 ───────────────────────────

function findContradiction(text: string): Issue | null {
	const low = text.toLowerCase();
	// 只有出现否定标记 + 前文有同向要求，才算可疑
	const hasNeg = CONTRADICT_MARKERS.some((m) => low.includes(m.toLowerCase()));
	if (!hasNeg) return null;

	// 「先 A 再 B」「A，但不要 B」结构
	const butIdx = low.search(/但是|但不过|不过|然而|but\b/);
	if (butIdx > 10) {
		const before = text.slice(0, butIdx);
		const after = text.slice(butIdx);
		const afterHasBan = CONTRADICT_MARKERS.some((m) => after.toLowerCase().includes(m.toLowerCase()));
		if (afterHasBan && before.length > 8) {
			return {
				kind: "前后矛盾",
				detail: `前文：「${before.slice(-60).trim()}」  转折后加了限制：「${after.slice(0, 60).trim()}」`,
				hint: "确认这两个要求是否同时成立；如果前者是主目标，后者可能把主功能堵死。",
			};
		}
	}

	// 同一句里既"要 X"又"不要 X"
	const m = /(?:要|需要|得|必须)([^，。,.;；]{2,20})[，,].{0,10}(?:不要|不用|别|禁止)([^，。,.;；]{2,20})/.exec(text);
	if (m) {
		const a = m[1].trim();
		const b = m[2].trim();
		if (a && b && (b.includes(a.slice(0, 2)) || a.includes(b.slice(0, 2)))) {
			return {
				kind: "前后矛盾",
				detail: `要「${a}」，又不要「${b}」`,
				hint: "这两条互相否定的范围可能重叠，需要用户说清边界。",
			};
		}
	}
	return null;
}

function findVague(text: string): Issue | null {
	const low = text.toLowerCase();
	const hit = VAGUE_VERBS.find((v) => low.includes(v));
	if (!hit) return null;
	const hasCriteria = CRITERIA.some((c) => low.includes(c));
	const hasObject = /[\/\w\-]+\.(py|md|txt|ts|js|c|sh|json|yaml)\b|[\u4e00-\u9fa5]{2,}(模块|函数|脚本|扩展|笔记|文档|流程)/.test(text);
	if (hasCriteria || hasObject) return null;
	return {
		kind: "目标不清",
		detail: `「${hit}」没有说明对象和验收标准`,
		hint: "问用户：改哪个文件/功能？怎么算改好（能跑通/不报错/输出什么）？",
	};
}

function findAbsoluteBan(text: string): Issue | null {
	const ban = ABSOLUTE_BANS.find((b) => text.includes(b));
	if (!ban) return null;
	return {
		kind: "限制过宽",
		detail: `出现绝对限制「${ban}」`,
		hint: "这类限制常把主功能一起堵死；确认是只限某路径/某类操作，还是真的全禁。",
	};
}

function analyzePrompt(text: string): Issue[] {
	const issues: Issue[] = [];
	if (!text || text.length < 4) return issues;
	for (const fn of [findContradiction, findVague, findAbsoluteBan]) {
		const r = fn(text);
		if (r) issues.push(r);
	}
	return issues;
}

// ─────────────────────────── 扩展主体 ───────────────────────────

export default function logicChecker(pi: ExtensionAPI) {
	let pendingIssues: Issue[] = [];
	let callHistory: CallRecord[] = [];
	let turn = 0;
	/** 已提示过的循环，避免每轮重复喊 */
	const alertedLoops = new Set<string>();
	/** 本轮是否有产出 */
	let productiveInTurn = false;

	const fp = (tool: string, input: unknown): string => {
		const s = (() => {
			try {
				return JSON.stringify(input ?? {});
			} catch {
				return String(input);
			}
		})();
		return createHash("sha1").update(`${tool}|${s}`).digest("hex").slice(0, 12);
	};

	// ── 分析用户输入 ──
	pi.on("input", async (event, ctx) => {
		// 扩展自己注入的消息不检查
		if (event.source === "extension") return { action: "continue" };

		const issues = analyzePrompt(event.text ?? "");
		pendingIssues = issues;
		if (issues.length) {
			ctx.ui.notify(`逻辑检查：${issues.map((i) => i.kind).join(" / ")}`, "warning");
		}
		return { action: "continue" };
	});

	// ── 把问题摆到模型面前 ──
	pi.on("before_agent_start", async (event, _ctx) => {
		if (!pendingIssues.length) return;
		const block = [
			"## 自然语言逻辑检查（本轮用户输入）",
			"",
			...pendingIssues.map(
				(i) => `- **${i.kind}**：${i.detail}\n  - 建议：${i.hint}`,
			),
			"",
			"处理要求：若问题会改变结果、范围或安全边界，**先用一两句问清**再动手；若只是措辞含糊但意图明确，按最合理理解执行并注明你的取舍。",
		].join("\n");
		return { systemPrompt: `${event.systemPrompt}\n\n${block}` };
	});

	// ── 记录每次工具调用 ──
	pi.on("tool_call", async (event, ctx) => {
		const tool = event.toolName;
		const f = fp(tool, (event as any).input);
		callHistory.push({ id: event.toolCallId, fp: f, tool, ok: true, turn });

		if (PRODUCTIVE_TOOLS.has(tool)) productiveInTurn = true;

		// 规则甲：同一调用已失败 ≥3 次 → 禁止原样再试（先说失败，更具体）
		const priorFails = callHistory.filter((c) => c.fp === f && !c.ok).length;
		if (priorFails >= 3) {
			ctx.ui.notify(`逻辑检查：${tool} 已失败 ${priorFails} 次，拦下原样重试`, "warning");
			return {
				block: true,
				reason:
					`同一 ${tool} 调用已失败 ${priorFails} 次（参数完全相同）。\n` +
					`原样重试不会变好：先看错误原因（路径不存在/权限/依赖缺失），换方法，或把情况告诉用户。`,
			};
		}

		// 规则乙：同一指纹在最近 6 次已发出调用中出现 ≥4 次 → 判为循环
		// 注意：并行 tool_call 可能在同一批里连续到达，历史只有「已发出」没有「已返回」，
		// 所以必须用 callHistory（发出记录）判定，不能依赖 tool_result。
		const recent = callHistory.slice(-6);
		const same = recent.filter((c) => c.fp === f);
		if (same.length >= 4 && !alertedLoops.has(f)) {
			alertedLoops.add(f);
			ctx.ui.notify(`逻辑检查：疑似循环（${tool} 同一参数 ${same.length} 次）`, "warning");
			return {
				block: true,
				reason:
					`疑似循环无用功：同一 ${tool} 调用（参数完全相同）已出现 ${same.length} 次。\n` +
					`先判断上一次为什么没得到想要的结果，换参数/换方法，或直接问用户，不要原样重试。`,
			};
		}
	});

	// ── 记录失败次数：同一指纹失败达阈后，下一次重试直接拦 ──
	pi.on("tool_result", async (event) => {
		const tool = event.toolName;
		const f = fp(tool, (event as any).input);
		const rec = callHistory.find((c) => c.id === event.toolCallId);
		if (!rec) return;
		if (!event.isError) return;

		rec.ok = false;
		const fails = callHistory.filter((c) => c.fp === f && !c.ok).length;
		if (fails >= 3 && !alertedLoops.has(`fail:${f}`)) {
			alertedLoops.add(`fail:${f}`);
		}
	});

	// ── 回合结束：检测原地打转 ──
	pi.on("turn_end", async (_event, ctx) => {
		turn += 1;
		const inTurn = callHistory.filter((c) => c.turn === turn - 1);
		const reads = inTurn.filter((c) => READ_TOOLS.has(c.tool)).length;
		if (reads >= 6 && !productiveInTurn) {
			ctx.ui.notify(`逻辑检查：本回合 ${reads} 次只读、无写入，疑似原地打转`, "warning");
		}
		productiveInTurn = false;
		// 只保留最近 40 条
		if (callHistory.length > 40) callHistory = callHistory.slice(-40);
	});

	// ── 追加到系统提示，让模型自查 ──
	pi.on("agent_settled", async (_event, ctx) => {
		const loops = [...alertedLoops].filter((k) => !k.startsWith("fail:"));
		if (loops.length) {
			ctx.ui.notify(`逻辑检查：本轮触发 ${loops.length} 次循环拦截`, "warning");
		}
	});

	pi.on("session_shutdown", async () => {
		callHistory = [];
		alertedLoops.clear();
		pendingIssues = [];
	});
}
