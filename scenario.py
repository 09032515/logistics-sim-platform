# -*- coding: utf-8 -*-
"""
scenario.py —— 功能4：多方案对比分析
=====================================
预置多套资源配置方案，对每个方案做批量仿真（复用 sim_core.run_batch_simulation），
横向对比 KPI，帮助选择最优配置。

预置方案：
  基础配置 / 增加拣选 / 增加AMR / 增加打包台 / 均衡强化
用户可以勾选 2~5 个方案参与对比。
"""

import pandas as pd

from sim_core import run_batch_simulation, summary_to_dict

# 预置方案（资源名与仿真设置一致）
SCENARIOS = {
    "基础配置": {"picker_num": 2, "pack_station_num": 1, "amr_num": 3},
    "增加拣选": {"picker_num": 3, "pack_station_num": 1, "amr_num": 3},
    "增加AMR": {"picker_num": 2, "pack_station_num": 1, "amr_num": 4},
    "增加打包台": {"picker_num": 2, "pack_station_num": 2, "amr_num": 3},
    "均衡强化": {"picker_num": 3, "pack_station_num": 2, "amr_num": 4},
}


def run_scenario_comparison(
    selected: list,            # 勾选的方案名列表
    base_settings: dict,       # 全局基础设置（时间模型、到达模式等）
    n_runs: int = 10,          # 每个方案的重复次数
    seed: int = 42,
    progress_cb=None,          # (当前方案序号, 总数, 当前次数, 总次数)
    order_arrival_list=None,   # 固定到达模式下的订单时刻列表
) -> pd.DataFrame:
    """
    对每个方案跑 n_runs 次批量仿真，返回对比表：
      行 = 方案名；列 = 各KPI的均值
    """
    compare_rows = {}
    total = len(selected)
    for idx, name in enumerate(selected, 1):
        settings = dict(base_settings)
        settings.update(SCENARIOS.get(name, {}))
        if progress_cb:

            def cb(i, n, _name=name, _idx=idx, _total=total):
                progress_cb(_idx, _total, i, n)

            _, df_summary = run_batch_simulation(settings, n_runs=n_runs,
                                                 seed=seed + idx * 100,
                                                 order_arrival_list=order_arrival_list,
                                                 progress_cb=cb)
        else:
            _, df_summary = run_batch_simulation(settings, n_runs=n_runs,
                                                 seed=seed + idx * 100,
                                                 order_arrival_list=order_arrival_list)
        compare_rows[name] = summary_to_dict(df_summary)
    compare_df = pd.DataFrame(compare_rows).T
    return compare_df


def recommend_scenario(compare_df: pd.DataFrame) -> str:
    """
    简单加权评分推荐最优方案：
      吞吐量(越高越好) × 0.4 + 平均周期倒数(越高越好) × 0.3
      + 平均等待倒数(越高越好) × 0.3
    """
    if compare_df is None or len(compare_df) == 0:
        return "暂无对比数据。"
    score = pd.Series(0.0, index=compare_df.index)
    if "throughput_per_hour" in compare_df.columns:
        tp = pd.to_numeric(compare_df["throughput_per_hour"], errors="coerce").fillna(0.0)
        score += 0.4 * (tp / tp.max()) if tp.max() > 0 else 0
    if "avg_cycle_time" in compare_df.columns:
        ct = pd.to_numeric(compare_df["avg_cycle_time"], errors="coerce")
        ct = ct.replace(0, float("nan"))
        inv_ct = 1.0 / ct
        if inv_ct.max() > 0:
            score += 0.3 * (inv_ct / inv_ct.max())
    waits = 0.0
    for col in ("avg_pick_wait", "avg_amr_wait", "avg_pack_wait"):
        if col in compare_df.columns:
            w = pd.to_numeric(compare_df[col], errors="coerce").fillna(0.0)
            inv_w = 1.0 / (w + 1.0)   # +1 防除零
            waits += 0.1 * (inv_w / inv_w.max())
    score += waits
    score = score.replace([float("inf"), float("-inf")], float("nan")).fillna(0.0)
    if score.max() <= 0:
        return "对比数据不足，无法给出推荐。"
    best = score.idxmax()
    return f"综合评分最高方案：**{best}**（评分 {score.max():.3f}）"


# ==================== 本地测试 ====================
if __name__ == "__main__":
    base = {"sim_duration": 480, "time_model": "gamma", "time_cv": 0.3,
            "arrival_mode": "poisson", "arrival_rate": 0.8, "max_orders": 500}
    compare = run_scenario_comparison(["基础配置", "增加拣选", "增加AMR"],
                                      base, n_runs=3, seed=1)
    print(compare.round(2).to_string())
    print(recommend_scenario(compare))
    print("✅ scenario.py 测试通过！")
