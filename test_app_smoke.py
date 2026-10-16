# -*- coding: utf-8 -*-
"""临时冒烟测试：用 Streamlit AppTest 完整执行 app.py 并点击各功能按钮"""
import sys
import time

from streamlit.testing.v1 import AppTest

LOG = []


def log(msg):
    print(msg, flush=True)
    LOG.append(msg)


def run_app(at: AppTest, desc: str):
    t0 = time.time()
    at.run(timeout=300)
    el = time.time() - t0
    if at.exception:
        for exc in at.exception:
            log(f"[FAIL] {desc} ({el:.1f}s): {exc.value}")
        return False
    log(f"[OK]   {desc} ({el:.1f}s)")
    return True


def click(at: AppTest, label: str):
    for b in at.button:
        if b.label == label:
            b.click()
            return True
    log(f"[WARN] 未找到按钮: {label}")
    return False


ok_all = True

# 1. 页面初始加载
at = AppTest.from_file("app.py", default_timeout=300)
ok_all &= run_app(at, "页面初始加载")

# 2. 功能1 智能计算
if click(at, "⚡ 自动计算人车配置"):
    ok_all &= run_app(at, "功能1 智能计算")

# 3. 功能2 单次仿真
if click(at, "🚀 运行单次仿真"):
    ok_all &= run_app(at, "功能2 单次仿真")

# 4. 功能4 多方案对比（小规模）
at.session_state["scen_runs"] = 3
if click(at, "🏁 开始方案对比"):
    ok_all &= run_app(at, "功能4 多方案对比")

# 5. 功能5 批量仿真
at.session_state["batch_n"] = 5
if click(at, "🎲 运行批量仿真"):
    ok_all &= run_app(at, "功能5 批量仿真")

# 6. 功能6 敏感性分析：参数扫描 + 龙卷风
at.session_state["sens_runs"] = 2
if click(at, "📈 运行参数扫描"):
    ok_all &= run_app(at, "功能6 参数扫描")
if click(at, "🌪️ 运行龙卷风分析"):
    ok_all &= run_app(at, "功能6 龙卷风分析")

# 7. 功能7 压力情景
at.session_state["stress_runs"] = 3
if click(at, "🧨 运行压力测试"):
    ok_all &= run_app(at, "功能7 压力情景")

# 8. 功能10 自动报告
if click(at, "📄 生成HTML报告"):
    ok_all &= run_app(at, "功能10 自动报告")

log("=" * 50)
log("全部通过 ✅" if ok_all else "存在失败项 ❌")
sys.exit(0 if ok_all else 1)
