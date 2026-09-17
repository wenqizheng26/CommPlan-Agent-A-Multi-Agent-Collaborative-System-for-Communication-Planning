"""Read-only BIFF workbook extraction and independent arithmetic reproduction.

This auditor does not use formula_rag.core or the approved formula catalog.
Only LOG10, COS, PI and scalar arithmetic in this workbook are supported.
Unsupported workbook formulas fail closed; macros and external links never run.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import math
import operator
from pathlib import Path
import re
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
CELL = re.compile(r"[A-Z]{1,3}[1-9][0-9]*\Z")
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def recompute_cell(address, formulas, cells, active=None, memo=None):
    """Resolve formula dependencies without reading any formula's cached value."""
    active = set() if active is None else active
    memo = {} if memo is None else memo
    if address in memo:
        return memo[address]
    if address in active:
        raise ValueError(f"circular cell reference: {address}")
    if address not in formulas:
        value = cells.get(address)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"missing or nonnumeric input: {address}")
        return float(value)
    expression = formulas[address].replace("$", "")
    if len(expression) > 4096:
        raise ValueError("Excel expression is too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("unsupported Excel formula syntax") from exc
    if sum(1 for _ in ast.walk(tree)) > 128:
        raise ValueError("Excel expression exceeds the node limit")
    active.add(address)

    def visit(node, depth=0):
        if depth > 32:
            raise ValueError("Excel expression exceeds the depth limit")
        if isinstance(node, ast.Constant) and not isinstance(node.value, bool) and isinstance(node.value, (int, float)):
            value = float(node.value)
        elif isinstance(node, ast.Name) and CELL.fullmatch(node.id):
            value = recompute_cell(node.id, formulas, cells, active, memo)
        elif isinstance(node, ast.BinOp) and type(node.op) in OPS:
            value = OPS[type(node.op)](visit(node.left, depth+1), visit(node.right, depth+1))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand, depth+1) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id
            if name == "PI" and not node.args:
                value = math.pi
            elif name in ("LOG10", "COS") and len(node.args) == 1:
                function = math.log10 if name == "LOG10" else math.cos
                value = function(visit(node.args[0], depth+1))
            else:
                raise ValueError(f"unsupported Excel function: {name}")
        else:
            raise ValueError(f"unsupported Excel construct: {type(node).__name__}")
        if not math.isfinite(value):
            raise ValueError("nonfinite Excel result")
        return value

    try:
        value = visit(tree.body)
        memo[address] = value
        return value
    finally:
        active.remove(address)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect(workbook_path, output_path, copy_source=False):
    # Optional dependencies are only needed to re-read the legacy source file.
    import olefile
    import xlrd
    from xlrd.formula import colname, decompile_formula, FMLA_TYPE_CELL

    workbook_path = Path(workbook_path).resolve()
    before_hash = _sha256(workbook_path)
    source_copy = ROOT/"knowledge"/"sources"/"链路预算-传输.xls"
    if copy_source and workbook_path != source_copy.resolve():
        source_copy.parent.mkdir(parents=True, exist_ok=True)
        if source_copy.exists() and _sha256(source_copy) != before_hash:
            raise ValueError("existing source fixture differs; will not overwrite it")
        if not source_copy.exists():
            shutil.copy2(workbook_path, source_copy)
        if _sha256(source_copy) != before_hash:
            raise ValueError("source copy hash mismatch")
    book = xlrd.open_workbook(str(workbook_path), formatting_info=True)
    sheets, all_cells, formula_records = [], {}, []
    for sheet in book.sheets():
        cells = {}
        coordinates = []
        for row in range(sheet.nrows):
            for col in range(sheet.ncols):
                cell = sheet.cell(row, col)
                if cell.ctype not in (0, 6):
                    address = f"{colname(col)}{row+1}"
                    cells[address] = cell.value
                    coordinates.append((row, col))
        all_cells[sheet.name] = cells
        content_range = None
        if coordinates:
            lo_r, lo_c = min(x[0] for x in coordinates), min(x[1] for x in coordinates)
            hi_r, hi_c = max(x[0] for x in coordinates), max(x[1] for x in coordinates)
            content_range = f"{colname(lo_c)}{lo_r+1}:{colname(hi_c)}{hi_r+1}"
        sheets.append({"name": sheet.name, "visibility": sheet.visibility,
                       "stored_dimensions": {"rows": sheet.nrows, "columns": sheet.ncols},
                       "nonempty_range": content_range, "nonempty_count": len(cells),
                       "notes_count": len(sheet.cell_note_map), "cells": cells})
    with olefile.OleFileIO(str(workbook_path)) as ole:
        streams = ole.listdir()
        stream_name = "Workbook" if ole.exists("Workbook") else "Book"
        data = ole.openstream(stream_name).read()
    position, bounds, current = 0, {}, None
    while position+4 <= len(data):
        record, length = struct.unpack_from("<HH", data, position)
        body = data[position+4:position+4+length]
        if len(body) != length:
            raise ValueError("truncated BIFF record")
        if record == 0x85:
            sheet_position = struct.unpack_from("<I", body)[0]
            bounds[sheet_position] = book.sheet_names()[len(bounds)]
        if position in bounds:
            current = bounds[position]
        if record == 0x6:
            if current is None or len(body) < 22:
                raise ValueError("formula record without valid worksheet")
            row, col = struct.unpack_from("<HH", body)
            token_count = struct.unpack_from("<H", body, 20)[0]
            tokens = body[22:22+token_count]
            expression = decompile_formula(book, tokens, token_count, fmlatype=FMLA_TYPE_CELL, browx=row, bcolx=col)
            if not expression:
                raise ValueError("unsupported formula token record")
            address = f"{colname(col)}{row+1}"
            formula_records.append({"sheet": current, "cell": address,
                                    "expression": expression,
                                    "cached_value": book.sheet_by_name(current).cell_value(row, col),
                                    "label": all_cells[current].get(f"B{row+1}")})
        position += 4+length
    formulas_by_sheet = {}
    for item in formula_records:
        formulas_by_sheet.setdefault(item["sheet"], {})[item["cell"]] = item["expression"]
    for item in formula_records:
        formulas = formulas_by_sheet[item["sheet"]]
        item["direct_dependencies"] = sorted(set(re.findall(r"\b[A-Z]{1,3}[1-9][0-9]*\b", item["expression"])) - {"LOG10"})
        try:
            recomputed = recompute_cell(item["cell"], formulas, all_cells[item["sheet"]])
            difference = abs(recomputed - item["cached_value"])
            item.update({"recomputed_value": recomputed, "absolute_difference": difference,
                         "within_tolerance": difference <= 1e-10})
        except (TypeError, ValueError, ArithmeticError) as exc:
            item.update({"within_tolerance": False, "error": str(exc)})
    after_hash = _sha256(workbook_path)
    if after_hash != before_hash:
        raise ValueError("source hash changed during read-only audit")
    matches = sum(item["within_tolerance"] for item in formula_records)
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "原表算术复现；不等同于物理模型验收或现场可靠度验收",
        "source": {"path": str(workbook_path), "sha256": before_hash, "bytes": workbook_path.stat().st_size,
                   "original_unchanged": before_hash == after_hash,
                   "preserved_copy": "knowledge/sources/链路预算-传输.xls" if source_copy.exists() and _sha256(source_copy) == before_hash else None},
        "reader": {"xlrd": xlrd.__version__, "olefile": olefile.__version__, "macros_executed": False, "external_links_executed": False},
        "expression_format": "BIFF compiled tokens decompiled to normalized Excel expressions; not the original typed character formatting",
        "method": "Separate AST calculator recursively recomputes every formula dependency from source inputs; formula cached outputs are used only for comparison.",
        "sheet_count": len(sheets), "sheets": sheets, "ole_streams": streams,
        "formula_count": len(formula_records), "matched_formula_count": matches,
        "absolute_tolerance": 1e-10,
        "all_match": bool(formula_records) and matches == len(formula_records),
        "expected_16_formulas": len(formula_records) == 16,
        "max_absolute_difference": max((item.get("absolute_difference", float("inf")) for item in formula_records), default=None),
        "formulas": formula_records,
        "physical_validity": "not_established_by_arithmetic_audit",
        "limitations": [
            "源表没有环境选择字段、明确适用范围或外部公式引用。",
            "C11/D11 的 10*LOG10(COS(...)) 缺少物理依据，不进入已审核的一般查询公式目录。当前速度为零，不能验证其非零速度适用性。",
            "源表多普勒使用近似光速 300000000 m/s；一般查询卡使用 NIST 精确定义的 299792458 m/s。",
            "源表噪声门限硬编码 -174 dBm/Hz，未显式提供温度；一般热噪声查询必须输入温度与噪声等效带宽。",
            "源表天线增益单位只写 dB，未说明 dBi/dBd 参考；一般链路公式明确要求 dBi。",
            "源表两个方向的距离分别为 0.2 km 和 0.4 km；未据此推断它们属于同一时刻的同一路径。",
            "表名包含可靠度，但实际非空内容截止电平余量，未发现独立可用率计算。"
        ]
    }
    output_path = Path(output_path)
    if output_path.resolve() in (workbook_path, source_copy.resolve()):
        raise ValueError("audit output cannot overwrite a workbook source")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Nonfinite values are not permitted in this inspectable JSON artifact.
    if report["max_absolute_difference"] is not None and not math.isfinite(report["max_absolute_difference"]):
        report["max_absolute_difference"] = None
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", nargs="?", type=Path, default=ROOT/"knowledge"/"sources"/"链路预算-传输.xls")
    parser.add_argument("--output", type=Path, default=ROOT/"reports"/"workbook_audit.json")
    parser.add_argument("--copy-source", action="store_true")
    parser.add_argument("--deps-dir", type=Path, help="Optional explicitly provided directory containing xlrd and olefile")
    args = parser.parse_args()
    if args.deps_dir:
        sys.path.insert(0, str(args.deps_dir.resolve()))
    report = inspect(args.workbook, args.output, args.copy_source)
    print(json.dumps({key: report[key] for key in ("formula_count", "matched_formula_count", "all_match", "max_absolute_difference")}, ensure_ascii=True))
    return 0 if report["all_match"] and report["expected_16_formulas"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
