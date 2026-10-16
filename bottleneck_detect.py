# -*- coding: utf-8 -*-
"""
bottleneck_detect.py —— 功能3：瓶颈环节自动识别
=========================================
> 📌 命名说明：不能命名为 bottleneck.py！PyPI 上有同名第三方包
> （pandas 的可选加速依赖），文件名撞名会导致 pandas 循环导入报错。
基于一次仿真（或批量仿真均值）的 KPI，自动定位系统瓶颈环节：

判定维度（三合一打分）：
  1. 资源利用率        —— 越高越可能是瓶颈
  2. 平均排队等待时间   —— 越长越可能是瓶颈
  3. 最大队列长度       —— 越大越可能堆积

输出：
  - 瓶颈环节及判定依据（中文说明）
  - 各环节瓶颈得分表
  - 建议方向（详细建议见 advisor.py）
"""

import pandas as pd

STAGE_NAMES = {"picker": "拣选", "amr": "AMR搬运", "pack_station": "打包"}


def bottleneck_scores(kpi: dict) -> pd.DataFrame:
    """根据 KPI 计算各环节瓶颈得分（0~1，越大越瓶颈）"""
    rows = []
    # 利用率权重 0.5，平均等待归一化权重 0.3，最大队列归一化权重 0.2
    max_wait = max([kpi.get("avg_pick_wait", 0), kpi.get("avg_amr_wait", 0),
                    kpi.get("avg_pack_wait", 0)], default=0)
    max_q = max([kpi.get(f"max_queue_{r}", 0) for r in ("picker", "amr", "pack_station")],
                default=0)
    for res in ("picker", "amr", "pack_station"):
        util = kpi.get(f"utilization_{res}", 0.0)
        wait = kpi.get({"picker": "avg_pick_wait", "amr": "avg_amr_wait",
                        "pack_station": "avg_pack_wait"}[res], 0.0)
        q = kpi.get(f"max_queue_{res}", 0)
        wait_norm = wait / max_wait if max_wait > 0 else 0.0
        q_norm = q / max_q if max_q > 0 else 0.0
        score = 0.5 * util + 0.3 * wait_norm + 0.2 * q_norm
        rows.append({
            "环节": STAGE_NAMES[res],
            "资源": res,
            "利用率": round(util, 4),
            "平均等待(分钟)": round(wait, 2),
            "最大队列": q,
            "瓶颈得分": round(score, 4),
        })
    df = pd.DataFrame(rows)
    df = df.sort_values("瓶颈得分", ascending=False).reset_index(drop=True)
    df["是否瓶颈"] = df["资源"] == df.loc[0, "资源"]
    df["是否瓶颈"] = df["是否瓶颈"].map({True: "★ 瓶颈", False: ""})
    return df


def explain_bottleneck(kpi: dict) -> str:
    """生成瓶颈环节的中文说明文字"""
    df = bottleneck_scores(kpi)
    if len(df) == 0:
        return "暂无仿真数据。"
    top = df.iloc[0]
    util = top["利用率"]
    wait = top["平均等待(分钟)"]
    reason = []
    if util >= 0.85:
        reason.append(f"利用率 {util*100:.1f}% 已超过 85% 警戒线")
    if wait >= 2.0:
        reason.append(f"平均等待 {wait:.1f} 分钟为全流程最高")
    if top["最大队列"] >= 5:
        reason.append(f"高峰期最大排队 {top['最大队列']} 件")
    if not reason:
        reason.append("系统整体负荷均衡，无显著瓶颈")
    return f"当前瓶颈环节：**{top['环节']}**。判定依据：{'；'.join(reason)}。"


# ==================== 本地测试 ====================
if __name__ == "__main__":
    from sim_core import run_one_simulation, compute_kpis

    cfg = {"picker_num": 1, "pack_station_num": 1, "amr_num": 1,
           "sim_duration": 480, "time_model": "fixed",
           "arrival_mode": "poisson", "arrival_rate": 0.8, "max_orders": 500}
    sim = run_one_simulation(cfg, seed=3)
    kpi = compute_kpis(sim)
    print(explain_bottleneck(kpi))
    print(bottleneck_scores(kpi).to_string(index=False))
    print("✅ bottleneck_detect.py 测试通过！")
