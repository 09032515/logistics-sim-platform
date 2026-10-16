# -*- coding: utf-8 -*-
"""
sensitivity.py —— 功能6：敏感性分析
====================================
回答两类问题：
  1. 参数扫描：固定其他参数，只改变某一资源数量（如拣选人员 1→6），
     观察 平均周期 / 吞吐量 / 利用率 如何变化，找到"边际收益递减拐点"。
  2. 龙卷风图：基准配置下，把每个资源数量分别 +1 / -1，
     比较对关键 KPI 的影响幅度，找出影响最大的参数。
"""

import pandas as pd

from sim_core import run_batch_simulation, summary_to_dict

# 各资源可扫描的取值范围（供网页滑块使用）
RESOURCE_RANGES = {
    "picker": (1, 6),
    "amr": (1, 8),
    "pack_station": (1, 4),
}


def run_sensitivity_scan(
    resource_key: str,          # 要扫描的资源，如 "picker"
    values,                     # 扫描值列表，如 [1,2,3,4,5,6]
    base_settings: dict,
    n_runs: int = 5,            # 每个取值重复次数（预览用，正式可加大）
    seed: int = 42,
    progress_cb=None,
    order_arrival_list=None,    # 固定到达模式下的订单时刻列表
) -> pd.DataFrame:
    """参数扫描：返回每行的 value + 各KPI均值"""
    rows = []
    for idx, v in enumerate(values, 1):
        settings = dict(base_settings)
        settings[resource_key] = int(v)
        _, df_summary = run_batch_simulation(settings, n_runs=n_runs,
                                             seed=seed + idx * 1000,
                                             order_arrival_list=order_arrival_list)
        row = {"value": int(v)}
        row.update(summary_to_dict(df_summary))
        rows.append(row)
        if progress_cb:
            progress_cb(idx, len(values))
    df = pd.DataFrame(rows)
    # 边际改善：吞吐量相邻取值的变化量
    if "throughput_per_hour" in df.columns and len(df) > 1:
        df["吞吐量边际改善"] = df["throughput_per_hour"].diff().round(3)
    return df


def find_inflection_point(sens_df: pd.DataFrame, kpi_col: str = "avg_cycle_time",
                          threshold: float = 0.05) -> int:
    """
    寻找边际收益递减拐点：当 KPI 改善幅度低于 threshold 时，认为继续加资源
    收益不大，返回该资源数量（建议配置）。
    """
    if sens_df is None or len(sens_df) < 2 or kpi_col not in sens_df.columns:
        return int(sens_df["value"].iloc[-1]) if sens_df is not None and len(sens_df) else 1
    vals = sens_df[kpi_col].astype(float)
    base = vals.iloc[0]
    if base <= 0:
        return int(sens_df["value"].iloc[-1])
    for i in range(1, len(vals)):
        improvement = (base - vals.iloc[i]) / base   # 相对改善比例
        if improvement < threshold:
            return int(sens_df["value"].iloc[max(0, i - 1)])
    return int(sens_df["value"].iloc[-1])


def run_tornado(
    base_settings: dict,
    kpi_col: str = "avg_cycle_time",
    n_runs: int = 5,
    seed: int = 42,
    resources=("picker", "amr", "pack_station"),
    order_arrival_list=None,    # 固定到达模式下的订单时刻列表
) -> pd.DataFrame:
    """龙卷风图数据：基准配置下，每个资源 +1/-1 对 kpi_col 的影响"""
    settings = dict(base_settings)
    _, base_summary = run_batch_simulation(settings, n_runs=n_runs, seed=seed,
                                           order_arrival_list=order_arrival_list)
    base_val = float(base_summary.loc[base_summary["指标"] == kpi_col, "均值"].iloc[0])

    rows = []
    for idx, res in enumerate(resources, 1):
        lo_vals, hi_vals = {}, {}
        for delta, out in ((-1, lo_vals), (1, hi_vals)):
            s = dict(base_settings)
            s[res] = max(1, int(s.get(res, 1)) + delta)
            _, sm = run_batch_simulation(s, n_runs=n_runs, seed=seed + idx * 100 + delta,
                                         order_arrival_list=order_arrival_list)
            out[kpi_col] = float(sm.loc[sm["指标"] == kpi_col, "均值"].iloc[0])
        impact = abs(hi_vals[kpi_col] - lo_vals[kpi_col]) / max(1e-9, abs(base_val))
        rows.append({
            "资源": res,
            "减1": round(lo_vals[kpi_col], 3),
            "基准": round(base_val, 3),
            "加1": round(hi_vals[kpi_col], 3),
            "影响幅度": round(impact, 4),
        })
    df = pd.DataFrame(rows).sort_values("影响幅度", ascending=False).reset_index(drop=True)
    return df


# ==================== 本地测试 ====================
if __name__ == "__main__":
    base = {"picker_num": 2, "pack_station_num": 1, "amr_num": 3,
            "sim_duration": 480, "time_model": "gamma", "time_cv": 0.3,
            "arrival_mode": "poisson", "arrival_rate": 0.8, "max_orders": 500}

    print("扫描拣选人员 1→5：")
    df_scan = run_sensitivity_scan("picker", [1, 2, 3, 4, 5], base, n_runs=3, seed=5)
    print(df_scan[["value", "avg_cycle_time", "throughput_per_hour",
                   "utilization_picker"]].round(3).to_string(index=False))
    print(f"拐点建议（平均周期改善<5%）：{find_inflection_point(df_scan)} 人")

    print("\n龙卷风分析（对 avg_cycle_time）：")
    df_torn = run_tornado(base, n_runs=3, seed=5)
    print(df_torn.to_string(index=False))
    print("✅ sensitivity.py 测试通过！")
