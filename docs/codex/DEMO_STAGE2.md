# Demo delivery — Stage 2 (2026-09-22)

Completed: task-first two-column workbench; five-step display-only progress; one collapsed architecture view; advanced model controls and UUID recovery collapsed; recent tasks preserved; unsupported business targets disabled in form and clarification choices; complete/missing/conflict/interval/candidate examples populate without submission; output display rounded to two decimals without changing raw values/tolerances; larger typography; role records folded below result meaning.

Validation:
- Full Windows `.venv/Scripts/python.exe -B -X utf8 -m unittest discover -s tests -p "test_*.py"`: 224 PASS, 82.455 s.
- `node --test tests/planning_*.test.mjs`: 24 PASS.
- `python -m pip check`: no broken requirements; `git diff --check` PASS.
- An earlier full run failed because the new progress.mjs was not yet written when static-serving regression ran; after file completion the entire suite above was rerun successfully.
- Manual Codex in-app browser smoke at port 18083, separate outputs/demo-stage2.sqlite: full 2 GHz/1 km confirmation -> 98.42 dB; refresh preserved result; edit to 3 GHz cleared confirmation/result and reset progress; missing distance answered; manual/text conflict 2/3 GHz resolved -> 98.42; interval -> 97.98–98.84; candidates -> separate 98.42 and 101.94. Busy inputs/buttons visibly disabled. Captured browser error/warning list empty after completed flows.
- This is in-app browser evidence, not target Chrome PASS. User requested in-app automation and will manually confirm Chrome. Final candidate gates must be repeated on final package.

Files: planning web layout/controls/progress/details, domain_calculation conclusion formatting, precision/progress/static HTTP tests, README example precision.

Git: codex/demo-delivery-final; OAuth workflow-scope blocker persists as of Stage 1 push retry. No remote CI PASS claimed.

Reviewer focus: published progress requires saved COMPLETED + final_report; old revision and rolled-back activity never make a new result green; confirmation and explicit selection semantics preserved; only human-facing precision changed.
