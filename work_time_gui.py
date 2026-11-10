#!/usr/bin/env python3
"""PyQt6 desktop dashboard for weekly working-time records."""

import json
import os
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


DATA_FILE = Path(__file__).resolve().parent / "work_hours.json"
SETTINGS_FILE = Path(__file__).resolve().parent / "work_settings.json"
HEALTH_DATA_FILE = Path(__file__).resolve().parent / "work_health.json"
DRINK_IMAGE_FILE = Path(__file__).resolve().parent / "assets" / "drink.png"
STAND_IMAGE_FILE = Path(__file__).resolve().parent / "assets" / "move.png"
WEEKLY_IMAGE_FILE = Path(__file__).resolve().parent / "assets" / "ccp.png"
MINIMUM_BREAK_MINUTES = 90
BASE_WEEKLY_HOURS = 40.0
DEFAULT_WEEKLY_TARGET_HOURS = 52.0
WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
DAY_NAMES = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")


def parse_clock(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def effective_break_minutes(break_start_text: str, break_end_text: str) -> Optional[int]:
    if not break_start_text or not break_end_text:
        return MINIMUM_BREAK_MINUTES
    try:
        break_start = parse_clock(break_start_text)
        break_end = parse_clock(break_end_text)
    except ValueError:
        return None
    base = date(2000, 1, 1)
    start = datetime.combine(base, break_start)
    end = datetime.combine(base, break_end)
    if end <= start:
        end += timedelta(days=1)
    return max(MINIMUM_BREAK_MINUTES, int((end - start).total_seconds() // 60))


def calculate_hours(
    start_text: str,
    end_text: str,
    break_start_text: str = "",
    break_end_text: str = "",
    fallback_break_minutes: Optional[int] = None,
) -> Optional[float]:
    if not start_text or not end_text:
        return None
    try:
        start = parse_clock(start_text)
        end = parse_clock(end_text)
    except ValueError:
        return None
    break_minutes = effective_break_minutes(break_start_text, break_end_text)
    if break_minutes == MINIMUM_BREAK_MINUTES and fallback_break_minutes is not None:
        break_minutes = max(MINIMUM_BREAK_MINUTES, int(fallback_break_minutes))
    base = date(2000, 1, 1)
    start_dt = datetime.combine(base, start)
    end_dt = datetime.combine(base, end)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    duration = end_dt - start_dt - timedelta(minutes=break_minutes)
    return duration.total_seconds() / 3600 if duration.total_seconds() > 0 else None


def load_records() -> dict:
    if not DATA_FILE.exists():
        return {}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            records = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return records if isinstance(records, dict) else {}


def save_records(records: dict) -> bool:
    try:
        with DATA_FILE.open("w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)
            file.write("\n")
        return True
    except OSError:
        return False


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {
            "weekly_target_hours": DEFAULT_WEEKLY_TARGET_HOURS,
            "weekly_target_coefficient": DEFAULT_WEEKLY_TARGET_HOURS / BASE_WEEKLY_HOURS,
        }
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as file:
            settings = json.load(file)
    except (OSError, json.JSONDecodeError):
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    target = settings.get("weekly_target_hours")
    if not isinstance(target, (int, float)) or target <= 0:
        return {
            "weekly_target_hours": DEFAULT_WEEKLY_TARGET_HOURS,
            "weekly_target_coefficient": DEFAULT_WEEKLY_TARGET_HOURS / BASE_WEEKLY_HOURS,
        }
    return {
        "weekly_target_hours": float(target),
        "weekly_target_coefficient": round(float(target) / BASE_WEEKLY_HOURS, 2),
    }


def save_settings(settings: dict) -> bool:
    try:
        with SETTINGS_FILE.open("w", encoding="utf-8") as file:
            json.dump(settings, file, ensure_ascii=False, indent=2)
            file.write("\n")
        return True
    except OSError:
        return False


def load_health_record() -> dict:
    today = date.today().isoformat()
    try:
        with HEALTH_DATA_FILE.open("r", encoding="utf-8") as file:
            record = json.load(file)
    except (OSError, json.JSONDecodeError):
        record = {}
    if not isinstance(record, dict) or record.get("date") != today:
        return {"date": today, "drink": {"count": 0, "last": None}, "stand": {"count": 0, "last": None}}
    result = {"date": today}
    for name in ("drink", "stand"):
        value = record.get(name, {})
        if not isinstance(value, dict):
            value = {}
        count = value.get("count", 0)
        last = value.get("last")
        result[name] = {
            "count": count if isinstance(count, int) and count >= 0 else 0,
            "last": last if isinstance(last, str) else None,
        }
    return result


def save_health_record(record: dict) -> bool:
    try:
        with HEALTH_DATA_FILE.open("w", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False, indent=2)
            file.write("\n")
        return True
    except OSError:
        return False


class RingWidget(QWidget):
    def __init__(self, caption: str = "", color: str = "#ff4d4f", image_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.caption = caption
        self.color = QColor(color)
        self.image = QPixmap(str(image_path)) if image_path else QPixmap()
        self.progress = 0.0
        self.center_text = "0%"
        self.setFixedSize(160, 204)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_progress(self, value: float, text: str) -> None:
        self.progress = max(0.0, min(value, 100.0))
        self.center_text = text
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), 150)
        margin = 12
        diameter = size - margin * 2
        left = (self.width() - diameter) // 2
        top = 12
        track = QPen(QColor("#224567"), 8)
        painter.setPen(track)
        painter.drawArc(left, top, diameter, diameter, 0, 360 * 16)
        pen = QPen(self.color, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        span = int(-360 * 16 * self.progress / 100)
        painter.drawArc(left, top, diameter, diameter, 90 * 16, span)

        image_size = int(diameter * 0.58)
        if not self.image.isNull():
            scaled = self.image.scaled(
                image_size,
                image_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap((self.width() - scaled.width()) // 2, top + (diameter - scaled.height()) // 2, scaled)
        else:
            painter.setPen(QColor("#e8f6ff"))
            painter.setFont(QFont("DejaVu Sans Mono", 13, QFont.Weight.Bold))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.center_text)

        if self.image:
            painter.setPen(QColor("#e8f6ff"))
            painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Weight.Bold))
            painter.drawText(0, top + diameter + 14, self.width(), 22, Qt.AlignmentFlag.AlignHCenter, self.center_text)
        painter.end()


class HealthRingWidget(QWidget):
    def __init__(self, title: str, color: str, image_path: Path, parent=None):
        super().__init__(parent)
        self.title = title
        self.color = QColor(color)
        self.image = QPixmap(str(image_path))
        self.count = 0
        self.last = None
        self.progress = 0.0
        self.setFixedSize(190, 212)
        self.clicked_callback = None

    def set_record(self, count: int, last: Optional[datetime]) -> None:
        self.count = count
        self.last = last
        self.tick()

    def tick(self) -> None:
        now = datetime.now()
        if self.last is None:
            minute_start = now.replace(minute=0, second=0, microsecond=0)
            elapsed = (now - minute_start).total_seconds()
        else:
            elapsed = (now - self.last).total_seconds()
            if elapsed < 0:
                elapsed = 0
        self.progress = min(elapsed / 3600, 1)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            center = QPointF(self.width() / 2, 30 + 132 / 2)
            radius = 132 / 2 + 8
            if QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2).contains(event.position()):
                if self.clicked_callback:
                    self.clicked_callback()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#e8f6ff"))
        painter.setFont(QFont("Noto Sans CJK SC", 10, QFont.Weight.Bold))
        painter.drawText(0, 0, self.width(), 22, Qt.AlignmentFlag.AlignHCenter, self.title)

        diameter = 132
        left = (self.width() - diameter) // 2
        top = 30
        track = QPen(QColor("#224567"), 9)
        painter.setPen(track)
        painter.drawArc(left, top, diameter, diameter, 0, 360 * 16)
        pen = QPen(self.color, 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        span = int(-360 * 16 * self.progress)
        painter.drawArc(left, top, diameter, diameter, 90 * 16, span)

        image_size = 82
        if not self.image.isNull():
            scaled = self.image.scaled(
                image_size,
                image_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap((self.width() - scaled.width()) // 2, top + (diameter - scaled.height()) // 2, scaled)

        painter.setPen(QColor("#e8f6ff"))
        painter.setFont(QFont("Noto Sans CJK SC", 9, QFont.Weight.Bold))
        painter.drawText(0, top + diameter + 2, self.width(), 20, Qt.AlignmentFlag.AlignHCenter, f"今日 {self.count} 次")
        remaining = max(0, 3600 - int(self.progress * 3600))
        painter.setPen(QColor("#7aa6c5"))
        painter.setFont(QFont("DejaVu Sans Mono", 8))
        painter.drawText(0, top + diameter + 20, self.width(), 16, Qt.AlignmentFlag.AlignHCenter, f"剩余 {remaining // 60:02d}:{remaining % 60:02d}")
        painter.end()


class WorkTimeWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.monday = self.get_monday(date.today())
        self.records = load_records()
        self.row_inputs = []
        self.settings = load_settings()
        self.health_record = load_health_record()
        self.setWindowTitle("当牛作马的计时器")
        self.resize(1180, 1080)
        self.setMinimumSize(1060, 1020)
        self.build_ui()
        self.load_and_update_health()
        self.render_rows()
        self.refresh_summary()
        self.update_clock()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_clock)
        self.timer.start(1000)

    def get_monday(self, value: date) -> date:
        return value - timedelta(days=value.weekday())

    def build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(16)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        title_box = QVBoxLayout()
        title = QLabel("当牛作马的计时器 // WORK TIME")
        title.setObjectName("title")
        self.week_label = QLabel()
        self.week_label.setObjectName("muted")
        title_box.addWidget(title)
        title_box.addWidget(self.week_label)
        header_layout.addLayout(title_box)
        header_layout.addStretch(1)
        clock_box = QVBoxLayout()
        self.clock_label = QLabel("00:00:00")
        self.clock_label.setObjectName("clock")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.date_label = QLabel()
        self.date_label.setObjectName("muted")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        clock_box.addWidget(self.clock_label)
        clock_box.addWidget(self.date_label)
        header_layout.addLayout(clock_box)
        layout.addWidget(header)

        main_columns = QHBoxLayout()
        main_columns.setSpacing(16)
        layout.addLayout(main_columns)
        left_panel = QVBoxLayout()
        left_panel.setSpacing(16)
        main_columns.addLayout(left_panel, 7)
        right_panel = QVBoxLayout()
        right_panel.setSpacing(16)
        main_columns.addLayout(right_panel, 4)

        table_group = QGroupBox("DAILY RECORDS // 每日记录")
        table_group.setObjectName("card")
        self.table_group = table_group
        left_panel.addWidget(table_group)
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(14, 18, 14, 14)
        table_layout.setSpacing(10)
        self.table_columns = (
            ("日期", 12, 104),
            ("上班", 9, 72),
            ("下班", 9, 72),
            ("休息开始", 10, 78),
            ("休息结束", 10, 78),
            ("工时", 8, 64),
            ("打卡", 8, 68),
            ("保存", 8, 68),
        )
        self.rows_widget = QWidget()
        self.rows_widget.setObjectName("tableGrid")
        self.rows_layout = QVBoxLayout(self.rows_widget)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(10)
        header_widget = QWidget()
        header_widget.setObjectName("tableHeader")
        header_widget.setFixedHeight(42)
        header_layout = QGridLayout(header_widget)
        header_layout.setContentsMargins(8, 0, 8, 2)
        header_layout.setSpacing(10)
        for column, (text, stretch, minimum_width) in enumerate(self.table_columns):
            label = QLabel(text)
            label.setObjectName("column")
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            header_layout.addWidget(label, 0, column)
            header_layout.setColumnStretch(column, stretch)
            header_layout.setColumnMinimumWidth(column, minimum_width)
        table_layout.addWidget(header_widget)
        table_layout.addWidget(self.rows_widget)
        table_layout.addStretch(1)

        health_group = QGroupBox("HEALTH // 饮水与站立")
        health_group.setObjectName("card")
        health_layout = QHBoxLayout(health_group)
        health_layout.setContentsMargins(14, 16, 14, 14)
        health_layout.setSpacing(16)
        self.health_rings = {}
        for name, title, color, image_path in (
            ("drink", "饮水打卡", "#39a9ff", DRINK_IMAGE_FILE),
            ("stand", "站立打卡", "#4fd1c5", STAND_IMAGE_FILE),
        ):
            ring = HealthRingWidget(title, color, image_path, health_group)
            ring.clicked_callback = lambda health_name=name: self.clock_health(health_name)
            button = QPushButton("打卡")
            button.setObjectName("secondary")
            button.clicked.connect(lambda checked=False, health_name=name: self.clock_health(health_name))
            box = QVBoxLayout()
            box.setSpacing(6)
            box.addWidget(ring, 1, Qt.AlignmentFlag.AlignHCenter)
            button.setFixedWidth(86)
            box.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            health_layout.addLayout(box, 1)
            self.health_rings[name] = ring
        table_layout.addWidget(health_group)

        overview_group = QGroupBox("WEEKLY OVERVIEW // 本周总览")
        overview_group.setObjectName("card")
        right_panel.addWidget(overview_group)
        overview_layout = QHBoxLayout(overview_group)
        overview_layout.setContentsMargins(16, 16, 16, 8)
        overview_layout.setSpacing(18)
        self.ring = RingWidget("weekly", "#ff4d4f", WEEKLY_IMAGE_FILE)
        overview_layout.addWidget(self.ring)
        progress_box = QVBoxLayout()
        progress_box.setSpacing(4)
        self.total_label = QLabel("0.0 H")
        self.total_label.setObjectName("metric")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.percent_label = QLabel("已完成 37.1%")
        self.percent_label.setObjectName("muted")
        self.remaining_label = QLabel("剩余 32.7 H")
        self.remaining_label.setObjectName("muted")
        self.recorded_label = QLabel("记录 0 / 7 天")
        self.recorded_label.setObjectName("muted")
        self.daily_label = QLabel("日均 0.0 H")
        self.daily_label.setObjectName("muted")
        progress_box.addWidget(self.total_label)
        progress_box.addWidget(self.progress)
        progress_box.addWidget(self.percent_label)
        progress_box.addWidget(self.remaining_label)
        progress_box.addWidget(self.recorded_label)
        progress_box.addWidget(self.daily_label)
        progress_box.addStretch(1)
        overview_layout.addLayout(progress_box, 1)

        controls_group = QGroupBox("DATA // 数据")
        controls_group.setObjectName("card")
        right_panel.addWidget(controls_group)
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setContentsMargins(16, 18, 16, 16)
        controls_layout.setSpacing(12)
        refresh_button = QPushButton("刷新本地数据")
        refresh_button.setObjectName("primary")
        refresh_button.clicked.connect(self.load_and_render)
        open_button = QPushButton("打开数据文件")
        open_button.setObjectName("primary")
        open_button.clicked.connect(self.open_data_file)
        controls_layout.addWidget(refresh_button)
        controls_layout.addWidget(open_button)
        self.message_label = QLabel("数据文件：work_hours.json")
        self.message_label.setObjectName("muted")
        self.message_label.setWordWrap(True)
        controls_layout.addWidget(self.message_label)

        month_group = QGroupBox("MONTHLY // 月工时")
        month_group.setObjectName("card")
        month_group.setMinimumHeight(380)
        right_panel.addWidget(month_group)
        month_layout = QVBoxLayout(month_group)
        month_layout.setContentsMargins(16, 18, 16, 8)
        month_layout.setSpacing(10)
        self.month_columns = (
            ("周区间", 10, 126),
            ("记录天数", 5, 58),
            ("周工时", 5, 58),
            ("系数", 6, 70),
        )
        self.month_title_label = QLabel()
        self.month_title_label.setObjectName("muted")
        self.month_table = QTableWidget(0, len(self.month_columns), month_group)
        self.month_table.setObjectName("monthTable")
        self.month_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.month_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.month_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.month_table.setShowGrid(False)
        self.month_table.setAlternatingRowColors(True)
        self.month_table.verticalHeader().setVisible(False)
        self.month_table.verticalHeader().setDefaultSectionSize(32)
        self.month_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.month_table.horizontalHeader().setStretchLastSection(False)
        for column, (text, _, width) in enumerate(self.month_columns):
            item = self.month_table.horizontalHeaderItem(column)
            if item is None:
                item = QTableWidgetItem(text)
                self.month_table.setHorizontalHeaderItem(column, item)
            else:
                item.setText(text)
            self.month_table.setColumnWidth(column, width)
        self.month_table.horizontalHeader().setSectionResizeMode(0, self.month_table.horizontalHeader().ResizeMode.Stretch)
        self.month_table.setFixedHeight(236)
        self.month_summary_box = QVBoxLayout()
        self.month_summary_box.setSpacing(4)
        self.month_total_label = QLabel("本月合计 0.00 小时")
        self.month_total_label.setObjectName("muted")
        self.month_average_label = QLabel("平均周工时 0.00 小时 · 系数 0.00")
        self.month_average_label.setObjectName("muted")
        self.month_daily_label = QLabel("")
        self.month_daily_label.setObjectName("muted")
        self.month_daily_label.setVisible(False)
        self.month_summary_box.addWidget(self.month_total_label)
        self.month_summary_box.addWidget(self.month_average_label)
        self.month_summary_box.addWidget(self.month_daily_label)
        month_layout.addWidget(self.month_title_label)
        month_layout.addWidget(self.month_table)
        month_layout.addLayout(self.month_summary_box)
        month_layout.addStretch(1)

        target_group = QGroupBox("TARGET // 周目标")
        target_group.setObjectName("card")
        right_panel.addWidget(target_group)
        target_layout = QGridLayout(target_group)
        target_layout.setContentsMargins(16, 18, 16, 16)
        target_layout.setHorizontalSpacing(12)
        target_layout.setVerticalSpacing(10)
        hours_title = QLabel("目标工时")
        hours_title.setObjectName("column")
        coefficient_title = QLabel("目标系数")
        coefficient_title.setObjectName("column")
        self.target_hours_input = QLineEdit(f"{self.settings['weekly_target_hours']:.2f}")
        self.target_coefficient_input = QLineEdit(f"{self.settings['weekly_target_coefficient']:.2f}")
        self.target_hours_input.setPlaceholderText("52")
        self.target_coefficient_input.setPlaceholderText("1.30")
        self.target_hours_input.editingFinished.connect(lambda: self.update_target("hours"))
        self.target_coefficient_input.editingFinished.connect(lambda: self.update_target("coefficient"))
        target_layout.addWidget(hours_title, 0, 0)
        target_layout.addWidget(coefficient_title, 0, 1)
        target_layout.addWidget(self.target_hours_input, 1, 0)
        target_layout.addWidget(self.target_coefficient_input, 1, 1)
        target_hint = QLabel("目标 = 40 小时 × 系数")
        target_hint.setObjectName("muted")
        target_layout.addWidget(target_hint, 2, 0, 1, 2)
        right_panel.addStretch(1)

    def render_rows(self) -> None:
        previous_rows = self.row_inputs
        self.row_inputs = []
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.records = load_records()
        today = date.today()
        for index in range(7):
            work_date = self.monday + timedelta(days=index)
            key = work_date.isoformat()
            record = self.records.get(key, {})
            row = QFrame()
            row.setObjectName("row")
            row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            layout = QGridLayout(row)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(10)
            for column, (_, stretch, minimum_width) in enumerate(self.table_columns):
                layout.setColumnStretch(column, stretch)
                layout.setColumnMinimumWidth(column, minimum_width)
            day_label = QLabel(f"{WEEKDAYS[index]}  {work_date.month:02d}/{work_date.day:02d}")
            day_label.setObjectName("dayLabel")
            day_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            start_input = QLineEdit(record.get("start", ""))
            end_input = QLineEdit(record.get("end", ""))
            break_start_input = QLineEdit(record.get("break_start", ""))
            break_end_input = QLineEdit(record.get("break_end", ""))
            hours_label = QLabel("--")
            hours_label.setObjectName("hoursLabel")
            hours_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            clock_button = QPushButton("打卡")
            clock_button.setObjectName("primary")
            clock_button.clicked.connect(
                lambda checked=False, row_key=key, values=(start_input, end_input, break_start_input, break_end_input), display=hours_label: self.clock_row(row_key, values, display)
            )
            save_button = QPushButton("保存")
            save_button.setObjectName("secondary")
            save_button.clicked.connect(
                lambda checked=False, row_key=key, values=(start_input, end_input, break_start_input, break_end_input), display=hours_label: self.save_row(row_key, values, display)
            )
            for input_widget in (start_input, end_input, break_start_input, break_end_input):
                input_widget.setProperty("timeInput", True)
                input_widget.installEventFilter(self)
                input_widget.editingFinished.connect(
                    lambda values=(start_input, end_input, break_start_input, break_end_input), display=hours_label: self.update_row_display(values, display)
                )
            for widget in (day_label, start_input, end_input, break_start_input, break_end_input, hours_label):
                if work_date == today:
                    widget.setProperty("today", True)
                widget.style().unpolish(widget)
                widget.style().polish(widget)
            widgets = (day_label, start_input, end_input, break_start_input, break_end_input, hours_label, clock_button, save_button)
            for column, widget in enumerate(widgets):
                layout.addWidget(widget, 0, column)
            self.rows_layout.addWidget(row)
            self.row_inputs.append(widgets)
            self.update_row_display((start_input, end_input, break_start_input, break_end_input), hours_label)
        self.update_week_label()

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() in (QEvent.Type.FocusIn, QEvent.Type.MouseButtonPress)
            and isinstance(watched, QLineEdit)
            and watched.property("timeInput") is True
        ):
            QTimer.singleShot(0, watched.selectAll)
        return super().eventFilter(watched, event)

    def update_week_label(self) -> None:
        sunday = self.monday + timedelta(days=6)
        year, week, _ = self.monday.isocalendar()
        self.week_label.setText(f"{year} · WEEK {week:02d} · {self.monday.month:02d}/{self.monday.day:02d} - {sunday.month:02d}/{sunday.day:02d}")

    def update_summary(self) -> None:
        weekly_target = self.settings["weekly_target_hours"]
        total = 0.0
        recorded = 0
        for index in range(7):
            record = self.records.get((self.monday + timedelta(days=index)).isoformat())
            if not record:
                continue
            hours = calculate_hours(
                record.get("start", ""),
                record.get("end", ""),
                record.get("break_start", ""),
                record.get("break_end", ""),
                record.get("break_minutes"),
            )
            if hours is not None:
                total += hours
                recorded += 1
        percent = min(total / weekly_target * 100, 100) if weekly_target else 0
        self.ring.set_progress(percent, f"{percent:.0f}%")
        self.total_label.setText(f"{total:.1f} H")
        self.progress.setValue(int(percent))
        self.percent_label.setText(f"已完成 {percent:.1f}%")
        self.remaining_label.setText(f"剩余 {max(0, weekly_target - total):.1f} H / {weekly_target:.2f} H")
        average = total / recorded if recorded else 0
        self.recorded_label.setText(f"记录 {recorded} / 7 天")
        self.daily_label.setText(f"日均 {average:.1f} H")
        self.update_month_summary()

    def load_and_update_health(self) -> None:
        self.health_record = load_health_record()
        for name, ring in self.health_rings.items():
            item = self.health_record[name]
            last = None
            if item["last"]:
                try:
                    last = datetime.fromisoformat(item["last"])
                except ValueError:
                    last = None
            ring.set_record(item["count"], last)

    def clock_health(self, name: str) -> None:
        now = datetime.now()
        item = self.health_record[name]
        item["count"] += 1
        item["last"] = now.isoformat(timespec="seconds")
        self.health_rings[name].set_record(item["count"], now)
        self.show_message(f"{self.health_rings[name].title}成功：今日 {item['count']} 次")
        if not save_health_record(self.health_record):
            self.show_message("健康打卡保存失败")

    def update_month_summary(self) -> None:
        month_start = date.today().replace(day=1)
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_month - timedelta(days=1)
        first_monday = month_start - timedelta(days=month_start.weekday())
        self.month_title_label.setText(f"月区间：{month_start.isoformat()} 至 {month_end.isoformat()}")

        month_dates = []
        week_start = first_monday
        row_index = 0
        while week_start <= month_end:
            month_dates.append(week_start)
            week_start += timedelta(days=7)
        self.month_table.setRowCount(len(month_dates))
        weekly_totals = []
        month_total = 0.0
        month_recorded = 0
        week_start = first_monday
        row_index = 0
        while week_start <= month_end:
            week_end = week_start + timedelta(days=6)
            display_start = max(week_start, month_start)
            display_end = min(week_end, month_end)
            weekly_total = 0.0
            recorded_days = 0
            for offset in range(7):
                work_date = week_start + timedelta(days=offset)
                if work_date < month_start or work_date > month_end:
                    continue
                record = self.records.get(work_date.isoformat())
                if not record:
                    continue
                hours = calculate_hours(
                    record.get("start", ""),
                    record.get("end", ""),
                    record.get("break_start", ""),
                    record.get("break_end", ""),
                    record.get("break_minutes"),
                )
                if hours is not None:
                    weekly_total += hours
                    recorded_days += 1
            weekly_totals.append(weekly_total)
            month_total += weekly_total
            month_recorded += recorded_days

            display_start = max(week_start, month_start)
            display_end = min(week_end, month_end)
            row_values = (
                f"{display_start.isoformat()} ~ {display_end.isoformat()}",
                str(recorded_days),
                f"{weekly_total:.2f}h",
                f"{weekly_total / BASE_WEEKLY_HOURS:.2f}",
            )
            for column, text in enumerate(row_values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
                self.month_table.setItem(row_index, column, item)
            row_index += 1
            week_start += timedelta(days=7)

        average_weekly_hours = sum(weekly_totals) / len(weekly_totals)
        average_coefficient = average_weekly_hours / BASE_WEEKLY_HOURS
        daily_text = ""
        if month_recorded:
            self.month_daily_label.setVisible(True)
            self.month_daily_label.setText(f"已记录 {month_recorded} 天，月平均日工时 {month_total / month_recorded:.2f} 小时")
        else:
            self.month_daily_label.setVisible(False)
        self.month_total_label.setText(f"本月合计 {month_total:.2f} 小时")
        self.month_average_label.setText(f"平均周工时 {average_weekly_hours:.2f} 小时 · 系数 {average_coefficient:.2f}")

    def clock_row(self, key: str, values, display: QLabel) -> None:
        start_input, end_input, break_start_input, break_end_input = values
        now_text = datetime.now().strftime("%H:%M")
        if not start_input.text().strip():
            start_input.setText(now_text)
            self.show_message(f"上班打卡：{now_text}")
            return
        end_input.setText(now_text)
        self.show_message(f"下班打卡：{now_text}")
        self.save_row(key, values, display)

    def update_row_display(self, values, display: QLabel) -> None:
        start_input, end_input, break_start_input, break_end_input = values
        hours = calculate_hours(
            start_input.text().strip(),
            end_input.text().strip(),
            break_start_input.text().strip(),
            break_end_input.text().strip(),
        )
        display.setText("--" if hours is None else f"{hours:.2f}h")

    def save_row(self, key: str, values, display: QLabel) -> None:
        start_input, end_input, break_start_input, break_end_input = values
        start_text = start_input.text().strip()
        end_text = end_input.text().strip()
        break_start_text = break_start_input.text().strip()
        break_end_text = break_end_input.text().strip()
        if not start_text or not end_text:
            self.show_message("上班和下班时间都需要填写")
            self.update_row_display(values, display)
            return
        break_minutes = effective_break_minutes(break_start_text, break_end_text)
        if break_minutes is None:
            self.show_message("休息时间格式应为 HH:MM")
            return
        hours = calculate_hours(start_text, end_text, break_start_text, break_end_text)
        if hours is None:
            self.show_message("时间格式应为 HH:MM，且扣除休息后必须大于 0 小时")
        else:
            self.records[key] = {
                "date": key,
                "start": start_text,
                "end": end_text,
                "break_start": break_start_text,
                "break_end": break_end_text,
                "break_minutes": break_minutes,
            }
            self.show_message("保存成功" if save_records(self.records) else "保存失败")
        display.setText("--" if hours is None else f"{hours:.2f}h")
        self.refresh_summary()

    def refresh_summary(self) -> None:
        self.records = load_records()
        self.settings = load_settings()
        if self.target_hours_input.text().strip() != f"{self.settings['weekly_target_hours']:.2f}":
            self.target_hours_input.setText(f"{self.settings['weekly_target_hours']:.2f}")
        if self.target_coefficient_input.text().strip() != f"{self.settings['weekly_target_coefficient']:.2f}":
            self.target_coefficient_input.setText(f"{self.settings['weekly_target_coefficient']:.2f}")
        self.update_summary()

    def update_target(self, source: str) -> None:
        hours_text = self.target_hours_input.text().strip()
        coefficient_text = self.target_coefficient_input.text().strip()
        try:
            if source == "hours":
                target_hours = float(hours_text)
                if target_hours <= 0:
                    raise ValueError
                target_coefficient = round(target_hours / BASE_WEEKLY_HOURS, 2)
                target_hours = round(BASE_WEEKLY_HOURS * target_coefficient, 2)
            else:
                target_coefficient = float(coefficient_text)
                if target_coefficient <= 0:
                    raise ValueError
                target_coefficient = round(target_coefficient, 2)
                target_hours = round(BASE_WEEKLY_HOURS * target_coefficient, 2)
        except ValueError:
            self.show_message("目标工时和系数必须是大于 0 的数字")
            self.target_hours_input.setText(f"{self.settings['weekly_target_hours']:.2f}")
            self.target_coefficient_input.setText(f"{self.settings['weekly_target_coefficient']:.2f}")
            return
        settings = {
            "weekly_target_hours": target_hours,
            "weekly_target_coefficient": target_coefficient,
        }
        if not save_settings(settings):
            self.show_message("目标设置保存失败")
            return
        self.settings = settings
        self.target_hours_input.setText(f"{target_hours:.2f}")
        self.target_coefficient_input.setText(f"{target_coefficient:.2f}")
        self.show_message(f"周目标已保存：{target_hours:.2f} 小时 / {target_coefficient:.2f}")
        self.update_summary()

    def load_and_render(self) -> None:
        self.render_rows()
        self.refresh_summary()
        self.show_message("数据已刷新")

    def open_data_file(self) -> None:
        try:
            subprocess.Popen(["xdg-open", str(DATA_FILE)])
            self.show_message("正在打开数据文件")
        except OSError:
            self.show_message("无法打开数据文件")

    def show_message(self, message: str) -> None:
        self.message_label.setText(message)

    def update_clock(self) -> None:
        now = datetime.now()
        self.clock_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(f"{now.year:04d} · {now.month:02d} · {now.day:02d} {DAY_NAMES[now.weekday()]}")
        current_monday = self.get_monday(now.date())
        if current_monday != self.monday:
            self.monday = current_monday
            self.render_rows()
            self.refresh_summary()
            self.show_message("已自动切换到新的一周")
        for ring in self.health_rings.values():
            ring.tick()
        for ring in self.health_rings.values():
            ring.tick()


def build_stylesheet() -> str:
    return """
    QMainWindow, QWidget { background: #071524; color: #e8f6ff; font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; font-size: 13px; }
    #header { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #082038, stop:1 #071524); border: 1px solid #153d5f; border-radius: 14px; }
    #title { color: #e8f6ff; font-size: 17px; font-weight: 800; letter-spacing: 1px; }
    #clock { color: #39a9ff; font-family: "DejaVu Sans Mono"; font-size: 30px; font-weight: 800; }
    #muted { color: #7aa6c5; font-size: 12px; }
    #column { color: #7aa6c5; font-size: 12px; font-weight: 700; }
    QGroupBox#card { background: #082038; border: 1px solid #174c74; border-radius: 16px; margin-top: 10px; padding-top: 6px; }
    QGroupBox#card::title { subcontrol-origin: margin; left: 16px; top: 2px; padding: 0 8px; color: #9ed9ff; font-weight: 700; letter-spacing: 1px; }
    QWidget#tableGrid { background: transparent; }
    QFrame#row { background: #0a2743; border: 1px solid #174c74; border-radius: 12px; }
    QWidget#tableHeader { background: #123c5f; border-radius: 10px; max-height: 42px; }
    QWidget#tableHeader QLabel { background: transparent; color: #9ed9ff; font-size: 12px; font-weight: 700; }
    QLabel { background: transparent; }
    QLabel[today="true"] { color: #39a9ff; font-weight: 700; }
    QLineEdit { background: #071524; border: 1px solid #174c74; border-radius: 10px; padding: 8px; color: #e8f6ff; font-family: "DejaVu Sans Mono"; font-weight: 600; }
    QLineEdit:focus { border-color: #39a9ff; }
    QLabel#metric { color: #39a9ff; font-family: "DejaVu Sans Mono"; font-size: 23px; font-weight: 800; }
    QProgressBar { background: #123c5f; border-radius: 4px; }
    QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4fd1c5, stop:1 #39a9ff); border-radius: 4px; }
    QTableWidget#monthTable { background: #0a2743; alternate-background-color: #0a2743; border: 0; border-radius: 12px; gridline-color: transparent; }
    QTableWidget#monthTable::item { background: transparent; color: #e8f6ff; padding: 4px; }
    QHeaderView::section { background: #123c5f; color: #9ed9ff; border: 0; border-bottom: 1px solid #174c74; padding: 8px; font-size: 12px; font-weight: 700; }
    QTableWidget#monthTable QScrollBar:vertical { background: #0a2743; width: 8px; margin: 0; }
    QTableWidget#monthTable QScrollBar::handle:vertical { background: #174c74; border-radius: 4px; min-height: 24px; }
    QTableWidget#monthTable QScrollBar::add-line:vertical, QTableWidget#monthTable QScrollBar::sub-line:vertical { height: 0; }
    QPushButton#primary { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2684ff, stop:1 #1462b8); border: 0; border-radius: 10px; color: white; font-weight: 700; padding: 8px; }
    QPushButton#primary:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3b98ff, stop:1 #1874d5); }
    QPushButton#secondary { background: #123c5f; border: 1px solid #39a9ff; border-radius: 10px; color: #e8f6ff; font-weight: 700; padding: 8px; }
    QPushButton#secondary:hover { background: #174c74; }
    """


def main() -> None:
    application = QApplication(sys.argv)
    application.setStyleSheet(build_stylesheet())
    window = WorkTimeWindow()
    window.show()
    raise SystemExit(application.exec())


if __name__ == "__main__":
    main()
