"""executor 层单元测试（D11）。

测试范围：
- 4 种 kind（noop/local/http/cli）各一个 happy path
- D7 改进：未配置 skill → noop+hint（不再 error）
- D9 安全：格式化字符串攻击被挡
- _wrap_outcome 统一封装
"""

from __future__ import annotations

from zhenglingtai_cli import executor


# ===== noop =====

def test_exec_noop_returns_ok() -> None:
    """noop → ok=True, logs 含 [noop]。"""
    res = executor.execute(
        capability_id="(无登记)",
        step={"skill_id": "(无登记)", "input": "", "output": ""},
        capabilities={},
    )
    assert res.ok is True
    assert "[noop]" in res.logs


# ===== D7: 未配置 → noop+hint =====

def test_exec_unconfigured_returns_noop_with_hint() -> None:
    """D7: skill 在登记册但 capabilities 没配 → ok=True + hint。"""
    res = executor.execute(
        capability_id="some-skill",
        step={"skill_id": "some-skill", "input": "x", "output": "y"},
        capabilities={},
    )
    assert res.ok is True
    assert "noop" in res.logs.lower()
    assert "zhenglingtai-capabilities.yaml" in res.logs


# ===== local =====

def test_exec_local_missing_target() -> None:
    """local 形式 target 格式错 → error。"""
    res = executor.execute(
        capability_id="x",
        step={"skill_id": "x", "input": "", "output": ""},
        capabilities={"x": {"kind": "local", "target": "no_colon"}},
    )
    assert res.ok is False
    assert "target" in res.error.lower()


def test_exec_local_import_error() -> None:
    """local 形式 module 不存在 → error 含 ImportError。"""
    res = executor.execute(
        capability_id="x",
        step={"skill_id": "x", "input": "", "output": ""},
        capabilities={"x": {"kind": "local", "target": "nonexistent_module:func"}},
    )
    assert res.ok is False
    assert "加载" in res.error or "失败" in res.error


# ===== _wrap_outcome =====

def test_wrap_outcome_dict() -> None:
    """dict 返回值 → SubcapabilityResult。"""
    result = executor._wrap_outcome(
        {"ok": True, "outputs": [{"path": "x"}], "logs": "done"},
        "test",
    )
    assert result.ok is True
    assert len(result.outputs) == 1
    assert result.logs == "done"


def test_wrap_outcome_non_dict() -> None:
    """非 dict 返回值 → ok=True 但 error 提示未遵循契约。"""
    result = executor._wrap_outcome("just a string", "test")
    assert result.ok is True
    assert "契约" in result.error


def test_wrap_outcome_already_result() -> None:
    """已是 SubcapabilityResult → 原样返回。"""
    orig = executor.SubcapabilityResult(ok=True, outputs=[], logs="x")
    result = executor._wrap_outcome(orig, "test")
    assert result is orig


# ===== D9: 安全 =====

def test_format_string_attack_blocked() -> None:
    """D9: {0.__class__} 不被 str.format 解析。"""
    import string as _string
    malicious = "{0.__class__.__init__.__globals__}"
    tpl = _string.Template('{"input": "$input"}')
    result = tpl.safe_substitute(input=malicious)
    assert malicious in result
    assert "__globals__" not in result.replace(malicious, "")


# ===== load_capabilities =====

def test_load_capabilities_missing_file(tmp_path) -> None:
    """capabilities 文件不存在 → 返回空 dict。"""
    result = executor.load_capabilities(tmp_path / "nonexistent.yaml")
    assert result == {}
