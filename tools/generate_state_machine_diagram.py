"""Write the operating-state diagram from ``src/state_machine.py``.

Run from the repo root:

    python tools/generate_state_machine_diagram.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from state_machine import (  # noqa: E402
    INITIAL_STATE,
    TRANSITIONS,
    State,
    Transition,
)

SPEC_DIR = ROOT / "specification-design_inputs"

# Box geometry for the figure. Arrows are derived from TRANSITIONS.
_ROW_Y = 86
_BOX_H = 46
_BOXES: dict[State, tuple[float, float, float, float]] = {
    State.INIT: (52, _ROW_Y, 132, _BOX_H),
    State.READY: (260, _ROW_Y, 136, _BOX_H),
    State.COOLING: (512, _ROW_Y, 150, _BOX_H),
    State.PUMPING: (778, _ROW_Y, 150, _BOX_H),
    State.ERROR: (260, 300, 136, _BOX_H),
}
_MAIN_ROW = (
    State.INIT,
    State.READY,
    State.COOLING,
    State.PUMPING,
)
_WIDTH = 968
_HEIGHT = 370
_BUS_Y = 214

_INK = "#1e1e1e"
_FAULT = "#9a4038"
_DASH = "#8a8175"
_FONT = "Segoe UI, sans-serif"


def _pairs() -> list[tuple[State, State]]:
    return [(item.source, item.target) for item in TRANSITIONS]


def _require_table() -> None:
    pairs = _pairs()
    if len(pairs) != len(set(pairs)):
        raise RuntimeError("TRANSITIONS has a duplicate pair")
    missing = [state for state in State if state not in _BOXES]
    if missing:
        names = ", ".join(state.value for state in missing)
        raise RuntimeError(f"Add a diagram box for {names}")
    if INITIAL_STATE not in _BOXES:
        raise RuntimeError("Add a diagram box for the initial state")


def _forward(source: State, target: State) -> bool:
    if source not in _MAIN_ROW or target not in _MAIN_ROW:
        return False
    return _MAIN_ROW.index(target) == _MAIN_ROW.index(source) + 1


def classify(item: Transition) -> str:
    """How the figure draws this transition. Every legal move has a route."""
    special = {
        (State.PUMPING, State.COOLING): "stop-pumping",
        (State.ERROR, State.READY): "acknowledge",
        (State.INIT, State.ERROR): "init-failed",
        (State.COOLING, State.READY): "back-to-ready",
        (State.PUMPING, State.READY): "pumping-to-ready",
    }
    if item.target == State.ERROR and item.label == "stop fault":
        return "bus"
    if (item.source, item.target) in special:
        return special[(item.source, item.target)]
    if item.requested and _forward(item.source, item.target):
        return "happy"
    raise RuntimeError(
        f"Add a figure route for {item.source.value} -> {item.target.value}"
    )


def _box(state: State) -> tuple[float, float, float, float]:
    return _BOXES[state]


def _mid_y(state: State) -> float:
    _, y, _, height = _box(state)
    return y + height / 2


def _cx(state: State) -> float:
    x, _, width, _ = _box(state)
    return x + width / 2


def _side(state: State, edge: str, along: float | None = None) -> tuple[float, float]:
    x, y, width, height = _box(state)
    if edge == "left":
        return x, _mid_y(state) if along is None else along
    if edge == "right":
        return x + width, _mid_y(state) if along is None else along
    if edge == "top":
        return (_cx(state) if along is None else along), y
    if edge == "bottom":
        return (_cx(state) if along is None else along), y + height
    raise ValueError(edge)


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _marker(name: str, color: str) -> str:
    return (
        f'<marker id="{name}" viewBox="0 0 8 8" refX="7.2" refY="4" '
        f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0 0 L8 4 L0 8 Z" fill="{color}"/></marker>'
    )


def _edge_attrs(item: Transition | None) -> str:
    """Attributes the unit test reads back off the picture."""
    if item is None:
        return ""
    return (
        f' data-from="{_esc(item.source.value)}"'
        f' data-to="{_esc(item.target.value)}"'
        f' data-label="{_esc(item.label)}"'
    )


def _path(
    points: list[tuple[float, float]],
    color: str,
    marker: str | None = None,
    dashed: bool = False,
    item: Transition | None = None,
) -> str:
    drawn = " ".join(
        ("M" if index == 0 else "L") + f"{x:.1f} {y:.1f}"
        for index, (x, y) in enumerate(points)
    )
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    arrow = f' marker-end="url(#{marker})"' if marker else ""
    return (
        f'<path d="{drawn}" fill="none" stroke="{color}" stroke-width="1.5"'
        f'{dash}{arrow}{_edge_attrs(item)}/>'
    )


def _label(x: float, y: float, text: str, color: str, anchor: str = "middle") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}" font-family="{_FONT}" '
        f'font-size="13" text-anchor="{anchor}" dominant-baseline="middle" '
        f'stroke="#ffffff" stroke-width="4" paint-order="stroke fill" '
        f'stroke-linejoin="round">{_esc(text)}</text>'
    )


def _happy(item: Transition) -> list[str]:
    y = _mid_y(item.source)
    x1, _ = _side(item.source, "right")
    x2, _ = _side(item.target, "left")
    parts = [_path([(x1, y), (x2, y)], _INK, "arrow", item=item)]
    if item.label:
        parts.append(_label((x1 + x2) / 2, y - 14, item.label, _INK))
    return parts


def _fault_bus(items: list[Transition]) -> list[str]:
    if not items:
        return []
    sources = [item.source for item in items]
    for source in sources:
        if source not in _MAIN_ROW:
            raise RuntimeError(f"Stop fault from {source.value} needs a bus stub")
    host = next(
        (source for source in sources if abs(_cx(source) - _cx(State.ERROR)) < 1),
        None,
    )
    if host is None:
        raise RuntimeError("Place Error under a state that takes a stop fault")
    by_source = {item.source: item for item in items}
    parts: list[str] = []
    host_x = _cx(host)
    host_bottom = _side(host, "bottom")[1]
    error_top = _side(State.ERROR, "top")[1]
    parts.append(
        _path(
            [(host_x, host_bottom), (host_x, error_top)],
            _FAULT,
            "fault",
            item=by_source[host],
        )
    )
    left = min([host_x, *(_cx(source) for source in sources)])
    right = max(_cx(source) for source in sources)
    parts.append(
        f'<path d="M {left:.1f} {_BUS_Y:.1f} L {right:.1f} {_BUS_Y:.1f}" '
        f'fill="none" stroke="{_FAULT}" stroke-width="1.5"/>'
    )
    for source in sources:
        if source == host:
            continue
        x = _cx(source)
        y = _side(source, "bottom")[1]
        parts.append(
            _path([(x, y), (x, _BUS_Y)], _FAULT, item=by_source[source])
        )
    label_x = (_cx(State.READY) + _cx(State.COOLING)) / 2
    parts.append(_label(label_x, _BUS_Y - 14, "stop fault", _FAULT))
    return parts


def _routes() -> list[str]:
    parts: list[str] = []
    faults: list[Transition] = []
    for item in TRANSITIONS:
        kind = classify(item)
        if kind == "bus":
            faults.append(item)
            continue
        if kind == "happy":
            parts.extend(_happy(item))
            continue
        parts.extend(_ROUTE[kind](item))
    parts.extend(_fault_bus(faults))
    return parts


def _stop_pumping(_item: Transition) -> list[str]:
    lane = 56
    start = _side(State.PUMPING, "top")
    end_x = _box(State.COOLING)[0] + _box(State.COOLING)[2] * 0.35
    end = _side(State.COOLING, "top", end_x)
    gap_left = _side(State.COOLING, "right")[0]
    gap_right = _side(State.PUMPING, "left")[0]
    return [
        _path([start, (start[0], lane), (end[0], lane), end], _INK, "arrow", item=_item),
        _label((gap_left + gap_right) / 2, lane - 13, "stop pumping", _INK),
    ]


def _acknowledge(_item: Transition) -> list[str]:
    x = _cx(State.ERROR) - 20
    top = _side(State.READY, "bottom")[1]
    bottom = _side(State.ERROR, "top")[1]
    label_x = _box(State.READY)[0] - 8
    return [
        _path([(x, bottom), (x, top)], _INK, "arrow", item=_item),
        _label(label_x, (top + bottom) / 2, "acknowledge", _INK, anchor="end"),
    ]


def _init_failed(_item: Transition) -> list[str]:
    start = _side(State.INIT, "bottom")
    end = _side(State.ERROR, "left")
    elbow = (start[0], end[1])
    return [
        _path([start, elbow, end], _FAULT, "fault", item=_item),
        _label((start[0] + end[0]) / 2, end[1] - 14, "init failed", _FAULT),
    ]


def _back_to_ready(_item: Transition) -> list[str]:
    y = _box(State.READY)[1] + _box(State.READY)[3] - 10
    start = _side(State.COOLING, "left", y)
    end = _side(State.READY, "right", y)
    return [_path([start, end], _DASH, "dash", dashed=True, item=_item)]


def _down_to_ready(source: State, lane_y: float, start_x: float, end_x: float, item: Transition) -> list[str]:
    """Dashed compatibility return that stays above the Error box."""
    bottom = _side(source, "bottom")[1]
    ready_bottom = _side(State.READY, "bottom")[1]
    return [
        _path(
            [(start_x, bottom), (start_x, lane_y), (end_x, lane_y), (end_x, ready_bottom)],
            _DASH,
            "dash",
            dashed=True,
            item=item,
        )
    ]


def _pumping_to_ready(item: Transition) -> list[str]:
    return _down_to_ready(State.PUMPING, 248, 820, 360, item)


_ROUTE = {
    "stop-pumping": _stop_pumping,
    "acknowledge": _acknowledge,
    "init-failed": _init_failed,
    "back-to-ready": _back_to_ready,
    "pumping-to-ready": _pumping_to_ready,
}


def _states() -> list[str]:
    parts: list[str] = []
    for state, (x, y, width, height) in _BOXES.items():
        if state == State.ERROR:
            fill, stroke, ink = "#fff4f2", _FAULT, _FAULT
        else:
            fill, stroke, ink = "#ffffff", _INK, _INK
        parts.append(
            f'<rect data-state="{_esc(state.value)}" x="{x:.1f}" y="{y:.1f}" '
            f'width="{width:.1f}" height="{height:.1f}" '
            f'rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{x + width / 2:.1f}" y="{y + height / 2:.1f}" fill="{ink}" '
            f'font-family="{_FONT}" font-size="15" text-anchor="middle" '
            f'dominant-baseline="middle">{_esc(state.value)}</text>'
        )
    return parts


def svg() -> str:
    """Standalone picture of the operating states."""
    _require_table()
    start_y = _mid_y(State.INIT)
    start_x = _box(State.INIT)[0] - 28
    init_left, _ = _side(State.INIT, "left")
    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" height="{_HEIGHT}" '
        f'viewBox="0 0 {_WIDTH} {_HEIGHT}" role="img">',
        "<title>Operating states</title>",
        f'<rect width="{_WIDTH}" height="{_HEIGHT}" fill="#ffffff"/>',
        "<defs>",
        _marker("arrow", _INK),
        _marker("fault", _FAULT),
        _marker("dash", _DASH),
        "</defs>",
        f'<circle cx="{start_x:.1f}" cy="{start_y:.1f}" r="6" fill="{_INK}"/>',
        _path([(start_x + 6, start_y), (init_left, start_y)], _INK, "arrow"),
        *_routes(),
        *_states(),
        "</svg>",
        "",
    ]
    return "\n".join(body)


SVG_PATH = ROOT / "docs" / "state-machine.svg"
_STALE = (
    SPEC_DIR / "state-machine.md",
    SPEC_DIR / "state-machine.svg",
    SPEC_DIR / "state-machine.html",
    ROOT / "docs" / "state-machine.md",
)


def write_all() -> None:
    for path in _STALE:
        if path.exists():
            path.unlink()
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text(svg(), encoding="utf-8", newline="\n")


def main() -> None:
    write_all()
    print(SVG_PATH.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
