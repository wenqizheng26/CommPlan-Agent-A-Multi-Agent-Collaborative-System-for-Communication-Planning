"""Run an unpacked, deterministic HTTP create/confirm/recovery smoke test."""

import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
import uuid


OPENER = build_opener(ProxyHandler({}))


def request(base, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Planning-Token"] = token
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = Request(base + path, data=data, headers=headers)
    with OPENER.open(req, timeout=15) as response:
        return json.load(response)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start(root, db, port):
    process = subprocess.Popen(
        [sys.executable, "-B", "-X", "utf8", "-m", "planning.web_server",
         "--root", str(root), "--db", str(db), "--port", str(port)],
        cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            error = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"workbench exited during smoke startup: {error[-2500:]}")
        try:
            session = request(base, "/api/session")
            if session.get("profile") == "confirmed-fspl-loop-v1":
                return process, base, session
        except (OSError, ValueError, URLError, HTTPError):
            time.sleep(0.25)
    stop(process)
    raise RuntimeError("workbench did not become ready within 45 seconds")


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=8)
    if process.stderr:
        process.stderr.close()


def command(action, state=None):
    result = {
        "action": action,
        "task_id": state["task_id"] if state else str(uuid.uuid4()),
        "event_id": str(uuid.uuid4()),
        "expected_revision": state["revision"] if state else 0,
        "expected_state_version": state["state_version"] if state else 0,
    }
    if action == "create":
        result.update(input={
            "raw_text": "按自由空间基准计算，频率2GHz，距离1km，求路径损耗。",
            "manual_parameters": {}, "condition": None, "target": None,
        }, mode="deterministic")
    elif action == "confirm":
        result["review_hash"] = state["review"]["review_hash"]
    return result


def smoke(root):
    root = Path(root).resolve()
    sys.path.insert(0, str(root))
    with tempfile.TemporaryDirectory(prefix="commplan-smoke-") as temporary:
        db = Path(temporary) / "tasks.sqlite"
        port = free_port()
        process, base, session = start(root, db, port)
        try:
            from planning.build_info import build_fingerprint
            if session.get("build") != build_fingerprint(root):
                raise RuntimeError("running workbench fingerprint mismatch")
            token = session["token"]
            draft = request(base, "/api/commands", command("create"), token)["state"]
            if draft["status"] == "COMPLETED" or draft.get("confirmed_snapshot") is not None:
                raise RuntimeError("create bypassed confirmation")
            completed = request(base, "/api/commands", command("confirm", draft), token)["state"]
            if completed["status"] != "COMPLETED" or not completed.get("final_report"):
                raise RuntimeError("confirm did not produce a final report")
            task_id = completed["task_id"]
            if request(base, f"/api/tasks/{task_id}")["state"] != completed:
                raise RuntimeError("HTTP task readback mismatch")
        finally:
            stop(process)
        process, base, _ = start(root, db, port)
        try:
            recovered = request(base, f"/api/tasks/{task_id}")["state"]
            history = request(base, f"/api/tasks/{task_id}/history")["history"]
            if recovered != completed or len(history) < 2:
                raise RuntimeError("restart/recovery mismatch")
        finally:
            stop(process)
    return {"status": "PASS", "task_id": task_id, "http_create": True,
            "http_confirm": True, "restart_recovery": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    print(json.dumps(smoke(args.root), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
