"""封驳打回循环 + headers 环境变量展开测试（v1.0.2）。

测试范围：
- _run_reject_loop：一次达标 / 重试后达标 / 打满 3 轮 ESCALATE / L3 失败短路
- _execute_procedure：上轮偏差注入 input / 步骤失败立即短路
- _expand_env_in_headers：$VAR 展开（EXTENDING.md 示例 `"Bearer $MY_API_KEY"` 的支撑）
- run_demo.py 冒烟：演示脚本必须能跑完（v1.0.1 的 TypeError 教训）
"""

from __future__ import annotations

import runpy

import pytest

from zhenglingtai_cli import __main__ as main_mod
from zhenglingtai_cli import discipline, executor


def _make_task() -> discipline.TaskBook:
    """构造测试任务书。"""
    return discipline.TaskBook(
        what="测试", why="测试", scope_in=["a"], scope_out=["b"],
        accept=["验收点1"], unknowns=[], intent_tags=["write_copy"],
    )


def _make_proc() -> discipline.Procedure:
    """构造单步工序单。"""
    return discipline.Procedure(
        main_skill="skill-a", cooperative=[], meta_delegate="",
        steps=[discipline.Step(index=1, skill_id="skill-a", input="原始输入")],
        stop_points=[], fallbacks={},
    )


def _acc(result: str, deviations: list[str] | None = None) -> discipline.Acceptance:
    """构造验收单。"""
    return discipline.Acceptance(
        result=result, per_item=[], deviations=deviations or [],
        subjective=[], deliverables=[],
    )


class _NullLog:
    """测试用静默 logger（logutil 的最小替身）。"""

    def info(self, msg, **kw): pass
    def warn(self, msg, **kw): pass
    def error(self, msg, **kw): pass


# ===== _run_reject_loop =====

def test_loop_succeeds_first_round(monkeypatch) -> None:
    """首轮达标 → 只跑 1 轮，偏差历史为空。"""
    calls = {"exec": 0, "verify": 0}

    def fake_execute(**kw):
        calls["exec"] += 1
        return executor.SubcapabilityResult(ok=True, outputs=[], logs="")

    monkeypatch.setattr(executor, "execute", fake_execute)
    monkeypatch.setattr(discipline, "layer4_verify",
                        lambda *a, **k: calls.__setitem__("verify", calls["verify"] + 1) or _acc("达标"))

    acc, history = main_mod._run_reject_loop(
        None, _make_task(), _make_proc(), {}, ".", _NullLog())
    assert acc.result == "达标"
    assert history == []
    assert calls["exec"] == 1 and calls["verify"] == 1


def test_loop_succeeds_after_retry(monkeypatch) -> None:
    """前 2 轮未达标、第 3 轮达标 → 3 轮，历史 2 条。"""
    results = [_acc("未达标", ["缺出处"]), _acc("未达标", ["缺结论页"]), _acc("达标")]
    calls = {"verify": 0}

    monkeypatch.setattr(executor, "execute",
                        lambda **kw: executor.SubcapabilityResult(ok=True, outputs=[], logs=""))

    def fake_verify(*a, **k):
        r = results[calls["verify"]]
        calls["verify"] += 1
        return r

    monkeypatch.setattr(discipline, "layer4_verify", fake_verify)
    acc, history = main_mod._run_reject_loop(
        None, _make_task(), _make_proc(), {}, ".", _NullLog())
    assert acc.result == "达标"
    assert history == [["缺出处"], ["缺结论页"]]
    assert calls["verify"] == 3


def test_loop_escalates_after_max_rounds(monkeypatch, capsys) -> None:
    """3 轮全未达标 → 返回未达标验收单 + 3 条历史（ESCALATE 由 cmd_run 输出）。"""
    monkeypatch.setattr(executor, "execute",
                        lambda **kw: executor.SubcapabilityResult(ok=True, outputs=[], logs=""))
    monkeypatch.setattr(discipline, "layer4_verify",
                        lambda *a, **k: _acc("未达标", ["就是不行"]))

    acc, history = main_mod._run_reject_loop(
        None, _make_task(), _make_proc(), {}, ".", _NullLog())
    assert acc.result == "未达标"
    assert len(history) == main_mod.MAX_REJECT_ROUNDS == 3
    # 打回提示确实打印了（前两轮）
    out = capsys.readouterr().out
    assert out.count("封驳打回") == main_mod.MAX_REJECT_ROUNDS - 1


def test_loop_short_circuits_on_exec_failure(monkeypatch) -> None:
    """L3 步骤失败 → 验收单为 None（cmd_run 据此 return 4），不再验收。"""
    monkeypatch.setattr(executor, "execute",
                        lambda **kw: executor.SubcapabilityResult(ok=False, outputs=[], logs="", error="boom"))
    verify_called = {"n": 0}
    monkeypatch.setattr(discipline, "layer4_verify",
                        lambda *a, **k: verify_called.__setitem__("n", verify_called["n"] + 1))

    acc, history = main_mod._run_reject_loop(
        None, _make_task(), _make_proc(), {}, ".", _NullLog())
    assert acc is None
    assert verify_called["n"] == 0


# ===== _execute_procedure 偏差注入 =====

def test_execute_procedure_injects_last_deviations(monkeypatch) -> None:
    """打回重跑时，上轮偏差清单附加到 step input 尾部。"""
    seen_inputs = []

    def fake_execute(capability_id, step, capabilities, *, work_dir=".", llm_cfg=None):
        seen_inputs.append(step["input"])
        return executor.SubcapabilityResult(ok=True, outputs=[], logs="")

    monkeypatch.setattr(executor, "execute", fake_execute)
    produced, fail = main_mod._execute_procedure(
        _make_proc(), {}, ".", _NullLog(), last_deviations=["缺出处", "缺结论页"])
    assert fail is False
    assert "缺出处" in seen_inputs[0] and "缺结论页" in seen_inputs[0]
    assert "原始输入" in seen_inputs[0]


def test_execute_procedure_no_injection_first_round(monkeypatch) -> None:
    """首轮（无偏差历史）input 原样传递。"""
    seen_inputs = []
    monkeypatch.setattr(executor, "execute",
                        lambda capability_id, step, capabilities, *, work_dir=".", llm_cfg=None: (
                            seen_inputs.append(step["input"]),
                            executor.SubcapabilityResult(ok=True, outputs=[], logs=""),
                        )[1])
    main_mod._execute_procedure(_make_proc(), {}, ".", _NullLog())
    assert seen_inputs == ["原始输入"]


# ===== headers 环境变量展开 =====

def test_expand_env_in_headers(monkeypatch) -> None:
    """`Bearer $TOKEN` 被环境变量展开——EXTENDING.md 示例的实际支撑。"""
    monkeypatch.setenv("ZLT_TEST_TOKEN", "sk-secret-123")
    headers = {"Authorization": "Bearer $ZLT_TEST_TOKEN", "X-Static": "keep"}
    out = executor._expand_env_in_headers(headers)
    assert out["Authorization"] == "Bearer sk-secret-123"
    assert out["X-Static"] == "keep"


def test_expand_env_missing_var_left_as_is(monkeypatch) -> None:
    """未定义的环境变量保持原样（expandvars 语义），不炸。"""
    monkeypatch.delenv("ZLT_NO_SUCH_VAR", raising=False)
    out = executor._expand_env_in_headers({"Authorization": "Bearer $ZLT_NO_SUCH_VAR"})
    assert out["Authorization"] == "Bearer $ZLT_NO_SUCH_VAR"


# ===== run_demo.py 冒烟 =====

def test_run_demo_script_completes(capsys) -> None:
    """演示脚本能完整跑完（v1.0.1 的 Step 序列化 TypeError 教训）。"""
    from pathlib import Path
    demo = Path(__file__).resolve().parent.parent / "examples" / "run_demo.py"
    runpy.run_path(str(demo), run_name="__main__")
    out = capsys.readouterr().out
    assert "演示完成" in out
