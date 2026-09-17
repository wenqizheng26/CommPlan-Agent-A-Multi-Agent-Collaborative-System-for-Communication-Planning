"""Read-only validation of Codex control documents; not a business test."""
from __future__ import annotations

import fnmatch
import json
from pathlib import Path
import re
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "codex"
errors: list[str] = []
warnings: list[str] = []

def check(ok: bool, message: str) -> None:
    if not ok:
        errors.append(message)

data = yaml.safe_load((DOCS / "TASK_BACKLOG.yaml").read_text(encoding="utf-8-sig"))
tasks = data["tasks"]
required = {
    "task_id", "title", "phase", "wbs_refs", "objective", "status",
    "dependencies", "owner_type", "inputs", "outputs", "allowed_files",
    "forbidden_files", "acceptance_criteria", "test_commands",
    "review_required", "human_gate_required", "risk_level", "retry_budget",
}
ids = [t["task_id"] for t in tasks]
check(len(ids) == len(set(ids)), "duplicate task IDs")
by_id = {t["task_id"]: t for t in tasks}
for task in tasks:
    tid = task["task_id"]
    check(required <= task.keys(), f"{tid}: missing fields {required - task.keys()}")
    for field in ("objective", "inputs", "outputs", "allowed_files", "acceptance_criteria", "test_commands"):
        check(bool(task.get(field)), f"{tid}: empty {field}")
    check(all(d in by_id for d in task["dependencies"]), f"{tid}: unknown dependency")
    check(tid not in task["dependencies"], f"{tid}: self dependency")
    check(task["retry_budget"] >= 0, f"{tid}: negative retry budget")
    for file in task["allowed_files"]:
        check(not any(fnmatch.fnmatchcase(file, deny) for deny in task["forbidden_files"]),
              f"{tid}: allowed and forbidden overlap: {file}")
        check(not file.startswith(("/", "..")) and ":" not in file, f"{tid}: non-repo allowed path: {file}")
    for file in task["outputs"]:
        check(file in task["allowed_files"], f"{tid}: output not allowed: {file}")

visiting, visited = set(), set()
def walk(tid: str) -> None:
    if tid in visiting:
        errors.append(f"dependency cycle at {tid}")
        return
    if tid in visited:
        return
    visiting.add(tid)
    for dep in by_id[tid]["dependencies"]:
        if dep in by_id:
            walk(dep)
    visiting.remove(tid)
    visited.add(tid)
for tid in ids:
    walk(tid)

wbs = json.loads((DOCS / "evidence" / "wbs_rows.json").read_text(encoding="utf-8-sig"))
source_ids = {r["id"] for r in wbs["rows"] if "id" in r}
impl = [t for t in tasks if re.fullmatch(r"T[0-9]{3}", t["task_id"])]
covered = {w for t in impl for w in t["wbs_refs"]}
check(len(source_ids) == 38, f"expected 38 WBS items, got {len(source_ids)}")
check(source_ids <= covered, f"unmapped WBS: {sorted(source_ids - covered)}")
check(covered <= source_ids, f"invented WBS: {sorted(covered - source_ids)}")
check(data["max_active_subagents"] <= 3, "more than 3 active subagents")
if not data["human_gate_0_approved"]:
    check(data["contract_status"] == "DRAFT", "H0 unapproved but contract frozen")
    for task in impl:
        check(task["status"] == "BLOCKED_HUMAN_GATE_0", f"{task['task_id']}: runnable before H0")

for task in impl:
    prefreeze = task["task_id"] in {"T001", "T002", "T003"}
    check(task.get("requires_frozen_contract") is (not prefreeze),
          f"{task['task_id']}: invalid contract-freeze prerequisite")
check({"REV-01", "REV-02"} <= set(by_id["H0"]["dependencies"]),
      "H0 must depend on both independent reviews")

def ancestors(tid: str, trail=None):
    trail = set() if trail is None else trail
    for dep in by_id[tid]["dependencies"]:
        if dep not in trail:
            trail.add(dep)
            ancestors(dep, trail)
    return trail

# Concurrently eligible tasks with a common file must share a scheduling lock.
if not errors:
    for i, left in enumerate(impl):
        for right in impl[i + 1:]:
            if left["task_id"] in ancestors(right["task_id"]) or right["task_id"] in ancestors(left["task_id"]):
                continue
            overlap = set(left["allowed_files"]) & set(right["allowed_files"])
            if overlap:
                check(bool(set(left["locks"]) & set(right["locks"])),
                      f"unlocked ownership overlap: {left['task_id']} / {right['task_id']}: {sorted(overlap)}")

required_docs = [
    "PROJECT_CONTEXT.md", "AUDIT_REPORT.md", "MASTER_IMPLEMENTATION_PLAN.md",
    "ARCHITECTURE_DECISIONS.md", "CONTRACTS.md", "WBS_STATUS.md",
    "WBS_TASK_MAPPING.md", "TASK_BACKLOG.yaml", "AGENT_ASSIGNMENTS.md",
    "IMPLEMENTATION_LOG.md", "TEST_BASELINE.md", "RISK_REGISTER.md", "NEXT_ACTION.md",
    "REPOSITORY_BASELINE.md", "RAG_CALCULATION_AUDIT.md", "WORKFLOW_GAP_ANALYSIS.md",
    "REVIEW_REPORT.md", "CONTRACT_PLAN_REVIEW.md", "GITHUB_PUBLICATION.md",
]
for name in required_docs:
    check((DOCS / name).is_file(), f"missing required document: {name}")
    check(any("docs/codex/" + name in t["allowed_files"] for t in tasks if t["phase"] == "P0"),
          f"no P0 owner for {name}")
for name in ("REVIEW_REPORT.md", "GITHUB_PUBLICATION.md"):
    if not (DOCS / name).exists():
        warnings.append(f"pending independent artifact: {name}")
for file in DOCS.glob("*.md"):
    text = file.read_text(encoding="utf-8-sig")
    check("\ufffd" not in text, f"replacement character in {file.name}")
    # Strict task tokens, not version IDs or prose numbers.
    for tid in re.findall(r"\bT[0-9]{3}\b", text):
        check(tid in by_id, f"{file.name}: unknown task reference {tid}")

# Tests named in planned commands must be delivered by some task or already exist.
planned_outputs = {p for t in tasks for p in t["outputs"]}
for task in impl:
    for command in task["test_commands"]:
        match = re.search(r"-p (test_[a-z0-9_]+\.py)", command)
        if match:
            path = "tests/" + match.group(1)
            check(path in planned_outputs or (ROOT / path).exists(),
                  f"{task['task_id']}: undefined future test {path}")

result = {
    "status": "PASS" if not errors else "FAIL",
    "tasks": len(tasks), "implementation_tasks": len(impl),
    "wbs_items": len(source_ids), "wbs_coverage": len(source_ids & covered),
    "dependency_dag": "acyclic" if len(visited) == len(tasks) and not any("cycle" in e for e in errors) else "invalid",
    "human_gate_0_approved": data["human_gate_0_approved"],
    "errors": errors, "warnings": warnings,
    "scope": "control document structure only; not business implementation or scientific validation",
}
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(1 if errors else 0)
