"""Tests for incremental USB mirroring of session CSVs."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from session_log_paths import usb_enabled, usb_volume_label  # noqa: E402
from usb_log_mirror import (  # noqa: E402
    STATE_MIRRORING,
    STATE_SAFE_TO_REMOVE,
    STATE_WAITING,
    UsbLogMirror,
    append_new_bytes,
    find_volume_mount,
)


class AppendNewBytesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_copies_only_new_bytes(self) -> None:
        source = self.root / "src.csv"
        dest = self.root / "usb" / "src.csv"
        source.write_bytes(b"header\n")
        self.assertEqual(append_new_bytes(source, dest), 7)
        self.assertEqual(dest.read_bytes(), b"header\n")

        source.write_bytes(b"header\nrow1\n")
        self.assertEqual(append_new_bytes(source, dest), 5)
        self.assertEqual(dest.read_bytes(), b"header\nrow1\n")
        self.assertEqual(append_new_bytes(source, dest), 0)

    def test_rewrites_if_destination_is_longer(self) -> None:
        source = self.root / "src.csv"
        dest = self.root / "usb" / "src.csv"
        dest.parent.mkdir()
        source.write_bytes(b"abc")
        dest.write_bytes(b"abcdef")
        self.assertEqual(append_new_bytes(source, dest), 3)
        self.assertEqual(dest.read_bytes(), b"abc")


class FindVolumeMountTests(unittest.TestCase):
    def test_override_path_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = {"logging": {"usb": {"mount_path": tmp}}}
            self.assertEqual(find_volume_mount(config), Path(tmp))
        missing = {"logging": {"usb": {"mount_path": "/no/such/usb-stick"}}}
        self.assertIsNone(find_volume_mount(missing))

    def test_empty_override_is_ignored(self) -> None:
        self.assertIsNone(find_volume_mount({"logging": {"usb": {"mount_path": ""}}}))


class UsbLogMirrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.source = self.root / "logs"
        self.usb = self.root / "usb"
        self.source.mkdir()
        self.usb.mkdir()
        self._mount: Path | None = self.usb
        self._unmounts: list[Path] = []
        self._events: list[tuple[str, str]] = []
        self.config = {
            "logging": {
                "directory": str(self.source),
                "usb": {
                    "enabled": True,
                    "volume_label": "SPINELOGS",
                    "destination_subdir": "logs",
                    "interval_s": 0.2,
                },
            }
        }
        self.mirror = UsbLogMirror(
            self.config,
            source_directory=self.source,
            find_mount=lambda: self._mount,
            unmount=self._fake_unmount,
            on_event=lambda event, message: self._events.append((event, message)),
        )

    def _fake_unmount(self, mount: Path) -> tuple[bool, str]:
        self._unmounts.append(mount)
        return True, f"unmounted {mount}"

    def tearDown(self) -> None:
        self.mirror.stop()
        self._tmpdir.cleanup()

    def test_disabled_does_not_start(self) -> None:
        config = {"logging": {"usb": {"enabled": False}}}
        mirror = UsbLogMirror(config, source_directory=self.source)
        self.assertFalse(usb_enabled(config))
        mirror.start()
        self.assertFalse(mirror.is_running)
        self.assertEqual(mirror.status().state, "disabled")

    def test_mirrors_session_csvs_incrementally(self) -> None:
        (self.source / "20260819_140000_sensors.csv").write_text("h\n", encoding="utf-8")
        self.mirror.start()
        self._wait_for(lambda: (self.usb / "logs" / "20260819_140000_sensors.csv").exists())
        dest = self.usb / "logs" / "20260819_140000_sensors.csv"
        self.assertEqual(dest.read_text(encoding="utf-8"), "h\n")

        (self.source / "20260819_140000_sensors.csv").write_text("h\n1\n", encoding="utf-8")
        (self.source / "20260819_140000_status_and_errors.csv").write_text(
            "e\n", encoding="utf-8"
        )
        self._wait_for(
            lambda: dest.read_text(encoding="utf-8") == "h\n1\n"
            and (self.usb / "logs" / "20260819_140000_status_and_errors.csv").exists()
        )
        self.assertEqual(self.mirror.status().state, STATE_MIRRORING)
        self.assertTrue(self.mirror.status().can_eject)

    def test_waiting_when_usb_absent(self) -> None:
        self._mount = None
        self.mirror.start()
        time.sleep(0.3)
        self.assertEqual(self.mirror.status().state, STATE_WAITING)
        self.assertFalse(self.mirror.status().can_eject)

    def test_eject_stops_copy_until_unplug_and_replug(self) -> None:
        (self.source / "a.csv").write_text("one\n", encoding="utf-8")
        self.mirror.start()
        dest = self.usb / "logs" / "a.csv"
        self._wait_for(dest.exists)
        self.mirror.request_eject()
        self._wait_for(lambda: self.mirror.status().state == STATE_SAFE_TO_REMOVE)
        self.assertEqual(self._unmounts, [self.usb])

        (self.source / "a.csv").write_text("one\ntwo\n", encoding="utf-8")
        time.sleep(0.4)
        self.assertEqual(dest.read_text(encoding="utf-8"), "one\n")

        self._mount = None
        time.sleep(0.4)
        self._mount = self.usb
        self._wait_for(lambda: dest.read_text(encoding="utf-8") == "one\ntwo\n")

    def test_stop_copies_remaining_bytes(self) -> None:
        source = self.source / "late.csv"
        source.write_text("abc\n", encoding="utf-8")
        self.mirror.start()
        self._wait_for(lambda: (self.usb / "logs" / "late.csv").exists())
        source.write_text("abc\ndef\n", encoding="utf-8")
        self.mirror.stop()
        self.assertEqual(
            (self.usb / "logs" / "late.csv").read_text(encoding="utf-8"),
            "abc\ndef\n",
        )

    def test_volume_label_default(self) -> None:
        self.assertEqual(usb_volume_label({}), "SPINELOGS")

    def _wait_for(self, predicate, timeout_s: float = 3.0) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                if predicate():
                    return
            except OSError:
                pass
            time.sleep(0.05)
        self.fail(f"condition not met within {timeout_s}s")


class UsbStatusUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt6.QtWidgets import QApplication
        except Exception as exc:
            raise unittest.SkipTest(f"PyQt6 unavailable on this host: {exc}") from exc
        cls._app = QApplication.instance() or QApplication([])

    def test_service_tab_eject_button_tracks_status(self) -> None:
        from gui import ServiceTab

        tab = ServiceTab()
        clicked = []
        tab.on_usb_eject_callback = lambda: clicked.append(True)
        tab.update_usb_status("waiting", "Waiting for USB labeled SPINELOGS", False)
        self.assertFalse(tab.usb_eject_button.isEnabled())
        tab.update_usb_status("mirroring", "Copying to /media/pi/SPINELOGS", True)
        self.assertTrue(tab.usb_eject_button.isEnabled())
        self.assertIn("Copying", tab.usb_status_label.text())
        tab.usb_eject_button.click()
        self.assertEqual(clicked, [True])
        tab.update_usb_status("safe_to_remove", "USB safe to remove", False)
        self.assertFalse(tab.usb_eject_button.isEnabled())
        self.assertEqual(tab.usb_status_label.text(), "USB safe to remove")


if __name__ == "__main__":
    unittest.main()
