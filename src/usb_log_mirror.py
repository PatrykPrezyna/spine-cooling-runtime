"""Background incremental copy of session CSVs onto a USB stick.

Local ``logs/`` remains the source of truth. This module never writes from
the 10 Hz / 100 Hz logging threads: a daemon loop finds a volume by label
(or an explicit mount path) and appends only the new bytes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from session_log_paths import (
    log_directory,
    usb_destination_subdir,
    usb_enabled,
    usb_interval_s,
    usb_mount_path_override,
    usb_volume_label,
)

STATE_DISABLED = "disabled"
STATE_WAITING = "waiting"
STATE_MIRRORING = "mirroring"
STATE_CATCHING_UP = "catching_up"
STATE_ERROR = "error"
STATE_EJECTING = "ejecting"
STATE_SAFE_TO_REMOVE = "safe_to_remove"

_CHUNK_SIZE = 64 * 1024
_LINUX_MOUNT_ROOTS = (
    Path("/media"),
    Path("/run/media"),
    Path("/mnt"),
)


@dataclass(frozen=True)
class UsbMirrorStatus:
    state: str
    message: str
    mount_path: Optional[str] = None
    can_eject: bool = False
    bytes_copied: int = 0
    free_bytes: Optional[int] = None


def _unescape_mount(token: str) -> str:
    return (
        token.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def _linux_mounts() -> list[tuple[Path, Path]]:
    """Return (device, mountpoint) pairs from /proc/mounts."""
    proc = Path("/proc/mounts")
    if not proc.exists():
        return []
    mounts: list[tuple[Path, Path]] = []
    try:
        text = proc.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        device = Path(_unescape_mount(parts[0]))
        mountpoint = Path(_unescape_mount(parts[1]))
        mounts.append((device, mountpoint))
    return mounts


def _linux_label_device(label: str) -> Optional[Path]:
    by_label = Path("/dev/disk/by-label") / label
    try:
        if by_label.exists():
            return by_label.resolve()
    except OSError:
        return None
    return None


def _linux_named_mount(label: str) -> Optional[Path]:
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "pi"
    candidates = [
        Path("/media") / user / label,
        Path("/media/pi") / label,
        Path("/media") / label,
        Path("/mnt") / label,
        Path("/run/media") / user / label,
    ]
    for root in _LINUX_MOUNT_ROOTS:
        if not root.exists():
            continue
        try:
            for child in root.iterdir():
                candidates.append(child / label)
                if child.name.casefold() == label.casefold():
                    candidates.append(child)
        except OSError:
            continue
    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.is_dir():
            return path
    return None


def _windows_labeled_drive(label: str) -> Optional[Path]:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
    except ImportError:
        return None
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    buf = ctypes.create_unicode_buffer(1024)
    wanted = label.casefold()
    for code in range(ord("A"), ord("Z") + 1):
        root = f"{chr(code)}:\\"
        if not os.path.isdir(root):
            continue
        try:
            ok = kernel32.GetVolumeInformationW(
                root, buf, 1024, None, None, None, None, 0
            )
        except OSError:
            continue
        if ok and buf.value.casefold() == wanted:
            return Path(root)
    return None


def find_volume_mount(config: dict[str, Any] | None) -> Optional[Path]:
    """Return the USB mount root, or None if the stick is not present."""
    override = usb_mount_path_override(config)
    if override:
        path = Path(override)
        if path.is_dir():
            return path
        return None

    label = usb_volume_label(config)
    device = _linux_label_device(label)
    if device is not None:
        try:
            resolved_device = device.resolve()
        except OSError:
            resolved_device = device
        for mount_device, mountpoint in _linux_mounts():
            try:
                if mount_device.resolve() == resolved_device:
                    return mountpoint
            except OSError:
                if mount_device == resolved_device:
                    return mountpoint

    named = _linux_named_mount(label)
    if named is not None:
        return named
    return _windows_labeled_drive(label)


def disk_free_bytes(path: Path) -> Optional[int]:
    """Return free bytes on the filesystem that contains ``path``, or None."""
    try:
        return int(shutil.disk_usage(path).free)
    except OSError:
        return None


def append_new_bytes(source: Path, dest: Path, chunk_size: int = _CHUNK_SIZE) -> int:
    """Copy bytes from ``source`` that are not yet in ``dest``. Returns count added."""
    src_size = source.stat().st_size
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest_size = dest.stat().st_size if dest.exists() else 0
    rewrite = dest_size > src_size
    if rewrite:
        dest_size = 0
    if dest_size == src_size:
        return 0

    copied = 0
    mode = "wb" if dest_size == 0 else "ab"
    with source.open("rb") as src, dest.open(mode) as dst:
        src.seek(dest_size)
        while True:
            chunk = src.read(chunk_size)
            if not chunk:
                break
            dst.write(chunk)
            copied += len(chunk)
        dst.flush()
        os.fsync(dst.fileno())
    return copied


def unmount_volume(mount: Path) -> tuple[bool, str]:
    """Flush OS buffers and unmount ``mount`` (Linux). Windows reports synced only."""
    try:
        if hasattr(os, "sync"):
            os.sync()
    except OSError:
        pass

    if sys.platform == "win32":
        return True, f"Synced to {mount}. Use Safely Remove Hardware before unplugging."

    device: Optional[Path] = None
    try:
        resolved_mount = mount.resolve()
    except OSError:
        resolved_mount = mount
    for mount_device, mountpoint in _linux_mounts():
        try:
            if mountpoint.resolve() == resolved_mount:
                device = mount_device
                break
        except OSError:
            if mountpoint == mount:
                device = mount_device
                break

    commands: list[list[str]] = []
    if device is not None:
        commands.append(["udisksctl", "unmount", "-b", str(device)])
        commands.append(["udisksctl", "power-off", "-b", str(device)])
    commands.append(["umount", str(mount)])

    errors: list[str] = []
    unmounted = False
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{command[0]}: {exc}")
            continue
        if completed.returncode == 0:
            if len(command) > 1 and command[1] == "power-off":
                continue
            unmounted = True
            continue
        detail = (completed.stderr or completed.stdout or "").strip()
        if detail:
            errors.append(detail)
    if unmounted:
        return True, f"USB unmounted ({mount})"
    return False, "; ".join(errors) or f"Failed to unmount {mount}"


class UsbLogMirror:
    """Copy growing session CSVs onto a USB stick from a background thread."""

    def __init__(
        self,
        config: dict[str, Any],
        source_directory: Optional[Path] = None,
        *,
        find_mount: Optional[Callable[[], Optional[Path]]] = None,
        unmount: Optional[Callable[[Path], tuple[bool, str]]] = None,
        on_event: Optional[Callable[[str, str], None]] = None,
        flush_sources: Optional[Callable[[], None]] = None,
    ):
        self._config = config
        self.source_directory = Path(
            source_directory if source_directory is not None else log_directory(config)
        )
        self.destination_subdir = usb_destination_subdir(config)
        self.interval_s = usb_interval_s(config)
        self.enabled = usb_enabled(config)
        self.volume_label = usb_volume_label(config)
        self._find_mount = find_mount or (lambda: find_volume_mount(self._config))
        self._unmount = unmount or unmount_volume
        self._on_event = on_event
        self._flush_sources = flush_sources

        self._stop = threading.Event()
        self._eject = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._bytes_copied = 0
        self._eject_gate_needs_absence = False
        self._eject_seen_absence = False
        self._status = UsbMirrorStatus(
            state=STATE_DISABLED if not self.enabled else STATE_WAITING,
            message=(
                "USB copy off"
                if not self.enabled
                else f"Waiting for USB labeled {self.volume_label}"
            ),
        )

    def start(self) -> None:
        if not self.enabled or self.is_running:
            return
        self._stop.clear()
        self._eject.clear()
        self._wake.clear()
        self._eject_gate_needs_absence = False
        self._eject_seen_absence = False
        self._thread = threading.Thread(
            target=self._run,
            name="usb_log_mirror",
            daemon=True,
        )
        self._thread.start()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> UsbMirrorStatus:
        with self._lock:
            return self._status

    def request_eject(self) -> None:
        if not self.enabled:
            return
        self._set_status(
            STATE_EJECTING,
            "Ejecting USB…",
            mount_path=self.status().mount_path,
            can_eject=False,
        )
        self._eject.set()
        self._wake.set()

    def stop(self) -> None:
        """Copy any remaining bytes, then stop the thread."""
        self._stop.set()
        self._eject.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=8.0)
        self._thread = None
        if self.enabled:
            self._copy_available(final=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._eject.is_set():
                self._eject.clear()
                if self._stop.is_set():
                    break
                self._handle_eject()
            else:
                self._copy_available(final=False)
            self._wake.wait(self.interval_s)
            self._wake.clear()

    def _handle_eject(self) -> None:
        mount = self._active_mount()
        self._copy_available(final=True)
        if mount is None:
            self._set_status(
                STATE_WAITING,
                f"Waiting for USB labeled {self.volume_label}",
                can_eject=False,
            )
            self._emit("usb", "Eject requested but no USB was mounted")
            return
        ok, message = self._unmount(mount)
        self._eject_gate_needs_absence = True
        self._eject_seen_absence = False
        if ok:
            self._set_status(
                STATE_SAFE_TO_REMOVE,
                "USB safe to remove",
                mount_path=str(mount),
                can_eject=False,
            )
        else:
            self._set_status(
                STATE_ERROR,
                f"Synced; eject failed ({message})",
                mount_path=str(mount),
                can_eject=True,
            )

    def _copy_available(self, *, final: bool) -> None:
        if self._flush_sources is not None:
            try:
                self._flush_sources()
            except Exception:
                pass
        mount = self._active_mount()
        if mount is None:
            current = self.status().state
            if current == STATE_DISABLED:
                return
            if current == STATE_EJECTING:
                return
            if current == STATE_SAFE_TO_REMOVE and not self._eject_seen_absence:
                return
            self._set_status(
                STATE_WAITING,
                f"Waiting for USB labeled {self.volume_label}",
                can_eject=False,
            )
            return

        dest_root = mount / self.destination_subdir if self.destination_subdir else mount
        try:
            dest_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._set_status(
                STATE_ERROR,
                f"USB not writable: {exc}",
                mount_path=str(mount),
                can_eject=True,
            )
            self._emit("usb", f"USB not writable: {exc}")
            return

        copied_this_pass = 0
        pending = False
        try:
            sources = sorted(self.source_directory.glob("*.csv"))
            for source in sources:
                dest = dest_root / source.name
                added = append_new_bytes(source, dest)
                copied_this_pass += added
                src_size = source.stat().st_size
                dest_size = dest.stat().st_size if dest.exists() else 0
                if dest_size < src_size:
                    pending = True
        except OSError as exc:
            self._set_status(
                STATE_ERROR,
                f"USB copy failed: {exc}",
                mount_path=str(mount),
                can_eject=True,
            )
            self._emit("usb", f"USB copy failed: {exc}")
            return

        if copied_this_pass:
            with self._lock:
                self._bytes_copied += copied_this_pass

        if pending and not final:
            state = STATE_CATCHING_UP
            message = f"Catching up on {mount}"
        else:
            state = STATE_MIRRORING
            message = f"Copying to {mount}"
        self._set_status(
            state,
            message,
            mount_path=str(mount),
            can_eject=True,
            free_bytes=disk_free_bytes(mount),
        )

    def _active_mount(self) -> Optional[Path]:
        try:
            mount = self._find_mount()
        except Exception:
            mount = None
        if not self._eject_gate_needs_absence:
            return mount
        if mount is None:
            self._eject_seen_absence = True
            return None
        if self._eject_seen_absence:
            self._eject_gate_needs_absence = False
            self._eject_seen_absence = False
            return mount
        return None

    def _set_status(
        self,
        state: str,
        message: str,
        *,
        mount_path: Optional[str] = None,
        can_eject: bool = False,
        free_bytes: Optional[int] = None,
    ) -> None:
        with self._lock:
            previous = self._status.state
            if free_bytes is None and mount_path:
                free_bytes = disk_free_bytes(Path(mount_path))
            self._status = UsbMirrorStatus(
                state=state,
                message=message,
                mount_path=mount_path,
                can_eject=can_eject,
                bytes_copied=self._bytes_copied,
                free_bytes=free_bytes,
            )
            changed = previous != state
        if changed and state in (
            STATE_ERROR,
            STATE_SAFE_TO_REMOVE,
            STATE_MIRRORING,
            STATE_CATCHING_UP,
        ):
            if previous in (
                STATE_WAITING,
                STATE_ERROR,
                STATE_SAFE_TO_REMOVE,
                STATE_EJECTING,
                STATE_DISABLED,
            ) or state in (STATE_ERROR, STATE_SAFE_TO_REMOVE):
                self._emit("usb", message)

    def _emit(self, event: str, message: str) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event, message)
        except Exception:
            pass
