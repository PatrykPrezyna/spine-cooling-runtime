"""The Pi halt command is only built on Linux."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from system_shutdown import raspberry_pi_halt_command  # noqa: E402


class SystemShutdownTests(unittest.TestCase):
    def test_command_matches_the_host(self) -> None:
        command = raspberry_pi_halt_command()
        if sys.platform != "linux":
            self.assertIsNone(command)
            return
        self.assertIn("shutdown", command)
        self.assertIn("-h", command)
        self.assertIn("now", command)


if __name__ == "__main__":
    unittest.main()
