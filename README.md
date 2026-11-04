# 当牛作马的计时器

命令行工具保持无第三方依赖；桌面窗口使用 PyQt6。数据保存在同目录的 `work_hours.json`。

## 每天录入

```bash
python3 work_time.py add
```

按提示输入日期、上班时间、下班时间和休息起止时间；直接按 Enter 可使用默认值。也可以一次输入完整参数：

```bash
python3 work_time.py add --date 2026-11-03 --start 09:00 --end 18:30 --break-start 12:00 --break-end 13:30
```

支持 `--date today`、`--date yesterday`。下班时间早于上班时间时，会自动按跨天计算。休息不足 90 分钟按 90 分钟计算，超过 90 分钟按实际时间计算；旧数据中的休息分钟数会继续兼容。

## 查看一周

```bash
python3 work_time.py show
```

显示指定日期所在自然周（周一至周日）的明细、总工时、与 52 小时目标的差距和日均工时。查看某一周：

```bash
python3 work_time.py show --week 2026-11-03
```

## 周目标设置

```bash
python3 work_time.py target
python3 work_time.py target --hours 52
python3 work_time.py target --coefficient 1.3
```

目标工时和目标系数基于 40 小时联动：修改任意一项，另一项都会同步保存。设置保存在 `work_settings.json`，命令行和桌面窗口共用。

## 桌面窗口

```bash
python3 work_time_gui.py
```

如果通过 Miniconda 运行且提示缺少 `GLIBCXX_3.4.29`，直接使用：

```bash
./start_gui.sh
```

窗口会自动监测当前日期和时间，实时刷新时钟；跨天时自动更新今日高亮，跨周时自动切换到新的周一至周日记录表。界面支持编辑本周 7 天的上下班时间和休息起止时间，并在右侧“TARGET // 周目标”中修改目标工时或目标系数，两项会实时联动并更新进度。左侧的“打卡”按钮会自动填入当前时间：第一次填上班时间，第二次填下班时间，并自动保存工时。休息不足 90 分钟按 90 分钟计算，超过 90 分钟按实际时间计算。所有修改会保存到同一个 `work_hours.json`。
