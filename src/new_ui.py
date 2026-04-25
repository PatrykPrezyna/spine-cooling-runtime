from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QSlider, QVBoxLayout, QWidget, QFormLayout
)

class TempGraph(QWidget):
    def __init__(self):
        super().__init__()
        self.values = [36.7, 36.8, 36.8, 36.9, 37.0, 37.1, 37.0, 37.1, 37.2, 37.2, 37.1]
        self.setMinimumHeight(320)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#F8FAFB"))
        r = self.rect().adjusted(26, 26, -26, -26)

        p.setPen(QPen(QColor("#E1E6EB"), 1))
        for i in range(5):
            y = r.top() + i * r.height() / 4
            p.drawLine(int(r.left()), int(y), int(r.right()), int(y))

        min_v, max_v = 36.4, 37.6
        points = []
        for i, v in enumerate(self.values):
            x = r.left() + i * r.width() / (len(self.values) - 1)
            y = r.bottom() - ((v - min_v) / (max_v - min_v)) * r.height()
            points.append((x, y))

        p.setPen(QPen(QColor("#0E6A76"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i in range(len(points) - 1):
            p.drawLine(int(points[i][0]), int(points[i][1]), int(points[i + 1][0]), int(points[i + 1][1]))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0E6A76"))
        for x, y in points:
            p.drawEllipse(int(x - 4), int(y - 4), 8, 8)

class AdminDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced Options")
        self.setModal(True)
        self.setFixedSize(420, 280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("Calibration", QLineEdit("+0.1 °C"))
        form.addRow("Alarm band", QLineEdit("±0.5 °C"))
        form.addRow("Role / PIN", QLineEdit("••••"))
        layout.addLayout(form)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryBtn")
        close_btn.clicked.connect(self.accept)
        layout.addStretch()
        layout.addWidget(close_btn)

        self.setStyleSheet('''
            QDialog { background: #F7F9FB; color: #1D2731; font-family: "Segoe UI"; font-size: 18px; }
            QLabel { color: #42515E; }
            QLineEdit { min-height: 46px; border: 1px solid #D7DDE3; border-radius: 14px; padding: 0 12px; background: white; }
            #secondaryBtn { min-height: 54px; border-radius: 16px; background: #E9EEF2; border: 1px solid #D3D9E0; font-weight: 600; }
        ''')

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Medical UI Simple")
        self.resize(1100, 760)
        self.error_active = False
        self.pump_running = False
        self.build_ui()
        self.apply_style()
        self.update_banner()

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        self.banner = QFrame()
        self.banner.setObjectName("bannerReady")
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(14, 10, 14, 10)
        self.banner_text = QLabel()
        self.banner_text.setObjectName("bannerText")
        banner_layout.addWidget(self.banner_text)
        banner_layout.addStretch()
        self.test_error_btn = QPushButton("Test Error")
        self.test_error_btn.setObjectName("quietBtn")
        self.test_error_btn.clicked.connect(self.toggle_error)
        banner_layout.addWidget(self.test_error_btn)
        outer.addWidget(self.banner)

        content_row = QHBoxLayout()
        content_row.setSpacing(12)

        graph_card = QFrame()
        graph_card.setObjectName("card")
        graph_layout = QVBoxLayout(graph_card)
        graph_layout.setContentsMargins(14, 14, 14, 14)
        graph_layout.setSpacing(8)
        self.graph = TempGraph()
        graph_layout.addWidget(self.graph)

        temp_row = QHBoxLayout()
        self.current_label = QLabel("Current 37.2 °C")
        self.current_label.setObjectName("metric")
        self.target_label = QLabel("Target 37.0 °C")
        self.target_label.setObjectName("metricAccent")
        temp_row.addWidget(self.current_label)
        temp_row.addStretch()
        temp_row.addWidget(self.target_label)
        graph_layout.addLayout(temp_row)
        content_row.addWidget(graph_card, 3)

        slider_card = QFrame()
        slider_card.setObjectName("card")
        slider_card.setMaximumWidth(360)
        slider_layout = QVBoxLayout(slider_card)
        slider_layout.setContentsMargins(16, 14, 16, 14)
        slider_layout.setSpacing(10)
        set_temp_label = QLabel("Set temperature")
        set_temp_label.setObjectName("label")
        self.slider_value = QLabel("37.0 °C")
        self.slider_value.setObjectName("metricAccent")
        slider_layout.addWidget(set_temp_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        slider_layout.addWidget(self.slider_value, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.slider = QSlider(Qt.Orientation.Vertical)
        self.slider.setRange(340, 400)
        self.slider.setValue(370)
        self.slider.setFixedHeight(300)
        self.slider.setFixedWidth(64)
        self.slider.valueChanged.connect(self.update_target)
        slider_layout.addWidget(self.slider, alignment=Qt.AlignmentFlag.AlignHCenter)
        slider_layout.addStretch()
        content_row.addWidget(slider_card, 2)

        outer.addLayout(content_row, 1)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.setMinimumHeight(70)
        self.start_btn.clicked.connect(self.toggle_start)
        self.ack_btn = QPushButton("Acknowledge")
        self.ack_btn.setObjectName("secondaryBtn")
        self.ack_btn.setFixedHeight(56)
        self.ack_btn.setFixedWidth(220)
        self.ack_btn.clicked.connect(self.acknowledge)
        self.advanced_btn = QPushButton("⋯")
        self.advanced_btn.setObjectName("advancedBtn")
        self.advanced_btn.setFixedSize(54, 54)
        self.advanced_btn.clicked.connect(self.open_advanced)
        action_row.addWidget(self.start_btn)
        action_row.addStretch()
        action_row.addWidget(self.ack_btn)
        action_row.addWidget(self.advanced_btn)
        outer.addLayout(action_row)

    def update_target(self, value):
        text = f"{value / 10:.1f} °C"
        self.slider_value.setText(text)
        self.target_label.setText(f"Target {text}")

    def toggle_start(self):
        self.pump_running = not self.pump_running
        self.start_btn.setText("Stop" if self.pump_running else "Start")
        self.update_banner()

    def toggle_error(self):
        self.error_active = not self.error_active
        self.update_banner()

    def acknowledge(self):
        self.error_active = False
        self.update_banner()

    def update_banner(self):
        if self.error_active:
            self.banner.setObjectName("bannerError")
            self.banner_text.setText("Attention required · Temperature deviation detected")
        elif self.pump_running:
            self.banner.setObjectName("bannerActive")
            self.banner_text.setText("Running · Temperature control active")
        else:
            self.banner.setObjectName("bannerReady")
            self.banner_text.setText("Ready · No active error")
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)

    def open_advanced(self):
        dlg = AdminDialog()
        dlg.exec()

    def apply_style(self):
        self.setStyleSheet('''
            QMainWindow, QWidget {
                background: #EEF2F5;
                color: #1B2430;
                font-family: "Segoe UI";
                font-size: 18px;
            }
            #card {
                background: #F8FAFB;
                border: 1px solid #D9E0E6;
                border-radius: 22px;
            }
            #metric {
                font-size: 26px;
                font-weight: 600;
                color: #23303B;
            }
            #metricAccent {
                font-size: 26px;
                font-weight: 600;
                color: #0E6A76;
            }
            #label {
                font-size: 18px;
                font-weight: 600;
                color: #44515D;
            }
            QPushButton {
                border-radius: 18px;
                padding: 0 20px;
                font-size: 20px;
                font-weight: 600;
            }
            #primaryBtn {
                background: #0E6A76;
                color: white;
            }
            #primaryBtn:pressed {
                background: #0B565F;
            }
            #secondaryBtn {
                background: #E8EDF2;
                color: #24313D;
                border: 1px solid #D1D8DF;
            }
            #quietBtn {
                min-height: 42px;
                padding: 0 14px;
                border-radius: 14px;
                background: rgba(255,255,255,0.55);
                border: 1px solid rgba(0,0,0,0.08);
                color: #4C5A67;
                font-size: 16px;
            }
            #advancedBtn {
                background: #F8FAFB;
                border: 1px solid #D5DCE3;
                color: #51606C;
                font-size: 28px;
                font-weight: 500;
                border-radius: 16px;
            }
            QSlider::groove:horizontal {
                height: 10px;
                background: #D8E0E6;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: #0E6A76;
                border-radius: 5px;
            }
            QSlider::handle:horizontal {
                background: white;
                border: 3px solid #0E6A76;
                width: 28px;
                margin: -11px 0;
                border-radius: 14px;
            }
            QSlider::groove:vertical {
                width: 14px;
                background: #D8E0E6;
                border-radius: 7px;
            }
            QSlider::sub-page:vertical {
                background: #0E6A76;
                border-radius: 7px;
            }
            QSlider::handle:vertical {
                background: white;
                border: 3px solid #0E6A76;
                height: 34px;
                margin: 0 -11px;
                border-radius: 17px;
            }
            #bannerReady, #bannerActive, #bannerError {
                border-radius: 18px;
                border: 1px solid transparent;
            }
            #bannerReady {
                background: #E9EEF2;
                border-color: #D6DCE2;
            }
            #bannerActive {
                background: #DFF0F2;
                border-color: #C6E0E3;
            }
            #bannerError {
                background: #F8E5DB;
                border-color: #EDCDBD;
            }
            #bannerText {
                font-size: 18px;
                font-weight: 600;
            }
        ''')

if __name__ == '__main__':
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
