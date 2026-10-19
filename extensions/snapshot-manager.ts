/**
 * 快照管理 —— 统一台账 + 生命周期 + 清理策略
 *
 * 现状：快照散在 4 个地方，没人知道总共多少、哪个能删。
 *   gengxin_wei/<领域>/_snap/     回注快照（回滚用）
 *   resume/done/                  续跑条备份（commit / patch / takeover / precompact）
 *   <数据根>/_bak_<名>            迁移备份（一次性）
 *   <skill>/<名>.bak-<时间>       早期备份
 *
 * 设计取舍：不搬文件。
 *   gengxin 的 snapshot.py 依赖 _snap/<时间戳> 这个固定路径做回滚，
 *   搬走会破坏它。所以本扩展只做三件事：
 *     1. 扫描各处 → 生成统一台账（树形）
 *     2. 生命周期表 → 每类快照留多久、留几份
 *     3. 过期候选只列出，用户确认后才删
 *
 * 台账落盘：<数据根>/_snapshots/INDEX.md + index.json
 */

import { existsSync, mkdirSync, readdirSync, rmSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import { type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { KM_ROOT, SKILLS_DIR } from "./_paths.ts";

// ─────────────────────────── 配置 ───────────────────────────
const CLIENT = join(KM_ROOT, "_snapshots");
const INDEX_MD = join(CLIENT, "INDEX.md");
const INDEX_JSON = join(CLIENT, "index.json");

/** 生命周期：每类快照保留策略 */
interface Lifecycle {
	type: string;
	scope: string;
	keep: number;
	keepDays: number;
	why: string;
}

const LIFECYCLE: Lifecycle[] = [
	{
		type: "gengxin-snap",
		scope: "gengxin_wei/<领域>/_snap/<时间戳>/",
		keep: 40,
		keepDays: 180,
		why: "回注回滚点。ctf-pwn 已积累 25 个（每次回注都拍），按实际节奏放宽到 40 份/180 天",
	},
	{
		type: "resume-precompact",
		scope: "resume/done/*-precompact-*.md",
		keep: 5,
		keepDays: 7,
		why: "压缩前自动拍的续跑条。只在压缩后几轮内有意义，过期无用",
	},
	{
		type: "resume-commit",
		scope: "resume/done/*-commit-*.md",
		keep: 20,
		keepDays: 30,
		why: "每次 commit 的前置备份。主要防覆盖丢失，30 天足够回溯",
	},
	{
		type: "resume-patch",
		scope: "resume/done/*-patch.md",
		keep: 20,
		keepDays: 30,
		why: "巡检改单行前的备份。同上",
	},
	{
		type: "resume-takeover",
		scope: "resume/done/*-takeover.md",
		keep: 10,
		keepDays: 60,
		why: "窗口接管记录。数量少、有追溯价值",
	},
	{
		type: "resume-task",
		scope: "resume/done/<时间>-<领域>-<题目>.md",
		keep: 50,
		keepDays: 180,
		why: "任务关链归档。是历史记录，不是临时快照",
	},
	{
		type: "migrate-bak",
		scope: "<数据根>/_bak_<名> 、_迁移备份前缀<名>",
		keep: 10,
		keepDays: 365,
		why: "整库迁移前的备份。用户决定长期保留（含历史快照链），不按超期清；只在数量超限时提示",
	},
	{
		type: "skill-bak",
		scope: "<skill 目录>/*_wei.bak-*/",
		keep: 2,
		keepDays: 30,
		why: "skill 整体改版前的备份",
	},
];

// ─────────────────────────── 扫描 ───────────────────────────

interface SnapItem {
	type: string;
	scopeKey: string; // 归属（领域 或 全局）
	name: string;
	path: string;
	bytes: number;
	mtime: Date;
	days: number;
	expired: boolean;
	reason: string;
}

function dirSize(p: string, depth = 0): number {
	if (depth > 6) return 0;
	try {
		const st = statSync(p);
		if (!st.isDirectory()) return st.size;
		let total = 0;
		for (const n of readdirSync(p)) total += dirSize(join(p, n), depth + 1);
		return total;
	} catch {
		return 0;
	}
}

function safeLs(p: string): string[] {
	try {
		return readdirSync(p);
	} catch {
		return [];
	}
}

function ruleOf(type: string): Lifecycle | undefined {
	return LIFECYCLE.find((l) => l.type === type);
}

function evalItem(type: string, scopeKey: string, name: string, path: string): SnapItem {
	let bytes = 0;
	let mtime = new Date(0);
	try {
		const st = statSync(path);
		mtime = st.mtime;
		bytes = st.isDirectory() ? dirSize(path) : st.size;
	} catch {
		/* ignore */
	}
	const days = Math.floor((Date.now() - mtime.getTime()) / 86400000);
	const rule = ruleOf(type);
	const expired = !!rule && days > rule.keepDays;
	return {
		type,
		scopeKey,
		name,
		path,
		bytes,
		mtime,
		days,
		expired,
		reason: rule ? `超过 ${rule.keepDays} 天` : "",
	};
}

function scanAll(): SnapItem[] {
	const items: SnapItem[] = [];

	// 1) gengxin 回注快照
	const gx = join(KM_ROOT, "gengxin_wei");
	for (const dom of safeLs(gx)) {
		const snapDir = join(gx, dom, "_snap");
		if (!existsSync(snapDir)) continue;
		for (const n of safeLs(snapDir)) {
			const p = join(snapDir, n);
			// preRollback 也归到同一类型（回滚副本）
			items.push(evalItem("gengxin-snap", dom, n, p));
		}
	}

	// 2) resume/done 各类
	const done = join(KM_ROOT, "resume/done");
	for (const n of safeLs(done)) {
		const p = join(done, n);
		let type = "resume-task";
		if (n.includes("-precompact-")) type = "resume-precompact";
		else if (n.includes("-commit-") || n.includes("-commit.")) type = "resume-commit";
		else if (n.includes("-patch")) type = "resume-patch";
		else if (n.includes("-takeover")) type = "resume-takeover";
		items.push(evalItem(type, "全局", n, p));
	}

	// 3) 迁移备份（根目录 _bak_* / _<任意词>bak*）
	for (const n of safeLs(KM_ROOT)) {
		if (!/^(_bak_|_\w*bak)/.test(n)) continue;
		items.push(evalItem("migrate-bak", "全局", n, join(KM_ROOT, n)));
	}

	// 4) skill 的 *wei.bak-*
	const skillsDir = SKILLS_DIR;
	for (const n of safeLs(skillsDir)) {
		if (!/\.bak-/.test(n)) continue;
		items.push(evalItem("skill-bak", n.split(".")[0], n, join(skillsDir, n)));
	}

	return items.sort((a, b) => b.mtime.getTime() - a.mtime.getTime());
}

// ─────────────────────────── 渲染 ───────────────────────────

function human(bytes: number): string {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
	if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
	return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function renderIndex(items: SnapItem[]): string {
	const L: string[] = [];
	const total = items.reduce((s, i) => s + i.bytes, 0);
	const exp = items.filter((i) => i.expired);

	L.push("# 快照总台账");
	L.push("");
	L.push(`> 自动生成于 ${new Date().toISOString().slice(0, 19).replace("T", " ")}；**只读**，由 snapshot-manager 扩展刷新。`);
	L.push("");
	L.push(`总计 **${items.length}** 项 / **${human(total)}**；其中过期候选 **${exp.length}** 项（只列不删，需确认）。`);
	L.push("");

	// 按类型分组 → 再按归属分
	const byType = new Map<string, SnapItem[]>();
	for (const i of items) {
		if (!byType.has(i.type)) byType.set(i.type, []);
		byType.get(i.type)!.push(i);
	}

	L.push("## 树形结构");
	L.push("");
	L.push("```text");
	L.push("快照/");
	const typeOrder = LIFECYCLE.map((l) => l.type);
	const types = [...byType.keys()].sort((a, b) => typeOrder.indexOf(a) - typeOrder.indexOf(b));
	for (let ti = 0; ti < types.length; ti++) {
		const t = types[ti];
		const list = byType.get(t)!;
		const isLastType = ti === types.length - 1;
		const b1 = isLastType ? "└─ " : "├─ ";
		L.push(`${b1}${t}/  (${list.length} 项, ${human(list.reduce((s, i) => s + i.bytes, 0))})`);

		const byScope = new Map<string, SnapItem[]>();
		for (const i of list) {
			if (!byScope.has(i.scopeKey)) byScope.set(i.scopeKey, []);
			byScope.get(i.scopeKey)!.push(i);
		}
		const scopes = [...byScope.keys()].sort();
		for (let si = 0; si < scopes.length; si++) {
			const sc = scopes[si];
			const sub = byScope.get(sc)!;
			const isLastScope = si === scopes.length - 1;
			const p2 = (isLastType ? "   " : "│  ") + (isLastScope ? "└─ " : "├─ ");
			L.push(`${p2}${sc}/  (${sub.length})`);
			for (let k = 0; k < Math.min(sub.length, 4); k++) {
				const it = sub[k];
				const p3 = (isLastType ? "   " : "│  ") + (isLastScope ? "   " : "│  ") + "└─ ";
				L.push(`${p3}${it.name}  ${it.days}天  ${human(it.bytes)}${it.expired ? "  ⚠过期" : ""}`);
			}
			if (sub.length > 4) {
				const p3 = (isLastType ? "   " : "│  ") + (isLastScope ? "   " : "│  ");
				L.push(`${p3}└─ …还有 ${sub.length - 4} 项`);
			}
		}
	}
	L.push("```");
	L.push("");

	// 生命周期表
	L.push("## 生命周期表");
	L.push("");
	L.push("| 类型 | 位置 | 保留份数 | 保留天数 | 为什么 |");
	L.push("|---|---|---|---|---|");
	for (const r of LIFECYCLE) {
		const n = byType.get(r.type)?.length ?? 0;
		const mark = n > r.keep ? " ⚠超份数" : "";
		L.push(`| ${r.type}${mark} | \`${r.scope}\` | ${r.keep} | ${r.keepDays} | ${r.why} |`);
	}
	L.push("");

	// 过期候选
	if (exp.length) {
		L.push("## 过期候选（只列，未删除）");
		L.push("");
		for (const i of exp) {
			L.push(`- [${i.type}] ${i.scopeKey}/${i.name} — ${i.days} 天 / ${human(i.bytes)}（${i.reason}）`);
			L.push(`  \`${i.path}\``);
		}
		L.push("");
		L.push("**清理方式**：`/snapcheck` 确认后执行；或用下方命令手动删。");
		L.push("");
	}
	return L.join("\n");
}

// ─────────────────────────── 扩展主体 ───────────────────────────

export default function snapshotManager(pi: ExtensionAPI) {
	function refresh(): SnapItem[] {
		const items = scanAll();
		try {
			mkdirSync(CLIENT, { recursive: true });
			writeFileSync(INDEX_MD, renderIndex(items), "utf-8");
			writeFileSync(
				INDEX_JSON,
				JSON.stringify(
					items.map((i) => ({
						type: i.type,
						scope: i.scopeKey,
						name: i.name,
						path: i.path,
						bytes: i.bytes,
						days: i.days,
						expired: i.expired,
					})),
					null,
					2,
				),
				"utf-8",
			);
		} catch {
			/* 索引写失败不影响使用 */
		}
		return items;
	}

	pi.on("session_start", async (_e, ctx) => {
		const items = refresh();
		const exp = items.filter((i) => i.expired).length;
		const total = items.reduce((s, i) => s + i.bytes, 0);
		ctx.ui.notify(
			`快照：${items.length} 项 / ${human(total)}${exp ? `，过期候选 ${exp} 项（/snapshot 查看）` : ""}`,
			exp ? "warning" : "info",
		);
	});

	// ── /snapshot：看台账 ──
	pi.registerCommand("snapshot", {
		description: "查看快照树形台账与生命周期表（/snapshot md 看完整 Markdown）",
		handler: async (args, ctx) => {
			const items = refresh();
			if ((args ?? "").trim() === "md") {
				pi.sendMessage({
					customType: "snapshot-index",
					display: true,
					content: `[快照台账 · ${items.length} 项]\n\n${renderIndex(items)}`,
				});
				return;
			}
			const byType = new Map<string, { n: number; b: number; exp: number }>();
			for (const i of items) {
				const cur = byType.get(i.type) ?? { n: 0, b: 0, exp: 0 };
				cur.n++;
				cur.b += i.bytes;
				if (i.expired) cur.exp++;
				byType.set(i.type, cur);
			}
			const lines = [...byType.entries()]
				.sort((a, b) => b[1].b - a[1].b)
				.map(([t, v]) => {
					const rule = ruleOf(t);
					return `${t}: ${v.n} 项 / ${human(v.b)}${v.exp ? ` ⚠${v.exp} 过期` : ""}${rule ? `（保留 ${rule.keep} 份 / ${rule.keepDays} 天）` : ""}`;
				});
			ctx.ui.notify(
				`快照 ${items.length} 项 / ${human(items.reduce((s, i) => s + i.bytes, 0))}\n${lines.join("\n")}`,
				items.some((i) => i.expired) ? "warning" : "info",
			);
		},
	});

	// ── /snapcheck：清理过期候选（必须确认）──
	pi.registerCommand("snapcheck", {
		description: "列出过期快照候选，确认后删除（默认只列不删）",
		handler: async (args, ctx) => {
			const items = refresh();
			const exp = items.filter((i) => i.expired);
			if (!exp.length) {
				ctx.ui.notify("没有过期快照", "info");
				return;
			}
			const totalB = exp.reduce((s, i) => s + i.bytes, 0);
			const lines = exp.map(
				(i) => `[${i.type}] ${i.scopeKey}/${i.name}\n  ${i.days} 天 / ${human(i.bytes)} — ${i.reason}`,
			);
			const wantDelete = (args ?? "").includes("--delete");
			if (!wantDelete) {
				pi.sendMessage({
					customType: "snapshot-expired",
					display: true,
					content: [
						`[过期快照候选 · ${exp.length} 项 / ${human(totalB)} · 未删除]`,
						"",
						...lines,
						"",
						"**这是清单，没有删除任何文件。** 确认后执行 `/snapcheck --delete`。",
					].join("\n"),
				});
				ctx.ui.notify(`已列出 ${exp.length} 个过期候选（未删除）`, "info");
				return;
			}
			const ok = await ctx.ui.confirm(
				`删除 ${exp.length} 个过期快照？`,
				`共 ${human(totalB)}\n\n${lines.slice(0, 12).join("\n")}${lines.length > 12 ? `\n…还有 ${lines.length - 12} 项` : ""}`,
			);
			if (!ok) {
				ctx.ui.notify("已取消，未删除", "info");
				return;
			}
			let n = 0;
			const failed: string[] = [];
			for (const i of exp) {
				try {
					if (statSync(i.path).isDirectory()) rmSync(i.path, { recursive: true, force: true });
					else unlinkSync(i.path);
					n++;
				} catch (e: any) {
					failed.push(`${i.name}: ${e?.message ?? "失败"}`);
				}
			}
			refresh();
			ctx.ui.notify(
				failed.length ? `已删 ${n} 项，失败 ${failed.length}：${failed.join("；")}` : `已清理 ${n} 项快照`,
				failed.length ? "warning" : "info",
			);
		},
	});

	// ── 阶段切换时顺手刷新（成本低，保证台账不陈旧）──
	pi.on("agent_end", async () => {
		refresh();
	});
}
