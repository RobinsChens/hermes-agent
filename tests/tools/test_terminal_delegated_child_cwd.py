"""A delegated subagent's shell must run in ITS OWN cwd record, not the parent's.

Regression test for the worktree-isolation shadowing bug: with
``delegation.worktree_isolation`` on, ``seed_workspace`` records the child's
worktree path under the CHILD's task_id, but ``terminal_tool`` resolved the cwd
record through the approval/session key, which in a delegated-child context is
the PARENT's session key (the contextvar does not cross tool-worker threads and
``HERMES_SESSION_KEY`` is inherited from the parent process). The parent's
recorded cwd therefore shadowed the child's own, so the child silently ran in
the shared checkout instead of its isolated worktree.
"""

from __future__ import annotations

import pytest

from tools import terminal_tool
from agent import delegation_context


def test_delegated_child_uses_own_task_id_as_cwd_anchor(monkeypatch):
    """Inside a delegated-child context the cwd anchor is the child's task_id."""
    monkeypatch.setattr(terminal_tool, "_session_cwd", {})
    terminal_tool.record_session_cwd("sa-child-1", "/repo/.worktrees/child")
    terminal_tool.record_session_cwd("parent-session", "/repo")

    captured = {}

    def _fake_resolve(*, workdir, default_cwd, session_key=None, env_type=None):
        captured["session_key"] = session_key
        return workdir or default_cwd

    monkeypatch.setattr(terminal_tool, "_resolve_command_cwd", _fake_resolve)

    from tools.approval_context import set_current_session_key, reset_current_session_key

    token = set_current_session_key("parent-session")
    try:
        with delegation_context.delegated_child_context("child-session"):
            terminal_tool.terminal_tool("pwd", task_id="sa-child-1")
    finally:
        reset_current_session_key(token)

    assert captured["session_key"] == "sa-child-1"


def test_non_delegated_context_keeps_parent_session_anchor(monkeypatch):
    """Outside a delegated-child context the parent session key stays authoritative."""
    monkeypatch.setattr(terminal_tool, "_session_cwd", {})
    terminal_tool.record_session_cwd("sa-child-1", "/repo/.worktrees/child")
    terminal_tool.record_session_cwd("parent-session", "/repo")

    captured = {}

    def _fake_resolve(*, workdir, default_cwd, session_key=None, env_type=None):
        captured["session_key"] = session_key
        return workdir or default_cwd

    monkeypatch.setattr(terminal_tool, "_resolve_command_cwd", _fake_resolve)

    from tools.approval_context import set_current_session_key, reset_current_session_key

    token = set_current_session_key("parent-session")
    try:
        terminal_tool.terminal_tool("pwd", task_id="sa-child-1")
    finally:
        reset_current_session_key(token)

    assert captured["session_key"] == "parent-session"


def test_child_cwd_record_wins_over_parent_record(monkeypatch):
    """The child's own worktree path is what a child command actually resolves to."""
    monkeypatch.setattr(terminal_tool, "_session_cwd", {})
    terminal_tool.record_session_cwd("sa-child-1", "/repo/.worktrees/child")
    terminal_tool.record_session_cwd("parent-session", "/repo")

    with delegation_context.delegated_child_context("child-session"):
        resolved = terminal_tool._resolve_command_cwd(
            workdir=None,
            default_cwd="/repo",
            session_key="sa-child-1",
            env_type="local",
        )

    assert resolved == "/repo/.worktrees/child"
