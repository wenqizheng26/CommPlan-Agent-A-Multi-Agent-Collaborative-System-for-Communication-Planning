# Demo delivery — Stage 1 (2026-09-22)

- Existing unitless-distance implementation retained; four V4 blocking cases reject confirmation; shared trailing-unit choices remain calculable.
- Runtime edges identify observed activity/responsibility relations, never literal LangGraph direct calls. No graph transitions or persistence changes.
- Build identity includes knowledge/formulas.json and runtime_config.json. Formula/config changes alter identity; SQLite history, logs and PIDs do not.
- NEXT_ACTION marks contradictory old issue/roadmap notes historical.

Validation:
- `.venv/Scripts/python.exe -B -X utf8 -m unittest discover -s tests -p "test_*.py"`: 222 PASS, 100.466 s.
- `node --test tests/planning_*.test.mjs`: 19 PASS.
- `.venv/Scripts/python.exe -m pip check`: no broken requirements.
- `git diff --check`: PASS.

Git: codex/demo-delivery-final. Stage 0 push retried after user updated GitHub authorization; GitHub still rejects the OAuth credential for missing workflow scope. No workflow file removed to bypass this requirement. Remote CI remains unverified.

Reviewer focus: unchanged graph/persistence, ownership-vs-direct-call wording and accessible SVG attributes, immutable asset fingerprint scope, false-positive protection for shared-unit candidates.
