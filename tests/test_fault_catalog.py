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


if __name__ == "__main__":
    unittest.main()
