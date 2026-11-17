"""Tests for the OBSERVE-only commit reminder hook in .claude/hooks."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "verification_gate.py"
_spec = importlib.util.spec_from_file_location("verification_gate", HOOK)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


@pytest.mark.parametrize("cmd", [
    "git commit -m x",
    "git -C repo commit -am 'x'",
    "cd a && git commit -m x",
    "FOO=1 env git commit",
    "bash -c 'git commit -m x'",
    "/usr/bin/git commit",
    "git add . ; git commit -m \"a; b\"",
    "git commit -m 'unbalanced",
])
def test_detects_commit(cmd):
    assert gate.is_git_commit(cmd)


@pytest.mark.parametrize("cmd", [
    "git status",
    "git commit --dry-run",
    "git commit -h",
    "echo git commit",
    "git log --grep commit",
    "git commit-tree abc",
    "",
])
def test_ignores_non_commit(cmd):
    assert not gate.is_git_commit(cmd)


def _event(cmd, tool="Bash"):
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool,
                       "tool_input": {"command": cmd}, "cwd": "/repo"})


def test_run_outputs_reminder_and_never_decides():
    out = gate.run(_event("git commit -m x"), env={})
    assert "systemMessage" in out
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "permissionDecision" not in out["hookSpecificOutput"]


def test_modes():
    assert gate.run(_event("git commit"), env={"CLAUDE_VERIFY_MODE": "off"}) is None
    enforce = gate.run(_event("git commit"), env={"CLAUDE_VERIFY_MODE": "enforce"})
    assert "not implemented" in enforce["systemMessage"].lower()
    assert gate.get_mode({"CLAUDE_VERIFY_MODE": "bogus"}) == "observe"


@pytest.mark.parametrize("stdin", ["not json", "[]", _event("git commit", tool="Edit"),
                                   _event("ls")])
def test_run_silent_on_other_input(stdin):
    assert gate.run(stdin, env={}) is None


def test_main_always_exits_zero():
    for stdin in ("garbage", _event("git commit -m x")):
        res = subprocess.run([sys.executable, str(HOOK)], input=stdin,
                             capture_output=True, text=True, timeout=10)
        assert res.returncode == 0
