#!/usr/bin/env python3
"""Agent-friendly editor for the Cool Spine roadmap workbook.

All commands print JSON to stdout and save changes atomically.
Requires: openpyxl
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from copy import copy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Font, PatternFill
from openpyxl.styles.colors import Color
from openpyxl.worksheet.datavalidation import DataValidation

HEADER_ROW = 5
DATE_ROW = 3
FIRST_TASK_ROW = 6
TASK_COL = 1
STATUS_COL = 2
FIRST_SPRINT_COL = 3
ALLOWED_STATUSES = ("Done", "Last Sprint", "Current Sprint", "Next Sprint", "Epic")
# RGB greens still count as a bar if an older edit wrote them. New bars copy the
# sheet's theme green (accent 6) so they match cells colored in Excel.
GREEN = "A9D18E"
DONE_GREEN = "70AD47"
GRAY = "D9E1F2"
SPRINT_LENGTH_DAYS = 14
RELATIVE_SPRINTS = {"current", "current sprint", "next", "next sprint"}


def emit(ok: bool, **payload: Any) -> None:
    print(json.dumps({"ok": ok, **payload}, ensure_ascii=False, indent=2, default=str))


def fail(message: str, code: int = 2, **payload: Any) -> None:
    emit(False, error=message, **payload)
    raise SystemExit(code)


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        fail(f"Invalid date '{value}'. Use YYYY-MM-DD.")


def normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def workbook_and_sheet(path: Path, sheet_name: str | None):
    if not path.exists():
        fail(f"Workbook not found: {path}")
    wb = load_workbook(path)
    if sheet_name:
        if sheet_name not in wb.sheetnames:
            fail(f"Sheet not found: {sheet_name}", sheets=wb.sheetnames)
        ws = wb[sheet_name]
    else:
        ws = wb.active
    return wb, ws


def sprint_columns(ws):
    columns = []
    for col in range(FIRST_SPRINT_COL, ws.max_column + 1):
        value = ws.cell(DATE_ROW, col).value
        if isinstance(value, datetime):
            columns.append((col, value.date()))
        elif isinstance(value, date):
            columns.append((col, value))
    if not columns:
        fail(f"No sprint dates found in row {DATE_ROW}.")
    return columns


def bucket_end(start: date) -> date:
    return start + timedelta(days=SPRINT_LENGTH_DAYS - 1)


def sprint_index_for_day(columns, day: date) -> int | None:
    for index, (_, start) in enumerate(columns):
        if start <= day <= bucket_end(start):
            return index
    return None


def sprint_bounds(columns, index: int | None) -> dict[str, Any] | None:
    if index is None or index < 0 or index >= len(columns):
        return None
    column, start = columns[index]
    return {"column": column, "start": start.isoformat(), "end": bucket_end(start).isoformat()}


def as_of_date(args) -> date:
    raw = getattr(args, "as_of", None)
    return parse_date(raw) if raw else date.today()


def resolve_bound(value: str, columns, today: date) -> date:
    key = normalize(value)
    if key not in RELATIVE_SPRINTS:
        return parse_date(value)
    index = sprint_index_for_day(columns, today)
    if index is None:
        fail(
            f"No sprint contains {today.isoformat()}.",
            timeline_start=columns[0][1],
            timeline_end=bucket_end(columns[-1][1]),
        )
    if key in {"next", "next sprint"}:
        if index + 1 >= len(columns):
            fail("There is no sprint after the current one.")
        return columns[index + 1][1]
    return columns[index][1]


def theme_green(ws) -> tuple[int, float]:
    for row in range(FIRST_TASK_ROW, ws.max_row + 1):
        for col in range(FIRST_SPRINT_COL, ws.max_column + 1):
            cell = ws.cell(row, col)
            fg = cell.fill.fgColor if cell.fill is not None else None
            if is_green(cell) and fg is not None and fg.type == "theme" and fg.theme is not None:
                return int(fg.theme), float(fg.tint or 0)
    return 6, 0.0


def green_fill(theme: int, tint: float) -> PatternFill:
    return PatternFill(fill_type="solid", fgColor=Color(theme=theme, tint=tint))


def clear_sprint_fills(ws, row: int) -> None:
    for col, _ in sprint_columns(ws):
        ws.cell(row, col).fill = PatternFill(fill_type=None)


def overlapping_buckets(columns, start: date, end: date) -> list[tuple[int, date]]:
    if end < start:
        fail("End date must be on or after start date.")
    timeline_end = bucket_end(columns[-1][1])
    if start > timeline_end or end < columns[0][1]:
        fail(
            "Requested period is outside the workbook timeline.",
            timeline_start=columns[0][1],
            timeline_end=timeline_end,
        )
    chosen = [
        (col, bucket_start)
        for col, bucket_start in columns
        if bucket_start <= end and bucket_end(bucket_start) >= start
    ]
    if not chosen:
        fail("Requested period does not overlap any sprint column.")
    return chosen


def paint_period(ws, row: int, start: date, end: date, keep_existing: bool = False) -> list[str]:
    columns = sprint_columns(ws)
    chosen = overlapping_buckets(columns, start, end)
    theme, tint = theme_green(ws)
    if not keep_existing:
        for col, _ in columns:
            cell = ws.cell(row, col)
            if is_green(cell):
                cell.fill = PatternFill(fill_type=None)
    for col, _ in chosen:
        ws.cell(row, col).fill = green_fill(theme, tint)
    return [bucket_start.isoformat() for _, bucket_start in chosen]


def period_fields(buckets: list[str]) -> dict[str, Any]:
    if not buckets:
        return {}
    end = date.fromisoformat(buckets[-1]) + timedelta(days=SPRINT_LENGTH_DAYS - 1)
    return {"period_start": buckets[0], "period_end": end.isoformat(), "sprint_buckets": buckets}


def task_rows(ws, include_epics: bool = False):
    rows = []
    for row in range(FIRST_TASK_ROW, ws.max_row + 1):
        name = ws.cell(row, TASK_COL).value
        status = ws.cell(row, STATUS_COL).value
        if name and (include_epics or normalize(status) != "epic"):
            rows.append(row)
    return rows


def find_task(ws, query: str, include_epics: bool = True) -> int:
    q = normalize(query)
    exact = [r for r in task_rows(ws, include_epics) if normalize(ws.cell(r, TASK_COL).value) == q]
    if len(exact) == 1:
        return exact[0]
    partial = [r for r in task_rows(ws, include_epics) if q in normalize(ws.cell(r, TASK_COL).value)]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        fail(f"Task not found: {query}")
    fail(f"Task name is ambiguous: {query}", matches=[ws.cell(r, TASK_COL).value for r in partial])


def status_name(value: str) -> str:
    mapping = {normalize(v): v for v in ALLOWED_STATUSES}
    key = normalize(value)
    if key not in mapping:
        fail(f"Invalid sprint status: {value}", allowed=list(ALLOWED_STATUSES))
    return mapping[key]


def is_green(cell) -> bool:
    fill = cell.fill
    if fill.fill_type != "solid":
        return False
    fg = fill.fgColor
    if fg.type == "theme" and fg.theme == 6:
        return True
    if fg.type == "rgb":
        return str(fg.rgb).upper()[-6:] in {GREEN, DONE_GREEN, "92D050", "C6E0B4"}
    return False


def atomic_save(wb, path: Path, backup: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.exists():
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)
    fd, temp_name = tempfile.mkstemp(prefix=path.stem + "_", suffix=path.suffix, dir=path.parent)
    os.close(fd)
    try:
        wb.save(temp_name)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def refresh_controls(ws) -> None:
    ws.auto_filter.ref = f"A{HEADER_ROW}:{ws.cell(HEADER_ROW, ws.max_column).column_letter}{ws.max_row}"
    # Replace only list validation applying to column B.
    for dv in list(ws.data_validations.dataValidation):
        if "B" in str(dv.sqref):
            ws.data_validations.dataValidation.remove(dv)
    dv = DataValidation(type="list", formula1='"' + ",".join(ALLOWED_STATUSES) + '"', allow_blank=True)
    dv.error = "Choose a value from the sprint-status list."
    dv.errorTitle = "Invalid sprint status"
    ws.add_data_validation(dv)
    dv.add(f"B{FIRST_TASK_ROW}:B{ws.max_row}")


def task_record(ws, row: int) -> dict[str, Any]:
    dates = sprint_columns(ws)
    active = [d for c, d in dates if is_green(ws.cell(row, c))]
    return {
        "row": row,
        "task": ws.cell(row, TASK_COL).value,
        "sprint_status": ws.cell(row, STATUS_COL).value,
        "period_start": min(active).isoformat() if active else None,
        "period_end": (max(active) + timedelta(days=13)).isoformat() if active else None,
    }


def cmd_analyze(args):
    _, ws = workbook_and_sheet(args.file, args.sheet)
    dates = sprint_columns(ws)
    counts = {s: 0 for s in ALLOWED_STATUSES}
    counts["Unassigned"] = 0
    for r in task_rows(ws, include_epics=True):
        value = ws.cell(r, STATUS_COL).value
        key = status_name(value) if value else "Unassigned"
        counts[key] = counts.get(key, 0) + 1
    emit(True, sheet=ws.title, task_count=len(task_rows(ws)), epic_count=counts.get("Epic", 0),
         sprint_count=len(dates), timeline_start=dates[0][1], timeline_end=dates[-1][1] + timedelta(days=13),
         status_counts=counts)


def cmd_list(args):
    _, ws = workbook_and_sheet(args.file, args.sheet)
    wanted = status_name(args.sprint)
    results = [task_record(ws, r) for r in task_rows(ws) if normalize(ws.cell(r, STATUS_COL).value) == normalize(wanted)]
    emit(True, sprint=wanted, count=len(results), tasks=results)


def cmd_set_status(args):
    wb, ws = workbook_and_sheet(args.file, args.sheet)
    row = find_task(ws, args.task, include_epics=True)
    status = status_name(args.status)
    ws.cell(row, STATUS_COL).value = status
    refresh_controls(ws)
    atomic_save(wb, args.file, not args.no_backup)
    emit(True, action="set-status", task=ws.cell(row, TASK_COL).value, row=row, sprint_status=status, file=args.file)


def cmd_set_period(args):
    wb, ws = workbook_and_sheet(args.file, args.sheet)
    row = find_task(ws, args.task, include_epics=False)
    columns = sprint_columns(ws)
    today = as_of_date(args)
    start = resolve_bound(args.start, columns, today)
    end = resolve_bound(args.end, columns, today)
    selected = paint_period(ws, row, start, end, keep_existing=args.keep_existing)
    atomic_save(wb, args.file, not args.no_backup)
    emit(True, action="set-period", task=ws.cell(row, TASK_COL).value, row=row,
         requested_start=start, requested_end=end, file=args.file, **period_fields(selected))


def copy_row_style(ws, source: int, target: int) -> None:
    ws.row_dimensions[target].height = ws.row_dimensions[source].height
    for col in range(1, ws.max_column + 1):
        src, dst = ws.cell(source, col), ws.cell(target, col)
        if src.has_style:
            dst._style = copy(src._style)
        if src.number_format:
            dst.number_format = src.number_format
        dst.alignment = copy(src.alignment)
        dst.protection = copy(src.protection)


def cmd_add(args):
    wb, ws = workbook_and_sheet(args.file, args.sheet)
    existing = [r for r in task_rows(ws, True) if normalize(ws.cell(r, TASK_COL).value) == normalize(args.task)]
    if existing:
        fail(f"Task already exists: {args.task}", row=existing[0])
    status = status_name(args.status) if args.status else None
    if status == "Epic":
        fail("Use a normal sprint status for a task; Epic is reserved for section rows.")
    if args.after:
        anchor = find_task(ws, args.after, include_epics=True)
        insert_at = anchor + 1
    elif args.epic:
        epic_row = find_task(ws, args.epic, include_epics=True)
        if normalize(ws.cell(epic_row, STATUS_COL).value) != "epic":
            fail(f"'{args.epic}' is not an Epic row.")
        insert_at = epic_row + 1
        while insert_at <= ws.max_row and normalize(ws.cell(insert_at, STATUS_COL).value) != "epic":
            insert_at += 1
        while insert_at > epic_row + 1 and not ws.cell(insert_at - 1, TASK_COL).value:
            insert_at -= 1
    else:
        insert_at = ws.max_row + 1
    chosen = None
    if args.start or args.end:
        if not args.start or not args.end:
            fail("Pass both --start and --end to color the sprint bar.")
        columns = sprint_columns(ws)
        today = as_of_date(args)
        chosen = overlapping_buckets(
            columns,
            resolve_bound(args.start, columns, today),
            resolve_bound(args.end, columns, today),
        )
    theme, tint = theme_green(ws)
    ws.insert_rows(insert_at, 1)
    source = insert_at - 1 if insert_at > FIRST_TASK_ROW else insert_at + 1
    copy_row_style(ws, source, insert_at)
    # A copied row brings the neighbor's green bar with it. Drop those fills
    # and paint only the sprint range requested for this task.
    clear_sprint_fills(ws, insert_at)
    # New tasks should use normal task formatting, not bold Epic formatting.
    ws.cell(insert_at, TASK_COL).font = copy(ws.cell(source, TASK_COL).font)
    ws.cell(insert_at, TASK_COL).font = Font(name=ws.cell(insert_at, TASK_COL).font.name,
                                            size=ws.cell(insert_at, TASK_COL).font.sz,
                                            bold=False, italic=ws.cell(insert_at, TASK_COL).font.italic,
                                            color=ws.cell(insert_at, TASK_COL).font.color)
    ws.cell(insert_at, TASK_COL).value = args.task
    ws.cell(insert_at, STATUS_COL).value = status
    buckets: list[str] = []
    if chosen:
        for col, bucket_start in chosen:
            ws.cell(insert_at, col).fill = green_fill(theme, tint)
            buckets.append(bucket_start.isoformat())
    refresh_controls(ws)
    atomic_save(wb, args.file, not args.no_backup)
    emit(True, action="add-task", task=args.task, row=insert_at, sprint_status=status,
         file=args.file, **period_fields(buckets))


def cmd_advance(args):
    wb, ws = workbook_and_sheet(args.file, args.sheet)
    changed = {"Done": [], "Last Sprint": [], "Current Sprint": []}
    # Evaluate old values first so each task moves exactly one step.
    updates = []
    for r in task_rows(ws):
        old = normalize(ws.cell(r, STATUS_COL).value)
        new = {"last sprint": "Done", "current sprint": "Last Sprint", "next sprint": "Current Sprint"}.get(old)
        if new:
            updates.append((r, new))
    for r, new in updates:
        ws.cell(r, STATUS_COL).value = new
        changed[new].append(ws.cell(r, TASK_COL).value)
    refresh_controls(ws)
    atomic_save(wb, args.file, not args.no_backup)
    emit(True, action="advance-sprint", changed_counts={k: len(v) for k, v in changed.items()}, changed=changed, file=args.file)


def cmd_current_sprint(args):
    _, ws = workbook_and_sheet(args.file, args.sheet)
    columns = sprint_columns(ws)
    today = as_of_date(args)
    index = sprint_index_for_day(columns, today)
    emit(
        True,
        today=today.isoformat(),
        current=sprint_bounds(columns, index),
        previous=sprint_bounds(columns, None if index is None else index - 1),
        next=sprint_bounds(columns, None if index is None else index + 1),
        sprints=[sprint_bounds(columns, i) for i in range(len(columns))],
    )


def cmd_epics(args):
    _, ws = workbook_and_sheet(args.file, args.sheet)
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in range(FIRST_TASK_ROW, ws.max_row + 1):
        name = ws.cell(row, TASK_COL).value
        status = ws.cell(row, STATUS_COL).value
        if not name:
            continue
        if normalize(status) == "epic":
            current = {"epic": name, "row": row, "insert": "epic", "tasks": []}
            sections.append(current)
            continue
        if current is None:
            current = {"epic": None, "row": None, "insert": "after", "tasks": []}
            sections.append(current)
        current["tasks"].append(name)
    for section in sections:
        if section["insert"] == "after" and section["tasks"]:
            section["after"] = section["tasks"][-1]
    emit(True, sections=sections)


def cmd_mark_done(args):
    wb, ws = workbook_and_sheet(args.file, args.sheet)
    row = find_task(ws, args.task, include_epics=False)
    ws.cell(row, STATUS_COL).value = "Done"
    if args.green_bar:
        for col, _ in sprint_columns(ws):
            if is_green(ws.cell(row, col)):
                ws.cell(row, col).fill = PatternFill("solid", fgColor=DONE_GREEN)
    refresh_controls(ws)
    atomic_save(wb, args.file, not args.no_backup)
    emit(True, action="mark-done", task=ws.cell(row, TASK_COL).value, row=row, file=args.file)


def build_parser():
    p = argparse.ArgumentParser(description="Agent-friendly Cool Spine roadmap editor")
    p.add_argument("--file", type=Path, default=Path("Cool_Spine_GANTT.xlsx"))
    p.add_argument("--sheet", help="Worksheet name; defaults to active sheet")
    p.add_argument("--no-backup", action="store_true", help="Do not create a .bak copy before saving")
    sub = p.add_subparsers(dest="command", required=True)

    q = sub.add_parser("analyze", help="Describe workbook structure and status counts")
    q.set_defaults(func=cmd_analyze)

    q = sub.add_parser("list", help="List tasks by sprint status")
    q.add_argument("--sprint", required=True, choices=ALLOWED_STATUSES[:-1])
    q.set_defaults(func=cmd_list)

    q = sub.add_parser("set-status", help="Set one task's sprint status")
    q.add_argument("--task", required=True)
    q.add_argument("--status", required=True, choices=ALLOWED_STATUSES)
    q.set_defaults(func=cmd_set_status)

    q = sub.add_parser("set-period", help="Color all overlapping 2-week sprint cells with the sheet green")
    q.add_argument("--task", required=True)
    q.add_argument("--start", required=True, help="YYYY-MM-DD, current, or next")
    q.add_argument("--end", required=True, help="YYYY-MM-DD, current, or next")
    q.add_argument("--keep-existing", action="store_true", help="Add to existing green cells instead of replacing them")
    q.add_argument("--as-of", help="Date used to resolve current/next (YYYY-MM-DD). Defaults to today.")
    q.set_defaults(func=cmd_set_period)

    q = sub.add_parser("add-task", help="Insert a task under an Epic, after another task, or at the end")
    q.add_argument("--task", required=True)
    loc = q.add_mutually_exclusive_group()
    loc.add_argument("--epic")
    loc.add_argument("--after")
    q.add_argument("--status", choices=ALLOWED_STATUSES[:-1])
    q.add_argument("--start", help="Bar start: YYYY-MM-DD, current, or next")
    q.add_argument("--end", help="Bar end: YYYY-MM-DD, current, or next")
    q.add_argument("--as-of", help="Date used to resolve current/next (YYYY-MM-DD). Defaults to today.")
    q.set_defaults(func=cmd_add)

    q = sub.add_parser("current-sprint", help="Show the sprint column that contains today, plus every sprint")
    q.add_argument("--as-of", help="Date used to resolve current/next (YYYY-MM-DD). Defaults to today.")
    q.set_defaults(func=cmd_current_sprint)

    q = sub.add_parser("epics", help="List epic sections and the tasks under each")
    q.set_defaults(func=cmd_epics)

    q = sub.add_parser("advance-sprint", help="Last->Done, Current->Last, Next->Current")
    q.set_defaults(func=cmd_advance)

    q = sub.add_parser("mark-done", help="Mark one task Done")
    q.add_argument("--task", required=True)
    q.add_argument("--green-bar", action="store_true", help="Darken its existing green timeline bar")
    q.set_defaults(func=cmd_mark_done)
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except PermissionError:
        fail("Cannot save the workbook. Close it in Excel and try again.")
    except SystemExit:
        raise
    except Exception as exc:
        fail(f"Unexpected error: {exc}", code=1, exception=type(exc).__name__)


if __name__ == "__main__":
    main()
