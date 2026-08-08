"""flet-charts 图表构建辅助。

统一封装 flet-charts 的 LineChart / BarChart，供四个页面使用。
"""

from __future__ import annotations

import flet_charts as fc


def equity_line_chart(data: list[float], color: str = "blue") -> fc.LineChart:
    """权益/活筹曲线（x=序号, y=数值）。"""
    points = [
        fc.LineChartDataPoint(x=float(i), y=float(v))
        for i, v in enumerate(data)
    ]
    series = fc.LineChartData(points=points, color=color, stroke_width=2)
    return fc.LineChart(
        data_series=[series],
        height=180,
        left_axis=fc.ChartAxis(),
        bottom_axis=fc.ChartAxis(),
    )


def ac_line_chart(data: list[dict], color: str = "green") -> fc.LineChart:
    """活筹曲线（date/value 序列，x=序号）。"""
    points = [
        fc.LineChartDataPoint(x=float(i), y=float(row["value"]))
        for i, row in enumerate(data)
    ]
    series = fc.LineChartData(points=points, color=color, stroke_width=2)
    return fc.LineChart(
        data_series=[series],
        height=180,
        left_axis=fc.ChartAxis(),
        bottom_axis=fc.ChartAxis(),
    )


def distribution_bar_chart(counts: dict[str, int], color: str = "orange") -> fc.BarChart:
    """信号类型分布条形图（label -> count）。"""
    groups = []
    for i, (label, count) in enumerate(counts.items()):
        groups.append(
            fc.BarChartGroup(
                x=i,
                rods=[fc.BarChartRod(to_y=float(count), color=color)],
            )
        )
    return fc.BarChart(
        groups=groups,
        height=200,
        left_axis=fc.ChartAxis(),
        bottom_axis=fc.ChartAxis(),
    )


def layers_bar_chart(
    layers: list[dict], color: str = "purple"
) -> fc.BarChart:
    """仓位三层目标占比条形图（layer -> target_amount）。"""
    groups = []
    for i, layer in enumerate(layers):
        groups.append(
            fc.BarChartGroup(
                x=i,
                rods=[fc.BarChartRod(to_y=float(layer.get("target_amount", 0)), color=color)],
            )
        )
    return fc.BarChart(
        groups=groups,
        height=200,
        left_axis=fc.ChartAxis(),
        bottom_axis=fc.ChartAxis(),
    )
