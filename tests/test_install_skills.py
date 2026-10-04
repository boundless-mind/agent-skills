"""Exercise the installer with real files and isolated harness directories."""

import itertools
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
AGENTS = ("claude-code", "codex", "opencode")
SKILLS = ("resume", "suspend", "thought")


class InstallSkillsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workbench-install-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.checkout = self.root / "checkout with spaces"
        (self.checkout / "scripts").mkdir(parents=True)
        installer = REPO / "scripts/install-skills.sh"
        if not installer.exists():
            installer = REPO / "scripts/install-codex-skills.sh"
        self.installer = self.checkout / "scripts/install-skills.sh"
        shutil.copy2(installer, self.installer)
        shutil.copytree(REPO / "plugins", self.checkout / "plugins")
        self.home = self.root / "home"
        self.home.mkdir()
        self.project = self.root / "target project"
        self.project.mkdir()
        self.env = os.environ.copy()
        for key in ("CODEX_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME"):
            self.env.pop(key, None)
        self.env["HOME"] = str(self.home)
        for key, directory in (
            ("XDG_DATA_HOME", "data"),
            ("XDG_CACHE_HOME", "cache"),
            ("XDG_STATE_HOME", "state"),
        ):
            self.env[key] = str(self.root / directory)

    def run_installer(self, *args):
        return subprocess.run(
            ["bash", str(self.installer), *args],
            cwd=self.project,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)

    def assert_development_skills(self, directory):
        for skill in SKILLS:
            entry = directory / f"dev-{skill}"
            self.assertTrue(entry.is_symlink(), entry)
            content = (entry / "SKILL.md").read_text()
            identity = re.search(r"^name: (.+)$", content, re.MULTILINE)
            self.assertIsNotNone(identity, entry)
            self.assertEqual(identity[1], f"dev-{skill}")
            source_reference = re.search(r"`([^`]+/SKILL\.md)`", content)
            self.assertIsNotNone(source_reference, entry)
            self.assertEqual(
                Path(source_reference[1]).resolve(),
                self.checkout / f"plugins/workbench/skills/{skill}/SKILL.md",
            )

    def test_every_nonempty_agent_selection_in_both_scopes(self):
        # Catches a missing harness, scope routing errors, and ignored selections.
        for scope in ("user", "project"):
            for size in (1, 2, 3):
                for agents in itertools.combinations(AGENTS, size):
                    with self.subTest(scope=scope, agents=agents):
                        destination = self.root / f"{scope}-{'-'.join(agents)}"
                        destination.mkdir()
                        if scope == "user":
                            self.env["HOME"] = str(destination)
                            targets = {
                                "claude-code": destination / ".claude/skills",
                                "codex": destination / ".agents/skills",
                                "opencode": destination / ".config/opencode/skills",
                            }
                            args = ["--scope", "user"]
                        else:
                            targets = {
                                "claude-code": destination / ".claude/skills",
                                "codex": destination / ".agents/skills",
                                "opencode": destination / ".opencode/skills",
                            }
                            args = ["--project", str(destination)]
                        for agent in agents:
                            args.extend(("--agent", agent))
                        self.assert_success(self.run_installer(*args))
                        for agent, target in targets.items():
                            if agent in agents:
                                self.assert_development_skills(target)
                            else:
                                self.assertFalse(target.exists(), target)

    def test_default_installs_all_agents_and_repeat_runs_share_entrypoints(self):
        self.assert_success(self.run_installer())
        self.assert_success(self.run_installer())
        targets = [
            self.home / ".claude/skills",
            self.home / ".agents/skills",
            self.home / ".config/opencode/skills",
        ]
        for target in targets:
            self.assert_development_skills(target)
        for skill in SKILLS:
            self.assertEqual(len({(t / f"dev-{skill}").resolve() for t in targets}), 1)

    def test_project_scope_uses_current_directory(self):
        self.assert_success(self.run_installer("--scope", "project"))
        self.assert_development_skills(self.project / ".agents/skills")
        self.assertEqual(list(self.home.iterdir()), [])

    def test_source_changes_and_resources_remain_live(self):
        self.assert_success(self.run_installer("--agent", "codex"))
        self.assert_development_skills(self.home / ".agents/skills")
        source = self.checkout / "plugins/workbench/skills/resume"
        (source / "SKILL.md").write_text("updated development instructions\n")
        (source / "reference.txt").write_text("new supporting resource\n")
        entry = self.home / ".agents/skills/dev-resume/SKILL.md"
        reference = re.search(r"`([^`]+/SKILL\.md)`", entry.read_text())[1]
        self.assertEqual(Path(reference).read_text(), "updated development instructions\n")
        self.assertEqual(Path(reference).with_name("reference.txt").read_text(), "new supporting resource\n")

    def test_public_skills_and_unrelated_files_are_preserved(self):
        target = self.home / ".claude/skills"
        (target / "resume").mkdir(parents=True)
        public = target / "resume/SKILL.md"
        public.write_text("public release\n")
        unrelated = target / "other-skill"
        unrelated.symlink_to(self.root / "missing-external-skill", target_is_directory=True)
        self.assert_success(self.run_installer("--agent", "claude-code"))
        self.assertEqual(public.read_text(), "public release\n")
        self.assertTrue(unrelated.is_symlink())
        self.assert_development_skills(target)

    def test_conflicts_are_rejected_before_any_harness_is_changed(self):
        target = self.home / ".config/opencode/skills"
        conflict = target / "dev-thought"
        conflict.mkdir(parents=True)
        note = conflict / "keep.txt"
        note.write_text("keep this\n")
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(note.read_text(), "keep this\n")
        self.assertFalse((self.home / ".claude/skills").exists())
        self.assertFalse((target / "dev-resume").exists())

    def test_conflicting_broken_symlinks_are_preserved(self):
        target = self.home / ".agents/skills"
        target.mkdir(parents=True)
        conflict = target / "dev-resume"
        conflict.symlink_to(self.root / "missing", target_is_directory=True)
        result = self.run_installer("--agent", "codex")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(conflict.readlink(), self.root / "missing")

    def test_ancestor_file_conflicts_are_rejected_before_other_harnesses_change(self):
        (self.home / ".config").mkdir()
        conflict = self.home / ".config/opencode"
        conflict.write_text("keep this file\n")
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(conflict.read_text(), "keep this file\n")
        self.assertFalse((self.home / ".claude/skills").exists())
        self.assertFalse((self.home / ".agents/skills").exists())

    @unittest.skipUnless(shutil.which("opencode"), "OpenCode CLI is not installed")
    def test_opencode_discovers_only_development_names_from_the_checkout(self):
        self.assert_success(self.run_installer("--agent", "opencode"))
        result = subprocess.run(
            ["opencode", "debug", "skill", "--pure"],
            cwd=self.project, env=self.env, capture_output=True, text=True, timeout=25,
        )
        self.assert_success(result)
        names = {skill["name"] for skill in json.loads(result.stdout)}
        self.assertTrue({"dev-resume", "dev-suspend", "dev-thought"} <= names)
        self.assertFalse(set(SKILLS) & names, names)

    def test_configuration_directory_overrides_are_honored(self):
        self.env.update({
            "CODEX_HOME": str(self.root / "custom codex"),
            "CLAUDE_CONFIG_DIR": str(self.root / "custom claude"),
            "XDG_CONFIG_HOME": str(self.root / "custom config"),
        })
        self.assert_success(self.run_installer())
        for path in ("custom codex/skills", "custom claude/skills", "custom config/opencode/skills"):
            self.assert_development_skills(self.root / path)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_invalid_arguments_and_help_do_not_install(self):
        for args in (("--agent", "unknown"), ("--scope", "local"), ("--agent",), ("--unknown",)):
            with self.subTest(args=args):
                self.assertNotEqual(self.run_installer(*args).returncode, 0)
        self.assert_success(self.run_installer("--help"))
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(list(self.project.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
