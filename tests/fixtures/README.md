# Shared cross-service test fixtures

`social_validator_parity.json` is the single checked-in parity table for
MoneyFast social-signal validators.

Runtime URL/handle/KAP/evidence helpers remain duplicated inside the backend,
orchestrator, and MCP packages because those containers cannot import each
other. Semantic drift is prevented by:

1. Both orchestrator and backend test suites loading **this** fixture path.
2. A byte-identity check in each suite that fails if a stale local copy differs.
3. Extended `evidence_block` / `citation_mismatch` cases that exercise the
   canonical evidence grammar and evidence-id binding at every boundary.
