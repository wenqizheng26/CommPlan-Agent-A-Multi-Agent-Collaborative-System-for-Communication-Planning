# CommPlan-Agent Demo validation record

Target: FSPL-stage Planning Workbench, Windows / Python 3.12. This is a living release gate record. A prior stage PASS does not prove a later source ZIP or accepted `main` build.

| Gate | Current evidence | Status |
| --- | --- | --- |
| Stage 0 preservation | 309 source/intended files backed up with SHA-256; d3e7f60 | PASS local |
| Stage 1 correctness | 222 Python, 19 Node, pip check; 3ac8819 | PASS local |
| Stage 2 productization | 224 Python, 24 Node, pip check; in-app browser FSPL/missing/conflict/interval/candidates/recovery; 8aabb57 | PASS local; Chrome pending |
| Stage 3 project-internal Qwen | 63 files / 2,683,695,110 bytes copied with matching per-file SHA-256; actual project-internal llama process on 18081; `/health`, `/v1/models`, workbench model status and three-role Qwen FSPL flow passed; external source retained | PASS local |
| Clean Python 3.12 Planning setup | source ZIP extracted without `.venv`; `setup_planning.cmd`, `pip check`, HTTP create/confirm/restart smoke passed on Windows | PASS local on precommit candidate |
| Source release ZIP | Rebuilt from clean commit `5c4363083c89dedb1a3b925bc2f6ec4236f82103` with `--require-clean`: `outputs/releases/commplan-agent-v0.1.0-demo-source.zip`, SHA-256 `59E26EAF1F335638ED825C5AF0AD8685A20B9C5A9D87F9D5AB6713BEE40AFB2A`; `source_dirty=false`, 76 allowlisted files. Validator PASS: safe extraction, fingerprint, HTTP create/confirm/restart recovery. Stage 5 must rebuild from accepted main. | PASS local |
| Stage 3 full regression | New repository `.venv` after CI `legacy-full` dependency setup: 233 Python OK (1 symlink privilege skip), 25 Node PASS, pip check PASS. Initial minimal Planning `.venv` failed only the legacy Torch import test; clean minimal install and smoke were verified separately. | PASS local |
| 2560×1440 in-app browser layout | CSS viewport 1430×804 at current Windows scale; body exactly 1430×804 with no whole-page scroll; input, flow, result, missing-input answer box and submit button visible. Notice is inline (`position: static`) and auto-dismisses; header labels removed. Browser console warnings/errors: none. | PASS in-app browser; target Chrome pending |
| Stage 4 model online/offline | On isolated database, live Qwen gave 98.42059991327963 dB with interpretation/calculation/review `llm`; after stopping only the verified project-owned 18081 process, service status became `unreachable`, the same FSPL task completed with deterministic interpretation and `deterministic_fallback` for calculation/review. Internal model was restarted; `/health`, `/v1/models`, and workbench status returned `ready`. | PASS local |
| Stage 4 Windows release extraction | PowerShell `Expand-Archive` preserved `启动.cmd` and `start.cmd`; extracted package HTTP smoke passed create, confirm, restart recovery. | PASS local |
| Target Chrome | Latest candidate at `http://127.0.0.1:18084` with isolated acceptance DB; user to confirm V4 §29 seven flows | BLOCKED_EXTERNAL_CHROME_VALIDATION |
| Independent final code review | Separate reviewer needed on `9ee7939..HEAD`; implementation agent and test agents do not count | BLOCKED_EXTERNAL_REVIEW |
| GitHub branch/CI | `codex/demo-delivery-final` pushed to `commplan`; [run 35820319930](https://github.com/wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning/actions/runs/35820319930) at `5c43630`: `planning-minimal` PASS, `legacy-full` PASS. Earlier run failed on a noncanonical Windows temporary path comparison; test fixed and rerun. | PASS |
| PR, accepted main, main-derived artifact, tag | after previous gates | PENDING |

The model files and llama runtime stay in ignored `models/signal-formula-qwen3/` for local use. This source release never contains model weights, runtime binaries, venv, DB, logs or PIDs. `BUILD_INFO.json` records the source commit and whether the build tree was dirty.

Reviewer focus: local preservation, graph activity semantics, fingerprint inputs, startup process identity, source package denylist, confirmation/revision/checkpoint behavior, unchanged deterministic raw calculation, and public docs consistency.
