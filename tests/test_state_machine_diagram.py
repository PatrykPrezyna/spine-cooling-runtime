"""The operating-state drawing matches the states and transitions in the code."""

import sys
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from state_machine import TRANSITIONS, State, StateMachine  # noqa: E402

SVG_PATH = PROJECT_ROOT / "docs" / "state-machine.svg"


def _picture() -> ET.Element:
    return ET.fromstring(SVG_PATH.read_text(encoding="utf-8"))


class StateMachineDiagramTests(unittest.TestCase):
    def test_table_is_what_the_machine_allows(self) -> None:
        pairs = {(item.source, item.target) for item in TRANSITIONS}
        self.assertEqual(len(pairs), len(TRANSITIONS))
        for source in State:
            for target in State:
                with redirect_stdout(StringIO()):
                    machine = StateMachine(ready_hold_after_startup_s=0)
                    machine.current_state = source
                    allowed = machine._change_state(target, "probe")
                self.assertEqual(allowed, (source, target) in pairs)

    def test_svg_matches_states_and_transitions(self) -> None:
        root = _picture()
        states = {element.get("data-state") for element in root.iter() if element.get("data-state")}
        self.assertEqual(states, {state.value for state in State})

        edges = [
            (element.get("data-from"), element.get("data-to"), element.get("data-label", ""))
            for element in root.iter()
            if element.get("data-from") is not None
        ]
        expected = [
            (item.source.value, item.target.value, item.label) for item in TRANSITIONS
        ]
        self.assertEqual(sorted(edges), sorted(expected))


if __name__ == "__main__":
    unittest.main()
