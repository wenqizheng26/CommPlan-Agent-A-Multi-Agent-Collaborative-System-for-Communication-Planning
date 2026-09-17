# SA-ENV: tested workflow dependency decision

Date: 2026-09-17. Scope: single requirements/planning graph only. No business contract changes.

## Decision and official evidence

Use `langgraph==1.2.11`, obtained from the publisher's [PyPI metadata](https://pypi.org/pypi/langgraph/1.2.11/json), which declares Python >=3.10 and MIT. The upstream [MIT license](https://github.com/langchain-ai/langgraph/blob/main/LICENSE) was checked. [Official graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) documents StateGraph and conditional edges; [official interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) documents interrupt, Command(resume=...), stable thread_id, and node re-entry. API compatibility is established by the installed-version test, not assumed from current docs.

The resolved package brings its required prebuilt/SDK/core dependencies; no provider integrations, SQLite backend, or full langchain package were separately requested. `requirements.lock.txt` pins the existing ML environment plus the actual resolved dependency closure. urllib3 moves from 2.7.0 to 2.8.0 only in the active environment. Archive URLs and SHA256 hashes plus distribution license metadata are recorded in `evidence/sa_env.json`. This is a version lock, not a pip --require-hashes file. CPU torch retains its existing special index requirement when rebuilding from scratch.

## Isolation and reproduction

Working directory: `E:\codex\项目\信号与AI\.workareas\signal-formula-rag-h0-implementation`.

Created active `.venv` using source Python 3.12.14:

```powershell
& 'E:/codex/项目/信号与AI/signal-formula-rag/.venv/Scripts/python.exe' -B -m venv .venv
./.venv/Scripts/python.exe -B -m pip install --ignore-installed --no-compile --report .venv/langgraph_install_report.json langgraph==1.2.11
```

Active `.venv/Lib/site-packages/source_ml_readonly.pth` contains the absolute source `.venv/Lib/site-packages` path. It is a read-only reuse convention, not an OS-enforced ACL. LangGraph and its entire resolved dependency closure are installed into active `.venv`; source torch 2.8.0+cpu and transformers 4.57.6 are reused. `--ignore-installed` prevents uninstalling or replacing source packages. Use active Python with `-B` (or PYTHONDONTWRITEBYTECODE=1 for child processes) to prevent source bytecode writes. The `.pth` is machine-local and ignored, so another checkout must create its own environment. No model downloads or inference were run.

## Verification

The test file was written before installing LangGraph. Initial run: exit 1, missing `langgraph`, with existing ML import test passing (2 tests, 1 error). Installation: exit 0, no network correction needed.

```powershell
./.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_workflow_dependencies.py -v
./.venv/Scripts/python.exe -B -m pip check
```

Both exit 0. The 2 smoke tests check real StateGraph conditional routing, an interrupted state, Command resume, re-entry of the interrupted node, direct completion, torch tensor execution, and transformers import. `pip check`: no broken requirements.

All 101 existing tests passed, no errors/failures/skips, using unittest discovery separately for `test_app`, `test_core`, `test_import`, `test_interpretation`, `test_launcher`, `test_parsing`, `test_pasted_input`, `test_pipeline`, `test_presentation`, and `test_scientific_scope` (8.930 seconds). New planning tests were intentionally excluded from this baseline run because Main owns them.

Source environment before/after hashes match for 47 files: distribution RECORD files, pyvenv.cfg, python.exe and .pth files. This proves the recorded install manifests/configuration/interpreter were unchanged; it is not a complete hash of every source environment file. No pip command targeted source. Evidence includes this precise scope.

InMemorySaver validates same-process API behavior only. It does not satisfy cross-process persistence, atomic state/checkpoint commit, durable idempotency, production confirmation, or SQLite acceptance. These remain outside this slice; no such completion is claimed.
