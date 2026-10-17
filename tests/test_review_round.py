import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "plugins/converge/skills/converge/review-round.mjs"

# A stand-in for codex-companion.mjs that supports --output-schema: it records its
# arguments and prompt, then answers with the next scripted reply. `setup` answers
# with setup.json instead.
STUB = r"""
// supports --output-schema
// Tracks task jobs like the companion: a foreground task is recorded as running with
// its own pid until it finishes; `cancel` marks it cancelled and ends that process.
const fs = require("node:fs");
const dir = process.env.STUB_DIR;
const read = (name, fallback) => fs.existsSync(dir + "/" + name) ? JSON.parse(fs.readFileSync(dir + "/" + name, "utf8")) : fallback;
const write = (name, value) => fs.writeFileSync(dir + "/" + name, JSON.stringify(value));
const command = process.argv[2];
if (command === "setup") {
  process.stdout.write(JSON.stringify(read("setup.json")));
  process.exit(0);
}
if (command === "status") {
  process.stdout.write(JSON.stringify({ running: read("jobs.json", []).filter((job) => job.status === "running") }));
  process.exit(0);
}
if (command === "cancel") {
  const jobs = read("jobs.json", []);
  const job = jobs.find((candidate) => candidate.id === process.argv[3]);
  job.status = "cancelled";
  write("jobs.json", jobs);
  write("cancels.json", [...read("cancels.json", []), job.id]);
  try { process.kill(job.pid, "SIGTERM"); } catch {}
  process.stdout.write(JSON.stringify({ jobId: job.id, status: "cancelled", turnInterrupted: true }));
  process.exit(0);
}
const calls = read("calls.json", []);
const replies = read("replies.json", []);
const prompt = fs.readFileSync(0, "utf8");
calls.push({ argv: process.argv.slice(2), prompt });
write("calls.json", calls);
const id = "task-" + calls.length;
write("jobs.json", [...read("jobs.json", []), { id, jobClass: "task", status: "running", pid: process.pid }]);
const reply = replies[calls.length - 1];
if (reply === "hang") {
  setInterval(() => {}, 1000);
} else {
  write("jobs.json", read("jobs.json", []).map((job) => job.id === id ? { ...job, status: "completed", pid: null } : job));
  process.stdout.write(JSON.stringify(reply));
}
"""

OLD_STUB = "process.stdout.write('{}')\n"


REQUEST = """## Under review
- out/parts/01.md

## Criteria
> Every idea has a verdict.
"""


def payload(findings, status=0, checklist=()):
    return {
        "status": status,
        "threadId": "thr_1",
        "rawOutput": "",
        "structuredOutput": {"summary": "s", "checklist": list(checklist), "findings": findings},
        "structuredOutputError": None,
    }


def finding(fid, severity):
    return {
        "id": fid,
        "severity": severity,
        "previous": "new",
        "location": "out/parts/01.md",
        "issue": "i",
        "recommendation": "r",
    }


class ReviewRoundTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.stub_dir = self.tmp / "stub"
        self.stub_dir.mkdir()
        # CommonJS stub, hence .cjs.
        self.companion = self.stub_dir / "codex-companion.cjs"
        self.companion.write_text(STUB, encoding="utf8")
        self.review = self.tmp / "review" / "01-part"
        self.request = self.tmp / "request.md"
        self.request.write_text(REQUEST, encoding="utf8")
        self.env = {k: v for k, v in os.environ.items() if k not in ("CODEX_COMPANION", "CLAUDE_CONFIG_DIR")}
        self.env.update(STUB_DIR=str(self.stub_dir), CODEX_COMPANION_SESSION_ID="sess-1")
        self.setup_reply({"ready": True, "codex": {"available": True}, "auth": {"loggedIn": True}, "nextSteps": []})

    def replies(self, *items):
        (self.stub_dir / "replies.json").write_text(json.dumps(list(items)), encoding="utf8")

    def setup_reply(self, reply):
        (self.stub_dir / "setup.json").write_text(json.dumps(reply), encoding="utf8")

    def jobs(self, *items):
        (self.stub_dir / "jobs.json").write_text(json.dumps(list(items)), encoding="utf8")

    def cancels(self):
        path = self.stub_dir / "cancels.json"
        return json.loads(path.read_text(encoding="utf8")) if path.exists() else []

    def calls(self):
        path = self.stub_dir / "calls.json"
        return json.loads(path.read_text(encoding="utf8")) if path.exists() else []

    def run_script(self, *args, env=None):
        result = subprocess.run(
            ["node", str(SCRIPT), *args], capture_output=True, text=True, env=env or self.env,
        )
        return result.returncode, json.loads(result.stdout.strip().splitlines()[-1])

    def run_round(self, *extra, max_rounds=5, companion=True, env=None):
        args = ["--dir", str(self.review), "--request", str(self.request), "--max", str(max_rounds),
                "--cwd", str(self.tmp)]
        if companion:
            args += ["--companion", str(self.companion)]
        return self.run_script(*args, *extra, env=env)

    def respond(self, round_number, text="F1 fixed: done\n"):
        (self.review / f"round-{round_number}-response.md").write_text(text, encoding="utf8")

    def plugin_cache(self, *versions):
        """Install companions in a fake plugin cache; versions are (name, source, age_seconds)."""
        config = self.tmp / "claude"
        for name, source, age in versions:
            scripts = config / "plugins" / "cache" / "market" / "codex" / name / "scripts"
            scripts.mkdir(parents=True)
            file = scripts / "codex-companion.mjs"
            # The cache holds .mjs files, so the CommonJS stub gets an ESM require.
            if source is STUB:
                source = 'import { createRequire } from "node:module";\nconst require = createRequire(import.meta.url);\n' + source
            file.write_text(source, encoding="utf8")
            stamp = time.time() - age
            os.utime(file, (stamp, stamp))
        return dict(self.env, CLAUDE_CONFIG_DIR=str(config))

    # Rounds

    def test_material_findings_leave_the_part_open_and_are_stored(self):
        self.replies(payload([finding("F1", "material"), finding("F2", "minor")]))
        code, out = self.run_round()
        self.assertEqual(code, 0)
        self.assertEqual(out["status"], "open")
        self.assertEqual((out["round"], out["material"], out["minor"], out["rounds_left"]), (1, 1, 1, 4))
        record = json.loads((self.review / "round-1.json").read_text(encoding="utf8"))
        self.assertEqual(record["material"], 1)
        argv = self.calls()[0]["argv"]
        self.assertIn("--resume-last", argv)
        self.assertIn("--output-schema", argv)
        self.assertNotIn("--write", argv)

    def test_next_round_requires_a_response_and_points_codex_at_it(self):
        self.replies(payload([finding("F1", "material")]), payload([]))
        self.run_round()
        code, out = self.run_round()
        self.assertEqual((code, out["status"]), (2, "error"))
        self.assertFalse((self.review / "round-2.json").exists())
        self.respond(1)
        code, out = self.run_round()
        self.assertEqual((code, out["status"], out["round"]), (0, "converged", 2))
        prompt = self.calls()[1]["prompt"]
        self.assertIn("round-1.json", prompt)
        self.assertIn("round-1-response.md", prompt)

    def test_the_response_must_answer_every_finding(self):
        self.replies(payload([finding("F1", "material"), finding("F12", "minor")]), payload([]))
        self.run_round()
        self.respond(1, "F1 fixed: done\nF1x rejected: not a finding id\n")
        code, out = self.run_round()
        self.assertEqual((code, out["status"]), (2, "error"))
        self.assertIn("F12", out["error"])
        self.assertEqual(len(self.calls()), 1)
        self.respond(1, "F1 fixed: done\nF12 rejected: out of scope\n")
        code, out = self.run_round()
        self.assertEqual((code, out["status"]), (0, "converged"))

    def test_round_limit_is_enforced_without_calling_codex(self):
        self.replies(payload([finding("F1", "material")]))
        code, out = self.run_round(max_rounds=1)
        self.assertEqual((out["status"], out["rounds_left"]), ("open", 0))
        self.respond(1)
        code, out = self.run_round(max_rounds=1)
        self.assertEqual((code, out["status"], out["material"]), (3, "max-rounds", 1))
        self.assertEqual(len(self.calls()), 1)

    def test_fresh_starts_a_new_thread_on_the_first_round_only(self):
        self.replies(payload([finding("F1", "material")]))
        self.run_round("--fresh")
        self.assertIn("--fresh", self.calls()[0]["argv"])
        self.assertNotIn("--resume-last", self.calls()[0]["argv"])
        self.respond(1)
        code, out = self.run_round("--fresh")
        self.assertEqual((code, out["status"]), (2, "error"))

    # Failures are loud and do not count as rounds

    def test_invalid_output_does_not_count_as_a_round(self):
        bad = payload([{"id": "F1", "severity": "blocker"}])
        self.replies(bad, payload([]))
        code, out = self.run_round()
        self.assertEqual((code, out["status"]), (2, "error"))
        self.assertTrue((self.review / "round-1.failed.json").exists())
        self.assertFalse((self.review / "round-1.json").exists())
        code, out = self.run_round()
        self.assertEqual((code, out["status"], out["round"]), (0, "converged", 1))

    def test_a_companion_that_ignores_the_schema_fails_the_round(self):
        reply = payload([])
        del reply["structuredOutput"]
        self.replies(reply)
        code, out = self.run_round()
        self.assertEqual((code, out["status"]), (2, "error"))
        self.assertIn("ignored --output-schema", out["error"])

    def test_a_hanging_review_times_out(self):
        self.replies("hang")
        code, out = self.run_round("--timeout", "1")
        self.assertEqual((code, out["status"]), (2, "error"))
        self.assertIn("timed out", out["error"])
        self.assertTrue((self.review / "round-1.failed.txt").exists())
        self.assertFalse((self.review / "round-1.json").exists())

    def test_a_timeout_cancels_the_tracked_task_so_the_next_round_can_run(self):
        self.replies("hang", payload([]))
        code, out = self.run_round("--timeout", "1")
        self.assertIn("cancelled Codex task task-1", out["error"])
        self.assertEqual(self.cancels(), ["task-1"])
        code, out = self.run_round()
        self.assertEqual((code, out["status"]), (0, "converged"))
        self.assertNotIn("recovered", out)

    def test_a_task_left_running_by_a_dead_process_is_cancelled_first(self):
        dead = subprocess.Popen(["true"])
        dead.wait()
        self.jobs({"id": "task-old", "jobClass": "task", "status": "running", "pid": dead.pid})
        self.replies(payload([]))
        code, out = self.run_round()
        self.assertEqual((code, out["status"], out["recovered"]), (0, "converged", ["task-old"]))
        self.assertEqual(self.cancels(), ["task-old"])

    def test_a_task_of_a_live_process_blocks_the_round(self):
        self.jobs({"id": "task-live", "jobClass": "task", "status": "running", "pid": os.getpid()})
        self.replies(payload([]))
        code, out = self.run_round()
        self.assertEqual((code, out["status"]), (2, "error"))
        self.assertIn("task-live is still running", out["error"])
        self.assertEqual((self.calls(), self.cancels()), ([], []))

    def test_a_missing_request_is_an_error_not_a_crash(self):
        self.request.unlink()
        code, out = self.run_round()
        self.assertEqual((code, out["status"]), (2, "error"))
        self.assertIn("request file not found", out["error"])

    def test_a_request_without_its_required_sections_is_refused(self):
        self.request.write_text("Please review out/parts/01.md.", encoding="utf8")
        self.replies(payload([]))
        code, out = self.run_round()
        self.assertEqual((code, out["status"]), (2, "error"))
        self.assertIn("## Under review", out["error"])
        self.assertIn("## Criteria", out["error"])
        self.assertEqual(self.calls(), [])

    # Reviewer context

    def test_the_prompt_lets_the_reviewer_look_beyond_the_request(self):
        self.replies(payload([]))
        self.run_round()
        prompt = self.calls()[0]["prompt"]
        self.assertIn("You are not limited to the files it names", prompt)
        self.assertIn("Leave `checklist` empty.", prompt)
        self.assertIn("Every idea has a verdict.", prompt)

    def make_job(self):
        job = self.tmp / "jobs" / "demo"
        (job / "context").mkdir(parents=True)
        (job / "out" / "parts").mkdir(parents=True)
        (job / "brief.md").write_text("# Brief\n", encoding="utf8")
        (job / "context" / "ideas.pdf").write_text("x", encoding="utf8")
        (job / "out" / "parts" / "01-ideas.md").write_text("x", encoding="utf8")
        return job

    def test_a_job_anchors_the_reviewer_in_the_brief_inputs_and_parts(self):
        job = self.make_job()
        self.replies(payload([]))
        code, out = self.run_round("--job", str(job))
        self.assertEqual(code, 0)
        prompt = self.calls()[0]["prompt"]
        self.assertIn("jobs/demo/brief.md", prompt)
        self.assertIn("jobs/demo/context/ideas.pdf", prompt)
        self.assertIn("jobs/demo/out/parts/01-ideas.md", prompt)

    def test_a_job_without_a_brief_is_refused(self):
        job = self.make_job()
        (job / "brief.md").unlink()
        code, out = self.run_round("--job", str(job))
        self.assertEqual((code, out["status"]), (2, "error"))
        self.assertIn("brief.md", out["error"])

    def test_a_checklist_is_requested_required_and_kept(self):
        self.replies(payload([], checklist=[" "]), payload([finding("F1", "material")], checklist=["Every idea has a verdict"]), payload([]))
        code, out = self.run_round("--fresh", "--checklist")
        self.assertEqual((code, out["status"]), (2, "error"))
        self.assertIn("checklist is empty", out["error"])
        self.assertIn("Before you read the work under review", self.calls()[0]["prompt"])
        code, out = self.run_round("--fresh", "--checklist")
        self.assertEqual((code, out["status"]), (0, "open"))
        record = json.loads((self.review / "round-1.json").read_text(encoding="utf8"))
        self.assertEqual(record["checklist"], ["Every idea has a verdict"])
        self.respond(1)
        code, out = self.run_round("--checklist")
        self.assertEqual((code, out["status"]), (2, "error"))
        code, out = self.run_round()
        self.assertEqual((code, out["status"]), (0, "converged"))
        self.assertIn("Your checklist from round 1", self.calls()[2]["prompt"])

    def test_rounds_refuse_to_run_without_a_claude_session(self):
        self.replies(payload([]))
        env = {k: v for k, v in self.env.items() if k != "CODEX_COMPANION_SESSION_ID"}
        code, out = self.run_round(env=env)
        self.assertEqual((code, out["status"]), (2, "error"))
        self.assertIn("CODEX_COMPANION_SESSION_ID", out["error"])
        self.assertEqual(self.calls(), [])

    # Finding the companion

    def test_an_explicit_companion_without_output_schema_is_refused(self):
        old = self.stub_dir / "old-companion.cjs"
        old.write_text(OLD_STUB, encoding="utf8")
        code, out = self.run_script("--dir", str(self.review), "--request", str(self.request), "--companion", str(old))
        self.assertEqual(code, 2)
        self.assertIn("--output-schema", out["error"])

    def test_a_newer_incompatible_install_does_not_mask_a_compatible_one(self):
        self.replies(payload([]))
        env = self.plugin_cache(("1.0.6-fork.3", STUB, 3600), ("1.0.7", OLD_STUB, 0))
        code, out = self.run_round(companion=False, env=env)
        self.assertEqual((code, out["status"]), (0, "converged"))
        self.assertEqual(len(self.calls()), 1)

    def test_only_incompatible_installs_are_named_in_the_error(self):
        env = self.plugin_cache(("1.0.7", OLD_STUB, 0))
        code, out = self.run_round(companion=False, env=env)
        self.assertEqual((code, out["status"]), (2, "error"))
        self.assertIn("1.0.7", out["error"])

    # Prerequisite check

    def test_check_reports_ready(self):
        code, out = self.run_script("--check", "--cwd", str(self.tmp), "--companion", str(self.companion))
        self.assertEqual((code, out["status"]), (0, "ready"))

    def test_check_fails_when_codex_is_not_logged_in(self):
        self.setup_reply({"ready": False, "codex": {"available": True}, "auth": {"loggedIn": False},
                          "nextSteps": ["Run `!codex login`."]})
        code, out = self.run_script("--check", "--cwd", str(self.tmp), "--companion", str(self.companion))
        self.assertEqual((code, out["status"]), (2, "error"))
        self.assertIn("logged in: false", out["error"])


if __name__ == "__main__":
    unittest.main()
