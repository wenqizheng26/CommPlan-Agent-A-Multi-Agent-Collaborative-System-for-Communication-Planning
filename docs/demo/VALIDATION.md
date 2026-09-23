# CommPlan-Agent Demo validation record

Target: FSPL-stage Planning Workbench, Windows / Python 3.12. This is a living release gate record. A prior stage PASS does not prove a later source ZIP or accepted `main` build.

| Gate | Current evidence | Status |
| --- | --- | --- |
| Stage 0 preservation | 309 source/intended files backed up with SHA-256; d3e7f60 | PASS local |
| Stage 1 correctness | 222 Python, 19 Node, pip check; 3ac8819 | PASS local |
| Stage 2 productization | 224 Python, 24 Node, pip check; in-app browser FSPL/missing/conflict/interval/candidates/recovery; 8aabb57 | PASS local; Chrome pending |
| Stage 3 project-internal Qwen | 63 files / 2,683,695,110 bytes copied with matching per-file SHA-256; actual project-internal llama process on 18081; `/health`, `/v1/models`, workbench model status and three-role Qwen FSPL flow passed; external source retained | PASS local |
| Clean Python 3.12 Planning setup | source ZIP extracted without `.venv`; `setup_planning.cmd`, `pip check`, HTTP create/confirm/restart smoke passed on Windows | PASS local on precommit candidate |
| Source release ZIP | explicit allowlist, SHA-256 manifest, safe extraction and unpacked smoke passed on precommit candidate; clean-commit rebuild still required | PASS precommit; formal rebuild pending |
| Stage 3 full regression | 233 Python OK (1 symlink privilege skip), 24 Node PASS, pip check PASS | PASS local |
| Target Chrome | user will manually confirm after candidate is ready | PENDING USER CHECK |
| Independent final code review | separate reviewer needed on final diff | PENDING EXTERNAL REVIEW |
| GitHub branch/CI | push rejected by OAuth credential missing workflow scope; no CI run | BLOCKED_REMOTE_AUTH |
| PR, accepted main, main-derived artifact, tag | after previous gates | PENDING |

The model files and llama runtime stay in ignored `models/signal-formula-qwen3/` for local use. This source release never contains model weights, runtime binaries, venv, DB, logs or PIDs. `BUILD_INFO.json` records the source commit and whether the build tree was dirty.

Reviewer focus: local preservation, graph activity semantics, fingerprint inputs, startup process identity, source package denylist, confirmation/revision/checkpoint behavior, unchanged deterministic raw calculation, and public docs consistency.
