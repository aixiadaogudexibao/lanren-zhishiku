/**
 * 临时脚本清理 —— 任务收尾时把调试用的临时脚本清掉
 *
 * 问题：
 *   解题过程中会随手写大量 probe_ / tmp_ / vfy 前缀的探针脚本，收尾后留在题目目录里。
 *   PWN-easy_rw 一个目录就堆了 8 个 probe_ 前缀脚本。这些既不是交付物，也不该进知识库。
 *
 * 做法：
 *   1. 记录本会话写过的「可疑临时脚本」（write 时按文件名判断）
 *   2. 会话收尾（agent_settled）时列出，TUI 下确认后删除
 *   3. 只删本会话自己写的，不碰历史文件；不删 exp.py / wp / flag 等交付物
 *
 * 安全约束：
 *   - 只处理扩展自己记录的路径（白名单），不扫全盘
 *   - 交付物白名单优先：名字像正式产的永远不删
 *   - 非 TUI 模式只报告不删
 *   - 删除前列出，可一键取消
 */

import { existsSync, readdirSync, readFileSync, statSync, unlinkSync } from "node:fs";
import { basename, join } from "node:path";
import { homedir } from "node:os";
import { isToolCallEventType, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

// ─────────────────────────── 判定规则 ───────────────────────────

/** 临时脚本特征：命中即视为可清理候选 */
const TEMP_PATTERN = /^(probe|tmp|temp|test|vfy|dbg|debug|scratch|try|check|poc_test|scratchpad)[_.-]?/i;

/** 交付物特征：命中则永不删（优先级高于临时特征） */
const KEEP_PATTERN = /(^|[\/_.-])(exp|exploit|solve|solution|payload|wp|writeup|agent)([\/_.-]|$)/i;

/** 只考虑这些扩展名 */
const SCRIPT_EXT = new Set([".py", ".sh", ".ts", ".js", ".c", ".pl", ".rb"]);

/** 允许清理的目录前缀（防止误删系统文件）
 *  默认只给家目录下的几个常见工作区；可用环境变量覆盖：
 *    TEMP_CLEAN_ROOTS="/path/a:/path/b"   （多个用 : 分隔）
 */
const ALLOWED_ROOTS = (process.env.TEMP_CLEAN_ROOTS ?? "")
	.trim()
	.split(":")
	.filter(Boolean)
	.map((p) => (p.endsWith("/") ? p : `${p}/`))
	.concat([join(homedir(), "Desktop") + "/", join(homedir(), "Downloads") + "/", "/tmp/"]);

/** 完全不碰的目录 */
const DENY_ROOTS = [join(homedir(), ".pi") + "/", join(homedir(), ".zhishiku") + "/", "/etc/", "/usr/", join(homedir(), ".ssh") + "/"];

function extOf(p: string): string {
	const m = /(\.[A-Za-z0-9]+)$/.exec(p);
	return m ? m[1].toLowerCase() : "";
}

function isAllowed(p: string): boolean {
	if (DENY_ROOTS.some((d) => p.startsWith(d))) return false;
	return ALLOWED_ROOTS.some((d) => p.startsWith(d));
}

/**
 * 推断文件用途，供用户在确认框里判断能否删
 * 顺序：docstring 首句 → 首个 shebang 后注释 → 内容特征 → 兜底
 */
function inferPurpose(p: string): string {
	let text = "";
	try {
		text = readFileSync(p, "utf8").slice(0, 4000);
	} catch {
		return "（读不到内容）";
	}
	const name = basename(p);

	// 1. 顶部 docstring（跳过 shebang / coding 行 / 普通 # 注释）
	const body = text.replace(/^#![^\n]*\n/, "");
	const doc =
		/^\s*"""([\s\S]{0,300}?)"""/.exec(body)?.[1] ??
		/^\s*([^#\s][^\n]{6,120})/.exec(body.split(/\n\s*\n/)[0])?.[1];
	if (doc) {
		const first = doc.split(/[\n。；]/)[0].trim();
		// 排除 import / print 这类代码行
		if (first.length >= 6 && !/^(import|from|print|def |class |#)/.test(first)) {
			return first.slice(0, 100);
		}
	}

	// 2. 按导入/调用特征猜
	const k: string[] = [];
	if (/from pwn import|import pwn/.test(text)) k.push("pwntools");
	if (/gdb\.attach|gdb\.debug/.test(text)) k.push("gdb 调试");
	if (/process\(|remote\(/.test(text)) k.push("本地/远程跑题");
	if (/sendline|recvuntil|sendafter/.test(text)) k.push("交互收发");
	if (/checksec|ELF\(/.test(text)) k.push("读 ELF");
	if (/printf|scanf|socket\(/.test(text)) k.push("C 探针");
	if (/requests\.|urllib/.test(text)) k.push("网络请求");
	if (/qemu|binwalk/.test(text)) k.push("固件/QEMU");
	if (/subprocess|os\.system/.test(text)) k.push("调外部命令");

	if (k.length) return `探针脚本（${k.slice(0, 3).join(" + ")}）`;

	// 3. 按文件名前缀兜底
	if (/^probe/i.test(name)) return "探测脚本（无说明）";
	if (/^(tmp|temp)/i.test(name)) return "临时脚本（无说明）";
	if (/^test/i.test(name)) return "试验脚本（无说明）";
	if (/^(vfy|dbg|debug)/i.test(name)) return "验证/调试脚本（无说明）";
	return "未识别用途";
}

/** 返回 true = 值得清理 */
function isTempScript(p: string): boolean {
	if (!SCRIPT_EXT.has(extOf(p))) return false;
	if (!isAllowed(p)) return false;
	const name = basename(p);
	if (KEEP_PATTERN.test(name)) return false; // 交付物优先
	return TEMP_PATTERN.test(name);
}

// ─────────────────────────── 扩展主体 ───────────────────────────

export default function tempScriptCleaner(pi: ExtensionAPI) {
	/** 本会话写入过的临时脚本：path → { bytes, ts } */
	const created = new Map<string, { bytes: number; ts: number }>();
	/** 已被用户确认保留的 */
	const keep = new Set<string>();
	/** 已经提示过、用户选择保留的文件；新增文件仍会再次提示 */
	const alreadyOffered = new Set<string>();
	/** 命名不合规的疑似临时脚本 */
	const badNamed = new Set<string>();

	/** 疑似一次性脚本但没按规定前缀命名：提醒改名，否则收尾清不到 */
	const SUSPECT_CONTENT = /^(#!.*\n)?[\s\S]{0,400}$/;
	const SUSPECT_KEYS = /process\(|remote\(|sendline|recvuntil|gdb\.|printf|scanf|socket\(|urllib|requests\./i;

	function looksThrowaway(p: string, content: string): boolean {
		if (!SCRIPT_EXT.has(extOf(p))) return false;
		if (!isAllowed(p)) return false;
		const name = basename(p);
		if (TEMP_PATTERN.test(name) || KEEP_PATTERN.test(name)) return false; // 已合规或是交付物
		if (content.length > 4000) return false; // 大文件更像正式脚本
		return SUSPECT_KEYS.test(content) && SUSPECT_CONTENT.test(content);
	}

	pi.on("tool_call", async (event, ctx) => {
		// 只记 write；edit 说明是改已有文件，不算本会话新建的临时件
		if (!isToolCallEventType("write", event)) return;
		const p = String(event.input.path ?? "");
		if (!p) return;
		const content = String((event.input as any).content ?? "");

		// 命名不合规提醒（不拦，只提醒；记下来下一轮注入，模型能看到）
		if (looksThrowaway(p, content)) {
			badNamed.add(p);
			ctx.ui.notify(`临时脚本命名不合规：${basename(p)}（建议 probe_/tmp_/test_/vfy_/dbg_/scratch_ 前缀）`, "warning");
		}

		if (!isTempScript(p) || keep.has(p)) return;
		const bytes = content.length;
		created.set(p, { bytes, ts: Date.now() });
		ctx.ui.notify(`已记录临时脚本：${basename(p)}（收尾时确认删除）`, "info");
	});

	// 用户明确说「保留」的，记下来
	pi.on("input", async (event) => {
		if (event.source === "extension") return { action: "continue" };
		const t = event.text ?? "";
		if (/保留|先留着|别删|不要删/.test(t)) {
			for (const p of created.keys()) {
				if (t.includes(basename(p))) keep.add(p);
			}
		}
		return { action: "continue" };
	});

	// ── 下一轮把不合规命名摆到模型面前 ──
	pi.on("before_agent_start", async (event) => {
		if (!badNamed.size) return;
		const list = [...badNamed].map((p) => `- ${p}`).join("\n");
		const block = [
			"## 临时脚本命名不合规（本轮刚写）",
			"",
			list,
			"",
			"规则：临时/探针脚本必须以 `probe` / `tmp` / `temp` / `test` / `vfy` / `dbg` / `debug` / `scratch` / `try` / `check` 前缀命名；",
			"正式交付物用 `exp` / `solve` / `wp` / `payload`。",
			"**处理：下一轮不再用这些名字创建文件；已存在的可改名为合规前缀（mv 而非重写），否则收尾清理识别不到。**",
		].join("\n");
		return { systemPrompt: `${event.systemPrompt}\n\n${block}` };
	});

	// ── 收尾：列出候选，确认后删除 ──
	pi.on("agent_settled", async (_event, ctx) => {
		// 只提示"本次新出现、且没提示过"的临时脚本；
		// 用户选保留的会被记进 alreadyOffered，后续不再打扰；
		// 但之后新写的临时文件仍会触发提示（旧的单一 alerted 标志会永久闭嘴）
		const alive = [...created.keys()].filter(
			(p) => !keep.has(p) && !alreadyOffered.has(p) && existsSync(p),
		);
		if (!alive.length) return;
		for (const p of alive) alreadyOffered.add(p);

		const lines = alive.map((p) => {
			let size = created.get(p)?.bytes ?? 0;
			try {
				size = statSync(p).size;
			} catch {
				/* 保持原值 */
			}
			return `  ${basename(p)}  (${size} B)\n    用途：${inferPurpose(p)}\n    ${p}`;
		});

		// 非 TUI：只报告，不删
		if (!ctx.hasUI) {
			const brief = alive.map((p) => `${basename(p)}（${inferPurpose(p)}）`).join("；");
			ctx.ui.notify(`临时脚本 ${alive.length} 个待清（非交互模式未删）：${brief}`, "warning");
			return;
		}

		const ok = await ctx.ui.confirm(
			`清理临时脚本（${alive.length} 个）`,
			`本会话写过的临时/探针脚本，收尾建议删除。\n确认后将删除下列文件：\n\n${lines.join("\n")}\n\n` +
				`不会删除 exp / solve / wp 等交付物；勾选取消则全部保留。`,
		);

		if (!ok) {
			// 记进 alreadyOffered，本次会话不再问；文件留着
			ctx.ui.notify(`已保留 ${alive.length} 个临时脚本（本次会话不再提示）`, "info");
			return;
		}

		let removed = 0;
		const failed: string[] = [];
		for (const p of alive) {
			try {
				unlinkSync(p);
				created.delete(p);
				removed++;
			} catch (e: any) {
				failed.push(`${basename(p)}: ${e?.message ?? "删除失败"}`);
			}
		}
		ctx.ui.notify(
			failed.length
				? `已删 ${removed} 个，失败 ${failed.length} 个：${failed.join("；")}`
				: `已清理 ${removed} 个临时脚本`,
			failed.length ? "warning" : "info",
		);
	});

	// ── 命令：手动清一次 ──
	pi.registerCommand("tmpclean", {
		description: "列出并清理本会话产生的临时脚本",
		handler: async (_args, ctx) => {
			const alive = [...created.keys()].filter((p) => !keep.has(p) && existsSync(p));
			if (!alive.length) {
				ctx.ui.notify("本会话没有记录到临时脚本", "info");
				return;
			}
			const ok = await ctx.ui.confirm(
				`清理 ${alive.length} 个临时脚本`,
				alive.map((p) => `${basename(p)}  ${p}`).join("\n"),
			);
			if (!ok) return;
			let n = 0;
			for (const p of alive) {
				try {
					unlinkSync(p);
					created.delete(p);
					n++;
				} catch {
					/* 忽略 */
				}
			}
			ctx.ui.notify(`已清理 ${n} 个`, "info");
		},
	});

	// ── 命令：扫目录里的历史残留（默认只列不删）──
	pi.registerCommand("tmpcand", {
		description: "列出指定目录的临时脚本候选（只列不删；加 --delete 才删，且需确认）",
		getArgumentCompletions: () => null,
		handler: async (args, ctx) => {
			const raw = (args ?? "").trim();
			const wantDelete = raw.includes("--delete");
			const dir = raw.replace("--delete", "").trim();
			if (!dir) {
				ctx.ui.notify("用法：/tmpcand <目录> [--delete]", "info");
				return;
			}
			let names: string[] = [];
			try {
				names = readdirSync(dir);
			} catch (e: any) {
				ctx.ui.notify(`读不了目录：${e?.message ?? e}`, "error");
				return;
			}
			const cands = names
				.map((n: string) => join(dir, n))
				.filter((p: string) => !keep.has(p) && isTempScript(p) && existsSync(p));

			if (!cands.length) {
				ctx.ui.notify("该目录没有合规前缀的临时脚本", "info");
				return;
			}

			const lines = cands.map((p: string) => {
				let size = 0;
				try {
					size = statSync(p).size;
				} catch {
					/* ignore */
				}
				return `  ${basename(p)}  (${size} B)\n    用途：${inferPurpose(p)}`;
			});

			if (!wantDelete) {
				// 只列不删：把候选交给模型，由模型问用户
				pi.sendMessage({
					customType: "tmp-candidates",
					display: true,
					content: [
						`[临时脚本候选 · ${cands.length} 个 · 未删除]`,
						dir,
						"",
						...lines,
						"",
						"**这是清单，没有删除任何文件。** 如需清理，先向用户确认；用户同意后再加 --delete。",
					].join("\n"),
				});
				ctx.ui.notify(`已列出 ${cands.length} 个候选（未删除）`, "info");
				return;
			}

			// --delete：仍需确认
			const ok = await ctx.ui.confirm(
				`删除 ${cands.length} 个临时脚本？`,
				`目录：${dir}\n\n${lines.join("\n")}\n\n此操作会直接删除文件，请确认。`,
			);
			if (!ok) {
				ctx.ui.notify("已取消，未删除", "info");
				return;
			}
			let n = 0;
			for (const p of cands) {
				try {
					unlinkSync(p);
					n++;
				} catch {
					/* ignore */
				}
			}
			ctx.ui.notify(`已删除 ${n} 个`, "info");
		},
	});

	pi.on("session_shutdown", async () => {
		created.clear();
		keep.clear();
	});
}
