# CommPlan-Agent Demo Delivery — Final Codex Handoff V4

> Repository: `wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning`
> Target: Finish the current FSPL-stage project as a stable, truthful, productized Demo release
> Audit date: 2026-09-22
> Principle: **Preserve valid local work first; fix confirmed correctness/delivery issues; freeze the proven backend core; productize the Demo; validate the final package; only then merge/tag.**

---

# 0. Status Legend

This handoff separates different evidence levels.

```text
CONFIRMED
= directly verified in the supplied current workspace

LOCAL_CANDIDATE_PENDING_VALIDATION
= local code appears to already fix the issue,
  but it is not yet an authoritative Windows-regression/GitHub baseline

EXTERNAL_GATE
= cannot honestly be marked PASS from the current audit environment;
  must be validated on the intended Windows/Chrome/review environment

IMPROVEMENT
= product-quality work, not proof of a broken backend core
```

Do not mix these categories.

---

# 1. Final Executive Conclusion

## 1.1 Backend architecture

**Freeze by default.**

No evidence from the final audit justifies rebuilding:

- LangGraph
- SQLite persistence
- checkpointing
- confirmation snapshot
- revision/state-version guards
- deterministic numerical execution
- formula/evidence/result provenance
- bounded orchestration
- current model fallback semantics

The current backend is sufficient for the present Demo stage.

The highest-risk mistake is:

> rewriting a stable workflow merely to make the architecture look more autonomous or more “multi-agent”.

Do not do that.

---

## 1.2 Current Demo scope

The current release is intentionally an FSPL-stage controlled planning workflow.

The fact that it currently focuses on FSPL is **not** a release blocker.

Do not expand this release into:

- full link budget
- rain attenuation
- maritime propagation
- autonomous orchestration
- LoRA
- new vector-RAG stack
- runtime Skills framework

These belong after the current Demo release.

---

# 2. Audit Evidence Already Obtained

## 2.1 Frontend tests

Executed:

```text
node --test tests/planning_*.test.mjs
```

Result:

```text
16 / 16 PASS
```

This is module-level Node regression, not real Chrome E2E.

---

## 2.2 Python source integrity

All Python source files under:

```text
planning
formula_rag
scripts
tests
```

compiled successfully.

Static test discovery found:

```text
217 Python test_* functions
```

Important:

> 217 is a static function count, not a claim that 217 tests passed.

The supplied `.venv` is a Windows environment and cannot be reused as a trustworthy Linux regression environment.

---

## 2.3 Frontend/static integrity

Verified:

- planning JS modules pass syntax checks
- frontend API paths map to server endpoint families
- DOM IDs referenced from `app.js` exist
- no duplicate HTML IDs were found
- no `innerHTML`, `insertAdjacentHTML`, `eval`, or `document.write` was found in the current Planning UI path
- source links use restricted protocols and safe external-link behavior

Do not perform unnecessary UI-security rewrites.

---

## 2.4 Local web hardening

Current Planning web server already includes useful local-service protections:

- loopback binding
- Host checks
- Origin checks
- per-session write token
- constant-time token comparison
- request body limit
- CSP
- `nosniff`
- `no-store`
- structured JSON responses
- no raw traceback returned to browser

Do not replace this with a large authentication framework for the current single-user local Demo.

---

# 3. P0 — Local Workspace vs GitHub Baseline Drift

## Status: CONFIRMED

The supplied local workspace is **not equivalent** to current GitHub `main`.

Observed GitHub reference at audit time:

```text
9ee79395e6a9016a163a72c14806e60fbb7c4074
fix: pass explicit user selections to requirements model
```

The local candidate contains many files that are either different from remote `main` or missing remotely.

Confirmed examples include local/remote differences in:

```text
planning/web/flow.mjs
planning/workflow/planning_graph.py
planning/workflow/task_service.py
planning/agents/requirements.py
planning/agents/review.py
planning/services/clarification.py
planning/services/input_domains.py
planning/services/requirement_parameters.py
planning/services/requirement_policy.py
planning/services/requirement_validation.py
planning/services/supplement.py
planning/workflow/task_store.py
planning/web/app.js
planning/web/index.html
planning/web/model-status.mjs
planning/web/details.mjs
planning/web/questions.mjs
planning/web_server.py
start_commplan.py
tests/test_planning_web.py
```

Confirmed local-only examples include:

```text
.github/workflows/tests.yml
setup_planning.cmd
planning/web/drafts.mjs
tests/planning_drafts.test.mjs
tests/test_audit_regressions.py
```

This list is illustrative, not exhaustive.

## Mandatory rule

Before Codex changes product behavior:

```text
DO NOT:
git reset --hard origin/main
git clean -fd
discard untracked local source/tests
start from a fresh main branch and reimplement the local candidate
```

The current local candidate contains valid work that would be lost.

---

# 4. Stage 0 — Preserve and Reconcile the Current Candidate

This is the first engineering step.

## 4.1 Preserve local work

In the real development workspace:

1. inspect `git status`
2. record current branch/worktree
3. back up all local modifications and intended untracked source/tests
4. exclude from preservation:
   - `.venv`
   - outputs DBs
   - runtime logs/PIDs
   - caches
5. only after preservation, fetch remote state

If working from the supplied ZIP, clone the repository separately and reconcile the ZIP source into a dedicated branch.

Do not treat the ZIP's broken `.git` worktree pointer as a usable Git repository.

---

## 4.2 Dedicated branch

Create or safely resume:

```text
codex/demo-delivery-final
```

The first commit should preserve the validated local candidate before new productization work.

Do not mix UI redesign into this preservation commit.

---

## 4.3 Validate the local candidate

On the intended Windows environment:

```text
python -B -X utf8 -m unittest discover -s tests -p "test_*.py"
node --test tests/planning_*.test.mjs
python -m pip check
```

Use repository-authoritative commands if actual paths differ.

Only after the candidate is green should local-only fixes become the authoritative baseline.

---

## 4.4 First GitHub push timing

First push occurs after:

```text
local candidate preserved
+
full current Windows regression passes
+
local-only source/tests/workflow files are classified
```

This push is a preservation checkpoint, not the final release.

---

# 5. Unitless-Distance Issue

## Status: LOCAL_CANDIDATE_PENDING_VALIDATION

`docs/codex/NEXT_ACTION.md` still says the old unitless-distance residue remains unresolved.

That note is stale relative to the supplied local candidate.

The local candidate now contains residue detection in:

```text
planning/services/requirement_parameters.py
```

and local regression coverage in:

```text
tests/test_audit_regressions.py
```

Direct parser probes against the supplied candidate produced blocking diagnostics for cases such as:

```text
距离3
距离大约3
频率2GHz，距离1km，距离3
频率2GHz，距离1km，距离大约3
```

while a legitimate explicit candidate form such as:

```text
频率2GHz，距离3或4km
```

still remains a candidate domain.

## Codex action

Do **not** reimplement the fix blindly.

Instead:

1. run the full Windows regression
2. inspect existing local regression coverage
3. add edge cases only if missing
4. if green, commit the existing local fix
5. update stale docs so they no longer claim the bug is unresolved

---

# 6. P0 — Runtime Flow Truthfulness

## Status: CONFIRMED

The static architecture diagram is allowed to show design collaboration.

It does not need to match LangGraph direct edges one-for-one.

The real issue is runtime semantics.

`flow.mjs` currently says:

```text
Only a real observed call animates an edge.
Architecture relations alone do not.
```

But activity instrumentation uses `details.caller` values such as:

```text
orchestrator
```

for some requirements/calculation/validation/review activity where the literal direct LangGraph predecessor is not always the Orchestrator node.

Real graph relationships include:

```text
START -> requirements
human_confirmation -> calculation
calculation -> orchestrator
orchestrator -> validate_result
validate_result -> review_result
review_result -> orchestrator
```

Therefore current `caller` can mean conceptual ownership/coordinator rather than literal direct graph call.

## Required resolution

Do not rewrite LangGraph.

Choose a truthful representation.

### Minimal option

Change wording/comments from:

```text
real observed direct call
```

to a truthful concept such as:

```text
observed runtime responsibility/activity relation
```

### Stronger option

Add explicit relation semantics such as:

```text
direct_call
workflow_transition
logical_owner
capability_use
```

Use the smallest change that removes the false implication.

## Required regression

Add tests proving that conceptual ownership is not presented as a literal direct call.

---

# 7. P0 — Build Fingerprint Omits Runtime-Critical Knowledge

## Status: CONFIRMED

Current:

```text
planning/build_info.py
```

hashes selected source extensions under:

```text
planning/
formula_rag/
```

but does **not** include:

```text
knowledge/formulas.json
```

Changing only the formula knowledge leaves the current build fingerprint unchanged.

## Why this matters

`start_commplan.py` uses build identity to decide whether an already-running workbench can be reused.

A future release could change only professional knowledge/formulas while an old workbench remains running.

If fingerprint ignores knowledge, the launcher may incorrectly reuse the old service.

## Fix

Include runtime-critical immutable product assets in build identity.

At minimum:

```text
knowledge/formulas.json
```

Also audit any other immutable runtime contract/config that can change behavior without changing Planning Python/JS.

Do not include mutable runtime data such as:

```text
SQLite history
runtime logs
PIDs
```

## Tests

Add regression proving:

```text
change formula knowledge
→ build fingerprint changes
```

and:

```text
change runtime history/log
→ build fingerprint does not change
```

---

# 8. Backend Core — Freeze

## Status: CONFIRMED POSITIVE

Keep the current conceptual architecture:

```text
User / UI
   ↓
Task Service
   ↓
LangGraph
   ↓
Requirements processing
   ├─ deterministic parsing
   ├─ lexical knowledge retrieval
   └─ optional Qwen semantic proposal
   ↓
Human confirmation
   ↓
Calculation role
   ↓
Deterministic numerical tool
   ↓
Hard validation
   ↓
Review role
   ↓
Bounded orchestration policy
   ↓
Publish / retry / return / stop
```

Parallel infrastructure:

```text
SQLite task state
event receipts/history
LangGraph checkpoint
revision/state_version
activity/provenance
```

Do not replace during this release:

- LangGraph
- SQLite
- confirmation snapshot
- revision guards
- stale-state guards
- deterministic numerical authority
- result/evidence binding
- bounded orchestration
- model fallback semantics

---

# 9. Agent Role Truth

## Requirements Agent

Current strongest semantic role.

Keep.

## Calculation Agent

At the current FSPL-only stage it is intentionally constrained.

Treat it as:

```text
controlled calculation/tool proposal role
```

not a broad autonomous planner.

This is not a current release blocker.

## Review Agent

Keep bounded review.

It may assess but must not rewrite professional numerical truth.

## Orchestrator

Accurate description:

```text
bounded scheduling/control policy
```

not autonomous LLM task decomposition.

UI may retain “总控 Agent”, but subtitle/technical description should make the bounded-policy nature explicit.

Do not strengthen the Agent story by weakening deterministic control.

---

# 10. Scientific/Calculation Layer

## Status: CONFIRMED POSITIVE

Current FSPL implementation is suitable for the declared scope.

It:

- uses the registered formula card
- binds result to confirmed snapshot/plan/evidence
- executes deterministic calculation
- validates outputs
- performs an independent exact `4πdf/c` magnitude check
- distinguishes confirmed model assumption from real-site proof
- does not claim LoS automatically proves free space

Preserve these properties.

---

# 11. Human-Facing Numerical Precision

## Status: IMPROVEMENT — Recommended Before Release

Current human-facing paths use six-decimal presentation, e.g.:

```text
98.420600 dB
101.942425 dB
```

Affected human-facing paths include:

```text
planning/services/domain_calculation.py
planning/web/details.mjs
README.md
planning/README.md
```

Raw internal values may retain full precision.

Recommended report display:

```text
98.42 dB
101.94 dB
```

Do not alter:

- raw float
- deterministic evaluator
- validation tolerance
- scientific checks
- provenance meaning

Update tests that explicitly expect six-place human-readable formatting.

---

# 12. Demo UI/Product Structure

## Status: IMPROVEMENT

Current UI is coherent as a development workbench but overweights implementation detail.

Normal Demo priority should be:

```text
What did I ask?
What does the system understand?
What does it still need from me?
What is happening now?
What result did I get?
```

before:

```text
Which Agent/node/service is active?
```

---

# 13. Do Not Restore the Historical Dual-View UI

## Status: CONFIRMED PROJECT DECISION

Current project direction uses the overall architecture single-view.

Historical execution-layout arrays remain in `flow.mjs`, but that does not justify restoring the old dual-view UI.

Use:

```text
Primary:
compact task progress/current action/result

Secondary:
existing overall architecture single-view
```

Do not redesign backend state to support presentation.

---

# 14. Stage 2 — Demo Productization

Recommended changes:

## 14.1 Task/result-first hierarchy

Add a compact presentation-level progress view such as:

```text
需求理解    ✓
参数确认    ✓
专业计算    ●
结果审查    ○
结果生成    ○
```

This is UI mapping, not a new backend state machine.

## 14.2 De-emphasize advanced controls

Preserve semantics, but move low-level controls such as:

- deterministic/Qwen mode
- detailed model service control
- raw task-ID recovery

into an advanced/technical area.

Do not silently change current default execution semantics.

## 14.3 Unsupported targets

Do not present unsupported:

```text
判断能否通信
比较方案
```

as normal active business options.

Hide or disable with clear future-scope wording.

Do not remove the existing target/model-condition context mechanism.

## 14.4 Examples

Reuse current examples.

Ensure visible coverage for:

- complete task
- missing parameter
- interval/candidate domain
- explicit conflict
- optional scope/boundary example

Examples may populate input but should not auto-run.

## 14.5 Typography

Audit excessive 9–12px text in:

- legends
- node subtitles
- timelines
- labels
- tables

The Demo should remain readable in screen sharing/projector use.

## 14.6 History

Keep recent-task recovery.

De-emphasize raw UUID restoration.

Task delete/search/title can remain later work unless trivial.

---

# 15. P0/P1 — Dependency/Setup Contract Is Inconsistent

## Status: CONFIRMED

The local candidate contains:

```text
setup_planning.cmd
```

which creates `.venv` and installs:

```text
requirements-planning.txt
```

But root README mainly points users to:

```text
requirements.lock.txt
```

and the local CI workflow installs:

```text
Torch + requirements.lock.txt
```

Therefore there are currently multiple environment stories.

## Required release contract

### Planning Demo runtime

Use/document:

```text
Python 3.12
requirements-planning.txt
```

with deterministic mode not requiring local model assets.

### Optional full/local model development environment

May use the larger lock/model stack.

Do not force the full ML environment on a user who only needs the Planning Demo.

---

# 16. Minimal Planning Install

## Status: EXTERNAL_GATE

Before release, validate on intended Windows:

```text
clean project directory
no pre-existing project .venv
Python 3.12 available
→ setup_planning.cmd
→ pip check
→ deterministic smoke task
→ web start
```

Do not mark this PASS until actually tested.

## CI recommendation

Add a Windows CI/smoke path using the minimal Planning dependency set.

The full legacy lock test may remain separately.

---

# 17. GitHub CI

## Status: CONFIRMED

The supplied local candidate contains:

```text
.github/workflows/tests.yml
```

but current GitHub `main` does not expose it.

Do not claim:

```text
GitHub CI passes
```

until the workflow is actually committed, pushed, and produces a successful workflow/status result.

---

# 18. Planning-Specific Release Builder

## Status: CONFIRMED MISSING

Legacy scripts such as:

```text
scripts/final_checks.py
scripts/runtime_smoke.py
```

primarily target the older Formula-RAG/web path.

They are not sufficient as the authoritative release builder/validator for the current Planning Workbench.

Create a Planning-specific scripted release process, for example:

```text
scripts/build_planning_release.py
scripts/validate_planning_release.py
```

Exact filenames are flexible.

The process must be scripted and repeatable.

---

# 19. Formal Release Denylist

Do not ship a ZIP of the development worktree.

Exclude at least:

```text
.venv/
.git/
__pycache__/
.pytest_cache/
outputs developer DB/history
runtime logs/PIDs
temporary acceptance DBs
developer-machine paths/logs
unnecessary internal historical evidence
```

Include only runtime/documentation assets needed for the intended Demo.

---

# 20. Build Metadata

Generated release should contain something equivalent to:

```text
VERSION
BUILD_INFO.json
```

Include:

```text
version
source commit SHA
build timestamp
intended platform
build fingerprint
validation record reference
```

---

# 21. Startup Is Already Implemented

## Status: CONFIRMED POSITIVE

`start_commplan.py` already includes substantial logic for:

- workbench reuse
- build check
- port handling
- local model resource discovery
- model reuse/start
- fallback
- readiness wait
- logs/PIDs
- browser opening

Do not build another launcher architecture.

---

# 22. Setup/Start UX

Use the intended roles:

```text
First-time:
setup_planning.cmd

Normal use:
启动.cmd
→ start_commplan.py
```

If `.venv` is missing, root launcher should explicitly direct the user to setup, or safely invoke it if intentionally approved.

Root README must tell the same story.

---

# 23. Service Shutdown/Lifecycle UX

## Status: IMPROVEMENT

Starting the Demo is easy, but stopping background services is not equally obvious.

At minimum, document safe shutdown.

A dedicated:

```text
stop_commplan.py
停止服务.cmd
```

may be added if implemented safely.

If added:

- verify PID/process identity
- do not kill unrelated Python processes
- do not kill a pre-existing external model service that was merely reused

This is product UX, not an architecture rewrite.

---

# 24. Filename/ZIP Interoperability

## Status: EXTERNAL/ROBUSTNESS CHECK

The Chinese launcher name is valid, but cross-platform extraction tools may render it inconsistently.

Before release test:

```text
final ZIP
→ intended Windows extraction tool
→ launcher filename and README links remain valid
```

An ASCII alias such as:

```text
start.cmd
```

is a reasonable robustness improvement.

---

# 25. Public Docs Must Be Portable

## Status: CONFIRMED

`planning/README.md` contains development-machine paths such as:

```text
E:\codex\项目\...
```

Replace normal user-facing instructions with portable commands/paths.

Historical internal docs may retain historical paths if clearly archival.

---

# 26. THIRD_PARTY.md Is Inconsistent

## Status: CONFIRMED

`THIRD_PARTY.md` currently references evidence paths such as:

```text
runtime/assets_manifest.json
runtime/licenses/python/
runtime/licenses/llama.cpp.LICENSE
```

but these paths are not present in the supplied current workspace.

KaTeX license/manifest assets do exist.

## Required

Make third-party documentation match what the formal release actually redistributes.

If the release does not redistribute:

- model weights
- llama.cpp binaries
- Python packages

say so clearly and point to upstream license/source information as appropriate.

Do not document nonexistent evidence paths.

---

# 27. Product Entry Point Must Be Clear

## Status: IMPROVEMENT

Repository contains both:

### Older Formula RAG entry

```text
app.py
launch.py
web/
```

### Current Planning Workbench

```text
planning/
start_commplan.py
planning/web/
```

No directory move is required.

Formal Demo docs/release should state clearly:

```text
PRIMARY DEMO:
CommPlan-Agent Planning Workbench

FOUNDATION / LEGACY:
Formula RAG components and older app entry
```

---

# 28. Documentation/Test Baseline Drift

## Status: CONFIRMED

Current docs contain multiple historical counts, including examples such as:

```text
177
189
198
207 Python tests

7
8
10
12 Node tests
```

Current supplied JS suite produced:

```text
16 / 16 PASS
```

Current source contains 217 Python `test_*` functions, but this audit does not claim 217 PASS.

## Final README must have one authoritative block

After final Windows candidate validation:

```text
Validated release:
commit: <sha>
Python: <actual command/result>
Node: <actual command/result>
Target Chrome: PASS / BLOCKED
Independent review: PASS / BLOCKED
Release smoke test: PASS / BLOCKED
```

Historical totals must be clearly archival.

---

# 29. Real Chrome Validation

## Status: EXTERNAL_GATE

Final release candidate must be tested in intended Chrome.

Minimum flows:

```text
complete FSPL
missing parameter
conflict resolution
interval/candidate domain
edit after completion
refresh/recovery
model unavailable fallback
```

Also verify:

- duplicate-submit protection
- stale late response does not overwrite a newer revision
- architecture/status/result remain coherent
- no console errors indicating broken behavior

If unavailable:

```text
BLOCKED_EXTERNAL_CHROME_VALIDATION
```

Do not substitute Node tests and call this PASS.

---

# 30. Independent Final Code Review

## Status: EXTERNAL_GATE

The current audit serves as a deep pre-change review.

After Codex changes the project, the final diff still needs a separate independent review.

Do not confuse this with:

- runtime Review Agent
- the coding agent reviewing itself
- unit tests

Review focus:

- local-vs-remote preservation
- state/revision/checkpoint behavior
- runtime activity semantics
- build fingerprint
- startup/shutdown
- release leakage
- docs/runtime consistency
- security boundary regressions
- missing tests

If unavailable:

```text
BLOCKED_EXTERNAL_REVIEW
```

Do not falsely report PASS.

---

# 31. Server Error Diagnostics

## Status: IMPROVEMENT

Unknown backend exception logging is minimal.

If practical, improve server-side diagnostics to include:

```text
trace_id
task_id
event_id
timestamp
exception type
stack trace
```

Browser should receive safe error text, optionally with trace ID.

Do not return raw stack traces.

Do not turn logging into a large subsystem rewrite.

---

# 32. Deferred Items

Do not block this release on:

```text
SSE replacing polling
Playwright
DB migration framework
task delete/search/title lifecycle
retention/VACUUM
signed evidence bundles
vector/dense Planning retrieval
new propagation models
full link budget
runtime Skills framework
LoRA
autonomous unrestricted orchestration
```

---

# 33. Final Implementation Order

Follow this order.

## Stage 0 — Preserve Current Candidate

1. back up local source/untracked intended files
2. inspect Git/worktree
3. fetch remote without resetting
4. reconcile local vs current `main`
5. run full current Windows regression
6. commit preserved local candidate
7. push dedicated branch

**No UI redesign before this checkpoint.**

---

## Stage 1 — Correctness and Truth

1. validate/commit the existing unitless-distance candidate fix
2. fix runtime caller/edge truthfulness
3. fix build fingerprint to include runtime-critical knowledge/config
4. add targeted regressions
5. update stale status docs

Then:

```text
full regression
→ commit
→ push
```

---

## Stage 2 — Demo Productization

1. make task/current need/result the primary hierarchy
2. keep overall architecture single-view as secondary technical detail
3. do not restore historical dual-view UI
4. move advanced controls away from normal path
5. hide/disable unsupported targets
6. productize current examples and add/clarify conflict example
7. use sensible human-facing result precision
8. improve small-text readability
9. de-emphasize raw task-ID recovery

Then:

```text
full regression
→ manual smoke
→ commit
→ push
```

---

## Stage 3 — Delivery Engineering

1. reconcile README with `setup_planning.cmd` + `requirements-planning.txt`
2. add minimal Planning install/smoke validation
3. commit/activate CI
4. create Planning-specific release builder/validator
5. generate clean release
6. add version/build metadata
7. clean portable user docs
8. correct `THIRD_PARTY.md`
9. clarify primary Planning entry
10. refine setup/start lifecycle
11. optionally add safe stop entry / ASCII launcher alias

Then:

```text
full regression
→ build release
→ unpack release
→ deterministic smoke
→ commit
→ push
```

---

## Stage 4 — Final Candidate Validation

Run on the actual release candidate:

```text
full Windows Python regression
Node regression
pip check
minimal clean setup
target Chrome flows
model-online flow
model-offline/fallback flow
refresh/history/revision behavior
release unzip/start smoke
independent final diff review
```

Generate one authoritative validation record.

No feature work after this stage begins unless required to fix a failed gate.

Any fix restarts affected validation.

Then:

```text
final commit
→ push
```

---

## Stage 5 — GitHub Formal Release

1. PR from Demo-delivery branch
2. confirm remote CI actually passes if enabled
3. merge to `main`
4. rebuild release **from accepted main**
5. unpack and smoke-test that main-derived package
6. tag:
   ```text
   v0.1.0
   ```
   or:
   ```text
   v0.1.0-demo
   ```
7. publish only the clean user-facing release artifact

---

# 34. GitHub Upload Timing

Do not wait until all work is done before first push.

Do not push every trivial CSS edit.

Meaningful checkpoints:

```text
Checkpoint 1:
preserved/reconciled local candidate

Checkpoint 2:
correctness/truth fixes

Checkpoint 3:
Demo productization

Checkpoint 4:
delivery engineering

Checkpoint 5:
final validated candidate
```

Only after final validation:

```text
PR
→ main
→ main-derived release
→ tag
```

If network/credentials are unavailable:

- keep clean local commits
- record branch
- record SHA
- provide exact push command
- mark remote action blocked

Never claim a push or CI pass that did not happen.

---

# 35. Regression Protection Matrix

The following must survive productization:

| Capability | Required |
|---|---|
| Natural-language extraction | YES |
| Manual parameter input | YES |
| Missing-parameter clarification | YES |
| Multi-question / partial-answer preservation | YES |
| Interval values | YES |
| Discrete candidates | YES |
| Text/manual conflict detection | YES |
| Explicit user target/model-condition context | YES |
| Human confirmation snapshot | YES |
| Revision behavior | YES |
| Edit invalidates old result | YES |
| stale revision protection | YES |
| idempotent command behavior | YES |
| cancellation rollback behavior | YES |
| task history recovery | YES |
| refresh/restart recovery | YES |
| model service health | YES |
| task model-use/fallback distinction | YES |
| deterministic numerical authority | YES |
| formula/evidence/result provenance | YES |
| hard result validation | YES |
| free-space scope boundary | YES |
| independent magnitude/physics check | YES |

Any regression blocks release.

---

# 36. Final Definition of Done

The current FSPL-stage Demo is releasable only when all applicable items pass.

## Source integrity

- [ ] valid local candidate preserved before reconciliation
- [ ] intended local-only source/tests committed
- [ ] GitHub branch reflects accepted candidate
- [ ] no valid local work discarded

## Correctness

- [ ] unitless-distance behavior validated by full regression
- [ ] runtime caller/edge semantics truthful
- [ ] build fingerprint changes when runtime-critical knowledge changes
- [ ] deterministic raw calculation preserved
- [ ] state/revision/checkpoint protections preserved

## UX

- [ ] task/result hierarchy is primary
- [ ] architecture is secondary technical detail
- [ ] historical dual-view UI not resurrected
- [ ] unsupported goals do not look supported
- [ ] advanced controls do not dominate
- [ ] result precision is sensible
- [ ] typography is readable
- [ ] example/boundary behavior is clear

## Environment/startup

- [ ] README and setup scripts tell one consistent minimal Planning environment story
- [ ] fresh Windows Planning setup passes
- [ ] deterministic mode works without model assets
- [ ] normal startup is clear
- [ ] lifecycle/stop behavior documented or safely implemented

## Release

- [ ] Planning-specific release builder exists
- [ ] package excludes dev venv/DB/logs/worktree metadata
- [ ] build metadata exists
- [ ] public docs do not require developer-machine paths
- [ ] third-party notice matches actual distributed assets
- [ ] primary product entry is unambiguous
- [ ] final ZIP tested after extraction on intended Windows tooling

## Validation

- [ ] full Python regression PASS
- [ ] Node regression PASS
- [ ] pip check PASS
- [ ] minimal Planning clean install/smoke PASS
- [ ] target Chrome PASS
- [ ] failure-path checks PASS
- [ ] independent final review PASS
- [ ] unpacked release smoke PASS
- [ ] one authoritative validation record exists

## GitHub

- [ ] validated branch pushed
- [ ] remote CI PASS if configured
- [ ] PR reviewed
- [ ] merged to `main`
- [ ] release rebuilt from accepted `main`
- [ ] final smoke PASS
- [ ] tag created

Only then may Codex report:

```text
CommPlan-Agent Demo Release Ready
```

---

# 37. Do Not Do These Things

Codex must not:

1. reset the valid local candidate to GitHub main
2. rebuild the graph to make the architecture look more Agent-like
3. turn bounded orchestration into unrestricted LLM routing
4. replace deterministic professional calculation with LLM-generated numbers
5. collapse backend states for UI convenience
6. bypass confirmation snapshot
7. remove revision/checkpoint/provenance protection
8. restore the superseded historical dual-view UI
9. add a new RAG framework merely for appearance
10. add LoRA
11. add H1 link-budget features before current release gates pass
12. claim minimal clean install passed without testing it
13. claim Chrome passed using Node tests
14. claim independent review passed using runtime Review Agent
15. claim GitHub CI passed when no workflow run exists
16. ship the development worktree ZIP as the formal release

---

# 38. After This Release — H1

Only after formal release should the project expand to:

```text
FSPL
→ Received Power
→ Receiver Threshold / Thermal Noise
→ Link Margin
→ Link-level summary
```

H1 should begin with:

1. capability contracts
2. deterministic numerical reference cases
3. dependency-aware planning
4. tool composition
5. independent validation
6. then Agent/UI expansion

At that point Calculation Agent and orchestration can gain genuine planning value without fabricating autonomy in the current FSPL-only Demo.

---

# 39. Final Operating Principle

When choosing between:

```text
adding more framework
```

and:

```text
making the existing system more truthful, stable, understandable, reproducible and deliverable
```

choose the second.

The current project already has enough architecture.

This release task is to turn the existing candidate into a trustworthy Demo product.
