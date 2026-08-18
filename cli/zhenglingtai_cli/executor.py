"""子能力执行器（CLI 形态替代 A 形态的 `Skill` 工具调用）。

Why this exists:
    A 形态（WorkBuddy 元 Skill）能直接 `Skill` 调用 WB 生态里的 skill。
    B 形态没有 WB 运行时，必须有个替代方案。

    本执行器设计成**通用执行器**：不预设子能力的形态，而是按配置走 4 种 kind 之一：

      kind = local：本地 Python 函数
                配置：target: "module:function"
      kind = http ：HTTP POST 一段 JSON
                配置：url / method / headers / body_template
      kind = cli  ：本地命令行
                配置：cmd + args 模板
      kind = noop ：不实际执行（用于通用模式 / 演示）

    每个子能力按"子能力契约"返回统一结果：
        {"ok": True, "outputs": [...], "logs": "...", "error": ""}

注释规范（沿用 ../SKILL.md）：
    - 每个函数三行 docstring
    - 关键判定显式注释
    - HARD: 标记不可绕过的硬约束
"""

from __future__ import annotations

import importlib
import json
import shlex
import string
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml


@dataclass
class SubcapabilityResult:
    """子能力执行结果。

    字段表：
      ok       bool         是否成功
      outputs  list[dict]   实际产物（给后续验收单用）
      logs     str          过程日志（给阶段简报用）
      error    str          错误描述
    """

    ok: bool
    outputs: list[dict]
    logs: str
    error: str = ""


def load_capabilities(cap_path=None) -> dict[str, dict]:
    """加载子能力配置。

    默认路径：./zhenglingtai-capabilities.yaml
    Why this exists:
        B 形态不知道每个 skill 怎么执行——配置由用户或政令台实例提供。
    """
    if cap_path is None:
        cap_path = Path("zhenglingtai-capabilities.yaml")
    p = Path(cap_path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def execute(
    capability_id: str,
    step: dict,
    capabilities: dict[str, dict],
    *,
    work_dir: str | Path = ".",
    llm_cfg: "LLMConfig | None" = None,  # noqa: F821 — 运行时仅查 llm 模块
) -> SubcapabilityResult:
    """执行一步工序。

    v1.2.0 起改为 4 级 fallback 链（参见 ../SKILL.md §2-⑤）：

      L1 原生能力（系统已装的库/CLI）
        ↓ 未命中或依赖不全
      L2 用户声明 cap（zhenglingtai-capabilities.yaml）
        ↓ 未声明
      L3 LLM 直接产文本（仅后缀在文本范围；需 llm_cfg）
        ↓ 不适用或调用失败
      L4 noop + 升级给人（带可执行的"启用建议"，例如 pip install 一行）

    Why 这条链：
      旧版（D7）只在 L2 找——刚装政令台啥都没配，全走 noop，
      然后 L4 验收机器契约必不达标 → ESCALATE 一头雾水。
      新版先"探环境"——Python stdlib + pyyaml + 已装三方库，本来就能跑很多事。

    Why L3 之后才升级而不是直接 L4：
      用户最常见的体验是"我就一句话，你给我个产物"。
      只要产物是文本（md/txt/py/json/yaml 等），LLM 直接写盘就行，
      跑得动总比直接放弃好。
    """
    # HARD: 通用模式下任何 skill_id 都视为无登记（参见 ../SKILL.md §3.4）
    if not capability_id or capability_id == "(无登记)":
        return _exec_noop(step, work_dir)

    # ===== L1: 原生能力 =====
    # 惰性 import 避免顶层硬依赖
    from . import native as _native
    nres = _native.invoke_if_ready(capability_id, step, work_dir)
    if nres is not None:
        return nres

    # ===== L2: 用户声明 cap =====
    cap = capabilities.get(capability_id)
    if cap:
        kind = cap.get("kind", "noop")
        if kind == "local":
            return _exec_local(capability_id, step, cap, work_dir)
        if kind == "http":
            return _exec_http(capability_id, step, cap)
        if kind == "cli":
            return _exec_cli(capability_id, step, cap, work_dir)
        # 已知 cap 但 kind 不可识别 → 走 L3
        fallback_hint = f"cap.kind={kind!r} 不可识别"

    # ===== L3: LLM 直接产文本 =====
    from . import llm_fallback as _llm_fb
    lres = _llm_fb.invoke_for_step(capability_id, step, llm_cfg, work_dir)
    if lres is not None:
        return lres

    # ===== L4: noop + 升级给人 =====
    return _exec_noop(step, work_dir, hint=_hint_for(capability_id))


def _exec_noop(step: dict, work_dir, hint: str = "") -> SubcapabilityResult:
    """noop：所有层都接不住时的最后兜底——不动手，留建议。

    Why ok=True 而不是 False：
        v1.1.0 在线契约检查发现"全错就 False 然后 L4 全报错"是反人类。
        ok=True 让 L4 走到机器契约检查，给出"文件不存在/页数不足"
        等有意义的偏差，而不是"子能力起不来"这种非技术黑话。
    """
    skill = step.get('skill_id', '?')
    base = f"[noop] 跳过执行：{skill} — {hint or '未匹配原生能力 / 用户 cap / LLM 三层中的任一层'}"
    return SubcapabilityResult(ok=True, outputs=[], logs=base, error="")


def _hint_for(capability_id: str) -> str:
    """给 L4 noop 生成可执行的"下一步怎么启用"提示。

    优先级：
      1) 原生能力缺依赖（cap_id 命中某条） → 给 pip install 一行
      2) 否则 → 给 yaml 配置路径
    Always 包含两类建议中至少一条——让用户总能立刻下手。
    """
    pip_line = ""
    try:
        from . import native as _native
        for line in _native.report_missing():
            if capability_id and capability_id in line:
                pip_line = line.strip()
                break
    except Exception:
        pass
    yaml_tip = "或 在 zhenglingtai-capabilities.yaml 添加此 skill 的配置"
    return f"pip 启用：{pip_line} {yaml_tip}" if pip_line \
        else f"在 zhenglingtai-capabilities.yaml 添加此 skill 的配置；或 pip install 启用原生能力"


def _exec_local(capability_id: str, step: dict, cap: dict, work_dir) -> SubcapabilityResult:
    """local：本地 Python 函数。"""
    target = cap.get("target", "")
    if ":" not in target:
        return SubcapabilityResult(
            ok=False, outputs=[], logs="",
            error=f"local 形式 target 必须 'module:function'，实际：{target}",
        )
    mod_name, func_name = target.split(":", 1)
    try:
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, func_name)
    except (ImportError, AttributeError) as e:
        return SubcapabilityResult(
            ok=False, outputs=[], logs="",
            error=f"加载本地子能力失败：{mod_name}:{func_name} → {e}",
        )
    try:
        out = fn(step.get("input", ""), work_dir=Path(work_dir))
    except Exception as e:  # noqa: BLE001
        return SubcapabilityResult(
            ok=False, outputs=[], logs="", error=f"执行本地子能力失败：{e}",
        )
    return _wrap_outcome(out, capability_id)


def _expand_env_in_headers(headers: dict) -> dict:
    """对 headers 的 value 做环境变量展开（$VAR / ${VAR}）。

    Why this exists:
        文档示例（EXTENDING.md / default_capabilities.yaml）写的是
        `Authorization: "Bearer $MY_API_KEY"`——"api_key 不落配置文件"的 HARD 承诺
        就指望这个展开。v1.0.2 前 headers 原样发送，$MY_API_KEY 字面量必 401。
    注意：只做 env 展开，不做 $input/$output 替换（header 不含步骤数据）。
    """
    import os
    return {k: os.path.expandvars(str(v)) for k, v in headers.items()}


def _exec_http(capability_id: str, step: dict, cap: dict) -> SubcapabilityResult:
    """http：HTTP POST。

    D9 安全加固：改用 string.Template 替代 str.format，防止格式化字符串攻击。
    body_template 里的占位符用 $input / $output 而非 {input} / {output}。
    v1.0.2：headers value 做环境变量展开（Bearer $TOKEN 类配置才可生效）。
    """
    url = cap.get("url", "")
    method = (cap.get("method") or "POST").upper()
    headers = _expand_env_in_headers(cap.get("headers") or {})
    template_raw = json.dumps(cap.get("body_template") or {})
    # 安全替换：只认 $input / $output，不解析 ${0.__class__} 等危险格式
    tpl = string.Template(template_raw)
    body_str = tpl.safe_substitute(
        input=str(step.get("input", "")),
        output=str(step.get("output", "")),
    )
    try:
        body = json.loads(body_str)
    except json.JSONDecodeError:
        body = {"input": step.get("input", "")}
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.request(method, url, headers=headers, json=body)
            resp.raise_for_status()
            out = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"raw": resp.text}
    except httpx.HTTPError as e:
        return SubcapabilityResult(
            ok=False, outputs=[], logs="", error=f"HTTP 子能力失败：{e}",
        )
    return _wrap_outcome(out, capability_id)


def _exec_cli(capability_id: str, step: dict, cap: dict, work_dir) -> SubcapabilityResult:
    """cli：本地命令行。"""
    cmd = shlex.split(cap.get("cmd", ""))
    args_tpl = cap.get("args") or []
    args = []
    for a in args_tpl:
        if isinstance(a, str) and "$" in a:
            # D9 安全加固：用 string.Template 替代 str.format
            tpl = string.Template(a)
            args.append(tpl.safe_substitute(
                input=str(step.get("input", "")),
                output=str(step.get("output", "")),
            ))
        else:
            args.append(str(a))

    if not cmd:
        return SubcapabilityResult(False, [], "", "cli 形式 cmd 不能为空")
    try:
        result = subprocess.run(
            cmd + args, cwd=Path(work_dir), capture_output=True, text=True, timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return SubcapabilityResult(
            ok=False, outputs=[], logs="", error=f"CLI 子能力失败：{e}",
        )
    if result.returncode != 0:
        return SubcapabilityResult(
            ok=False, outputs=[], logs=result.stdout,
            error=f"CLI 退出码 {result.returncode}：{result.stderr[:500]}",
        )
    # v1.0.3 修复：旧返回 {"stdout": ...} 不符合子能力契约——
    # _wrap_outcome 只认 ok/outputs/logs/error 键，stdout 被静默丢弃，logs 永远为空
    return _wrap_outcome(
        {"ok": True, "outputs": [], "logs": result.stdout}, capability_id)


def _wrap_outcome(out: Any, capability_id: str) -> SubcapabilityResult:
    """统一封装子能力返回值为 SubcapabilityResult。"""
    if isinstance(out, SubcapabilityResult):
        return out
    if isinstance(out, dict):
        return SubcapabilityResult(
            ok=bool(out.get("ok", True)),
            outputs=list(out.get("outputs") or []),
            logs=str(out.get("logs") or ""),
            error=str(out.get("error") or ""),
        )
    return SubcapabilityResult(
        ok=True, outputs=[], logs=repr(out)[:500],
        error="（子能力未遵循契约，请返回 dict）",
    )
