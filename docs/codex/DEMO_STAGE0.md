# Demo delivery — Stage 0 (2026-09-22)

Authority: [V4](DEMO_HANDOFF_V4.md) plus the user's model migration requirements. Scope remains FSPL. Later stages must not rewrite the backend core.

- Preserved 309 tracked/intended untracked files before fetching; ZIP CRC and each SHA-256 verified. Local rollback archive: sibling workarea `demo-delivery-preservation-20260922/candidate.zip`; manifest includes original Git status and hashes. No venv, models, runtime, outputs, caches or Git metadata included.
- Initial branch `integrate-h0`; HEAD and freshly fetched target main both `9ee79395e6a9016a163a72c14806e60fbb7c4074` (0/0 commits). Candidate differences are working-tree changes, not a divergent committed history. No reset/clean/discard/reimplementation.
- `origin` points to the legacy signal-formula-rag repository. Delivery uses the explicit V4 target URL; shared worktree remote configuration is unchanged.
- Existing 23 modified tracked files: parser/source guards, whole-domain replacement, transport diagnostics/deadline/cancellation rollback, recent history, UI drafts/state and launcher reuse guard. Preserved as a single baseline checkpoint, no new UI redesign.
- Intended untracked code: model_transport.py, build_info.py, drafts.mjs; tests: planning_drafts, audit_regressions, model_transport; delivery: requirements-planning.txt, setup_planning.cmd, .github/workflows/tests.yml; historical evidence: audit-fixes-live-20260922.json. All included. The evidence file is historical, not this run's live-model validation.

Windows validation (Python in existing .venv):

- `.venv/Scripts/python.exe -B -X utf8 -m unittest discover -s tests -p "test_*.py"`: 217 tests PASS, 74.254 s.
- `node --test tests/planning_*.test.mjs`: 16 PASS.
- `.venv/Scripts/python.exe -m pip check`: no broken requirements.
- `git diff --check`: PASS.

Model discovery audit: existing resource layout has runtime_config.json, generation weights under models/Qwen3-4B-GGUF and executable/DLLs under runtime/llama.cpp-b10950. E: free space about 486 GB, model weight about 2.50 GB; Stage 3 will copy and hash-check the complete required runtime before switching priority. Original assets remain rollback material. No model assets staged or distributed.

Known pending gates: Stage 1 truth/fingerprint, Stage 2 UX, Stage 3 clean installation/release/migration, Stage 4 Chrome and external independent review, Stage 5 remote CI/PR/accepted-main release. Existing CI being pushed is not evidence of a successful run. Historical NEXT_ACTION unitless-distance and roadmap notes are superseded by V4 and current regression evidence.
