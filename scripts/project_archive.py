"""Plan/capture/verify a Windows FILE_PAYLOAD; restore and Git recovery are later batches."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import sys
import uuid
import zipfile

from archive_common import (ALGORITHMS, ArchiveError, CHUNK_SIZE, HEX64, SCHEMA, compression,
                            json_bytes, member_table, observe, open_source, plain_absolute,
                            publish, read_json, safe_member, sha256_file, within, write_exclusive)

ROOT_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
FIXED_FILES = {"PLAN.json", "WINDOW.json", "ARCHIVE_INFO.json", "files.jsonl", "links.jsonl",
               "dependencies.json", "events.jsonl", "payload.zip"}
LATER = {"original_restore_integrity": "NOT_RUN", "hardlink_topology_recovery": "NOT_RUN",
         "acl_restoration": "RECORD_ONLY", "git_history_recovery": "NOT_RUN",
         "dependency_recovery": "NOT_RUN", "retained_version_independence": "NOT_RUN"}


def utc():
    return datetime.now(timezone.utc).isoformat()


def _entry_id(root_id, relative):
    return hashlib.sha256((root_id + "\0" + relative).encode("utf-8")).hexdigest()


def roots_for(project, dependencies):
    rows = [{"root_id": "project", "path": str(plain_absolute(project)), "prefix": "project"}]
    if not isinstance(dependencies, list):
        raise ArchiveError("dependencies must be an exact list of external roots")
    for item in dependencies:
        if (not isinstance(item, dict) or not ROOT_ID.fullmatch(str(item.get("dependency_id", "")))
                or item["dependency_id"] == "project"):
            raise ArchiveError("invalid dependency ID")
        rows.append({"root_id": item["dependency_id"], "path": str(plain_absolute(item["path"])),
                     "prefix": "dependencies/" + item["dependency_id"]})
    if len({r["root_id"] for r in rows}) != len(rows):
        raise ArchiveError("duplicate root ID")
    for index, row in enumerate(rows):
        root = Path(row["path"])
        row["kind"] = "directory" if root.is_dir() else "regular_file"
        for other in rows[:index]:
            if within(root, other["path"]) or within(other["path"], root):
                raise ArchiveError("overlapping capture roots; internal targets are already captured")
    if rows[0]["kind"] != "directory":
        raise ArchiveError("project root must be a directory")
    return rows


def _source(row, roots):
    root = next(root for root in roots if root["root_id"] == row["root_id"])
    return Path(root["path"]) / row["relative_path"] if row["relative_path"] else Path(root["path"])


def _member(root, relative, kind):
    name = root["prefix"]
    if relative:
        name += "/" + relative
    elif root["kind"] == "regular_file":
        name += "/" + Path(root["path"]).name
    if kind == "directory":
        name += "/"
    safe_member(name, kind == "directory")
    return name


def snapshot(roots):
    """All paths are included; do not run Git or follow reparse directories."""
    entries, links = [], []
    for root in roots:
        base = plain_absolute(root["path"])
        pending = [(base, "")]
        while pending:
            path, relative = pending.pop()
            plain_absolute(path.parent)
            observation = observe(path)
            kind = observation["kind"]
            identifier = _entry_id(root["root_id"], relative)
            member = _member(root, relative, kind)
            streams = []
            for stream in observation["streams"]:
                item = dict(stream)
                item["stream_id"] = hashlib.sha256((identifier + stream["name"]).encode("utf-8")).hexdigest()
                item["archive_member"] = member if stream["is_default"] else "streams/" + item["stream_id"] + ".bin"
                item["compress_type"] = compression(item["archive_member"], item["size"])
                streams.append(item)
            row = {"entry_id": identifier, "root_id": root["root_id"], "relative_path": relative,
                   "archive_member": None if kind == "link_record" else member, "kind": kind,
                   "observation": observation, "streams": streams,
                   "git_classification": "NOT_RUN_RAW_FILE_PAYLOAD"}
            entries.append(row)
            if kind == "directory":
                with os.scandir(path) as children:
                    names = sorted(child.name for child in children)
                for name in reversed(names):
                    pending.append((path / name, relative + "/" + name if relative else name))
            elif kind == "link_record":
                try:
                    target = path.resolve(strict=True)
                except (OSError, RuntimeError) as error:
                    raise ArchiveError("GAP: unresolved link target: " + str(path)) from error
                matching = [candidate for candidate in roots if within(target, candidate["path"])]
                if len(matching) != 1:
                    raise ArchiveError("GAP: link target is not in an exact capture root: " + str(path))
                target_root = matching[0]
                target_relative = str(target.relative_to(target_root["path"])).replace("\\", "/")
                if target_relative == ".":
                    target_relative = ""
                links.append({"entry_id": identifier, "root_id": root["root_id"], "relative_path": relative,
                              "reparse_type": observation["reparse_type"], "reparse_tag": observation["reparse_tag"],
                              "target_text": observation["target_text"], "resolved_target": str(target),
                              "relation": "internal" if target_root["root_id"] == root["root_id"] else "registered_external",
                              "target_resource_id": target_root["root_id"],
                              "target_entry_id": _entry_id(target_root["root_id"], target_relative),
                              "target_captured": True, "recovery": "NOT_RUN",
                              "body_streams": "NOT_RUN_NOFOLLOW"})
    entries.sort(key=lambda row: (row["root_id"], row["relative_path"]))
    links.sort(key=lambda row: row["entry_id"])
    by_id = {row["entry_id"]: row for row in entries}
    for link in links:
        if link["target_entry_id"] not in by_id or by_id[link["target_entry_id"]]["kind"] == "link_record":
            raise ArchiveError("GAP: resolved link target has no captured ordinary entry")
    members = []
    for row in entries:
        if row["kind"] == "directory":
            members.append((row["archive_member"], True))
        members.extend((stream["archive_member"], False) for stream in row["streams"])
    member_table(members)
    grouped = {}
    for row in entries:
        if row["kind"] == "regular_file":
            identity = row["observation"]["file_identity"]
            key = (identity["volume_serial"], identity["file_id"])
            grouped.setdefault(key, []).append(row)
    hardlinks = []
    for key, rows in sorted(grouped.items()):
        counts = {row["observation"]["file_identity"]["link_count"] for row in rows}
        if len(counts) != 1 or next(iter(counts)) < len(rows):
            raise ArchiveError("hardlink count changed or identity duplicated across roots")
        count = next(iter(counts))
        if count > 1:
            identifier = f"v{key[0]:x}-f{key[1]:x}"
            hardlinks.append({"hardlink_group_id": identifier, "volume_serial": key[0], "file_id": key[1],
                              "link_count": count, "captured_entry_ids": [r["entry_id"] for r in rows],
                              "in_scope_alias_count": len(rows), "outside_scope_aliases": count - len(rows),
                              "outside_scope_resolution": "NOT_RUN", "recovery": "NOT_RUN"})
            for row in rows:
                row["hardlink_group_id"] = identifier
    return {"entries": entries, "links": links, "hardlinks": hardlinks,
            "total_stream_bytes": sum(s["size"] for row in entries for s in row["streams"]),
            "member_count": len(members)}


def _outside(path, roots):
    path = plain_absolute(path, must_exist=False)
    for root in roots:
        if within(path, root["path"]) or within(root["path"], path):
            raise ArchiveError("output overlaps a capture root: " + str(path))
    return path


def plan(project, dependencies, output):
    roots = roots_for(project, dependencies)
    output = _outside(output, roots)
    if output.exists():
        raise ArchiveError("plan output already exists")
    observed = snapshot(roots)
    value = {"schema": SCHEMA, "scope": "FILE_PAYLOAD", "created_utc": utc(), "roots": roots,
             "snapshot": observed, "compression": "STORED for compressed/large files, otherwise DEFLATED",
             "capacity": {"payload_bytes": observed["total_stream_bytes"],
                          "required_free_bytes": observed["total_stream_bytes"] * 2 + 16 * 1024 * 1024},
             "limitations": ["SACL not read; owner/group/DACL recorded only",
                             "Link-body streams/security not followed; target data recorded separately",
                             "Git classification/history, original restore and usable dependency recovery not run"]}
    write_exclusive(output, json_bytes(value))
    return value


def _check_plan(value):
    if not isinstance(value, dict) or value.get("schema") != SCHEMA or value.get("scope") != "FILE_PAYLOAD":
        raise ArchiveError("unsupported plan schema/scope")
    roots = value.get("roots")
    if not isinstance(roots, list) or not roots or roots[0].get("root_id") != "project":
        raise ArchiveError("invalid plan roots")
    verified = roots_for(roots[0]["path"], [{"dependency_id": r["root_id"], "path": r["path"]} for r in roots[1:]])
    if roots != verified:
        raise ArchiveError("invalid root kind/prefix contract")
    return roots


def _window(value, roots):
    if (not isinstance(value, dict) or value.get("scope") != "FILE_PAYLOAD"
            or not isinstance(value.get("window_id"), str) or not value["window_id"]
            or value.get("source_writers_stopped") is not True
            or value.get("approved_root_paths") != [r["path"] for r in roots]):
        raise ArchiveError("missing current stopped-writer window or exact approved roots")


def _without_hashes(observation):
    result = copy.deepcopy(observation)
    for stream in result["streams"]:
        stream.pop("sha256", None)
    return result


def _write_payload(path, roots, observed, hook):
    captured = []
    with zipfile.ZipFile(path, "x", allowZip64=True) as archive:
        for row in observed["entries"]:
            if hook:
                hook("before_entry", row)
            source = _source(row, roots)
            actual = observe(source, hashes=False)
            if actual != _without_hashes(row["observation"]):
                raise ArchiveError("source metadata/stream set changed before capture: " + str(source))
            item = copy.deepcopy(row)
            item["before"] = copy.deepcopy(row["observation"])
            item["captured"] = copy.deepcopy(actual)
            item["metadata_status"] = {"content": "CAPTURED", "streams": "CAPTURED",
                                       "basic_attributes_times": "RECORDED", "owner_group_dacl": "RECORD_ONLY",
                                       "sacl": "NOT_READ", "restoration": "NOT_RUN"}
            if row["kind"] == "directory":
                info = zipfile.ZipInfo(row["archive_member"])
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = (stat.S_IFDIR | 0o700) << 16 | 0x10
                archive.writestr(info, b"")
            for index, stream in enumerate(item["streams"]):
                digest, count = hashlib.sha256(), 0
                info = zipfile.ZipInfo(stream["archive_member"])
                info.compress_type = stream["compress_type"]
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                info.file_size = stream["size"]
                with open_source(source, stream["name"]) as reader, archive.open(info, "w", force_zip64=True) as writer:
                    while block := reader.read(CHUNK_SIZE):
                        count += len(block)
                        if count > stream["size"]:
                            raise ArchiveError("source stream exceeds planned size: " + str(source))
                        digest.update(block)
                        writer.write(block)
                        if hook:
                            hook("stream_block", row)
                if count != stream["size"] or digest.hexdigest() != stream["sha256"]:
                    raise ArchiveError("source stream bytes changed during capture: " + str(source))
                stream["zip_crc32"] = archive.getinfo(stream["archive_member"]).CRC
                item["captured"]["streams"][index]["sha256"] = digest.hexdigest()
            if row["kind"] == "link_record":
                item["metadata_status"]["content"] = "LINK_RECORD_ONLY"
                item["metadata_status"]["streams"] = "NOT_RUN_NOFOLLOW"
                item["metadata_status"]["owner_group_dacl"] = "NOT_READ_NOFOLLOW"
            captured.append(item)
    return captured


def _jsonl(path, rows):
    write_exclusive(path, b"".join((json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8") for row in rows))


def _read_jsonl(path):
    rows = []
    # The same strict decoder applies to each line without accepting duplicate keys.
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line:
            raise ArchiveError("empty JSONL record")
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ArchiveError("duplicate JSONL key")
                result[key] = value
            return result
        def invalid(value):
            raise ArchiveError("non-finite JSONL number: " + value)
        rows.append(json.loads(line, object_pairs_hook=pairs, parse_constant=invalid))
    return rows


def capture(plan_path, window_path, output, *, hook=None):
    value = read_json(plan_path)
    roots = _check_plan(value)
    window = read_json(window_path)
    _window(window, roots)
    output = _outside(output, roots)
    if output.exists():
        raise ArchiveError("archive output already exists")
    output.mkdir()
    stage, started = "before", utc()
    initial = {"schema": SCHEMA, "scope": "FILE_PAYLOAD", "status": "INCOMPLETE", "started_utc": started}
    write_exclusive(output / "ARCHIVE_INFO.json.part", json_bytes(initial))
    try:
        before = snapshot(roots)
        if before != value["snapshot"]:
            raise ArchiveError("source differs from the reviewed plan")
        needed = before["total_stream_bytes"] * 2 + 16 * 1024 * 1024
        if shutil.disk_usage(output).free < needed:
            raise ArchiveError("insufficient free capacity for planned streams and manifests")
        write_exclusive(output / "PLAN.json", json_bytes(value))
        write_exclusive(output / "WINDOW.json", json_bytes(window))
        stage = "capture"
        captured = _write_payload(output / "payload.zip.part", roots, before, hook)
        if hook:
            hook("before_after_scan", None)
        stage = "after"
        after = snapshot(roots)
        if before != after:
            write_exclusive(output / "SOURCE_DIFFERENCE.json", json_bytes({"before": before, "after": after}))
            raise ArchiveError("source changed between before/captured/after")
        after_by_id = {row["entry_id"]: row for row in after["entries"]}
        for row in captured:
            row["after"] = after_by_id[row["entry_id"]]["observation"]
            if row["before"] != row["captured"] or row["before"] != row["after"]:
                raise ArchiveError("unstable captured entry: " + row["entry_id"])
        stage = "verify_payload"
        _verify_payload(output / "payload.zip.part", captured, before)
        if hook:
            hook("before_publish", None)
        publish(output / "payload.zip.part", output / "payload.zip")
        _jsonl(output / "files.jsonl", captured)
        _jsonl(output / "links.jsonl", before["links"])
        write_exclusive(output / "dependencies.json", json_bytes({"roots": roots, "hardlinks": before["hardlinks"],
                                                                   "dependency_recovery": "NOT_RUN"}))
        _jsonl(output / "events.jsonl", [{"time": started, "stage": "begin", "window_id": window["window_id"]},
                                         {"time": utc(), "stage": "source_and_payload_verified"}])
        tool_files = [Path(__file__), Path(__file__).with_name("archive_common.py")]
        final = dict(initial, status="FILE_PAYLOAD_COMPLETE", ended_utc=utc(), batch_id=uuid.uuid4().hex,
                     plan_sha256=sha256_file(output / "PLAN.json")[1], window_id=window["window_id"], roots=roots,
                     counts={"entries": len(captured), "members": before["member_count"],
                             "stream_bytes": before["total_stream_bytes"]},
                     compression=value["compression"], python=platform.python_version(), os=platform.platform(),
                     tool_source_commit="NOT_QUERIED", tool_files={p.name: sha256_file(p)[1] for p in tool_files},
                     file_payload_integrity="PASS", streams_integrity="PASS", relations_recorded="PASS",
                     raw_metadata_recorded="RECORD_ONLY", limitations=value["limitations"], **LATER)
        write_exclusive(output / "ARCHIVE_INFO.json", json_bytes(final))
        checksums = {"schema": SCHEMA, "files": {name: dict(zip(("size", "sha256"), sha256_file(output / name)))
                                                   for name in sorted(FIXED_FILES)}}
        write_exclusive(output / "CHECKSUMS.json", json_bytes(checksums))
        checksum_hash = sha256_file(output / "CHECKSUMS.json")[1]
        stage = "verify_archive"
        _verify(output, checksum_hash, require_marker=False)
        (output / "ARCHIVE_INFO.json.part").unlink()
        write_exclusive(output / "FILE_PAYLOAD_COMPLETE.json", json_bytes({"schema": SCHEMA, "scope": "FILE_PAYLOAD",
                                                                          "checksums_sha256": checksum_hash,
                                                                          "status": "FILE_PAYLOAD_COMPLETE"}))
        return {"status": "FILE_PAYLOAD_COMPLETE", "archive_dir": str(output), "checksums_sha256": checksum_hash,
                "entries": len(captured), "members": before["member_count"], "stream_bytes": before["total_stream_bytes"],
                **LATER}
    except BaseException as error:
        failure = {"schema": SCHEMA, "scope": "FILE_PAYLOAD", "status": "INCOMPLETE", "stage": stage,
                   "error_type": type(error).__name__, "error": str(error), "time": utc()}
        write_exclusive(output / "FAILURE.json", json_bytes(failure))
        raise


def _verify_payload(path, rows, planned):
    expected = {}
    for row in rows:
        if row["kind"] == "directory":
            expected[row["archive_member"]] = {"directory": True, "size": 0, "compress_type": zipfile.ZIP_STORED}
        for stream in row["streams"]:
            if stream["archive_member"] in expected:
                raise ArchiveError("duplicate manifest member")
            expected[stream["archive_member"]] = dict(stream, directory=False)
    if len(expected) != planned["member_count"] or sum(r["size"] for r in expected.values()) != planned["total_stream_bytes"]:
        raise ArchiveError("member counts/bytes disagree with reviewed plan")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        member_table((info.filename, info.is_dir()) for info in infos)
        if {info.filename for info in infos} != set(expected) or len(infos) != len(expected):
            raise ArchiveError("ZIP member set differs from the complete manifest")
        for info in infos:
            item = expected[info.filename]
            mode = stat.S_IFMT(info.external_attr >> 16)
            if (info.orig_filename != info.filename or info.flag_bits & 1 or info.compress_type not in ALGORITHMS
                    or info.compress_type != item["compress_type"]
                    or mode not in {0, stat.S_IFDIR if item["directory"] else stat.S_IFREG}
                    or info.is_dir() != item["directory"] or info.file_size != item["size"]):
                raise ArchiveError("unsupported ZIP member attributes/algorithm/size")
            count, digest = 0, hashlib.sha256()
            with archive.open(info) as reader:
                while block := reader.read(CHUNK_SIZE):
                    count += len(block)
                    if count > item["size"]:
                        raise ArchiveError("ZIP member exceeds planned bytes")
                    digest.update(block)
            if count != item["size"]:
                raise ArchiveError("ZIP member truncated")
            if not item["directory"] and (digest.hexdigest() != item["sha256"] or info.CRC != item["zip_crc32"]):
                raise ArchiveError("ZIP member SHA256/CRC differs from captured stream")
    return len(expected)


def _logical_plan(value):
    """Validate saved path/stream contracts without opening any original location."""
    roots = value.get("roots")
    if not isinstance(roots, list) or not roots or roots[0].get("root_id") != "project":
        raise ArchiveError("invalid saved roots")
    by_root = {}
    for root in roots:
        identifier = root.get("root_id")
        if (not isinstance(identifier, str) or not ROOT_ID.fullmatch(identifier) or identifier in by_root
                or root.get("kind") not in {"directory", "regular_file"}
                or not isinstance(root.get("path"), str) or not Path(root["path"]).is_absolute()
                or root.get("prefix") != ("project" if identifier == "project" else "dependencies/" + identifier)):
            raise ArchiveError("invalid saved root mapping")
        by_root[identifier] = root
    observed = value.get("snapshot")
    if not isinstance(observed, dict) or not isinstance(observed.get("entries"), list) or not observed["entries"]:
        raise ArchiveError("empty/invalid saved snapshot")
    for row in observed["entries"]:
        if row.get("root_id") not in by_root or row.get("kind") not in {"regular_file", "directory", "link_record"}:
            raise ArchiveError("invalid saved entry type/root")
        relative = row.get("relative_path")
        if not isinstance(relative, str):
            raise ArchiveError("invalid original relative path")
        if relative:
            safe_member(relative)
        if row.get("entry_id") != _entry_id(row["root_id"], relative):
            raise ArchiveError("invalid entry ID")
        expected_member = _member(by_root[row["root_id"]], relative, row["kind"])
        if row.get("archive_member") != (None if row["kind"] == "link_record" else expected_member):
            raise ArchiveError("entry path/member mapping mismatch")
        observation = row.get("observation")
        if not isinstance(observation, dict) or observation.get("kind") != row["kind"]:
            raise ArchiveError("invalid observation kind")
        streams = row.get("streams")
        if not isinstance(streams, list) or not isinstance(observation.get("streams"), list) or len(streams) != len(observation["streams"]):
            raise ArchiveError("invalid saved stream set")
        names = set()
        for stream, original in zip(streams, observation["streams"]):
            name = stream.get("name")
            from archive_common import stream_path
            stream_path("C:/unused-host", name)
            stream_id = hashlib.sha256((row["entry_id"] + name).encode("utf-8")).hexdigest()
            member = expected_member if name == "::$DATA" else "streams/" + stream_id + ".bin"
            if (name in names or stream.get("stream_id") != stream_id or stream.get("archive_member") != member
                    or stream.get("is_default") is not (name == "::$DATA")
                    or type(stream.get("size")) is not int or stream["size"] < 0
                    or not isinstance(stream.get("sha256"), str) or not HEX64.fullmatch(stream["sha256"])
                    or stream.get("compress_type") not in ALGORITHMS
                    or any(stream.get(key) != item for key, item in original.items())):
                raise ArchiveError("invalid saved stream mapping/metadata")
            names.add(name)
        if observation.get("stream_enumeration", {}).get("names") != [s["name"] for s in observation["streams"]]:
            raise ArchiveError("enumerated stream set mismatch")
        if row["kind"] == "regular_file" and "::$DATA" not in names:
            raise ArchiveError("missing file default stream")
        if row["kind"] != "regular_file" and "::$DATA" in names:
            raise ArchiveError("invalid directory/link default stream")
    return observed


def _verify(output, expected_hash, *, require_marker=True):
    output = plain_absolute(output)
    if not isinstance(expected_hash, str) or not HEX64.fullmatch(expected_hash):
        raise ArchiveError("external CHECKSUMS SHA256 required")
    if sha256_file(plain_absolute(output / "CHECKSUMS.json"))[1] != expected_hash:
        raise ArchiveError("external CHECKSUMS SHA256 mismatch")
    checksum = read_json(output / "CHECKSUMS.json")
    if checksum.get("schema") != SCHEMA or set(checksum.get("files", {})) != FIXED_FILES:
        raise ArchiveError("incorrect checksum member contract")
    for name, record in checksum["files"].items():
        path = plain_absolute(output / name)
        if not path.is_file() or (record.get("size"), record.get("sha256")) != sha256_file(path):
            raise ArchiveError("fixed file checksum mismatch: " + name)
    info, value = read_json(output / "ARCHIVE_INFO.json"), read_json(output / "PLAN.json")
    if (info.get("schema") != SCHEMA or info.get("status") != "FILE_PAYLOAD_COMPLETE"
            or info.get("scope") != "FILE_PAYLOAD" or any(info.get(key) != state for key, state in LATER.items())):
        raise ArchiveError("invalid FILE_PAYLOAD status or later-stage assertion")
    # Verification is independent of original roots: never query them or execute captured Git.
    if value.get("schema") != SCHEMA or value.get("scope") != "FILE_PAYLOAD":
        raise ArchiveError("invalid captured plan")
    rows = _read_jsonl(output / "files.jsonl")
    planned = _logical_plan(value)
    if (info.get("roots") != value["roots"] or info.get("plan_sha256") != sha256_file(output / "PLAN.json")[1]
            or info.get("counts") != {"entries": len(planned["entries"]), "members": planned["member_count"],
                                     "stream_bytes": planned["total_stream_bytes"]}
            or info.get("window_id") != read_json(output / "WINDOW.json").get("window_id")):
        raise ArchiveError("archive information disagrees with saved plan/window")
    if len(rows) != len(planned["entries"]) or len({r["entry_id"] for r in rows}) != len(rows):
        raise ArchiveError("entry manifest mismatch")
    for row, original in zip(rows, planned["entries"]):
        for key, item in original.items():
            if key != "streams" and row.get(key) != item:
                raise ArchiveError("captured path/observation differs from plan")
        if row.get("before") != row.get("captured") or row.get("before") != row.get("after") or row.get("before") != original["observation"]:
            raise ArchiveError("before/captured/after disagreement")
        if len(row["streams"]) != len(original["streams"]):
            raise ArchiveError("stream set differs from plan")
        for stream, planned_stream in zip(row["streams"], original["streams"]):
            if any(stream.get(key) != item for key, item in planned_stream.items()):
                raise ArchiveError("stream differs from plan")
    links = _read_jsonl(output / "links.jsonl")
    dependencies = read_json(output / "dependencies.json")
    if links != planned["links"] or dependencies != {"roots": value["roots"], "hardlinks": planned["hardlinks"], "dependency_recovery": "NOT_RUN"}:
        raise ArchiveError("link/hardlink/root relation manifest mismatch")
    count = _verify_payload(output / "payload.zip", rows, planned)
    if require_marker:
        if {p.name for p in output.iterdir()} != FIXED_FILES | {"CHECKSUMS.json", "FILE_PAYLOAD_COMPLETE.json"}:
            raise ArchiveError("unexpected/missing files in sealed archive batch")
        marker = read_json(plain_absolute(output / "FILE_PAYLOAD_COMPLETE.json"))
        if marker != {"schema": SCHEMA, "scope": "FILE_PAYLOAD", "checksums_sha256": expected_hash, "status": "FILE_PAYLOAD_COMPLETE"}:
            raise ArchiveError("invalid/missing FILE_PAYLOAD marker")
    if (output / "COMPLETE.json").exists():
        raise ArchiveError("this micro-batch cannot assert full archive completion")
    return {"status": "FILE_PAYLOAD_COMPLETE", "file_payload_integrity": "PASS", "streams_integrity": "PASS",
            "relations_recorded": "PASS", "entries": len(rows), "members": count,
            "checksums_sha256": expected_hash, **LATER}


def verify(output, expected_hash):
    return _verify(output, expected_hash)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan")
    planning.add_argument("--project-root", type=Path, required=True)
    planning.add_argument("--dependencies", type=Path, required=True, help="JSON exact external roots list (or [])")
    planning.add_argument("--output", type=Path, required=True)
    capturing = commands.add_parser("capture")
    capturing.add_argument("--plan", type=Path, required=True)
    capturing.add_argument("--window-record", type=Path, required=True)
    capturing.add_argument("--output", type=Path, required=True)
    checking = commands.add_parser("verify")
    checking.add_argument("--archive-dir", type=Path, required=True)
    checking.add_argument("--expected-checksums-sha256", required=True)
    for name in ("restore", "verify-restored"):
        commands.add_parser(name)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = plan(args.project_root, read_json(args.dependencies), args.output)
        elif args.command == "capture":
            result = capture(args.plan, args.window_record, args.output)
        elif args.command == "verify":
            result = verify(args.archive_dir, args.expected_checksums_sha256)
        else:
            raise ArchiveError("NOT_IMPLEMENTED: original/Git recovery belongs to later micro-batches")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ArchiveError, OSError, KeyError, TypeError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "FAIL", "error_type": type(error).__name__, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
