# CommPlan-Agent Demo validation record

Target: FSPL-stage Planning Workbench, Windows / Python 3.12. This is a living release gate record. A prior stage PASS does not prove a later source ZIP or accepted `main` build.

| Gate | Current evidence | Status |
| --- | --- | --- |
| Stage 0 preservation | 309 source/intended files backed up with SHA-256; d3e7f60 | PASS local |
| Stage 1 correctness | 222 Python, 19 Node, pip check; 3ac8819 | PASS local |
| Stage 2 productization | 224 Python, 24 Node, pip check; in-app browser FSPL/missing/conflict/interval/candidates/recovery; 8aabb57 | PASS local; Chrome pending |
| Stage 3 project-internal Qwen | 63 files / 2,683,695,110 bytes copied with matching per-file SHA-256; actual project-internal llama process on 18081; `/health`, `/v1/models`, workbench model status and three-role Qwen FSPL flow passed; external source retained | PASS local |
| C3 historical archive | `03c985f8757651ef3f6fb3ca54d947ead18c9585`: 118 tracked historical files and NEXT_ACTION history, plus 20 inactive output items moved under external `_archive/2026-09-23-commplan/`; 139-entry manifest; 4 cited evidence files and active SQLite databases retained; retained Markdown has no broken relative links | PASS local |
| Clean Python 3.12 Planning setup | source ZIP extracted without `.venv`; `setup_planning.cmd`, `pip check`, HTTP create/confirm/restart smoke passed on Windows | PASS local on precommit candidate |
| Source release ZIP | Rebuilt from clean commit `03c985f8757651ef3f6fb3ca54d947ead18c9585` with `--require-clean`: `outputs/releases/commplan-agent-v0.1.0-demo-source.zip`, SHA-256 `64CA21C1DAE6FF21B51CF7A05333D878CBC76AEFD7D1F97DC6D89CF3AE66942C`; `source_dirty=false`, 76 allowlisted files. Validator PASS: safe extraction, fingerprint, HTTP create/confirm/restart recovery. Stage 5 must rebuild from accepted main. | PASS local |
| Stage 4 full regression after visual redesign | At `03c985f`: 233 Python OK (1 symlink privilege skip), 27 Node PASS, pip check PASS. Initial minimal Planning `.venv` failed only the legacy Torch import test; clean minimal install and smoke were verified separately. | PASS local |
| 2560×1440 in-app browser layout | CSS viewport 1430×804 at current Windows scale; body exactly 1430×804 with no whole-page scroll. Input, complete flow and primary result are visible together; flow panel has no inner scroll, while long result details scroll within their column. Inline notice does not cover the top-right controls. Latest light appearance and online/offline flow/result consistency checked; browser console warnings/errors: none. System-dark visual inspection remains pending. | PASS light in-app browser; dark and target Chrome pending |
| Stage 4 model online/offline after visual redesign | Isolated live Qwen task `3278b9ec` completed at 98.42059991327963 dB with interpretation/calculation/review all `llm`. After stopping the verified project-owned 18081 process, isolated task `bc667b82` completed at the same value with deterministic interpretation and `deterministic_fallback` calculation/review; browser flow showed LLM “调用已降级” with published result 98.42 dB. Project-internal model restarted; `/health` and `/v1/models` returned ready. | PASS local and in-app browser |
| Stage 4 Windows release extraction | PowerShell `Expand-Archive` preserved `启动.cmd` and `start.cmd`; extracted package HTTP smoke passed create, confirm, restart recovery. | PASS local |
| Target Chrome | Latest UI candidate at `http://127.0.0.1:18088`; user to confirm V4 §29 seven flows on the post-redesign candidate | BLOCKED_EXTERNAL_CHROME_VALIDATION |
| Independent final code review | Separate reviewer needed on `9ee7939..HEAD`; implementation agent and test agents do not count | BLOCKED_EXTERNAL_REVIEW |
| GitHub branch/CI | Previous [run 35820319930](https://github.com/wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning/actions/runs/35820319930) at `5c43630`: `planning-minimal` and `legacy-full` PASS. Post-redesign and C3 candidate `03c985f` is not yet pushed/verified by remote CI. | PENDING current candidate |
| PR, accepted main, main-derived artifact, tag | after previous gates | PENDING |

The model files and llama runtime stay in ignored `models/signal-formula-qwen3/` for local use. This source release never contains model weights, runtime binaries, venv, DB, logs or PIDs. `BUILD_INFO.json` records the source commit and whether the build tree was dirty.

Reviewer focus: local preservation, graph activity semantics, fingerprint inputs, startup process identity, source package denylist, confirmation/revision/checkpoint behavior, unchanged deterministic raw calculation, and public docs consistency.
