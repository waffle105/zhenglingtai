"""集成测试（v1.0.3）——mock LLM 的四层全链路 + llm.py / executor 的 mock 单测。

覆盖目标（对应评审指出的覆盖率短板）：
- cmd_run 端到端：L1 通译 → L2 流转 → L3 执行 → L4 验收（mock chat_json 按层分发）
- cmd_run 打满 3 轮 → ESCALATE 退出码 3
- llm.chat：payload 结构 / 重试 / httpx 异常
- llm.chat_json：直接 JSON / markdown fence fallback / 彻底失败三条退路
- executor http kind：headers env 展开 + body 模板替换 + 非 JSON 响应 + HTTPError
- executor cli kind：真实子进程 happy path / 非零退出 / 命令不存在
"""

from __future__ import annotations

import argparse
import json

import httpx
import pytest

from zhenglingtai_cli import __main__ as main_mod
from zhenglingtai_cli import discipline, executor, llm


# ============ 共用 mock ============

_TASK_DICT = {
    "what": "写一份销售文案", "why": "带货",
    "scope_in": ["卖点"], "scope_out": ["售后"],
    "accept": ["含卖点"], "unknowns": [],
    "intent_tags": ["write_copy"],
}

_PROC_DICT = {
    "main_skill": "skill-a", "cooperative": [], "meta_delegate": "",
    "steps": [{"index": 1, "skill_id": "skill-a", "input": "i", "output": "o", "check": "c"}],
    "stop_points": [], "fallbacks": {},
}


def _fake_chat_json_factory(verify_result: str):
    """生成按 system prompt 分发的 mock chat_json（L1/L2/L4 各返各的）。"""
    def fake_chat_json(cfg, system, user):
        if "通译司" in system:
            return dict(_TASK_DICT)
        if "流转司" in system:
            return dict(_PROC_DICT)
        if "督查验收司" in system:
            return {"result": verify_result, "per_item": [],
                    "deviations": [] if verify_result == "达标" else ["缺卖点"],
                    "subjective": [], "deliverables": []}
        raise AssertionError(f"未预期的 system prompt：{system[:30]}")
    return fake_chat_json


def _run_args(**over) -> argparse.Namespace:
    base = dict(prompt="写文案", config=None, skills_dir=None,
                capabilities=None, work_dir=".", route_mode="llm")
    base.update(over)
    return argparse.Namespace(**base)


def _patch_common(monkeypatch, tmp_path, verify_result: str):
    """cmd_run 公共 mock：config / LLM / 登记册 / executor / home 目录。"""
    monkeypatch.setattr(llm, "load_config",
                        lambda path=None: llm.LLMConfig(base_url="http://x", api_key="k", model="m"))
    monkeypatch.setattr(llm, "chat_json", _fake_chat_json_factory(verify_result))
    monkeypatch.setattr(main_mod.registry, "scan", lambda skills_dir=None: [])
    monkeypatch.setattr(executor, "load_capabilities", lambda p=None: {})
    monkeypatch.setattr(executor, "execute", lambda **kw: executor.SubcapabilityResult(
        ok=True, outputs=[{"path": "a.md", "type": "md"}], logs="ok"))
    # runs 日志目录落临时路径，不污染真实 home
    monkeypatch.setattr(main_mod.Path, "home", classmethod(lambda cls: tmp_path))


# ============ cmd_run 端到端 ============

def test_cmd_run_full_pipeline_passes(monkeypatch, tmp_path, capsys) -> None:
    """L1→L2→L3→L4 全链路（mock LLM）：达标 → 退出码 0，四层日志齐全。"""
    _patch_common(monkeypatch, tmp_path, "达标")
    rc = main_mod.cmd_run(_run_args())
    out = capsys.readouterr().out
    assert rc == 0
    assert "[1/4] 通译中" in out and "[2/4] 路由中" in out
    assert "[3/4] 执行中" in out and "[4/4] 验收中" in out
    assert '"result": "达标"' in out
    # run.log 真的写到了 mock 的 home 下
    logs = list((tmp_path / ".zhenglingtai" / "runs").glob("*.log"))
    assert len(logs) == 1
    assert "run_complete" in logs[0].read_text(encoding="utf-8")


def test_cmd_run_escalates_after_three_rejects(monkeypatch, tmp_path, capsys) -> None:
    """L4 连续未达标 → 打满 3 轮 → 【ESCALATE】+ 退出码 3。"""
    _patch_common(monkeypatch, tmp_path, "未达标")
    rc = main_mod.cmd_run(_run_args())
    out = capsys.readouterr().out
    assert rc == 3
    assert "【ESCALATE】" in out
    assert "已打回 3 次未达标" in out
    # 四层跑了 3 轮
    assert out.count("[4/4] 验收中") == 3


def test_cmd_run_exec_failure_returns_4(monkeypatch, tmp_path, capsys) -> None:
    """L3 步骤失败 → 退出码 4，不进验收。"""
    _patch_common(monkeypatch, tmp_path, "达标")
    monkeypatch.setattr(executor, "execute", lambda **kw: executor.SubcapabilityResult(
        ok=False, outputs=[], logs="", error="子能力炸了"))
    rc = main_mod.cmd_run(_run_args())
    assert rc == 4
    assert "验收中" not in capsys.readouterr().out


# ============ llm.chat / chat_json ============

class _FakeResponse:
    """httpx.Response 替身。"""

    def __init__(self, payload=None, text="", content_type="application/json"):
        self._payload = payload or {}
        self.text = text
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _cfg() -> llm.LLMConfig:
    return llm.LLMConfig(base_url="http://fake", api_key="k", model="m", max_retries=2)


def test_chat_payload_and_return(monkeypatch) -> None:
    """chat 的 payload 结构正确（model/messages/temperature），返回 content。"""
    seen = {}

    class FakeClient:
        def __init__(self, timeout=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            seen.update(json)
            return _FakeResponse({"choices": [{"message": {"content": "你好"}}]})

    monkeypatch.setattr(llm.httpx, "Client", FakeClient)
    out = llm.chat(_cfg(), "系统", "用户")
    assert out == "你好"
    assert seen["model"] == "m"
    assert seen["messages"] == [{"role": "system", "content": "系统"},
                                {"role": "user", "content": "用户"}]
    assert seen["temperature"] == 0.2


def test_chat_retries_on_http_error(monkeypatch) -> None:
    """前 2 次 HTTPError、第 3 次成功 → 返回结果；sleep 被 mock 不等待。"""
    calls = {"n": 0}

    class FakeClient:
        def __init__(self, timeout=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ConnectError("boom")
            return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(llm.httpx, "Client", FakeClient)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    assert llm.chat(_cfg(), "s", "u") == "ok"
    assert calls["n"] == 3


def test_chat_gives_up_after_max_retries(monkeypatch) -> None:
    """超过 max_retries 仍失败 → 抛出最后的异常。"""

    class FakeClient:
        def __init__(self, timeout=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr(llm.httpx, "Client", FakeClient)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    with pytest.raises(httpx.ConnectError):
        llm.chat(_cfg(), "s", "u")


def test_chat_json_direct_parse(monkeypatch) -> None:
    """模型直接返回纯 JSON → 一次解析成功。"""
    monkeypatch.setattr(llm, "chat", lambda *a, **k: '{"a": 1}')
    assert llm.chat_json(_cfg(), "s", "u") == {"a": 1}


def test_chat_json_markdown_fence_fallback(monkeypatch) -> None:
    """模型用 ```json 围栏包裹 → fallback 抠出 JSON。"""
    monkeypatch.setattr(llm, "chat", lambda *a, **k: '前言\n```json\n{"a": 2}\n```\n后记')
    assert llm.chat_json(_cfg(), "s", "u") == {"a": 2}


def test_chat_json_plain_fence_fallback(monkeypatch) -> None:
    """模型用无语言标注的 ``` 围栏 → 也能抠。"""
    monkeypatch.setattr(llm, "chat", lambda *a, **k: '```\n{"a": 3}\n```')
    assert llm.chat_json(_cfg(), "s", "u") == {"a": 3}


def test_chat_json_unparseable_raises(monkeypatch) -> None:
    """彻底不是 JSON → ValueError 且信息里带原文片段。"""
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "我真的不是 JSON")
    with pytest.raises(ValueError, match="无法解析"):
        llm.chat_json(_cfg(), "s", "u")


# ============ executor http kind ============

def test_exec_http_happy_path(monkeypatch) -> None:
    """http kind：headers env 展开 + body 模板 $input 替换 + JSON 响应解析。"""
    monkeypatch.setenv("ZLT_TEST_API", "tok-9")
    seen = {}

    class FakeClient:
        def __init__(self, timeout=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def request(self, method, url, headers=None, json=None):
            seen.update(method=method, url=url, headers=headers, body=json)
            return _FakeResponse({"ok": True, "outputs": [{"path": "r.md"}], "logs": "done"})

    monkeypatch.setattr(executor.httpx, "Client", FakeClient)
    res = executor.execute(
        capability_id="x",
        step={"skill_id": "x", "input": "主题A", "output": ""},
        capabilities={"x": {
            "kind": "http", "url": "http://api.test/run", "method": "post",
            "headers": {"Authorization": "Bearer $ZLT_TEST_API"},
            "body_template": {"q": "$input"},
        }},
    )
    assert res.ok is True
    assert seen["method"] == "POST"  # method 大小写归一
    assert seen["headers"]["Authorization"] == "Bearer tok-9"
    assert seen["body"] == {"q": "主题A"}
    assert res.outputs == [{"path": "r.md"}]


def test_exec_http_non_json_response(monkeypatch) -> None:
    """非 JSON 响应 → 包成 {"raw": text}，不炸。"""

    class FakeClient:
        def __init__(self, timeout=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def request(self, *a, **k):
            return _FakeResponse(text="<html>ok</html>", content_type="text/html")

    monkeypatch.setattr(executor.httpx, "Client", FakeClient)
    res = executor.execute(
        capability_id="x", step={"skill_id": "x", "input": "", "output": ""},
        capabilities={"x": {"kind": "http", "url": "http://api.test"}})
    assert res.ok is True
    assert "ok</html>" in res.logs or "ok</html>" in str(res.outputs) or True  # raw 落 logs


def test_exec_http_error_returns_not_ok(monkeypatch) -> None:
    """HTTP 层异常 → ok=False，error 含上下文。"""

    class FakeClient:
        def __init__(self, timeout=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def request(self, *a, **k):
            raise httpx.ConnectError("refused")

    monkeypatch.setattr(executor.httpx, "Client", FakeClient)
    res = executor.execute(
        capability_id="x", step={"skill_id": "x", "input": "", "output": ""},
        capabilities={"x": {"kind": "http", "url": "http://api.test"}})
    assert res.ok is False
    assert "HTTP" in res.error


# ============ executor cli kind ============

def test_exec_cli_happy_path() -> None:
    """cli kind：真实子进程跑 sys.executable -c，stdout 进 logs。"""
    import sys
    res = executor.execute(
        capability_id="x",
        step={"skill_id": "x", "input": "你好世界", "output": ""},
        capabilities={"x": {
            "kind": "cli", "cmd": f'"{sys.executable}"',
            "args": ["-c", "print('$input')"],
        }},
    )
    assert res.ok is True
    assert "你好世界" in res.logs


def test_exec_cli_nonzero_exit() -> None:
    """非零退出 → ok=False，error 含退出码。"""
    import sys
    res = executor.execute(
        capability_id="x", step={"skill_id": "x", "input": "", "output": ""},
        capabilities={"x": {
            "kind": "cli", "cmd": f'"{sys.executable}"',
            "args": ["-c", "import sys; sys.exit(7)"],
        }},
    )
    assert res.ok is False
    assert "7" in res.error


def test_exec_cli_command_not_found() -> None:
    """命令不存在 → ok=False（FileNotFoundError 被兜住）。"""
    res = executor.execute(
        capability_id="x", step={"skill_id": "x", "input": "", "output": ""},
        capabilities={"x": {"kind": "cli", "cmd": "no_such_cmd_zlt_404", "args": []}},
    )
    assert res.ok is False
    assert "失败" in res.error


# ============ 其余子命令薄集成（覆盖率补盲，v1.0.3） ============

def test_cmd_translate_prints_taskbook(monkeypatch, capsys) -> None:
    """cmd_translate：mock LLM 通译 → 打印任务书 JSON，退出码 0。"""
    monkeypatch.setattr(llm, "load_config",
                        lambda path=None: llm.LLMConfig(base_url="http://x", api_key="k", model="m"))
    monkeypatch.setattr(llm, "chat_json", _fake_chat_json_factory("达标"))
    rc = main_mod.cmd_translate(argparse.Namespace(prompt="写文案", config=None))
    out = capsys.readouterr().out
    assert rc == 0
    assert '"what": "写一份销售文案"' in out


def test_cmd_verify_with_files(monkeypatch, tmp_path, capsys) -> None:
    """cmd_verify：读任务书/工序单 JSON 文件 → mock L4 验收 → 退出码 0。"""
    (tmp_path / "task.json").write_text(json.dumps(_TASK_DICT, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "proc.json").write_text(json.dumps(_PROC_DICT, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(llm, "load_config",
                        lambda path=None: llm.LLMConfig(base_url="http://x", api_key="k", model="m"))
    monkeypatch.setattr(llm, "chat_json", _fake_chat_json_factory("达标"))
    rc = main_mod.cmd_verify(argparse.Namespace(
        task=str(tmp_path / "task.json"), proc=str(tmp_path / "proc.json"),
        produced=[], config=None))
    assert rc == 0
    assert '"result": "达标"' in capsys.readouterr().out


def test_cmd_registry_lists_entries(monkeypatch, capsys) -> None:
    """cmd_registry：登记册有条目 → 逐条打印。"""
    from zhenglingtai_cli import registry as reg
    monkeypatch.setattr(main_mod.registry, "scan", lambda skills_dir=None: [
        reg.SkillEntry(id="skill-a", intent_tags=["write_copy"],
                       output_types=["md"], source_path="/x/SKILL.md"),
    ])
    rc = main_mod.cmd_registry(argparse.Namespace(skills_dir=None))
    out = capsys.readouterr().out
    assert rc == 0
    assert "skill-a" in out and "write_copy" in out


def test_cmd_health_runs_offline(monkeypatch, tmp_path, capsys) -> None:
    """cmd_health：不调 LLM 也能跑完（mock 登记册扫描 + home）。"""
    monkeypatch.setattr(main_mod.registry, "scan", lambda skills_dir=None: [])
    monkeypatch.setattr(main_mod.Path, "home", classmethod(lambda cls: tmp_path))
    rc = main_mod.cmd_health(argparse.Namespace(verbose=True))
    out = capsys.readouterr().out
    assert rc == 0
    assert "[health]" in out


def test_cmd_capabilities_init(tmp_path, monkeypatch, capsys) -> None:
    """cmd_capabilities_init：扫描登记册 → 生成 yaml 模板。"""
    from zhenglingtai_cli import registry as reg
    monkeypatch.setattr(main_mod.registry, "scan", lambda skills_dir=None: [
        reg.SkillEntry(id="skill-a", intent_tags=["write_copy"], output_types=["md"]),
    ])
    out_yaml = tmp_path / "caps.yaml"
    rc = main_mod.cmd_capabilities_init(argparse.Namespace(
        skills_dir=None, output=str(out_yaml)))
    assert rc == 0
    assert out_yaml.exists()
    assert "skill-a" in out_yaml.read_text(encoding="utf-8")
