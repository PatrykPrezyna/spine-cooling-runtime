"""Capture UI screenshots and write a brief operator PDF.

Run from the repo root:

    python scripts/generate_operator_pdf.py
"""

from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QPixmap  # noqa: E402

from fault_catalog import FAULTS, FaultCode, Severity, operator_help  # noqa: E402
from gui import FaultHelpDialog, MainScreen  # noqa: E402

SHOT_DIR = ROOT / "docs" / "screenshots"
PDF_PATH = ROOT / "docs" / "Spine_Cooling_Operator_Guide.pdf"

TEMPS = {
    "Tip": 36.4,
    "Cartrige Out": 18.2,
    "Catheter In": 21.4,
    "Catheter Out": 24.8,
    "Cartrige In": 25.1,
    "Probe 1": 36.1,
    "Probe 2": 36.3,
    "Plate": 4.2,
}
PRESSURES = {
    "Pump In": 1.71,
    "Pump Out": 2.16,
    "Catheter In": 1.35,
    "Catheter Out": 0.98,
}
SENSORS_OK = {
    "Level Low": True,
    "Level Critical": True,
    "Cartridge In Place": True,
    "Leak Sensor": True,
}


def _load_config() -> dict:
    with (ROOT / "config.yaml").open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    config.setdefault("ui", {})
    config["ui"]["fullscreen"] = False
    return config


def _process() -> None:
    QApplication.processEvents()


def _grab(widget: QWidget, path: Path) -> Path:
    _process()
    pix: QPixmap = widget.grab()
    path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(path), "PNG")
    return path


def _seed_deque(history, n: int, builder) -> None:
    history.clear()
    now = time.monotonic()
    for i in range(n):
        history.append(builder(now - (n - i) * 2.0, i, n))


def _seed_graphs(ui: MainScreen) -> None:
    n = 90
    set_temp = ui.main_graph_widget.set_temperature

    def main_point(ts: float, i: int, total: int):
        frac = i / max(1, total - 1)
        csf = 36.8 - 3.2 * frac
        inlet = 22.0 + 2.5 * math.sin(frac * 4.0)
        return (ts, set_temp, csf, inlet)

    _seed_deque(ui.main_graph_widget._temp_history, n, main_point)
    ui.main_graph_widget.current_csf_temperature = TEMPS["Probe 2"]
    ui.main_graph_widget.current_catheter_in_temperature = TEMPS["Catheter In"]
    ui.main_graph_widget.current_catheter_out_temperature = TEMPS["Catheter Out"]

    temp_names = ui.temperature_sensor_names
    graph = ui.temperature_graph_tab.graph_widget

    def temp_point(ts: float, i: int, total: int):
        frac = i / max(1, total - 1)
        values = {"Set Temp": set_temp}
        for name, base in TEMPS.items():
            if name in temp_names:
                values[name] = base + 0.4 * math.sin(frac * 6 + hash(name) % 7)
        values["Probe 2"] = 36.8 - 3.2 * frac
        values["Plate"] = 12.0 - 8.0 * frac
        return (ts, values)

    _seed_deque(graph._history, n, temp_point)

    ui.pressure_service_tab.update_pressures(PRESSURES)
    ui.pressure_service_tab.update_pump_speed(pump_speed_rpm=102, flow_ml_per_min=60.0)
    pgraph = ui.pressure_service_tab.graph_widget

    def pressure_point(ts: float, i: int, total: int):
        frac = i / max(1, total - 1)
        flow = 10.0 + 50.0 * frac
        return (
            ts,
            {
                "Pump In": 1.52 + 0.21 * frac,
                "Pump Out": 1.93 + 0.28 * frac,
                "Catheter In": 1.24 + 0.14 * frac,
                "Catheter Out": 0.90 + 0.10 * frac,
                "Flow": flow,
            },
        )

    _seed_deque(pgraph._history, n, pressure_point)

    ui.power_graph_tab.update_temperatures(TEMPS)
    ui.power_graph_tab.update_pump_speed(pump_speed_rpm=102, flow_ml_per_min=60.0)
    power_graph = ui.power_graph_tab.graph_widget

    def power_point(ts: float, i: int, total: int):
        frac = i / max(1, total - 1)
        return (ts, {"Catheter": 4.0 + 8.0 * frac, "Cartridge": 6.0 + 10.0 * frac})

    _seed_deque(power_graph._history, n, power_point)

    ui.service2_tab.update_sensors(SENSORS_OK)
    ui.service2_tab.update_temperatures(TEMPS)
    ui.calibration_tab.update_current_temperatures(TEMPS, TEMPS)
    ui.temperature_graph_tab._update_checkbox_labels(
        {**TEMPS, "Set Temp": ui.main_graph_widget.set_temperature}
    )
    ui.pressure_service_tab._update_checkbox_labels({**PRESSURES, "Flow": 60.0})
    ui.power_graph_tab._update_checkbox_labels({"Catheter": 12.0, "Cartridge": 16.0})
    ui.service_tab.update_outputs(
        compressor_on=True,
        compressor_control_enabled=True,
        heat_ex_temp_c=TEMPS["Plate"],
        refresh_heat_ex=True,
        stepper_speed_rpm=102,
    )
    ui.main_graph_widget.update()
    ui.temperature_graph_tab.graph_widget.update()
    ui.pressure_service_tab.graph_widget.update()
    ui.power_graph_tab.graph_widget.update()


def _capture_all(app: QApplication, config: dict) -> list[tuple[str, str, Path]]:
    shots: list[tuple[str, str, Path]] = []
    ui = MainScreen(config)
    ui.show()
    _process()
    _seed_graphs(ui)
    _process()

    def add(name: str, title: str, caption: str) -> None:
        shots.append((title, caption, _grab(ui, SHOT_DIR / f"{name}.png")))

    ui._show_main_view()
    ui.update_state_display("Ready")
    add(
        "01_main_ready",
        "Main screen — Ready",
        "START COOLING stays disabled until the cartridge is seated and both level switches are OK.",
    )

    ui.update_state_display("Cooling")
    add(
        "02_main_cooling",
        "Main screen — Cooling",
        "The compressor is already cooling the plate. Place the catheter, set the CSF target with + / −, then press START COOLING.",
    )

    ui.update_state_display(
        "Error",
        error_message="Level sensor failure detected",
        fault_code=FaultCode.LEVEL_SENSOR,
    )
    ui.set_acknowledge_enabled(True)
    add(
        "04_main_error",
        "Main screen — Error",
        "A stop fault latches the Error state, stops pumping, and shows the message. Tap the message for help. ACKNOWLEDGE ERROR is enabled only after the fault condition has cleared.",
    )

    causes, steps = operator_help(FaultCode.LEVEL_SENSOR)
    dialog = FaultHelpDialog(ui, "Level sensor failure detected", causes, steps)
    dialog.setWindowModality(Qt.WindowModality.NonModal)
    dialog.show()
    _process()
    shots.append(
        (
            "Error help sheet",
            "Tap the error chip to open probable causes and recovery steps. Close the sheet, fix the cause, then acknowledge.",
            _grab(dialog, SHOT_DIR / "05_error_help.png"),
        )
    )
    dialog.close()

    ui.update_state_display("Cooling")
    ui.update_warnings(["Battery low"])
    add(
        "06_main_warning",
        "Main screen — warning",
        "MESSAGE-severity alerts (for example battery low) do not stop the workflow. They appear as a yellow banner until the condition clears.",
    )
    ui.update_warnings([])

    ui._show_expert_view()
    ui.expert_tab_selector.setCurrentIndex(0)
    add(
        "07_expert_temperature",
        "Expert — Temperature",
        "Read-only traces for all thermistors plus the setpoint. Toggle series on the right. House icon returns to the main screen.",
    )

    ui.expert_tab_selector.setCurrentIndex(1)
    add(
        "08_expert_pressure",
        "Expert — Pressure and Flow",
        "Catheter and pump pressures (bar) with pump flow (ml/min) on the right axis.",
    )

    ui.expert_tab_selector.setCurrentIndex(2)
    add(
        "09_expert_power",
        "Expert — Power",
        "Estimated catheter and cartridge cooling power from flow and ΔT. Use this to confirm heat is actually being extracted.",
    )

    ui.expert_tab_selector.setCurrentIndex(3)
    add(
        "10_expert_status",
        "Expert — Status",
        "Live digital inputs. HIGH / green means the switch is satisfied; LOW / red is a problem during cooling or pumping.",
    )

    ui._show_service_view()
    ui.service_tab_selector.setCurrentIndex(0)
    add(
        "11_service_manual",
        "Service — Manual Operation",
        "Reached from the gear icon on the expert page. Jog or run the pump, set flow, and enable compressor control. Do not use this during a patient session unless instructed.",
    )

    ui.service_tab_selector.setCurrentIndex(1)
    add(
        "13_service_calibration",
        "Service — Calibration",
        "Two-point temperature calibration (measured at 0 °C and 100 °C). Apply only after a controlled ice / boiling-water check.",
    )

    ui.close()
    return shots


def _build_pdf(shots: list[tuple[str, str, Path]], dest_path: Path | None = None) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image,
        KeepTogether,
        ListFlowable,
        ListItem,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    TEAL = colors.HexColor("#0e6a76")
    INK = colors.HexColor("#1b2430")
    MUTED = colors.HexColor("#51606c")
    RULE = colors.HexColor("#d5dce3")
    PAGE_W, PAGE_H = A4
    margin = 14 * mm

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "CoverTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            textColor=TEAL,
            alignment=TA_CENTER,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "CoverSub",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=11,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            "H",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=TEAL,
            spaceBefore=8,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12.5,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "ShotTitle",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            textColor=TEAL,
            spaceBefore=2,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            "Caption",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=MUTED,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "Cell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            textColor=INK,
        )
    )
    styles.add(
        ParagraphStyle(
            "CellHead",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=colors.white,
        )
    )
    styles.add(
        ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=MUTED,
        )
    )

    def header_footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(TEAL)
        canvas.rect(0, PAGE_H - 8 * mm, PAGE_W, 8 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(margin, PAGE_H - 5.5 * mm, "Spine Cooling Runtime  ·  Operator guide")
        canvas.setFillColor(RULE)
        canvas.rect(0, 0, PAGE_W, 10 * mm, fill=1, stroke=0)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(margin, 4 * mm, "Prototype — not a certified IFU")
        canvas.drawRightString(PAGE_W - margin, 4 * mm, f"{doc.page}")
        canvas.restoreState()

    story = []
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Spine Cooling Runtime", styles["CoverTitle"]))
    story.append(Paragraph("Brief operator guide  ·  Raspberry Pi medical-device prototype", styles["CoverSub"]))

    story.append(Paragraph("How to use it", styles["H"]))
    steps = [
        "The device enters <b>Cooling</b> by itself. The compressor cools the plate to −1 °C.",
        "Seat the cartridge until <b>Cartridge In Place</b> is ON. Fill until <b>Level Low</b> and <b>Level Critical</b> are OK.",
        "Place the catheter. Set the CSF target with <b>+</b> / <b>−</b> (30–35 °C).",
        "Press <b>START COOLING</b>. The pump runs closed-loop toward the setpoint.",
    ]
    story.append(
        ListFlowable(
            [ListItem(Paragraph(s, styles["Body"]), leftIndent=8, value=str(i)) for i, s in enumerate(steps, 1)],
            bulletType="1",
            start="1",
            leftIndent=14,
            bulletFontName="Helvetica-Bold",
            bulletFontSize=9,
            bulletColor=TEAL,
        )
    )

    story.append(Paragraph("Screens", styles["H"]))
    story.append(
        Paragraph(
            "Main is the treatment page. Expert is monitoring. Service can move hardware and is one extra tap away on purpose.",
            styles["Body"],
        )
    )

    usable_w = PAGE_W - 2 * margin
    img_w = usable_w
    img_h = img_w * 480 / 800

    for title, caption, path in shots:
        img = Image(str(path), width=img_w, height=img_h)
        img.hAlign = "CENTER"
        block = [Paragraph(title, styles["ShotTitle"]), img, Paragraph(caption, styles["Caption"])]
        story.append(KeepTogether(block))

    story.append(PageBreak())
    story.append(Paragraph("Error handling", styles["H"]))
    story.append(
        Paragraph(
            "<b>STOP</b> faults enter Error, stop the pump, and require ACKNOWLEDGE ERROR after the cause is gone. "
            "Tap the orange error chip for causes and steps. "
            "<b>MESSAGE</b> faults only show a yellow banner and do not change state. "
            "If several STOP faults are active, the highest-priority one is shown (I/O, level, cartridge, fridge, leak, CSF low, heat exchanger, cooling ineffective).",
            styles["Body"],
        )
    )

    header = [
        Paragraph("Fault", styles["CellHead"]),
        Paragraph("When it trips", styles["CellHead"]),
        Paragraph("What to do", styles["CellHead"]),
    ]
    rows = [header]
    trip_when = {
        FaultCode.LEVEL_SENSOR: "Cooling/Pumping and a level switch is LOW.",
        FaultCode.CARTRIDGE_REMOVED: "Cooling/Pumping and cartridge switch is OFF.",
        FaultCode.CSF_LOW_TEMP: "CSF (Probe 2) below the low-temp limit (default 28 °C).",
        FaultCode.IO_READ_FAILURE: "A sensor board or bus read failed.",
        FaultCode.BATTERY_LOW: "Reported battery below 20% (warning only).",
        FaultCode.USB_NOT_PRESENT: "USB logging is on and no SPINELOGS stick is mounted (warning only).",
        FaultCode.SD_STORAGE_LOW: "Local logs disk (SD card) has less than 1 GB free (warning only).",
        FaultCode.USB_STORAGE_LOW: "USB stick has less than 1 GB free (warning only).",
        FaultCode.FRIDGE_DEFECT: "Compressor/fridge defect flag is set.",
        FaultCode.LEAK_DETECTED: "Leak sensor stays LOW (wet). Detection can be disabled in config.",
        FaultCode.HEAT_EX_TOO_COLD: "Plate below the heat-exchanger minimum (default −10 °C).",
        FaultCode.COOLING_INEFFECTIVE: "Pump + compressor on, but CSF does not drop enough within the timeout.",
    }
    for code, fault in FAULTS.items():
        _causes, steps_t = operator_help(code)
        do = " ".join(steps_t[:2])
        sev = "STOP" if fault.severity == Severity.STOP else "WARN"
        rows.append(
            [
                Paragraph(f"<b>{fault.message}</b><br/>{code.value} · {sev}", styles["Cell"]),
                Paragraph(trip_when.get(code, "See catalog."), styles["Cell"]),
                Paragraph(do, styles["Cell"]),
            ]
        )

    table = Table(rows, colWidths=[42 * mm, 62 * mm, usable_w - 104 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), TEAL),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8fafb"), colors.white]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.3, RULE),
            ]
        )
    )
    story.append(table)

    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    dest = dest_path or PDF_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(dest),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Spine Cooling Runtime — Operator Guide",
        author="Spine Cooling Runtime",
    )
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    return dest


def main() -> int:
    os.chdir(ROOT)
    config = _load_config()
    app = QApplication.instance() or QApplication(sys.argv)
    shots = _capture_all(app, config)
    try:
        out = _build_pdf(shots, PDF_PATH)
    except PermissionError:
        fallback = PDF_PATH.with_name("Spine_Cooling_Runtime_Operator_Guide.pdf")
        out = _build_pdf(shots, fallback)
    print(f"Wrote {len(shots)} screenshots to {SHOT_DIR}")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
