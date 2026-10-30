"""Load and save the lean roadmap YAML.

The file shape matches tools/GANTT/roadmap.template.yaml.
Task duration is stored as sprint start dates. A milestone stores one date.
"""
from __future__ import annotations

import os
import re
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

STATUSES = ("done", "in_progress", "future")
PLAIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()/,+\-]*$")
YAML_WORDS = {"yes", "no", "true", "false", "null", "on", "off", "~"}


class RoadmapError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def load_roadmap(path: Path) -> dict:
    import yaml

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RoadmapError(f"Could not read {path.name}: {exc}", 500) from exc
    if not isinstance(raw, dict):
        raise RoadmapError("Roadmap file is not a mapping", 500)
    _reject_unknown(raw, {"version", "title", "timeline", "epics"}, "roadmap")
    if raw.get("version") != 1:
        raise RoadmapError("Roadmap version is not 1", 500)
    if not isinstance(raw.get("title"), str) or not raw["title"].strip():
        raise RoadmapError("Roadmap title is missing", 500)
    timeline = _timeline(raw.get("timeline"))
    epics_raw = raw.get("epics")
    if not isinstance(epics_raw, list):
        raise RoadmapError("Roadmap epics are missing", 500)
    epics = [_epic(item) for item in epics_raw]
    data = {
        "version": 1,
        "title": raw["title"],
        "timeline": timeline,
        "epics": epics,
    }
    ids = _ids(data)
    if len(ids) != len(set(ids)):
        raise RoadmapError("Roadmap ids are not unique", 500)
    _check_dates(data)
    return data


def save_roadmap(path: Path, data: dict) -> None:
    text = dump_roadmap(data)
    if path.exists() and b"\r\n" in path.read_bytes():
        text = text.replace("\n", "\r\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + "_", suffix=".yaml", dir=path.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_bytes(text.encode("utf-8"))
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def dump_roadmap(data: dict) -> str:
    start = data["timeline"]["start"]
    lines = [
        "version: 1",
        f"title: {yaml_quote(data['title'])}",
        "timeline:",
        f'  start: "{start.isoformat()}"',
        f"  sprint_days: {data['timeline']['sprint_days']}",
        f"  sprint_count: {data['timeline']['sprint_count']}",
        "epics:",
    ]
    for epic in data["epics"]:
        lines.append(f"  - id: {epic['id']}")
        lines.append(f"    name: {yaml_quote(epic['name'])}")
        if not epic["items"]:
            lines.append("    items: []")
            continue
        lines.append("    items:")
        for item in epic["items"]:
            lines.append(f"      - id: {item['id']}")
            lines.append(f"        kind: {item['kind']}")
            lines.append(f"        name: {yaml_quote(item['name'])}")
            if item["kind"] == "task":
                lines.append(f"        status: {item['status']}")
                if "start" in item:
                    lines.append(f'        start: "{item["start"].isoformat()}"')
                    lines.append(f'        end: "{item["end"].isoformat()}"')
            elif "date" in item:
                lines.append(f'        date: "{item["date"].isoformat()}"')
    return "\n".join(lines) + "\n"


def view_roadmap(data: dict, today: date | None = None) -> dict:
    today = today or date.today()
    step = data["timeline"]["sprint_days"]
    sprints = []
    today_sprint = None
    for start in sprint_starts(data):
        last = start + timedelta(days=step - 1)
        sprints.append({"id": start.isoformat(), "last_day": last.isoformat()})
        if start <= today <= last:
            today_sprint = start.isoformat()
    epics = []
    for epic in data["epics"]:
        items = []
        for item in epic["items"]:
            if item["kind"] == "task":
                items.append({
                    "id": item["id"],
                    "kind": "task",
                    "name": item["name"],
                    "status": item["status"],
                    "start": item["start"].isoformat() if "start" in item else None,
                    "end": item["end"].isoformat() if "end" in item else None,
                })
            else:
                items.append({
                    "id": item["id"],
                    "kind": "milestone",
                    "name": item["name"],
                    "date": item["date"].isoformat() if "date" in item else None,
                })
        epics.append({"id": epic["id"], "name": epic["name"], "items": items})
    return {
        "title": data["title"],
        "timeline": {
            "start": data["timeline"]["start"].isoformat(),
            "sprint_days": step,
            "sprint_count": data["timeline"]["sprint_count"],
        },
        "today": today.isoformat(),
        "today_sprint": today_sprint,
        "sprints": sprints,
        "epics": epics,
    }


def add_task(data: dict, epic_id: str, name: str = "New task") -> str:
    if epic_id == "milestones":
        raise RoadmapError("Tasks cannot be added to Milestones")
    epic = _find_epic(data, epic_id)
    if epic is None:
        raise RoadmapError("Epic not found", 404)
    clean = name.strip()
    if not clean:
        raise RoadmapError("Name is empty")
    if len(clean) > 500:
        raise RoadmapError("Name is too long")
    item_id = _unique_id(data, clean)
    epic["items"].append({
        "id": item_id,
        "kind": "task",
        "name": clean,
        "status": "future",
    })
    return item_id


def update_task(data: dict, item_id: str, fields: dict) -> None:
    item = _find_item(data, item_id)
    if item is None:
        raise RoadmapError("Task not found", 404)
    if item["kind"] == "milestone":
        _update_milestone(data, item, fields)
        return
    if item["kind"] != "task":
        raise RoadmapError("Item cannot be edited")
    unknown = set(fields) - {"name", "status", "start", "end"}
    if unknown:
        raise RoadmapError("Unknown fields: " + ", ".join(sorted(unknown)))
    if "name" in fields:
        if not isinstance(fields["name"], str):
            raise RoadmapError("Name must be a string")
        clean = fields["name"].strip()
        if not clean:
            raise RoadmapError("Name is empty")
        if len(clean) > 500:
            raise RoadmapError("Name is too long")
        item["name"] = clean
    if "status" in fields:
        if fields["status"] not in STATUSES:
            raise RoadmapError("Status must be done, in_progress, or future")
        item["status"] = fields["status"]
    if "start" in fields or "end" in fields:
        if "start" not in fields or "end" not in fields:
            raise RoadmapError("Pass both start and end")
        start, end = fields["start"], fields["end"]
        if start is None and end is None:
            item.pop("start", None)
            item.pop("end", None)
        elif isinstance(start, str) and isinstance(end, str):
            start_day = _sprint_day(data, start)
            end_day = _sprint_day(data, end)
            if end_day < start_day:
                raise RoadmapError("End sprint is before the start sprint")
            item["start"] = start_day
            item["end"] = end_day
        else:
            raise RoadmapError("Start and end must both be sprint dates, or both null")


def _update_milestone(data: dict, item: dict, fields: dict) -> None:
    unknown = set(fields) - {"name", "date"}
    if unknown:
        raise RoadmapError("Unknown fields: " + ", ".join(sorted(unknown)))
    if "name" in fields:
        if not isinstance(fields["name"], str):
            raise RoadmapError("Name must be a string")
        clean = fields["name"].strip()
        if not clean:
            raise RoadmapError("Name is empty")
        if len(clean) > 500:
            raise RoadmapError("Name is too long")
        item["name"] = clean
    if "date" not in fields:
        return
    value = fields["date"]
    if value is None:
        item.pop("date", None)
        return
    if not isinstance(value, str):
        raise RoadmapError("Date must be YYYY-MM-DD, or null")
    try:
        day = date.fromisoformat(value)
    except ValueError as exc:
        raise RoadmapError("Date must be YYYY-MM-DD") from exc
    step = data["timeline"]["sprint_days"]
    first = data["timeline"]["start"]
    last = sprint_starts(data)[-1] + timedelta(days=step - 1)
    if not first <= day <= last:
        raise RoadmapError("Date is outside the timeline")
    item["date"] = day


def sprint_starts(data: dict) -> list[date]:
    timeline = data["timeline"]
    step = timedelta(days=timeline["sprint_days"])
    return [timeline["start"] + step * index for index in range(timeline["sprint_count"])]


def yaml_quote(value: str) -> str:
    if PLAIN.fullmatch(value) and value.casefold() not in YAML_WORDS:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _timeline(raw) -> dict:
    if not isinstance(raw, dict):
        raise RoadmapError("Timeline is missing", 500)
    _reject_unknown(raw, {"start", "sprint_days", "sprint_count"}, "timeline")
    start = _as_date(raw.get("start"), "timeline start")
    days = raw.get("sprint_days")
    count = raw.get("sprint_count")
    if not isinstance(days, int) or isinstance(days, bool) or days <= 0:
        raise RoadmapError("sprint_days must be a positive number", 500)
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise RoadmapError("sprint_count must be a positive number", 500)
    return {"start": start, "sprint_days": days, "sprint_count": count}


def _epic(raw) -> dict:
    if not isinstance(raw, dict):
        raise RoadmapError("An epic is not a mapping", 500)
    _reject_unknown(raw, {"id", "name", "items"}, "epic")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RoadmapError("An epic name is missing", 500)
    items_raw = raw.get("items")
    if not isinstance(items_raw, list):
        raise RoadmapError(f"Epic {name!r} has no items list", 500)
    return {"id": _check_id(raw.get("id")), "name": name, "items": [_item(item) for item in items_raw]}


def _item(raw) -> dict:
    if not isinstance(raw, dict):
        raise RoadmapError("An item is not a mapping", 500)
    kind = raw.get("kind")
    name = raw.get("name")
    if not isinstance(name, str) or name.strip() == "":
        raise RoadmapError("An item name is missing", 500)
    item_id = _check_id(raw.get("id"))
    if kind == "task":
        _reject_unknown(raw, {"id", "kind", "name", "status", "start", "end"}, name)
        status = raw.get("status")
        if status not in STATUSES:
            raise RoadmapError(f"{name!r} has no status", 500)
        item = {"id": item_id, "kind": "task", "name": name, "status": status}
        has_start = "start" in raw and raw["start"] is not None
        has_end = "end" in raw and raw["end"] is not None
        if has_start != has_end:
            raise RoadmapError(f"{name!r} needs both start and end", 500)
        if has_start:
            item["start"] = _as_date(raw["start"], name)
            item["end"] = _as_date(raw["end"], name)
        return item
    if kind == "milestone":
        _reject_unknown(raw, {"id", "kind", "name", "date"}, name)
        item = {"id": item_id, "kind": "milestone", "name": name}
        if "date" in raw and raw["date"] is not None:
            item["date"] = _as_date(raw["date"], name)
        return item
    raise RoadmapError(f"{name!r} has an unknown kind", 500)


def _check_dates(data: dict) -> None:
    starts = set(sprint_starts(data))
    step = data["timeline"]["sprint_days"]
    first = data["timeline"]["start"]
    last = sprint_starts(data)[-1] + timedelta(days=step - 1)
    for epic in data["epics"]:
        for item in epic["items"]:
            if item["kind"] == "task" and "start" in item:
                if item["start"] not in starts or item["end"] not in starts:
                    raise RoadmapError(f"{item['name']!r} is not on a sprint", 500)
                if item["end"] < item["start"]:
                    raise RoadmapError(f"{item['name']!r} ends before it starts", 500)
            if item["kind"] == "milestone" and "date" in item:
                if not first <= item["date"] <= last:
                    raise RoadmapError(f"{item['name']!r} is outside the timeline", 500)


def _sprint_day(data: dict, value: str) -> date:
    try:
        day = date.fromisoformat(value)
    except ValueError as exc:
        raise RoadmapError("Sprint date must be YYYY-MM-DD") from exc
    if day not in set(sprint_starts(data)):
        raise RoadmapError("Date is not a sprint start")
    return day


def _as_date(value, label: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise RoadmapError(f"{label} is not a date", 500) from exc
    raise RoadmapError(f"{label} is not a date", 500)


def _check_id(value) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or "/" in value:
        raise RoadmapError("An id is missing or invalid", 500)
    return value


def _reject_unknown(raw: dict, allowed: set[str], label: str) -> None:
    unknown = set(raw) - allowed
    if unknown:
        raise RoadmapError(f"{label} has unknown fields: {', '.join(sorted(unknown))}", 500)


def _ids(data: dict) -> list[str]:
    found = []
    for epic in data["epics"]:
        found.append(epic["id"])
        for item in epic["items"]:
            found.append(item["id"])
    return found


def _find_epic(data: dict, epic_id: str):
    for epic in data["epics"]:
        if epic["id"] == epic_id:
            return epic
    return None


def _find_item(data: dict, item_id: str):
    for epic in data["epics"]:
        for item in epic["items"]:
            if item["id"] == item_id:
                return item
    return None


def _unique_id(data: dict, name: str) -> str:
    used = set(_ids(data))
    base = _slug(name) or "task"
    candidate = base
    number = 2
    while candidate in used:
        candidate = f"{base}-{number}"
        number += 1
    return candidate


def _slug(name: str) -> str:
    text = name.casefold().replace("&", " and ")
    kept = [ch for ch in text if ch.isalnum() or ch in " -"]
    raw = re.sub(r"-{2,}", "-", "".join(kept).replace(" ", "-")).strip("-")
    return raw
