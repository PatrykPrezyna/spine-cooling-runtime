import argparse
import logging
import queue
import signal
import sys
from pathlib import Path
import threading

from PyQt6.QtWidgets import QApplication

from spine_cooling.config import AppConfig
from spine_cooling.data_logger import DataLogger
from spine_cooling.logger import setup_logging
from spine_cooling.sensor_manager import DevelopmentSensorManager, SensorManager
from spine_cooling.compressor_controller import CompressorController
from spine_cooling.watchdog import WatchdogThread
from spine_cooling.ui import MainWindow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Spine Cooling Raspberry Pi DAQ")
    parser.add_argument("--config", default="config.yaml", help="Path to the YAML configuration file")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode")
    parser.add_argument("--desktop", action="store_true", help="Run in desktop/laptop development mode")
    return parser.parse_args()


def run_application(config_path: Path, daemonize: bool, desktop: bool = False) -> int:
    config = AppConfig.load(config_path)
    if desktop:
        config.set_run_mode("desktop")
    config.ensure_directories()
    setup_logging(config.log_path)

    logger = logging.getLogger(__name__)
    stop_event = threading.Event()

    ui_queue = queue.Queue(maxsize=100)
    logger_queue = queue.Queue(maxsize=200)

    if daemonize or config.is_desktop_mode:
        logger.info("Desktop/dev mode enabled: skipping Raspberry Pi watchdog")
    if config.is_desktop_mode:
        sensor_manager = DevelopmentSensorManager(config=config, ui_queue=ui_queue, logger_queue=logger_queue, stop_event=stop_event)
    else:
        sensor_manager = SensorManager(config=config, ui_queue=ui_queue, logger_queue=logger_queue, stop_event=stop_event)

    data_logger = DataLogger(config=config, record_queue=logger_queue, stop_event=stop_event)
    compressor_controller = CompressorController(config=config, sensor_manager=sensor_manager, stop_event=stop_event)
    watchdog = None
    if not config.is_desktop_mode:
        watchdog = WatchdogThread(
            dev_path=Path("/dev/watchdog"),
            reset_pin=config.watchdog_reset_pin,
            interval=config.watchdog_interval,
            stop_event=stop_event,
        )

    def shutdown(signum, frame):
        logger.info("Received signal %s, shutting down", signum)
        stop_event.set()
        QApplication.quit()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    sensor_manager.start()
    data_logger.start()
    compressor_controller.start()
    if watchdog is not None:
        watchdog.start()

    app = QApplication(sys.argv)
    window = MainWindow(db_path=config.db_path, live_queue=ui_queue, update_interval_ms=config.ui_update_interval)
    window.showFullScreen()

    exit_code = app.exec()
    stop_event.set()

    for thread in (sensor_manager, data_logger, compressor_controller, watchdog):
        if thread is not None:
            thread.join(timeout=3.0)

    logger.info("Application stopped")
    return int(exit_code)


def main() -> int:
    args = parse_args()
    if args.daemon:
        try:
            from daemon import DaemonContext

            with DaemonContext():
                return run_application(Path(args.config), daemonize=True, desktop=args.desktop)
        except ImportError:
            print("The python-daemon package is required for daemon mode.")
            return 1
    return run_application(Path(args.config), daemonize=False, desktop=args.desktop)


if __name__ == "__main__":
    raise SystemExit(main())
