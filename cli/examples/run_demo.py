"""跑通示例：本地无 LLM 时演示纪律层骨架。

运行：
    python examples/run_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 让 import 能找到 ../zhenglingtai_cli
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from zhenglingtai_cli import discipline, executor, registry  # noqa: E402


def main() -> None:
    print("===== 政令台 CLI（B 形态）· 无 LLM 跑通演示 =====\n")

    entries = registry.scan()
    print(f"[1/4] 通译（演示）：跳过 LLM，预填一个示例任务书")
    task = discipline.TaskBook(
        what="A vs B 两家产品的 4 维度竞品分析",
        why="给老板汇报，需结论清晰、数据可信",
        scope_in=["功能/价格/定位/用户口碑 4 维度对比", "产出 md + pptx"],
        scope_out=["市场规模预测", "财务建模"],
        accept=[
            "md 含 A、B 双方案例维度对比",
            "关键数据有出处",
            "PPT 页数 ≥ 10",
        ],
        unknowns=[],
        intent_tags=["competitor_analysis", "make_ppt"],
    )
    print(json.dumps(task.__dict__, ensure_ascii=False, indent=2))

    print("\n[2/4] 路由（演示）：直接用占位工序单")
    proc = discipline.Procedure(
        main_skill="example-competitor-analysis",
        cooperative=["example-ppt"],
        meta_delegate="",
        steps=[
            discipline.Step(index=1, skill_id="example-competitor-analysis",
                            input="A vs B 主题", output="交付物/竞品分析.md",
                            check="md 存在、含 4 维度对比"),
            discipline.Step(index=2, skill_id="example-ppt",
                            input="竞品分析.md", output="交付物/竞品分析.pptx",
                            check="pptx 存在、页数 ≥ 10"),
        ],
        stop_points=[1],
        fallbacks={"example-ppt": "退回 markdown 汇报版"},
    )
    # v1.0.2 修复：steps 里是 Step 对象，__dict__ 不能直接 JSON 序列化，用 asdict 递归转换
    from dataclasses import asdict
    print(json.dumps(asdict(proc), ensure_ascii=False, indent=2))

    print("\n[3/4] 执行（演示）：所有 skill 走 noop 兜底")
    caps = {}
    for step in proc.steps:
        res = executor.execute(capability_id=step.skill_id, step=step.__dict__, capabilities=caps)
        print(f"   步骤 {step.index} ok={res.ok} logs={res.logs[:60]}")

    print("\n[4/4] 验收（演示）：手填一个达标验收单")
    acc = discipline.Acceptance(
        result="达标",
        per_item=[
            {"item": "md 含 A、B 双方案例维度对比", "status": "ok", "evidence": "4 维度齐全"},
            {"item": "关键数据有出处", "status": "ok", "evidence": "8 处带 URL"},
            {"item": "PPT 页数 ≥ 10", "status": "ok", "evidence": "12 页"},
        ],
        deviations=[],
        subjective=["文风是否符合预期？"],
        deliverables=[
            {"path": "交付物/竞品分析.md", "type": "md", "summary": "4 维度对比"},
            {"path": "交付物/竞品分析.pptx", "type": "pptx", "summary": "12 页汇报版"},
        ],
    )
    print(json.dumps(acc.__dict__, ensure_ascii=False, indent=2))

    print("\n===== 演示完成 =====")
    print("想真让 LLM 跑起来：")
    print("  1. cp config.example.yaml zlt.config.yaml")
    print("  2. 改 base_url / api_key / model")
    print("  3. zlt run '你的指令'   # 或装了 shim 的话：zhengling run '你的指令'")


if __name__ == "__main__":
    main()
