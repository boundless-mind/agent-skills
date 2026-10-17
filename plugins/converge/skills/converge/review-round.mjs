#!/usr/bin/env node
// One review round of the converge skill: ask Codex (through the codex-plugin-cc
// companion) to review a part, store the structured findings, and report whether
// the part has converged. The round limit is enforced here, not by the caller.
//
// Usage:
//   node review-round.mjs --dir <part review dir> --request <file> [--max 5] [--fresh] [--checklist]
//                         [--job <job dir>] [--cwd <workspace>] [--companion <codex-companion.mjs>]
//                         [--timeout <seconds>]
//   node review-round.mjs --check [--cwd <workspace>] [--companion <codex-companion.mjs>]
//
// Every outcome is one JSON line on stdout with a "status".
// Exit codes: 0 round done or check passed, 2 error, 3 round limit reached.

import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCHEMA = path.join(HERE, "review.schema.json");
// Set by the codex plugin's SessionStart hook. Without it, the companion's --resume-last
// falls back to the newest task thread of any session in the workspace.
const SESSION_ENV = "CODEX_COMPANION_SESSION_ID";
// Below the 600 s cap of a Claude Code Bash call, so a slow review fails here, with a record.
const DEFAULT_TIMEOUT_S = 540;

class Failure extends Error {
  constructor(message, code = 2) {
    super(message);
    this.code = code;
  }
}

function fail(message) {
  throw new Failure(message);
}

function emit(result) {
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

function parseArgs(argv) {
  const opts = { max: 5, fresh: false, checklist: false, check: false, cwd: process.cwd(), timeout: DEFAULT_TIMEOUT_S };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const value = () => {
      if (i + 1 >= argv.length) fail(`${arg} needs a value`);
      i += 1;
      return argv[i];
    };
    if (arg === "--dir") opts.dir = value();
    else if (arg === "--request") opts.request = value();
    else if (arg === "--max") opts.max = Number(value());
    else if (arg === "--cwd") opts.cwd = value();
    else if (arg === "--companion") opts.companion = value();
    else if (arg === "--timeout") opts.timeout = Number(value());
    else if (arg === "--job") opts.job = value();
    else if (arg === "--fresh") opts.fresh = true;
    else if (arg === "--checklist") opts.checklist = true;
    else if (arg === "--check") opts.check = true;
    else fail(`unknown argument: ${arg}`);
  }
  if (!isDirectory(opts.cwd)) fail(`--cwd is not a directory: ${opts.cwd}`);
  if (!Number.isInteger(opts.timeout) || opts.timeout < 1) fail("--timeout must be a positive number of seconds");
  if (opts.check) return opts;
  if (!opts.dir) fail("--dir is required");
  if (!opts.request) fail("--request is required");
  if (!Number.isInteger(opts.max) || opts.max < 1) fail("--max must be a positive integer");
  if (opts.job && !fs.existsSync(path.join(opts.job, "brief.md"))) fail(`--job has no brief.md: ${opts.job}`);
  return opts;
}

function isDirectory(dir) {
  try {
    return fs.statSync(dir).isDirectory();
  } catch {
    return false;
  }
}

function safeReaddir(dir) {
  try {
    return fs.readdirSync(dir);
  } catch {
    return [];
  }
}

function supportsOutputSchema(file) {
  try {
    return fs.readFileSync(file, "utf8").includes("--output-schema");
  } catch {
    return false;
  }
}

// An explicitly named companion must work; it never falls back to another one.
// Otherwise the newest compatible companion in the plugin cache wins, so an
// incompatible newer install cannot mask a compatible one.
function findCompanion(explicit) {
  const named = explicit ?? process.env.CODEX_COMPANION;
  if (named) {
    const source = explicit ? "--companion" : "CODEX_COMPANION";
    if (!fs.existsSync(named)) fail(`${source} does not exist: ${named}`);
    if (!supportsOutputSchema(named)) fail(`${source} ${named} does not support --output-schema; use the codex-plugin-cc fork`);
    return named;
  }
  const configDir = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), ".claude");
  const cache = path.join(configDir, "plugins", "cache");
  const found = [];
  for (const marketplace of safeReaddir(cache)) {
    const pluginDir = path.join(cache, marketplace, "codex");
    for (const version of safeReaddir(pluginDir)) {
      const file = path.join(pluginDir, version, "scripts", "codex-companion.mjs");
      if (fs.existsSync(file)) found.push(file);
    }
  }
  const compatible = found
    .filter(supportsOutputSchema)
    .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  if (compatible.length) return compatible[0];
  if (found.length) {
    fail(`no installed codex companion supports --output-schema (found: ${found.join(", ")}); install the codex-plugin-cc fork`);
  }
  fail(`codex-companion.mjs not found under ${cache}: install the codex-plugin-cc fork, or pass --companion`);
}

function requireSession() {
  if (!process.env[SESSION_ENV]) {
    fail(
      `${SESSION_ENV} is not set, so rounds could continue an unrelated Codex thread. Run inside Claude Code with the codex plugin enabled (its SessionStart hook sets it).`
    );
  }
}

function runCompanion(companion, args, { input, timeoutS }) {
  const run = spawnSync(process.execPath, [companion, ...args], {
    input,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
    timeout: timeoutS * 1000,
    killSignal: "SIGTERM"
  });
  const timedOut = run.error?.code === "ETIMEDOUT";
  if (run.error && !timedOut) fail(`could not start the codex companion: ${run.error.message}`);
  let payload = null;
  try {
    payload = JSON.parse(run.stdout);
  } catch {
    // reported by the caller
  }
  return { run, timedOut, payload };
}

function isAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

// The companion's active task jobs in this session. A foreground task records the
// companion's own pid; while one is marked running, --resume-last refuses to start.
function activeTasks(companion, cwd) {
  const { run, payload } = runCompanion(companion, ["status", "--json", "--cwd", cwd], { timeoutS: 60 });
  if (!payload || !Array.isArray(payload.running)) {
    fail(`codex companion status returned no job list (exit ${run.status}): ${tail(run.stderr || run.stdout)}`);
  }
  return payload.running.filter((job) => job.jobClass === "task");
}

// Cancel interrupts the job's Codex turn, ends its process tree, and marks it cancelled.
function cancelTask(companion, cwd, jobId) {
  const { run, payload } = runCompanion(companion, ["cancel", jobId, "--json", "--cwd", cwd], { timeoutS: 60 });
  if (payload?.status === "cancelled") return { cancelled: true, turnInterrupted: Boolean(payload.turnInterrupted) };
  return { cancelled: false, detail: tail(run.stderr || run.stdout, 300) };
}

// A task marked running whose process is gone was left behind by a killed round
// (or a killed review-round.mjs); cancel it. A task whose process lives is real work.
function recoverStaleTasks(companion, cwd) {
  const recovered = [];
  for (const job of activeTasks(companion, cwd)) {
    if (Number.isInteger(job.pid) && isAlive(job.pid)) {
      fail(`Codex task ${job.id} is still running in this session (pid ${job.pid}); wait for it, or cancel it with /codex:cancel ${job.id}`);
    }
    const result = cancelTask(companion, cwd, job.id);
    if (!result.cancelled) fail(`could not cancel the stale Codex task ${job.id}: ${result.detail}`);
    recovered.push(job.id);
  }
  return recovered;
}

// Runs the review turn. On timeout it cancels the companion's tracked job while the
// companion still runs (so the pid is still ours), then makes sure the process ends.
function runTask(companion, args, { input, timeoutS, cwd }) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [companion, ...args], { stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    let timeout = null;
    child.stdout.setEncoding("utf8").on("data", (chunk) => (stdout += chunk));
    child.stderr.setEncoding("utf8").on("data", (chunk) => (stderr += chunk));
    child.stdin.on("error", () => {});
    child.stdin.end(input);

    const timer = setTimeout(() => {
      timeout = { cancelled: false, detail: "no tracked job found for the companion process" };
      try {
        const job = activeTasks(companion, cwd).find((candidate) => candidate.pid === child.pid);
        if (job) timeout = { jobId: job.id, ...cancelTask(companion, cwd, job.id) };
      } catch (error) {
        timeout = { cancelled: false, detail: error.message };
      }
      if (child.exitCode === null) child.kill("SIGTERM");
      setTimeout(() => child.exitCode === null && child.kill("SIGKILL"), 10_000).unref();
    }, timeoutS * 1000);

    child.on("error", (error) => {
      clearTimeout(timer);
      resolve({ startError: error });
    });
    child.on("close", (status) => {
      clearTimeout(timer);
      let payload = null;
      try {
        payload = JSON.parse(stdout);
      } catch {
        // reported by the caller
      }
      resolve({ status, stdout, stderr, payload, timeout });
    });
  });
}

function tail(text, length = 600) {
  const trimmed = String(text ?? "").trim();
  return trimmed.length > length ? `…${trimmed.slice(-length)}` : trimmed;
}

function check(opts) {
  const companion = findCompanion(opts.companion);
  requireSession();
  const { run, timedOut, payload } = runCompanion(companion, ["setup", "--json", "--cwd", path.resolve(opts.cwd)], {
    timeoutS: 60
  });
  if (timedOut) fail("codex companion setup timed out after 60 s");
  if (!payload) fail(`codex companion setup returned no JSON (exit ${run.status}): ${tail(run.stderr || run.stdout)}`);
  if (!payload.ready) {
    const steps = Array.isArray(payload.nextSteps) ? payload.nextSteps.join(" ") : "";
    fail(`Codex is not ready (codex available: ${Boolean(payload.codex?.available)}, logged in: ${Boolean(payload.auth?.loggedIn)}). ${steps}`.trim());
  }
  emit({ status: "ready", companion });
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    fail(`cannot read ${file}: ${error.message}`);
  }
}

function completedRounds(dir) {
  return safeReaddir(dir)
    .map((name) => /^round-(\d+)\.json$/.exec(name))
    .filter(Boolean)
    .map((match) => Number(match[1]))
    .sort((a, b) => a - b);
}

function requireResponse(dir, last) {
  const file = path.join(dir, `round-${last}-response.md`);
  if (!fs.existsSync(file)) fail(`write your response to each finding of round ${last} to ${file} first`);
  const response = fs.readFileSync(file, "utf8");
  const previous = readJson(path.join(dir, `round-${last}.json`));
  const missing = (previous.findings ?? [])
    .map((finding) => finding.id)
    .filter((id) => !new RegExp(`(^|[^\\w-])${id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([^\\w-]|$)`, "m").test(response));
  if (missing.length) fail(`${file} does not answer finding(s) ${missing.join(", ")}; answer each one as "<id> fixed: …" or "<id> rejected: …"`);
}

const SEVERITIES = new Set(["material", "minor"]);
const PREVIOUS = new Set(["new", "maintained"]);
const TEXT_FIELDS = ["id", "location", "issue", "recommendation"];

function validationError(output, { checklist }) {
  if (!output || typeof output !== "object") return "no structured output";
  if (typeof output.summary !== "string") return "summary is missing";
  if (!Array.isArray(output.checklist) || !output.checklist.every((item) => typeof item === "string")) {
    return "checklist is not a list of strings";
  }
  if (checklist && !output.checklist.some((item) => item.trim())) return "the requested checklist is empty";
  if (!Array.isArray(output.findings)) return "findings is not a list";
  const ids = new Set();
  for (const [index, finding] of output.findings.entries()) {
    if (!finding || typeof finding !== "object") return `finding ${index + 1} is not an object`;
    for (const field of TEXT_FIELDS) {
      if (typeof finding[field] !== "string" || !finding[field].trim()) return `finding ${index + 1} has no ${field}`;
    }
    if (!SEVERITIES.has(finding.severity)) return `finding ${finding.id} has severity "${finding.severity}"`;
    if (!PREVIOUS.has(finding.previous)) return `finding ${finding.id} has previous "${finding.previous}"`;
    if (ids.has(finding.id)) return `finding id ${finding.id} appears twice`;
    ids.add(finding.id);
  }
  return null;
}

// The request is written by the author, so it must say plainly what is under review and
// what it is judged against; the reviewer's context does not depend on it (see buildPrompt).
const REQUIRED_SECTIONS = ["Under review", "Criteria"];

function requireRequestStructure(request, file) {
  const missing = REQUIRED_SECTIONS.filter(
    (title) => !new RegExp(`^##\\s+${title}\\b`, "im").test(request)
  );
  if (missing.length) {
    fail(`${file} lacks the section(s) ${missing.map((title) => `"## ${title}"`).join(", ")}; see the request format in the converge skill`);
  }
}

function shown(file, cwd) {
  const relative = path.relative(cwd, file);
  return relative && !relative.startsWith("..") && !path.isAbsolute(relative) ? relative : file;
}

function listFiles(dir, limit = 50) {
  const files = [];
  const walk = (current) => {
    for (const entry of safeReaddir(current).sort()) {
      if (files.length >= limit || entry.startsWith(".")) continue;
      const full = path.join(current, entry);
      if (isDirectory(full)) walk(full);
      else files.push(full);
    }
  };
  walk(dir);
  return files;
}

// Anchors the reviewer in the job's own sources, independent of what the author's request names.
function jobAnchors(job, cwd) {
  const brief = path.join(job, "brief.md");
  const context = listFiles(path.join(job, "context"));
  const parts = listFiles(path.join(job, "out", "parts"));
  const lines = [
    "",
    `This work belongs to a job in ${shown(job, cwd)}. Its assignment is ${shown(brief, cwd)}: read it in full before you judge the work, and judge the work against it.`
  ];
  if (context.length) {
    lines.push(`The inputs the author was given (${shown(path.join(job, "context"), cwd)}):`, ...context.map((file) => `- ${shown(file, cwd)}`));
  }
  if (parts.length) {
    lines.push(`The parts written so far (${shown(path.join(job, "out", "parts"), cwd)}):`, ...parts.map((file) => `- ${shown(file, cwd)}`));
  }
  return lines;
}

function buildPrompt({ round, dir, request, job, checklist, cwd }) {
  const lines = [
    "You are an independent reviewer of work produced by another AI agent (Claude). You have read-only access to the workspace.",
    "",
    "The request below names what is under review and the criteria it must meet. You are not limited to the files it names: read the assignment, the inputs, earlier work, and anything else in the workspace you need to judge the work, as you would if you had been asked to review it directly. Check claims against their sources, not against the author's description of the work. A section headed \"Author's notes\" is the author's view, not established fact. Cite the files you rely on.",
    "",
    "Classify each finding:",
    "- material: it would change a verdict, number, estimate, recommendation, or conclusion; it is a factual error or an unsupported claim; or it leaves out something the assignment or the criteria require.",
    "- minor: wording, style, structure, or additions that change no conclusion.",
    "",
    "Report a material finding only when you are confident it holds. An empty findings list means the work is ready; do not invent findings to have something to say."
  ];
  if (job) lines.push(...jobAnchors(job, cwd));
  lines.push(
    "",
    checklist
      ? "Before you read the work under review, read the assignment and its inputs, and write down in `checklist` what a good answer must contain and get right: the items you would check if you had set the assignment yourself. Then review the work against that list as well as the criteria. An item on your list that the work misses or gets wrong is a finding."
      : "Leave `checklist` empty."
  );
  if (round > 1) {
    const previous = path.join(dir, `round-${round - 1}.json`);
    const response = path.join(dir, `round-${round - 1}-response.md`);
    lines.push(
      "",
      `This is review round ${round}. Your findings from the previous round are in ${shown(previous, cwd)}; the author's response to each finding is in ${shown(response, cwd)}.`,
      "For each previous material finding: if the change or the author's reasoning resolves it, drop it. If not, report it again with the same id, previous: \"maintained\", and why the response does not resolve it. Then review the updated work for anything new."
    );
    const first = readJson(path.join(dir, "round-1.json"));
    if (first.checklist?.length) {
      lines.push(`Your checklist from round 1 is in ${shown(path.join(dir, "round-1.json"), cwd)}; keep reviewing against it.`);
    }
  }
  lines.push("", "The request:", "", request.trim(), "");
  return lines.join("\n");
}

async function reviewRound(opts) {
  const dir = path.resolve(opts.dir);
  fs.mkdirSync(dir, { recursive: true });

  const done = completedRounds(dir);
  const last = done.length ? done[done.length - 1] : 0;
  if (last >= opts.max) {
    const findingsFile = path.join(dir, `round-${last}.json`);
    const previous = readJson(findingsFile);
    emit({ status: "max-rounds", round: last, max: opts.max, material: previous.material, findings_file: findingsFile });
    return 3;
  }

  const round = last + 1;
  if (opts.fresh && round > 1) fail("--fresh applies only to the first round of a part");
  if (opts.checklist && round > 1) fail("--checklist applies only to the first round of a part");
  if (round > 1) requireResponse(dir, last);

  const requestFile = path.resolve(opts.request);
  if (!fs.existsSync(requestFile)) fail(`request file not found: ${requestFile}`);
  const request = fs.readFileSync(requestFile, "utf8");
  if (!request.trim()) fail(`request file is empty: ${requestFile}`);
  requireRequestStructure(request, requestFile);

  const companion = findCompanion(opts.companion);
  requireSession();
  const cwd = path.resolve(opts.cwd);
  const job = opts.job ? path.resolve(opts.job) : null;
  const recovered = recoverStaleTasks(companion, cwd);
  const threadFlag = round === 1 && opts.fresh ? "--fresh" : "--resume-last";

  // No --write: the companion runs the Codex turn in a read-only sandbox.
  const run = await runTask(companion, ["task", threadFlag, "--output-schema", SCHEMA, "--json", "--cwd", cwd], {
    input: buildPrompt({ round, dir, request, job, checklist: opts.checklist, cwd }),
    timeoutS: opts.timeout,
    cwd
  });
  if (run.startError) fail(`could not start the codex companion: ${run.startError.message}`);
  const payload = run.payload;

  if (run.timeout || !payload) {
    fs.writeFileSync(path.join(dir, `round-${round}.failed.txt`), `${run.stdout}\n--- stderr ---\n${run.stderr}`);
    if (run.timeout) {
      const { jobId, cancelled, turnInterrupted, detail } = run.timeout;
      const cleanup = cancelled
        ? `cancelled Codex task ${jobId}${turnInterrupted ? " and interrupted its turn" : " (turn interrupt not confirmed)"}`
        : `could not cancel the Codex task (${detail}); the next round cancels it if its process is gone`;
      fail(`review round ${round} timed out after ${opts.timeout} s; ${cleanup}; see round-${round}.failed.txt`);
    }
    fail(`codex companion returned no JSON (exit ${run.status}): ${tail(run.stderr || run.stdout)}; see round-${round}.failed.txt`);
  }

  let problem = null;
  if (payload.status !== 0) problem = payload.errorMessage || `Codex turn ended with status ${payload.status}`;
  else if (!("structuredOutput" in payload)) problem = "the companion ignored --output-schema";
  else if (payload.structuredOutputError) problem = `structured output: ${payload.structuredOutputError}`;
  else problem = validationError(payload.structuredOutput, { checklist: opts.checklist });
  if (problem) {
    fs.writeFileSync(path.join(dir, `round-${round}.failed.json`), `${JSON.stringify(payload, null, 2)}\n`);
    fail(`review round ${round} failed: ${problem}; see round-${round}.failed.json`);
  }

  const output = payload.structuredOutput;
  const material = output.findings.filter((finding) => finding.severity === "material").length;
  const previousThread = round > 1 ? readJson(path.join(dir, `round-${last}.json`)).threadId : null;
  const record = {
    round,
    fresh: threadFlag === "--fresh",
    threadId: payload.threadId ?? null,
    at: new Date().toISOString(),
    summary: output.summary,
    checklist: opts.checklist ? output.checklist : [],
    material,
    minor: output.findings.length - material,
    findings: output.findings
  };
  const findingsFile = path.join(dir, `round-${round}.json`);
  fs.writeFileSync(findingsFile, `${JSON.stringify(record, null, 2)}\n`);

  const result = {
    status: material === 0 ? "converged" : "open",
    round,
    max: opts.max,
    rounds_left: opts.max - round,
    material,
    minor: record.minor,
    findings_file: findingsFile
  };
  if (previousThread && record.threadId && previousThread !== record.threadId) {
    result.warning = `this round ran in Codex thread ${record.threadId}, not ${previousThread} like the previous round`;
  }
  if (recovered.length) result.recovered = recovered;
  emit(result);
  return 0;
}

try {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.check) {
    check(opts);
    process.exitCode = 0;
  } else {
    process.exitCode = await reviewRound(opts);
  }
} catch (error) {
  emit({ status: "error", error: error instanceof Failure ? error.message : `unexpected: ${error.stack || error}` });
  process.exitCode = error instanceof Failure ? error.code : 2;
}
