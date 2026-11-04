#!/usr/bin/env python3.12
"""Record daily clock-in/clock-out times and summarize one week."""

import argparse
import json
import unicodedata
from typing import Dict, Optional, Union
from datetime import date, datetime, time, timedelta
from pathlib import Path


DATA_FILE = Path(__file__).resolve().parent / "work_hours.json"
SETTINGS_FILE = Path(__file__).resolve().parent / "work_settings.json"
DAILY_TARGET_HOURS = 8
MINIMUM_BREAK_MINUTES = 90
BASE_WEEKLY_HOURS = 40.0
DEFAULT_WEEKLY_TARGET_HOURS = 52.0


def parse_date(value: str) -> date:
    aliases = {
        "today": date.today(),
        "yesterday": date.today() - timedelta(days=1),
        "tomorrow": date.today() + timedelta(days=1),
    }
    if value.lower() in aliases:
        return aliases[value.lower()]
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("日期格式应为 YYYY-MM-DD") from error


def parse_time(value: str) -> time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as error:
        raise argparse.ArgumentTypeError("时间格式应为 HH:MM，例如 09:00") from error


def effective_break_minutes(break_start_text: str, break_end_text: str) -> int:
    break_start = datetime.strptime(break_start_text, "%H:%M")
    break_end = datetime.strptime(break_end_text, "%H:%M")
    if break_end <= break_start:
        break_end += timedelta(days=1)
    return max(MINIMUM_BREAK_MINUTES, int((break_end - break_start).total_seconds() // 60))


def load_records() -> Dict[str, dict]:
    if not DATA_FILE.exists():
        return {}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        raise SystemExit(f"无法读取 {DATA_FILE}: {error}") from error
    if not isinstance(data, dict):
        raise SystemExit(f"数据文件格式错误：{DATA_FILE} 顶层必须是对象")
    return data


def save_records(records: Dict[str, dict]) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_settings() -> Dict[str, float]:
    if not SETTINGS_FILE.exists():
        return {"weekly_target_hours": DEFAULT_WEEKLY_TARGET_HOURS, "weekly_target_coefficient": DEFAULT_WEEKLY_TARGET_HOURS / BASE_WEEKLY_HOURS}
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as file:
            settings = json.load(file)
    except (json.JSONDecodeError, OSError):
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    target = settings.get("weekly_target_hours")
    coefficient = settings.get("weekly_target_coefficient")
    if not isinstance(target, (int, float)) or not isinstance(coefficient, (int, float)) or target <= 0 or coefficient <= 0:
        return {"weekly_target_hours": DEFAULT_WEEKLY_TARGET_HOURS, "weekly_target_coefficient": DEFAULT_WEEKLY_TARGET_HOURS / BASE_WEEKLY_HOURS}
    coefficient = round(target / BASE_WEEKLY_HOURS, 2)
    return {"weekly_target_hours": float(target), "weekly_target_coefficient": coefficient}


def save_settings(weekly_target_hours: Optional[float] = None, weekly_target_coefficient: Optional[float] = None) -> None:
    settings = load_settings()
    if weekly_target_coefficient is not None:
        if weekly_target_coefficient <= 0:
            raise ValueError("系数必须大于 0")
        coefficient = round(weekly_target_coefficient, 2)
        target = round(BASE_WEEKLY_HOURS * coefficient, 2)
    elif weekly_target_hours is not None:
        if weekly_target_hours <= 0:
            raise ValueError("目标工时必须大于 0")
        coefficient = round(weekly_target_hours / BASE_WEEKLY_HOURS, 2)
        target = round(BASE_WEEKLY_HOURS * coefficient, 2)
    else:
        target = settings["weekly_target_hours"]
    settings = {
        "weekly_target_hours": target,
        "weekly_target_coefficient": round(target / BASE_WEEKLY_HOURS, 2),
    }
    try:
        with SETTINGS_FILE.open("w", encoding="utf-8") as file:
            json.dump(settings, file, ensure_ascii=False, indent=2)
            file.write("\n")
    except OSError as error:
        raise SystemExit(f"无法写入 {SETTINGS_FILE}: {error}") from error


def ask(prompt: str, parser, default: str) -> str:
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        value = raw or default
        try:
            parser(value)
            return value
        except (argparse.ArgumentTypeError, ValueError) as error:
            print(f"输入无效：{error}")


def calculate_hours(
    work_date: date,
    start_text: str,
    end_text: str,
    break_start_text: str,
    break_end_text: str,
    fallback_break_minutes: Optional[Union[str, int]] = None,
) -> float:
    if not break_start_text and not break_end_text:
        break_minutes = max(MINIMUM_BREAK_MINUTES, int(fallback_break_minutes or MINIMUM_BREAK_MINUTES))
    else:
        break_minutes = effective_break_minutes(break_start_text, break_end_text)
    start = datetime.combine(work_date, parse_time(start_text))
    end = datetime.combine(work_date, parse_time(end_text))
    if end <= start:
        end += timedelta(days=1)
    duration = end - start - timedelta(minutes=break_minutes)
    if duration <= timedelta(0):
        raise ValueError("计算结果无效：扣除休息后的工作时间必须大于 0")
    return duration.total_seconds() / 3600


def working_hours(record: Dict[str, Union[str, int]]) -> float:
    work_date = date.fromisoformat(str(record["date"]))
    return calculate_hours(
        work_date,
        str(record["start"]),
        str(record["end"]),
        str(record.get("break_start", "")),
        str(record.get("break_end", "")),
        str(record.get("break_minutes", MINIMUM_BREAK_MINUTES)),
    )


def normalize_record(work_date: date, start: str, end: str, break_start: str, break_end: str) -> dict:
    start_time = parse_time(start)
    end_time = parse_time(end)
    break_minutes = effective_break_minutes(break_start, break_end)
    start_dt = datetime.combine(work_date, start_time)
    end_dt = datetime.combine(work_date, end_time)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    duration = end_dt - start_dt
    if duration <= timedelta(minutes=break_minutes):
        raise ValueError("计算结果无效：上下班之间必须留出大于休息时间的工时")
    return {
        "date": work_date.isoformat(),
        "start": start_time.strftime("%H:%M"),
        "end": end_time.strftime("%H:%M"),
        "break_start": break_start,
        "break_end": break_end,
        "break_minutes": break_minutes,
    }


def display_width(value: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in ("F", "W") else 1 for char in value)


def align(value: str, width: int, right: bool = False) -> str:
    padding = max(0, width - display_width(value))
    spaces = " " * padding
    return spaces + value if right else value + spaces


def show_row(date_text: str, weekday: str, start: str, end: str, break_text: str, hours: str) -> None:
    print("  ".join([
        align(date_text, 10),
        align(weekday, 4),
        align(start, 5),
        align(end, 5),
        align(break_text, 15),
        align(hours, 6, right=True),
    ]))


def add_record(args: argparse.Namespace) -> None:
    work_date = args.date
    if args.start is None:
        args.start = ask("上班时间", parse_time, "09:00")
    if args.end is None:
        args.end = ask("下班时间", parse_time, "18:00")
    if args.break_start is None:
        args.break_start = ask("休息开始", parse_time, "12:00")
    if args.break_end is None:
        args.break_end = ask("休息结束", parse_time, "13:30")

    record = normalize_record(work_date, args.start, args.end, args.break_start, args.break_end)
    records = load_records()
    existed = work_date.isoformat() in records
    records[work_date.isoformat()] = record
    save_records(records)
    hours = working_hours(record)
    action = "已更新" if existed else "已记录"
    print(f"{action}：{work_date.isoformat()}，工作 {hours:.2f} 小时")


def show_week(args: argparse.Namespace) -> None:
    monday = args.week - timedelta(days=args.week.weekday())
    dates = [monday + timedelta(days=offset) for offset in range(7)]
    records = load_records()
    weekly_target = load_settings()["weekly_target_hours"]

    print(f"\n周区间：{dates[0].isoformat()} 至 {dates[-1].isoformat()}")
    show_row("日期", "星期", "上班", "下班", "休息", "工时")
    print("-" * 54)

    total_hours = 0.0
    recorded_days = 0
    for work_date in dates:
        key = work_date.isoformat()
        weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
        if key not in records:
            show_row(key, weekday_names[work_date.weekday()], "--", "--", "--", "--")
            continue
        record = records[key]
        break_display = "--"
        if record.get("break_start") and record.get("break_end"):
            break_display = f"{record['break_start']}-{record['break_end']}"
        elif record.get("break_minutes") is not None:
            break_display = f"{record['break_minutes']}分"
        hours = working_hours(record)
        total_hours += hours
        recorded_days += 1
        show_row(key, weekday_names[work_date.weekday()], record["start"], record["end"], break_display, f"{hours:.2f}h")

    print("-" * 54)
    print(f"本周合计：{total_hours:.2f} 小时（目标 {weekly_target:.2f} 小时）")
    difference = total_hours - weekly_target
    status = "多出" if difference >= 0 else "还差"
    print(f"与目标差距：{status} {abs(difference):.2f} 小时")
    if recorded_days:
        print(f"已记录 {recorded_days} 天，日均 {total_hours / recorded_days:.2f} 小时")
    print(f"数据文件：{DATA_FILE}\n")


def set_target(args: argparse.Namespace) -> None:
    if args.hours is not None and args.coefficient is not None:
        raise ValueError("目标工时和系数只能选择一个设置")
    if args.hours is None and args.coefficient is None:
        settings = load_settings()
        print(f"周目标：{settings['weekly_target_hours']:.2f} 小时")
        print(f"系数：{settings['weekly_target_coefficient']:.2f}")
        return
    save_settings(weekly_target_hours=args.hours, weekly_target_coefficient=args.coefficient)
    settings = load_settings()
    print(f"已保存周目标：{settings['weekly_target_hours']:.2f} 小时")
    print(f"已保存系数：{settings['weekly_target_coefficient']:.2f}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="按天记录上下班时间并汇总每周工时")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="录入或覆盖某一天的工作时间")
    add_parser.add_argument("--date", type=parse_date, default=date.today(), help="日期，默认今天")
    add_parser.add_argument("--start", help="上班时间，格式 HH:MM")
    add_parser.add_argument("--end", help="下班时间，格式 HH:MM")
    add_parser.add_argument("--break-start", help="休息开始时间，格式 HH:MM")
    add_parser.add_argument("--break-end", help="休息结束时间，格式 HH:MM")
    add_parser.set_defaults(func=add_record)

    show_parser = subparsers.add_parser("show", help="显示包含指定日期的周一到周日汇总")
    show_parser.add_argument("--week", type=parse_date, default=date.today(), help="该日期所在周，默认本周")
    show_parser.set_defaults(func=show_week)

    target_parser = subparsers.add_parser("target", help="查看或设置每周目标工时")
    target_parser.add_argument("--hours", type=float, help="每周目标工时，例如 52")
    target_parser.add_argument("--coefficient", type=float, help="相对 40 小时的系数，例如 1.3")
    target_parser.set_defaults(func=set_target)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
