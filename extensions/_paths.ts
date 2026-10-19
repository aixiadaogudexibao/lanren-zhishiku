/**
 * 路径解析 —— 所有扩展共用的一个出口
 *
 * 设计取舍：不在源码里硬编码任何用户名/绝对路径。
 *   优先级：环境变量 > ~ 推导
 *
 *   ZHISHIKU_ROOT  知识数据根（默认 ~/.zhishiku）
 *   PI_AGENT_DIR   harness 配置根（默认 ~/.pi/agent）
 *   PI_SKILLS_DIR  skill 目录（默认 <PI_AGENT_DIR>/skills）
 *
 * 这样同一份扩展在任何机器、任何用户名下都能跑。
 */

import { homedir } from "node:os";
import { join } from "node:path";

function env(name: string): string {
	return (process.env[name] ?? "").trim();
}

/** harness 配置根，如 ~/.pi/agent */
export const PI_AGENT_DIR = env("PI_AGENT_DIR") || join(homedir(), ".pi", "agent");

/** skill 目录，如 ~/.pi/agent/skills */
export const SKILLS_DIR = env("PI_SKILLS_DIR") || join(PI_AGENT_DIR, "skills");

/** 知识库数据根，如 ~/.zhishiku */
export const KM_ROOT = env("ZHISHIKU_ROOT") || join(homedir(), ".zhishiku");

/** 缺口板（采集标记来源） */
export const GAPBOARD = join(SKILLS_DIR, "zhishiku-chuli", "xinxi.txt");

/** 续跑条 */
export const RESUME = join(KM_ROOT, "resume", "current.md");

/** 续跑条归档目录 */
export const RESUME_DONE = join(KM_ROOT, "resume", "done");

/** 知识容器根（gengxin_wei） */
export const GENGXIN = join(KM_ROOT, "gengxin_wei");

/** 采集/提炼根 */
export const CAIJI = join(KM_ROOT, "caiji_wei");
export const TILIAN = join(KM_ROOT, "tilian_wei");
