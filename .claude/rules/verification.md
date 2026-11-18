# Verification Rules
- Use risk-based checks proportional to the change.
- Run cheap checks before expensive ones.
- E2E for material user-facing flows; property tests for invariants and boundaries; differential tests for behavior-preserving rewrites.
- Preserve evidence of failures and diagnose root causes.
- Never report unexecuted checks as passed.
- Stop after three unsuccessful meaningful fix-and-verify rounds for the same issue.
- Report PASS, PARTIAL, FAIL, or NOT VERIFIED with supporting evidence.
