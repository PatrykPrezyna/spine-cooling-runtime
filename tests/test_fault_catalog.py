"""Unit tests for the static fault catalog."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fault_catalog import (  # noqa: E402
    FaultCode,
    GENERIC_CAUSES,
    GENERIC_STEPS,
    get_fault,
    operator_help,
    operator_help_sections,
)


class FaultCatalogTests(unittest.TestCase):
    def test_every_fault_has_operator_help(self) -> None:
        for code in FaultCode:
            fault = get_fault(code)
            self.assertTrue(fault.causes, msg=code.value)
            self.assertTrue(fault.steps, msg=code.value)
            causes, steps = operator_help(code)
            self.assertEqual(causes, fault.causes)
            self.assertEqual(steps, fault.steps)

    def test_unknown_fault_uses_generic_help(self) -> None:
        causes, steps = operator_help(None)
        self.assertEqual(causes, GENERIC_CAUSES)
        self.assertEqual(steps, GENERIC_STEPS)

    def test_help_sections_list_every_active_fault(self) -> None:
        sections = operator_help_sections(
            [FaultCode.CARTRIDGE_REMOVED, FaultCode.LEVEL_SENSOR],
            fallback_code=FaultCode.CSF_LOW_TEMP,
        )
        self.assertEqual(
            [title for title, _, _ in sections],
            [
                get_fault(FaultCode.CARTRIDGE_REMOVED).message,
                get_fault(FaultCode.LEVEL_SENSOR).message,
            ],
        )

    def test_help_sections_fall_back_to_latched_fault(self) -> None:
        sections = operator_help_sections(
            [],
            fallback_code=FaultCode.LEAK_DETECTED,
            fallback_title="ignored",
        )
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0][0], get_fault(FaultCode.LEAK_DETECTED).message)

    def test_help_sections_without_a_code_use_the_banner_title(self) -> None:
        sections = operator_help_sections([], fallback_title="Initialization failed")
        self.assertEqual(sections[0][0], "Initialization failed")
        self.assertEqual(sections[0][1], GENERIC_CAUSES)


if __name__ == "__main__":
    unittest.main()
