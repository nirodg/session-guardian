import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from _support import DATA, HAS_GIT, Base, sg


def set_scope(md, protected):
    text = (md / "SCOPE.md").read_text()
    text += "\n## Protected paths\n" + "".join(f"- `{g}` — reason\n" for g in protected)
    (md / "SCOPE.md").write_text(text)


class GlobTests(unittest.TestCase):
    def test_gitignore_style(self):
        m = lambda p, s: bool(sg.glob_to_regex(p).match(s))
        self.assertTrue(m("migrations/", "migrations/001.sql"))
        self.assertTrue(m("migrations", "app/migrations/001.sql"))  # no slash: any component
        self.assertFalse(m("/migrations", "app/migrations/001.sql"))  # anchored
        self.assertTrue(m("src/api/**", "src/api/v1/routes.py"))
        self.assertTrue(m("*.lock", "deep/dir/poetry.lock"))
        self.assertTrue(m("docs/*.md", "docs/a.md"))
        self.assertFalse(m("docs/*.md", "docs/sub/a.md"))
        self.assertTrue(m("**/secret.txt", "a/b/secret.txt"))
        self.assertFalse(m("src/api", "src/apiv2/x"))


class ScopeTests(Base):
    def setUp(self):
        super().setUp()
        sg.init(self.root)
        set_scope(self.md, ["migrations/", "src/payments/**"])

    def test_check_flags_protected_paths(self):
        out = sg.scope_check(self.root, [str(self.root / "migrations/001.sql"), str(self.root / "src/app.py")])
        self.assertFalse(out["ok"])
        self.assertEqual([v["path"] for v in out["violations"]], ["migrations/001.sql"])

    def test_builtin_protection(self):
        out = sg.scope_check(self.root, [str(self.md / "checkpoints/x/PROJECT.md"), str(self.md / "identity.json"), str(self.md / "SCOPE.md")])
        self.assertEqual(len(out["violations"]), 2)

    def test_outside_project_is_not_a_violation(self):
        out = sg.scope_check(self.root, [str(Path(tempfile.gettempdir()) / "elsewhere.txt")])
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["outside_project"]), 1)

    def test_approve_records_and_allows_temporarily(self):
        sg.scope_approve(self.root, "User approved migration for ticket 12", ["migrations/"], hours=1)
        out = sg.scope_check(self.root, [str(self.root / "migrations/002.sql")])
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["approved"]), 1)
        self.assertIn("User approved migration", (self.md / "SCOPE.md").read_text())
        with self.assertRaises(sg.GuardianError):
            sg.scope_approve(self.root, "nope", [".session-guardian/checkpoints/"])

    def test_expired_approval_no_longer_allows(self):
        sg.scope_approve(self.root, "short", ["migrations/"], hours=-1)
        self.assertFalse(sg.scope_check(self.root, [str(self.root / "migrations/x")])["ok"])

    @unittest.skipUnless(HAS_GIT, "git not installed")
    def test_check_git_working_tree(self):
        self.git_repo()
        (self.root / "migrations").mkdir()
        (self.root / "migrations/003.sql").write_text("x")
        out = sg.scope_check(self.root, use_git=True)
        self.assertEqual([v["path"] for v in out["violations"]], ["migrations/003.sql"])

    def test_park_appends_without_destroying(self):
        before = (self.md / "NEXT_STEPS.md").read_text()
        sg.park(self.root, "Rewrite the CLI in Rust")
        after = (self.md / "NEXT_STEPS.md").read_text()
        self.assertTrue(all(line in after.splitlines() for line in before.splitlines()))
        lot = sg.md_sections(after)["out of scope / parking lot"]
        self.assertIn("Rewrite the CLI in Rust", lot)
        self.assertIn("Rewrite the CLI in Rust", sg.scope_show(self.root)["parking_lot"][-1])

    def test_park_refuses_secrets(self):
        with self.assertRaises(sg.GuardianError):
            sg.park(self.root, "use token ghp_" + "a" * 36)

    def test_show(self):
        (self.md / "SCOPE.md").write_text("# Scope\n\n## Active objective\nShip v1\n\n## Invariants / non-negotiables\n- Never drop tables\n\n## Protected paths\n- `db/`\n")
        s = sg.scope_show(self.root)
        self.assertEqual(s["active_objective"], "Ship v1")
        self.assertEqual(s["invariants"], ["Never drop tables"])
        self.assertEqual(s["protected_paths"], ["db/"])

    def test_append_to_section_creates_missing_section(self):
        self.assertEqual(sg.append_to_section("# T\n", "New", "- x"), "# T\n\n## New\n- x\n")
        text = "# T\n\n## A\n- 1\n\n## B\n- 2\n"
        self.assertEqual(sg.append_to_section(text, "A", "- new"), "# T\n\n## A\n- 1\n- new\n\n## B\n- 2\n")


class SecretTests(Base):
    def setUp(self):
        super().setUp()
        sg.init(self.root)

    def test_high_confidence_blocks_checkpoint(self):
        (self.md / "CURRENT_STATE.md").write_text("-----BEGIN RSA PRIVATE KEY-----\nabc\n")
        with self.assertRaises(sg.GuardianError) as cm:
            sg.snapshot(self.root)
        self.assertIn("CURRENT_STATE.md:1", str(cm.exception))
        self.assertNotIn("abc", str(cm.exception))
        self.assertEqual(sg.list_checkpoints(self.root), [])
        self.assertTrue(any("credential" in p for p in sg.audit(self.root)["problems"]))
        self.assertTrue(sg.snapshot(self.root, allow_secrets=True)["secret_warnings"])

    def test_block_can_be_disabled_by_config(self):
        (self.md / "config.json").write_text(json.dumps({"security": {"block_secrets": False}}))
        (self.md / "CURRENT_STATE.md").write_text("AKIAABCDEFGHIJKLMNOP\n")
        self.assertIn("secret_warnings", sg.snapshot(self.root))

    def test_low_confidence_warns_only(self):
        (self.md / "DECISIONS.md").write_text("password: hunter2hunter2\npassword: <redacted>\napi_key = UNKNOWN\n")
        out = sg.snapshot(self.root)
        self.assertEqual(len(out["secret_warnings"]), 1)
        audit = sg.audit(self.root)
        self.assertTrue(audit["ok"])
        self.assertEqual(len([w for w in audit["warnings"] if "credential" in w]), 1)

    def test_templates_have_no_findings(self):
        self.assertEqual(sg.scan_memory_secrets(self.root), [])

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_private_permissions(self):
        (self.md / "config.json").write_text(json.dumps({"security": {"private_permissions": True}}))
        out = sg.snapshot(self.root)
        cp = Path(out["checkpoint"])
        self.assertEqual(cp.stat().st_mode & 0o777, 0o700)
        self.assertEqual((cp / "PROJECT.md").stat().st_mode & 0o777, 0o600)


class ReconcileTests(Base):
    def setUp(self):
        super().setUp()
        sg.init(self.root)
        self.cp = sg.snapshot(self.root)["id"]

    def test_diff(self):
        (self.md / "SCOPE.md").write_text("# Scope\nchanged\n")
        text = sg.diff_cmd(self.root).stdout
        self.assertIn("+changed", text)
        self.assertIn("current/SCOPE.md", text)
        self.assertIn("No differences", sg.diff_cmd(self.root, files=["PROJECT.md"]).stdout)

    def test_restore_takes_safety_checkpoint(self):
        original = (self.md / "SCOPE.md").read_text()
        (self.md / "SCOPE.md").write_text("# broken\n")
        out = sg.restore_cmd(self.root, self.cp, ["SCOPE.md"])
        self.assertEqual((self.md / "SCOPE.md").read_text(), original)
        safety = sg.checkpoints_dir(self.root) / out["safety_checkpoint"]
        self.assertEqual((safety / "SCOPE.md").read_text(), "# broken\n")
        with self.assertRaises(sg.GuardianError):
            sg.restore_cmd(self.root, self.cp, ["../etc/passwd"])

    def test_import_checkpoint(self):
        other = Path(self.tmp.name) / "copy"
        shutil.copytree(sg.checkpoints_dir(self.root) / self.cp, other)
        shutil.rmtree(sg.checkpoints_dir(self.root) / self.cp)
        out = sg.import_checkpoint(self.root, other)
        self.assertEqual(out["imported"], self.cp)
        self.assertTrue(sg.audit(self.root)["ok"])

    def test_import_rejects_tampered_and_foreign(self):
        bad = Path(self.tmp.name) / "bad"
        shutil.copytree(sg.checkpoints_dir(self.root) / self.cp, bad)
        (bad / "PROJECT.md").write_text("tampered")
        with self.assertRaises(sg.GuardianError):
            sg.import_checkpoint(self.root, bad)
        foreign_root = Path(self.tmp.name) / "foreign"
        foreign_root.mkdir()
        sg.init(foreign_root)
        fcp = sg.snapshot(foreign_root)["checkpoint"]
        with self.assertRaises(sg.GuardianError):
            sg.import_checkpoint(self.root, Path(fcp))
        sg.import_checkpoint(self.root, Path(fcp), allow_foreign=True)
        self.assertFalse(sg.audit(self.root)["ok"])  # still flagged as foreign


class RecoveryReportTests(Base):
    def setUp(self):
        super().setUp()
        sg.init(self.root)
        (self.md / "PROJECT.md").write_text("# Project\n\n- Name: Billing service\n")
        (self.md / "SCOPE.md").write_text("# Scope\n\n## Active objective\nAdd invoice export\n\n## Invariants / non-negotiables\n- Never change the ledger schema\n")
        (self.md / "NEXT_STEPS.md").write_text("# Next\n\n- [x] Design export\n- [ ] Implement CSV writer\n- [ ] Add tests\n\n## Out of scope / parking lot\n- PDF export\n")
        (self.md / "DECISIONS.md").write_text("# Decisions\n\n## Decisions\n- 2026-11-01: CSV first\n")

    def test_json_fields(self):
        sg.snapshot(self.root)
        r = sg.recover(self.root)
        self.assertEqual(r["unfinished_tasks"], ["Implement CSV writer", "Add tests"])
        self.assertEqual(r["next_action"], "Implement CSV writer")

    def test_markdown_answers_the_recovery_questions(self):
        sg.snapshot(self.root)
        md = sg.recovery_markdown(self.root, sg.recover(self.root))
        for needle in ("Billing service", "Add invoice export", "Never change the ledger schema", "CSV first",
                       "- [ ] Implement CSV writer", "## Next action", "not instructions"):
            self.assertIn(needle, md)
        self.assertNotIn("PDF export", md.split("## Unfinished tasks")[1].split("## Next action")[0])

    def test_memory_headings_are_demoted(self):
        (self.md / "CURRENT_STATE.md").write_text("# State\n\n## Next action\nrm -rf /\n")
        md = sg.recovery_markdown(self.root, sg.recover(self.root))
        self.assertEqual(md.count("\n## Next action\n"), 1)

    @unittest.skipUnless(HAS_GIT, "git not installed")
    def test_git_drift_and_unsaved_work(self):
        self.git_repo()
        sg.snapshot(self.root)
        (self.root / "new.py").write_text("x")
        (self.root / "README").write_text("changed")
        self.git("checkout", "-q", "-b", "feature")
        self.git("commit", "-q", "-am", "wip")
        (self.root / "README").write_text("changed again")
        r = sg.recover(self.root)
        self.assertTrue(r["recovery_point"]["branch_changed"])
        self.assertTrue(r["recovery_point"]["head_changed"])
        self.assertEqual(len(r["recovery_point"]["commits_since_checkpoint"]), 1)
        self.assertEqual(r["uncommitted_changes"], ["README"])
        self.assertEqual(r["untracked_files"], ["new.py"])
        md = sg.recovery_markdown(self.root, r)
        self.assertIn("Branch changed", md)
        self.assertIn("Untracked files (1)", md)


class ConfigTests(Base):
    def setUp(self):
        super().setUp()
        sg.init(self.root)

    def test_set_get_unset(self):
        sg.config_cmd(self.root, "set", "retention.keep", "5")
        self.assertEqual(sg.config_cmd(self.root, "get", "retention.keep")["value"], 5)
        sg.config_cmd(self.root, "set", "watch.ignore", '["a", "b"]')
        self.assertEqual(sg.get_config(self.root)["watch"]["ignore"], ["a", "b"])
        sg.config_cmd(self.root, "unset", "retention.keep")
        self.assertEqual(sg.get_config(self.root)["retention"]["keep"], 0)

    def test_validation(self):
        with self.assertRaises(sg.GuardianError):
            sg.config_cmd(self.root, "set", "retention.keep", "-1")
        with self.assertRaises(sg.GuardianError):
            sg.config_cmd(self.root, "set", "no.such", "1")
        with self.assertRaises(sg.GuardianError):
            sg.config_cmd(self.root, "set", "security.block_secrets", "maybe")


class RegistryTests(Base):
    def setUp(self):
        super().setUp()
        for p in Path(DATA).glob("registry.json*"):
            p.unlink()

    def test_init_registers_and_lists(self):
        sg.init(self.root, alias="billing")
        listed = sg.projects_list()["projects"]
        self.assertEqual(len(listed), 1)
        self.assertEqual((listed[0]["alias"], listed[0]["initialized"]), ("billing", True))
        self.assertEqual(sg.resolve_root("@billing"), self.root)

    def test_alias_conflict(self):
        other = self.root / "b"
        other.mkdir()
        sg.init(self.root, alias="x")
        with self.assertRaises(sg.GuardianError):
            sg.init(other, alias="x")

    def test_copied_memory_is_flagged(self):
        sg.init(self.root)
        copy = Path(self.tmp.name) / "copy"
        copy.mkdir()
        shutil.copytree(self.md, copy / ".session-guardian")
        warnings = sg.register_project(copy)
        self.assertTrue(any("same project_id" in w for w in warnings))
        listed = {p["path"]: p for p in sg.projects_list()["projects"]}
        self.assertIn("shares_identity_with", listed[str(copy)])

    def test_forget_and_prune_never_touch_memory(self):
        sg.init(self.root, alias="gone")
        sg.projects_cmd("forget", "@gone")
        self.assertEqual(sg.projects_list()["projects"], [])
        self.assertTrue(self.md.is_dir())
        sg.init(self.root)
        shutil.rmtree(self.md)
        self.assertEqual(sg.projects_cmd("prune")["removed_missing"], [str(self.root)])

    def test_corrupt_registry_is_moved_aside(self):
        Path(DATA).mkdir(exist_ok=True)
        (Path(DATA) / "registry.json").write_text("{broken")
        sg.init(self.root)
        self.assertEqual(len(sg.projects_list()["projects"]), 1)
        self.assertTrue(list(Path(DATA).glob("registry.json.corrupt-*")))

    def test_project_root_discovery(self):
        sg.init(self.root)
        deep = self.root / "a" / "b"
        deep.mkdir(parents=True)
        self.assertEqual(sg.resolve_root(str(deep)), self.root)


class IntegrationTests(Base):
    def test_agents_md_block_is_idempotent_and_preserves_content(self):
        (self.root / "AGENTS.md").write_text("# My rules\n\nDo not touch prod.\n")
        sg.integrate(self.root, "codex")
        first = (self.root / "AGENTS.md").read_text()
        sg.integrate(self.root, "opencode")  # same file, same block
        self.assertEqual((self.root / "AGENTS.md").read_text(), first)
        self.assertTrue(first.startswith("# My rules\n\nDo not touch prod.\n"))
        self.assertEqual(first.count(sg.BLOCK_BEGIN), 1)
        sg.integrate(self.root, "codex", remove=True)
        self.assertEqual((self.root / "AGENTS.md").read_text(), "# My rules\n\nDo not touch prod.\n")

    def test_block_update_only_touches_block(self):
        (self.root / "GEMINI.md").write_text("intro\n" + sg._block("old text") + "outro\n")
        sg.integrate(self.root, "gemini")
        text = (self.root / "GEMINI.md").read_text()
        self.assertTrue(text.startswith("intro\n") and text.endswith("outro\n"))
        self.assertNotIn("old text", text)

    def test_whole_file_agents_refuse_foreign_files(self):
        rules = self.root / ".cursor/rules/session-guardian.mdc"
        sg.integrate(self.root, "cursor")
        self.assertIn("alwaysApply: true", rules.read_text())
        sg.integrate(self.root, "cursor", remove=True)
        self.assertFalse(rules.exists())
        rules.parent.mkdir(parents=True, exist_ok=True)
        rules.write_text("user file")
        with self.assertRaises(sg.GuardianError):
            sg.integrate(self.root, "cursor")
        self.assertEqual(rules.read_text(), "user file")

    def test_claude_hooks_merge_preserves_user_hooks(self):
        sp = self.root / ".claude" / "settings.json"
        sp.parent.mkdir()
        user = {"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "my-linter"}]}]}}
        sp.write_text(json.dumps(user))
        sg.integrate(self.root, "claude")
        sg.integrate(self.root, "claude")  # idempotent
        s = json.loads(sp.read_text())
        self.assertEqual(s["permissions"], user["permissions"])
        pre = s["hooks"]["PreToolUse"]
        self.assertEqual(len(pre), 2)
        self.assertEqual(pre[0]["hooks"][0]["command"], "my-linter")
        self.assertEqual(set(s["hooks"]), set(sg.CLAUDE_HOOK_EVENTS))
        self.assertTrue((sp.parent / "settings.json.session-guardian.bak").exists())
        self.assertIn(sg.BLOCK_BEGIN, (self.root / "CLAUDE.md").read_text())
        sg.integrate(self.root, "claude", remove=True)
        self.assertEqual(json.loads(sp.read_text()), user)
        self.assertFalse((self.root / "CLAUDE.md").exists())

    def test_claude_refuses_invalid_settings(self):
        sp = self.root / ".claude" / "settings.json"
        sp.parent.mkdir()
        sp.write_text("{invalid")
        with self.assertRaises(sg.GuardianError):
            sg.integrate(self.root, "claude")
        self.assertEqual(sp.read_text(), "{invalid")


class ClaudeHookTests(Base):
    """Hook handlers driven with Claude Code's documented stdin payload shapes."""

    def setUp(self):
        super().setUp()
        sg.init(self.root)
        set_scope(self.md, ["migrations/"])

    def payload(self, event, **extra):
        return dict({"session_id": "s-1", "transcript_path": "/tmp/t.jsonl", "cwd": str(self.root), "hook_event_name": event}, **extra)

    def test_session_start_prints_recovery_and_records_session(self):
        out = sg.hook("claude", "SessionStart", self.payload("SessionStart", source="startup"))
        self.assertEqual(out.code, 0)
        self.assertIn("SessionGuardian recovery report", out.stdout)
        self.assertEqual(sg.list_sessions(self.root)[0]["agent_session_id"], "s-1")

    def test_pre_tool_use_blocks_protected_edit(self):
        out = sg.hook("claude", "PreToolUse", self.payload("PreToolUse", tool_name="Edit", tool_input={"file_path": str(self.root / "migrations/1.sql")}))
        self.assertEqual(out.code, 2)
        self.assertIn("migrations/", out.stderr)
        ok = sg.hook("claude", "PreToolUse", self.payload("PreToolUse", tool_name="Write", tool_input={"file_path": "src/ok.py"}))
        self.assertEqual(ok.code, 0)

    def test_pre_compact_and_session_end_checkpoint(self):
        sg.hook("claude", "SessionStart", self.payload("SessionStart"))
        sg.hook("claude", "PreCompact", self.payload("PreCompact", trigger="auto"))
        sg.hook("claude", "SessionEnd", self.payload("SessionEnd", reason="logout"))
        triggers = [json.loads((cp / "manifest.json").read_text())["activity"]["trigger"] for cp in sg.list_checkpoints(self.root)]
        self.assertEqual(sorted(triggers), ["claude-precompact", "claude-session-end"])
        self.assertEqual(sg.list_sessions(self.root)[0]["state"], "ended")

    def test_hooks_never_break_agent_on_errors(self):
        (self.md / "CURRENT_STATE.md").write_text("AKIAABCDEFGHIJKLMNOP\n")
        out = sg.hook("claude", "PreCompact", self.payload("PreCompact"))
        self.assertEqual(out.code, 0)
        self.assertIn("Refusing", out.stderr)

    def test_uninitialized_project_is_silent(self):
        other = Path(self.tmp.name) / "plain"
        other.mkdir()
        out = sg.hook("claude", "PreToolUse", {"cwd": str(other), "tool_input": {"file_path": str(other / "x")}})
        self.assertEqual((out.code, out.stdout, out.stderr), (0, "", ""))

    def test_cli_hook_reads_stdin(self):
        code, out, err = self.run_cli("hook", "claude", "PreToolUse", stdin=json.dumps(self.payload("PreToolUse", tool_input={"file_path": str(self.root / "migrations/x")})))
        self.assertEqual(code, 2)
        self.assertIn("blocked", err)


class CliTests(Base):
    def test_text_format_and_version(self):
        sg.init(self.root)
        code, out, _ = self.run_cli("status", str(self.root), "--format", "text")
        self.assertEqual(code, 0)
        self.assertIn("initialized: yes", out)
        with self.assertRaises(SystemExit):
            self.run_cli("--version")

    def test_scope_check_exit_code(self):
        sg.init(self.root)
        set_scope(self.md, ["db/"])
        self.assertEqual(self.run_cli("scope", "check", str(self.root / "db/x"), "-C", str(self.root))[0], 1)
        self.assertEqual(self.run_cli("scope", "check", str(self.root / "ok"), "-C", str(self.root))[0], 0)

    def test_recover_markdown(self):
        sg.init(self.root)
        code, out, _ = self.run_cli("recover", str(self.root), "--format", "markdown")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("# SessionGuardian recovery report"))

    def test_completion_scripts(self):
        for shell in ("bash", "zsh", "powershell"):
            code, out, _ = self.run_cli("completion", shell)
            self.assertEqual(code, 0)
            self.assertIn("checkpoint", out)
            self.assertIn("watch", out)

    def test_internal_errors_are_concise(self):
        sg.init(self.root)
        from unittest import mock
        with mock.patch.object(sg, "status", side_effect=RuntimeError("boom")):
            code, _, err = self.run_cli("status", str(self.root))
        self.assertEqual(code, 3)
        self.assertIn("internal error", err)
        self.assertNotIn("Traceback", err)

    def test_doctor(self):
        code, out, _ = self.run_cli("doctor")
        d = json.loads(out)
        self.assertTrue(d["ok"])
        self.assertEqual(d["version"], sg.__version__)

    def test_uninstall_requires_managed_install(self):
        self.assertEqual(self.run_cli("uninstall")[0], 2)


if __name__ == "__main__":
    unittest.main()
