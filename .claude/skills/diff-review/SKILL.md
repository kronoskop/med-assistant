---
name: diff-review
description: Review code changes for actionable defects using the diff-triggered reliability checks in REVIEW.md at the repository root. Use before commits, pull requests, or when a policy-based review is requested. (Separate from the built-in /code-review, which it does not replace.)
---

# Diff Review Skill
1. Read REVIEW.md at the repository root.
2. Inspect current diff against an appropriate trusted baseline.
3. Identify applicable reliability triggers and inspect surrounding code and tests.
4. Identify actionable correctness, security, and compatibility defects; distinguish regressions from pre-existing issues.
5. Report severity, location, evidence, impact, and recommended correction.
6. Re-review affected areas after corrections.
Do not invent findings, treat test success as proof of correctness, or ignore changes to verification infrastructure.
