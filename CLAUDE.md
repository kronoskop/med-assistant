# Project instructions: med-assistant

Medical assistant that answers from clinical guidelines (FastAPI + local LLM in LM Studio).
Run: `make run` (default port 8001). Tests: `make test` (`uv run pytest -q`).

## Secrets and configuration

- Do not read `.env`, `auth.json`, API keys, connection settings, private server addresses or other secrets.
  Use `.env.example` for the list of settings.
- Do not extract secrets from setup scripts, shell history, logs or processes.
- Do not print whole configs or a full environment dump.
  If a property cannot be checked safely, treat it as unknown.
  Do not reproduce secrets encountered by accident.

## Delegated executors

- Delegated executors (subagents, external CLIs) do not edit sources, configs, tests or
  snapshots; they do not auto-fix, install, commit or delegate further.
- For tests, temporary files, caches and build outputs are allowed.
- Each executor gets a narrow task and returns a short result with verifiable references
  (path:line, commands, exit codes, short error excerpts).

<!-- BEGIN verification-framework v1.0 (managed block) -->
# Verification framework

## Principles
- Correctness over apparent completion; verify observable behavior.
- Prefer minimal, targeted, reversible changes.
- Preserve existing behavior and compatibility unless changes are authorized.
- Never invent test results, claim unobserved success, or silently suppress failures.
- Respect project-specific instructions and existing tooling.
- Avoid unnecessary dependencies, complexity, and token usage.

## Before coding
For nontrivial changes, inspect the relevant code and tests, define acceptance criteria, identify regression risks, and select verification checks before implementing. Use proportionate checks for trivial changes.

## During coding
Make the smallest effective change. Avoid unrelated refactoring. Update meaningful tests when behavior changes. Never weaken tests or disable checks to force a pass.

## Verification
1. Inspect the final diff.
2. Run relevant cheap checks first (format, lint, types).
3. Run targeted unit/integration tests and build checks as appropriate.
4. Exercise real runtime behavior and E2E workflows when applicable and feasible.
5. Use property-based tests for invariants, parsers, and calculations.
6. Use differential tests for refactors and behavior-preserving migrations.
7. Record actual evidence, unverified areas, and remaining risks.
Do not run unrelated expensive suites for trivial changes. Skill: `/verify`.

## Failures
Diagnose root causes; do not blindly retry or mask flaky tests. After three unsuccessful meaningful fix-and-verify rounds for the same issue, stop and escalate. Separate pre-existing failures from introduced regressions.

## Review
Use REVIEW.md (repository root) and apply only diff-triggered checks (skill: `/diff-review`; the built-in `/code-review` is unchanged). Treat changes to verification infrastructure as sensitive; never weaken gates without authorization.

## Commit gate
A project PreToolUse hook (`.claude/hooks/verification_gate.py`, registered in `.claude/settings.json`) prints a reminder before `git commit`. It is OBSERVE-only: it does not track test evidence and never blocks. Its silence or warning is not evidence either way.

## Completion report
For coding tasks report changes, commands and observed results, runtime evidence where applicable, omissions, risks, and status:
- PASS: all required checks passed with evidence.
- PARTIAL: some checks passed, but material verification remains.
- FAIL: a required check failed.
- NOT VERIFIED: no meaningful verification was performed.
Never report PASS without sufficient evidence.
<!-- END verification-framework v1.0 -->

Detailed rules: `.claude/rules/verification.md`, `.claude/rules/reliability.md`.
