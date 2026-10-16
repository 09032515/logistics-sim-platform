# -*- coding: utf-8 -*-
"""
stress.py —— 功能7：压力情景测试
=================================
模拟业务高峰或异常情况，检验系统抗压能力：

  正常情景         —— 基础需求
  需求暴涨×1.5    —— 到达速率提高 50%
  需求暴涨×2.0    —— 到达速率提高 100%（接近系统极限）
  拣选设备故障     —— 第120~180分钟拣选人员全部停机
  AMR设备故障      —— 第120~180分钟AMR全部停机
  组合压力         —— 需求×1.5 + 拣选设备故障

每个情景跑批量仿真，横向对比 平均周期 / P95周期 / 吞吐量 / 最大队列，
直观看出哪个情景下系统"扛不住"。
"""

import pandas as pd

from sim_core import run_batch_simulation, summary_to_dict


def build_stress_scenarios(base_settings: dict) -> dict:
    """基于全局设置构造各压力情景的 settings 字典"""
    scenarios = {
        "正常情景": {},
        "需求暴涨×1.5": {"demand_multiplier": 1.5},
        "需求暴涨×2.0": {"demand_multiplier": 2.0},
        "拣选设备故障": {"failure_events": {"picker": [(120, 180)]}},
        "AMR设备故障": {"failure_events": {"amr": [(120, 180)]}},
        "组合压力(需求×1.5+拣选故障)": {"demand_multiplier": 1.5,
                                          "failure_events": {"picker": [(120, 180)]}},
    }
    result = {}
    for name, patch in scenarios.items():
        s = dict(base_settings)
        s.update(patch)
        result[name] = s
    return result


def run_stress_comparison(
    scenarios: dict,          # {情景名: settings 补丁后的完整settings}
    n_runs: int = 10,
    seed: int = 42,
    progress_cb=None,         # (当前情景序号, 总数, 当前次数, 总次数)
    order_arrival_list=None,  # 固定到达模式下的订单时刻列表
) -> pd.DataFrame:
    """每个情景跑批量仿真，返回对比表：行=情景，列=KPI均值"""
    compare_rows = {}
    total = len(scenarios)
    for idx, (name, settings) in enumerate(scenarios.items(), 1):
        if progress_cb:

            def cb(i, n, _name=name, _idx=idx, _total=total):
                progress_cb(_idx, _total, i, n)

            _, df_summary = run_batch_simulation(settings, n_runs=n_runs,
                                                 seed=seed + idx * 50,
                                                 progress_cb=cb,
                                                 order_arrival_list=order_arrival_list)
        else:
            _, df_summary = run_batch_simulation(settings, n_runs=n_runs,
                                                 seed=seed + idx * 50,
                                                 order_arrival_list=order_arrival_list)
        compare_rows[name] = summary_to_dict(df_summary)
    return pd.DataFrame(compare_rows).T


def stress_verdict(compare_df: pd.DataFrame) -> str:
    """给出压力测试结论：哪个情景最先扛不住。"""
    if compare_df is None or len(compare_df) == 0:
        return "暂无压力测试数据。"
    if "avg_cycle_time" not in compare_df.columns:
        return "压力测试数据不足（缺少平均周期指标），请检查订单参数。"
    ct = pd.to_numeric(compare_df["avg_cycle_time"], errors="coerce")
    if ct.isna().all():
        return "压力测试数据不足（可能未生成订单），请检查订单到达参数。"
    normal = compare_df.loc["正常情景"] if "正常情景" in compare_df.index else None
    worst_name = ct.idxmax()
    worst = compare_df.loc[worst_name]
    if normal is None:
        return f"压力最敏感情景：**{worst_name}**，平均周期 {worst['avg_cycle_time']:.1f} 分钟。"
    ratio = float(worst["avg_cycle_time"]) / max(1e-6, float(normal["avg_cycle_time"]))
    return (f"相对正常情景，**{worst_name}** 的平均周期膨胀至 {ratio:.1f} 倍"
            f"（{float(normal['avg_cycle_time']):.1f} → {float(worst['avg_cycle_time']):.1f} 分钟），"
            f"是最先触及系统承载上限的压力点。")


# ==================== 本地测试 ====================
if __name__ == "__main__":
    base = {"picker_num": 2, "pack_station_num": 1, "amr_num": 3,
            "sim_duration": 480, "time_model": "gamma", "time_cv": 0.3,
            "arrival_mode": "poisson", "arrival_rate": 0.8, "max_orders": 1000}
    scen = build_stress_scenarios(base)
    compare = run_stress_comparison(scen, n_runs=3, seed=2)
    print(compare[["avg_cycle_time", "p95_cycle_time",
                   "throughput_per_hour", "max_queue_picker"]].round(2).to_string())
    print(stress_verdict(compare))
    print("✅ stress.py 测试通过！")
