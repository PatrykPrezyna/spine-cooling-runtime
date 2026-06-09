"""Second-window UI for runtime sensor injection during testing."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from sensor_injection import SensorInjectionController


class SensorOverrideWindow(QMainWindow):
    """Desktop test window for overwriting sensor inputs at runtime."""

    _WINDOW_STYLE = """
        QMainWindow {
            background-color: #f3f4f6;
        }
        QGroupBox {
            font-weight: bold;
            border: 2px solid #cbd5e1;
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 8px;
            background-color: white;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }
    """

    def __init__(self, config: dict, controller: SensorInjectionController):
        super().__init__()
        self.config = config
        self.controller = controller

        self._digital_value_checks: dict[str, QCheckBox] = {}
        self._digital_simulate_checks: dict[str, QCheckBox] = {}
        self._temp_spins: dict[str, QDoubleSpinBox] = {}
        self._temp_simulate_checks: dict[str, QCheckBox] = {}
        self._pressure_spins: dict[str, QDoubleSpinBox] = {}
        self._pressure_simulate_checks: dict[str, QCheckBox] = {}

        self.setWindowTitle("Sensor Override (Test UI)")
        self.resize(480, 640)
        self.setStyleSheet(self._WINDOW_STYLE)

        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(central)
        self.setCentralWidget(scroll)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(self._build_digital_group())
        layout.addWidget(self._build_temperature_group())
        layout.addWidget(self._build_pressure_group())
        layout.addStretch()

    def _build_digital_group(self) -> QGroupBox:
        group = QGroupBox("Digital Sensors")
        grid = QGridLayout()
        grid.addWidget(QLabel("Sensor"), 0, 0)
        grid.addWidget(QLabel("HIGH"), 0, 1)
        grid.addWidget(QLabel("Simulate"), 0, 2)

        for index, name in enumerate(self.controller.digital_names):
            row = index + 1
            value_check = QCheckBox()
            value_check.setChecked(True)
            value_check.toggled.connect(lambda _checked, n=name: self._on_digital_value_changed(n))

            simulate_check = QCheckBox("Simulate")
            simulate_check.toggled.connect(lambda enabled, n=name: self._on_digital_simulate_toggled(n, enabled))

            self._digital_value_checks[name] = value_check
            self._digital_simulate_checks[name] = simulate_check

            grid.addWidget(QLabel(name), row, 0)
            grid.addWidget(value_check, row, 1)
            grid.addWidget(simulate_check, row, 2)

        group.setLayout(grid)
        return group

    def _build_temperature_group(self) -> QGroupBox:
        group = QGroupBox("Temperatures (raw °C)")
        grid = QGridLayout()
        grid.addWidget(QLabel("Channel"), 0, 0)
        grid.addWidget(QLabel("Value"), 0, 1)
        grid.addWidget(QLabel("Simulate"), 0, 2)

        for index, label in enumerate(self.controller.temperature_labels):
            row = index + 1
            spin = QDoubleSpinBox()
            spin.setRange(-20.0, 80.0)
            spin.setDecimals(1)
            spin.setSingleStep(0.5)
            spin.setFixedWidth(90)
            spin.setValue(25.0)
            spin.valueChanged.connect(lambda _v, lbl=label: self._on_temperature_changed(lbl))

            simulate_check = QCheckBox("Simulate")
            simulate_check.toggled.connect(
                lambda enabled, lbl=label: self._on_temperature_simulate_toggled(lbl, enabled)
            )

            self._temp_spins[label] = spin
            self._temp_simulate_checks[label] = simulate_check

            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(spin, row, 1)
            grid.addWidget(simulate_check, row, 2)

        group.setLayout(grid)
        return group

    def _build_pressure_group(self) -> QGroupBox:
        group = QGroupBox("Pressures")
        grid = QGridLayout()
        grid.addWidget(QLabel("Channel"), 0, 0)
        grid.addWidget(QLabel("Value"), 0, 1)
        grid.addWidget(QLabel("Simulate"), 0, 2)

        for index, label in enumerate(self.controller.pressure_labels):
            row = index + 1
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 400.0)
            spin.setDecimals(1)
            spin.setSingleStep(1.0)
            spin.setFixedWidth(90)
            spin.setValue(100.0)
            spin.valueChanged.connect(lambda _v, lbl=label: self._on_pressure_changed(lbl))

            simulate_check = QCheckBox("Simulate")
            simulate_check.toggled.connect(
                lambda enabled, lbl=label: self._on_pressure_simulate_toggled(lbl, enabled)
            )

            self._pressure_spins[label] = spin
            self._pressure_simulate_checks[label] = simulate_check

            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(spin, row, 1)
            grid.addWidget(simulate_check, row, 2)

        group.setLayout(grid)
        return group

    def _on_digital_simulate_toggled(self, name: str, enabled: bool) -> None:
        value_check = self._digital_value_checks.get(name)
        if value_check is None:
            return
        if enabled:
            self.controller.set_digital(name, value_check.isChecked())
        else:
            self.controller.clear_override("digital", name)

    def _on_digital_value_changed(self, name: str) -> None:
        simulate_check = self._digital_simulate_checks.get(name)
        value_check = self._digital_value_checks.get(name)
        if simulate_check is None or value_check is None:
            return
        if simulate_check.isChecked():
            self.controller.set_digital(name, value_check.isChecked())

    def _on_temperature_simulate_toggled(self, label: str, enabled: bool) -> None:
        spin = self._temp_spins.get(label)
        if spin is None:
            return
        if enabled:
            self.controller.set_temperature_raw(label, float(spin.value()))
            self.controller._sync_thermocouple_inner()
        else:
            self.controller.clear_override("temperature", label)
            self.controller._sync_thermocouple_inner()

    def _on_temperature_changed(self, label: str) -> None:
        simulate_check = self._temp_simulate_checks.get(label)
        spin = self._temp_spins.get(label)
        if simulate_check is None or spin is None:
            return
        if simulate_check.isChecked():
            self.controller.set_temperature_raw(label, float(spin.value()))
            self.controller._sync_thermocouple_inner()

    def _on_pressure_simulate_toggled(self, label: str, enabled: bool) -> None:
        spin = self._pressure_spins.get(label)
        if spin is None:
            return
        if enabled:
            self.controller.set_pressure(label, float(spin.value()))
        else:
            self.controller.clear_override("pressure", label)

    def _on_pressure_changed(self, label: str) -> None:
        simulate_check = self._pressure_simulate_checks.get(label)
        spin = self._pressure_spins.get(label)
        if simulate_check is None or spin is None:
            return
        if simulate_check.isChecked():
            self.controller.set_pressure(label, float(spin.value()))
