# -*- coding: utf-8 -*-
"""
calculator.py —— 功能1：智能计算系统
====================================
输入：预计处理货物量、可用作业时间、目标利用率
输出：自动计算出需要的 拣选人员 / AMR搬运机器人 / 打包工作台 数量，
      并给出每个环节的实际利用率、瓶颈环节提示。
同时支持"反算产能"：给定资源配置，估算一个班次最多能处理多少货物。

核心公式（单环节）：
    理论需求量 = 货物量 × 单件作业时间 ÷ 可用时间 ÷ 目标利用率
    建议配置   = ceil(理论需求量 × 安全系数)
    实际利用率 = 货物量 × 单件作业时间 ÷ 可用时间 ÷ 建议配置
    环节产能   = 资源数量 × 可用时间 × 目标利用率 ÷ 单件作业时间
    系统产能   = min(各环节产能)   ← 木桶效应，取最短的那块板
"""

import math
import pandas as pd

from sim_core import DEFAULT_STAGE_TIMES

# 环节中文名（与仿真资源名一一对应）
STAGE_NAMES = {
    "picker": "拣选",
    "amr": "AMR搬运",
    "pack_station": "打包",
}

# 示例成本参数（元/台·班次），用于决策建议与预算校验，可在网页上修改
DEFAULT_COSTS = {
    "picker": 200.0,      # 每名拣选人员一个班次成本
    "amr": 500.0,         # 每台AMR一个班次成本
    "pack_station": 300.0,# 每个打包工作台一个班次成本
}


def calculate_resources(
    goods_count: float,          # 预计处理货物量（件）
    work_time_min: float,        # 可用作业时间（分钟），如 480
    target_utilization: float,   # 目标资源利用率（0~1），如 0.85
    stage_times: dict = None,    # 单件作业时间，默认取 sim_core 口径
    safety_factor: float = 1.0,  # 安全系数（>1 多配一点，应对波动）
) -> pd.DataFrame:
    """
    正向计算：给定目标处理量 → 各环节所需资源数量
    返回 DataFrame，包含：环节 / 单件时间 / 理论需求量 / 建议配置 / 实际利用率 / 是否瓶颈
    """
    stage_times = stage_times or dict(DEFAULT_STAGE_TIMES)
    rows = []
    util_list = []
    for stage, unit_time in stage_times.items():
        # 单环节总工时需求（分钟）
        total_work_min = goods_count * unit_time
        # 可用时间不变，目标利用率决定有效产能
        theory = total_work_min / work_time_min / target_utilization
        needed = max(1, math.ceil(theory * safety_factor))
        actual_util = total_work_min / work_time_min / needed
        rows.append({
            "环节": STAGE_NAMES.get(stage, stage),
            "资源名称": stage,
            "单件作业时间(分钟)": unit_time,
            "总工时需求(分钟)": round(total_work_min, 1),
            "理论需求量": round(theory, 2),
            "建议配置": needed,
            "实际利用率": round(actual_util, 4),
        })
        util_list.append((stage, actual_util))

    df = pd.DataFrame(rows)
    # 瓶颈环节 = 实际利用率最高（离目标最近）的环节
    bottleneck = max(util_list, key=lambda x: x[1])[0]
    df["是否瓶颈"] = df["资源名称"].apply(lambda s: "★" if s == bottleneck else "")
    return df


def estimate_capacity(
    resources: dict,             # 资源配置，如 {"picker": 3, "amr": 4, "pack_station": 2}
    work_time_min: float = 480,  # 可用作业时间（分钟）
    target_utilization: float = 0.85,
    stage_times: dict = None,
) -> tuple:
    """
    反算产能：给定资源配置 → 估算一个班次最多能处理多少货物
    返回 (各环节产能 DataFrame, 系统产能)
    """
    stage_times = stage_times or dict(DEFAULT_STAGE_TIMES)
    rows = []
    caps = {}
    for stage, n in resources.items():
        cap = n * work_time_min * target_utilization / stage_times.get(stage, 1.0)
        caps[stage] = cap
        rows.append({
            "环节": STAGE_NAMES.get(stage, stage),
            "资源数量": n,
            "单件作业时间(分钟)": stage_times.get(stage, 1.0),
            "环节产能(件/班次)": round(cap, 1),
        })
    df = pd.DataFrame(rows)
    system_cap = min(caps.values()) if caps else 0.0
    return df, system_cap


def estimate_cost(resources: dict, costs: dict = None) -> float:
    """按示例单价估算一个班次的资源总成本"""
    costs = costs or DEFAULT_COSTS
    total = 0.0
    for stage, n in resources.items():
        total += n * costs.get(stage, 0.0)
    return total


# ==================== 本地测试 ====================
if __name__ == "__main__":
    print("=" * 60)
    print("测试1：目标处理 1000 件货物，480 分钟，目标利用率 85%")
    print("=" * 60)
    df_req = calculate_resources(goods_count=1000, work_time_min=480,
                                 target_utilization=0.85)
    print(df_req.to_string(index=False))

    print("\n" + "=" * 60)
    print("测试2：给定配置 3人/4台/2台，反算产能")
    print("=" * 60)
    df_cap, sys_cap = estimate_capacity({"picker": 3, "amr": 4, "pack_station": 2})
    print(df_cap.to_string(index=False))
    print(f"系统产能（木桶短板）= {sys_cap:.1f} 件/班次")

    print("\n✅ calculator.py 测试通过！")
