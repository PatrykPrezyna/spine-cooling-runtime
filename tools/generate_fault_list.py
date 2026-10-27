"""Write the fault list from the safety rules and the fault catalog.

Run from the repo root:

    python tools/generate_fault_list.py
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fault_catalog import FAULTS, FaultCode, Severity, get_fault  # noqa: E402
from safety_rules import RULES, listed_faults  # noqa: E402

HTML_PATH = ROOT / "docs" / "fault-list.html"


def _version() -> str:
    spec = importlib.util.spec_from_file_location(
        "spine_cooling_runtime",
        SRC / "__init__.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load src/__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.__version__)


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _require() -> None:
    codes = [rule.code for rule in RULES]
    if len(codes) != len(set(codes)):
        raise RuntimeError("RULES has a duplicate fault")
    if set(codes) != set(FaultCode):
        raise RuntimeError("RULES does not list every fault code")
    if set(FAULTS) != set(FaultCode):
        raise RuntimeError("FAULTS does not list every fault code")
    for code, fault in FAULTS.items():
        if fault.code is not code:
            raise RuntimeError(f"{code.value} catalog entry is mis-keyed")
        if not fault.message or not fault.causes or not fault.steps:
            raise RuntimeError(f"{code.value} is missing message, causes, or steps")
    for rule in RULES:
        if not rule.when.strip():
            raise RuntimeError(f"{rule.code.value} is missing a when sentence")


def _class_label(severity: Severity) -> tuple[str, str]:
    if severity is Severity.STOP:
        return "Stop", "badge stop"
    if severity is Severity.MESSAGE:
        return "Message", "badge warn"
    raise RuntimeError(f"No label for {severity.value}")


def _items(values: tuple[str, ...], field: str) -> str:
    lines = "".join(f"<li>{_esc(item)}</li>" for item in values)
    return f'<ul data-field="{field}">{lines}</ul>'


def html() -> str:
    """Standalone list of every fault the runtime can raise."""
    _require()
    rows: list[str] = []
    for rule in listed_faults():
        fault = get_fault(rule.code)
        label, badge = _class_label(fault.severity)
        ack = "Required" if fault.ack_required else "Not required"
        rows.append(
            "\n".join(
                [
                    f'<tr data-code="{_esc(rule.code.value)}" '
                    f'data-severity="{_esc(fault.severity.value)}" '
                    f'data-ack="{"true" if fault.ack_required else "false"}">',
                    f'<td data-field="code">{_esc(rule.code.value)}</td>',
                    f'<td data-field="message">{_esc(fault.message)}</td>',
                    f'<td data-field="class"><span class="{badge}">{label}</span></td>',
                    f'<td data-field="acknowledge">{ack}</td>',
                    f'<td data-field="when">{_esc(rule.when)}</td>',
                    f"<td>{_items(fault.causes, 'causes')}</td>",
                    f"<td>{_items(fault.steps, 'steps')}</td>",
                    "</tr>",
                ]
            )
        )
    body = "\n".join(
        [
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8"/>',
            "<title>Errors and warnings</title>",
            '<link rel="stylesheet" href="docs.css"/>',
            "<style>",
            ".sheet { max-width: 12.5in; }",
            "td ul { margin: 0; padding-left: 1.1em; }",
            "td li { margin: 0 0 2px; }",
            "</style>",
            "</head>",
            "<body>",
            '<div class="sheet">',
            "<header>",
            "<h1>Errors and warnings</h1>",
            "<p>Generated from src/safety_rules.py and src/fault_catalog.py. "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, version {_esc(_version())}.</p>",
            "</header>",
            "<table>",
            "<thead>",
            "<tr>",
            "<th>Code</th>",
            "<th>Message</th>",
            "<th>Class</th>",
            "<th>Acknowledge</th>",
            "<th>When it trips</th>",
            "<th>Causes</th>",
            "<th>Steps</th>",
            "</tr>",
            "</thead>",
            "<tbody>",
            *rows,
            "</tbody>",
            "</table>",
            '<p class="foot">Regenerate with python tools/generate_fault_list.py.</p>',
            "</div>",
            "</body>",
            "</html>",
            "",
        ]
    )
    return body


def write_all() -> None:
    HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(html(), encoding="utf-8", newline="\n")


def main() -> None:
    write_all()
    print(HTML_PATH.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
