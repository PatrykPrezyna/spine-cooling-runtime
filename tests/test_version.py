"""The prototype has one semantic version, and it stays at 0.0.1."""

import importlib.util
import re
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from version import __version__  # noqa: E402

_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _package_version() -> str:
    spec = importlib.util.spec_from_file_location(
        "spine_cooling_runtime",
        SRC_DIR / "__init__.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load src/__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.__version__)


class VersionTests(unittest.TestCase):
    def test_prototype_stays_at_0_0_1(self) -> None:
        self.assertRegex(__version__, _SEMVER)
        self.assertEqual(__version__, "0.0.1")

    def test_package_exports_the_same_version(self) -> None:
        self.assertEqual(_package_version(), __version__)


if __name__ == "__main__":
    unittest.main()
