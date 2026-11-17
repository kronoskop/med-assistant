---
name: verify
description: Verify code changes using executable checks and evidence. Use after significant coding changes, before commits, or when asked to verify functionality.
---

# Verification Skill
1. Inspect the diff, relevant code, project instructions, and acceptance criteria.
2. Choose the smallest reliable set of checks: static, unit/integration, build, E2E, property, or differential as relevant.
3. Execute checks; when feasible, launch the actual application and exercise affected workflows.
4. Capture exit codes, logs, traces, screenshots, or other meaningful evidence.
5. Investigate failures; after each fix rerun failed checks and relevant regressions. Stop after three unsuccessful meaningful correction rounds for the same issue.
6. Report exact revision/working-tree state, commands, results, runtime observations, missing verification, remaining risks, and PASS/PARTIAL/FAIL/NOT VERIFIED.
Do not run destructive operations without authorization or mark unexecuted checks as passed.
