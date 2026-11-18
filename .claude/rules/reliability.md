# Reliability Rules
- Identify risks from the actual diff; check compatibility, authorization, concurrency, and data integrity when relevant.
- Treat verification configuration changes as sensitive.
- Never disable or weaken tests or gates to obtain a green result.
- Separate pre-existing defects from introduced regressions.
- Require approval for destructive operations.
- Turn repeated confirmed defects into candidate rules; periodically prune obsolete rules.
