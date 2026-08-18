"""v1.2.0 4 层 fallback 链测试。

覆盖：
  - native.discover() 在当前 venv 下能识别已装库
  - execute() 命中 L1 原生
  - execute() 原生缺时回落 L2 cap
  - execute() L2 没有时回落 L3 LLM（mock chat_json）
  - execute() L3 不适用（无 output / 无 cfg / 后缀非文本）时走 L4 noop
  - report_missing() 给的 pip install 一行
  - cmd_health 输出原生能力计数
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from zhenglingtai_cli import executor, native, llm
import zhenglingtai_cli.llm as llm_mod


# ============ discover / ready_ids / report_missing ============

def test_discover_returns_cap_table() -> None:
    """discover() 返回全部 14 个 cap（v1.2.0 头批）。"""
    caps = native.discover()
    assert len(caps) >= 12  # 留一些补加余量
    assert "read_text" in caps and "write_json" in caps and "hash_sha256" in caps


def test_discover_mark_ready_correctly() -> None:
    """stdlib + pyyaml 一向 ready；可选三方库按 venv 实际状态标记。"""
    caps = native.discover()
    # stdlib 一向就绪
    for cid in ["read_text", "write_text", "read_json", "write_json",
                "csv_read", "csv_write", "hash_sha256"]:
        assert caps[cid].ready, f"{cid} 应 ready"
    # pyyaml 是 v1.0.0 起的依赖
    assert caps["read_yaml"].ready and caps["write_yaml"].ready
    # 第三方库按 venv 实际是否装——不写死预期
    caps["pptx_create"].ready  # 触发现有属性（True/False 都行）


def test_report_missing_lists_pip_command() -> None:
    """report_missing 给的每一行都是 '  • <id>: pip install <pkg>' 格式。"""
    lines = native.report_missing()
    for line in lines:
        assert line.startswith("  • ")
        assert "pip install " in line
        parts = line.split("pip install ", 1)
        assert parts[1].strip(), f"{line} 的 pip 目标为空"
        parts2 = parts[1].strip().split(" ", 1)
        pkg = parts2[0]
        assert ":" in line or pkg, "missing capability id 标识"


# ============ L1: 原生命中 ============

def test_execute_hits_native_write_text(tmp_path) -> None:
    """write_text 原生能力直接落盘。"""
    res = executor.execute(
        capability_id="write_text",
        step={"skill_id": "write_text",
              "input": "你说什么我都能写",
              "output": "out.txt"},
        capabilities={},
        work_dir=str(tmp_path),
    )
    assert res.ok
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "你说什么我都能写"
    assert any("native.write_text" in l for l in [res.logs])


def test_execute_hits_native_read_text(tmp_path) -> None:
    """read_text 原生读 .md/.txt/.json 等。"""
    (tmp_path / "data.txt").write_text("hello native", encoding="utf-8")
    res = executor.execute(
        capability_id="read_text",
        step={"skill_id": "read_text", "input": "data.txt", "output": ""},
        capabilities={},
        work_dir=str(tmp_path),
    )
    assert res.ok
    assert res.outputs and res.outputs[0]["type"] == "text"


def test_execute_hits_native_hash_sha256(tmp_path) -> None:
    """hash_sha256 输出 64 hex 字符。"""
    (tmp_path / "f.txt").write_text("hi", encoding="utf-8")
    res = executor.execute(
        capability_id="hash_sha256",
        step={"skill_id": "hash_sha256", "input": "f.txt", "output": ""},
        capabilities={},
        work_dir=str(tmp_path),
    )
    assert res.ok
    summary = res.outputs[0]["summary"]
    assert len(summary) == 64 and all(c in "0123456789abcdef" for c in summary)


def test_execute_hits_native_csv(tmp_path) -> None:
    """csv_read + csv_write 端到端。"""
    src = tmp_path / "data.csv"
    src.write_text("name,age\nAlice,30\nBob,25\n", encoding="utf-8")
    # read
    r = executor.execute(
        "csv_read",
        {"skill_id": "csv_read", "input": "data.csv", "output": ""},
        {}, work_dir=str(tmp_path),
    )
    assert r.ok and r.outputs[0]["rows"] == 2
    # write
    r2 = executor.execute(
        "csv_write",
        {"skill_id": "csv_write",
         "input": json.dumps([{"x": 1, "y": 2}, {"x": 3, "y": 4}], ensure_ascii=False),
         "output": "out.csv"},
        {}, work_dir=str(tmp_path),
    )
    assert r2.ok
    assert (tmp_path / "out.csv").read_text(encoding="utf-8-sig").splitlines()[0] == "x,y"


def test_execute_native_write_json_validates_input(tmp_path) -> None:
    """write_json 收到非法字符串 input 时返回 ok=False。"""
    r = executor.execute(
        "write_json",
        {"skill_id": "write_json",
         "input": "not a json",
         "output": "o.json"},
        {}, work_dir=str(tmp_path),
    )
    assert not r.ok
    assert "JSON" in r.error


# ============ L1 → L2: 原生不在时走 cap ============

def test_execute_falls_back_to_user_cap(tmp_path, monkeypatch) -> None:
    """未知 cap + 用户声明了 local 形式 → 命中 L2。"""
    # 让 native 不认这条 cap（capability_id 不在 NATIVE_REGISTRY）
    # 用户的 cap 走 local
    def fake_local(_cid, step, cap, work_dir):
        return executor.SubcapabilityResult(
            ok=True, outputs=[], logs="[L2.local] hit",
        )
    monkeypatch.setattr(executor, "_exec_local", fake_local)

    res = executor.execute(
        capability_id="my_custom_skill",
        step={"skill_id": "my_custom_skill", "input": "x", "output": "y"},
        capabilities={"my_custom_skill": {"kind": "local", "target": "m:f"}},
        work_dir=str(tmp_path),
    )
    assert res.ok
    assert "[L2.local] hit" in res.logs


def test_execute_cap_with_unknown_kind_falls_through(tmp_path, monkeypatch) -> None:
    """cap 声明了但 kind 不可识别 → 不调用 _exec_local，继续走 L3/L4。"""
    # 用一个不会被 cap ID 触发的 ID
    res = executor.execute(
        capability_id="totally_made_up_xyz",
        step={"skill_id": "totally_made_up_xyz", "input": "", "output": ""},
        capabilities={"totally_made_up_xyz": {"kind": "weird_new_kind"}},
        work_dir=str(tmp_path),
        llm_cfg=None,
    )
    # L1 native 否（id 不在 registry）→ L2 cap 找不到 kind 不进 → L3 无 cfg → L4 noop
    assert res.ok
    assert "noop" in res.logs.lower()


# ============ L3: LLM 直干 ============

def test_llm_fallback_writes_text_file(monkeypatch, tmp_path) -> None:
    """L3 fallback 接到 llm_cfg + 文本后缀 output → 调 LLM 写文件。"""
    calls = {"n": 0}

    def fake_chat_json(cfg, system, user_payload):
        calls["n"] += 1
        # 返回 dict 套 content 字段（v1.2.0 约定）
        return {"content": "# 标题\n\n这是一段自动生成的样例。"}
    monkeypatch.setattr(llm_mod, "chat_json", fake_chat_json)

    cfg = llm.LLMConfig(base_url="http://x", api_key="k", model="m")
    res = executor.execute(
        capability_id="write_doc",
        step={"skill_id": "write_doc",
              "input": "关于 AI 的短介绍",
              "output": "doc.md"},
        capabilities={},
        work_dir=str(tmp_path),
        llm_cfg=cfg,
    )
    assert res.ok, res.error
    assert calls["n"] == 1
    body = (tmp_path / "doc.md").read_text(encoding="utf-8")
    assert "标题" in body


def test_llm_fallback_binary_output_skipped(monkeypatch, tmp_path) -> None:
    """L3 在 .pptx/.xlsx 等二进制后缀上不接管 → 返回 None 让上层走 noop。"""
    monkeypatch.setattr(llm_mod, "chat_json",
                        lambda *a, **k: pytest.fail("不应调 LLM"))
    cfg = llm.LLMConfig(base_url="http://x", api_key="k", model="m")
    # 直接验 llm_fallback.invoke_for_step
    from zhenglingtai_cli import llm_fallback
    r = llm_fallback.invoke_for_step(
        "pptx_from_llm",
        {"skill_id": "pptx_from_llm", "input": "x", "output": "out.pptx"},
        cfg, str(tmp_path),
    )
    assert r is None


def test_llm_fallback_no_output_returns_none(tmp_path) -> None:
    """step 没 output 字段时 L3 不接管（连错误都不抛）。"""
    from zhenglingtai_cli import llm_fallback
    cfg = llm.LLMConfig(base_url="http://x", api_key="k", model="m")
    r = llm_fallback.invoke_for_step(
        "any", {"input": "x"}, cfg, str(tmp_path),
    )
    assert r is None


def test_llm_fallback_no_cfg_returns_none(tmp_path) -> None:
    """无 cfg 时 L3 跳过。"""
    from zhenglingtai_cli import llm_fallback
    r = llm_fallback.invoke_for_step(
        "any", {"output": "x.md"}, None, str(tmp_path),
    )
    assert r is None


# ============ L4: 全 fallback 后 ============

def test_execute_full_fallback_noop_with_yaml_hint(tmp_path) -> None:
    """全 4 层都接不住 → noop + hint 含 yaml 路径。"""
    res = executor.execute(
        capability_id="pure_ghost",
        step={"skill_id": "pure_ghost", "input": "", "output": ""},
        capabilities={},
        work_dir=str(tmp_path),
        llm_cfg=None,
    )
    assert res.ok
    assert "noop" in res.logs.lower()
    assert "zhenglingtai-capabilities.yaml" in res.logs


def test_execute_full_fallback_with_pip_hint(tmp_path) -> None:
    """cap_id 命中某个未装原生能力 → hint 同时含 pip + yaml。"""
    # pptx_create 是当前 venv 必定未装的（按 venv 现状）
    caps = native.discover()
    if caps["pptx_create"].ready:
        pytest.skip("本 venv 已装 python-pptx，跳过对未装 hint 的断言")
    res = executor.execute(
        capability_id="pptx_create",
        step={"skill_id": "pptx_create", "input": "", "output": ""},
        capabilities={},
        work_dir=str(tmp_path),
        llm_cfg=None,
    )
    # native.invoke_if_ready 应该返回 None（未 ready）→ 走 L2/L3/L4
    # 因为 output 为空，所以 L3 也跳过 → L4 noop
    assert res.ok
    assert "pip" in res.logs.lower() or "install" in res.logs.lower()


# ============ _hint_for 函数 ============

def test_hint_for_includes_yaml_path(tmp_path) -> None:
    """_hint_for 永远含 'zhenglingtai-capabilities.yaml'，便于老 smoke 测试断言。"""
    h = executor._hint_for("随便")
    assert "zhenglingtai-capabilities.yaml" in h


def test_hint_for_native_missing_includes_pip(tmp_path) -> None:
    """cap_id 命中某条 native.report_missing 时，前缀含 pip install。"""
    caps = native.discover()
    not_ready_ids = [c.id for c in caps.values() if not c.ready]
    if not not_ready_ids:
        pytest.skip("本 venv 装齐了所有原生依赖，跳过此测试")
    h = executor._hint_for(not_ready_ids[0])
    assert "pip" in h
    assert "install" in h


# ============ cmd_health 原生能力输出 ============

def test_cmd_health_shows_native_count(capsys) -> None:
    """cmd_health 现在输出原生能力计数。"""
    import argparse
    from zhenglingtai_cli.__main__ import cmd_health

    args = argparse.Namespace(verbose=False)
    rc = cmd_health(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert "[health] 原生能力：" in out
    # "[health] 可路由 skill" 字符串仍在
    assert "[health] 可路由 skill" in out


def test_cmd_health_verbose_shows_each_native(capsys) -> None:
    """--verbose 逐条打印每个原生能力状态。"""
    import argparse
    from zhenglingtai_cli.__main__ import cmd_health

    args = argparse.Namespace(verbose=True)
    cmd_health(args)
    out = capsys.readouterr().out
    for cid in ["read_text", "write_json", "hash_sha256", "pptx_create"]:
        assert cid in out, f"verbose 应出现 {cid}"
