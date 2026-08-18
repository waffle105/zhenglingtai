"""四层纪律（B 形态实现，与 A 形态共用 schema）。

为什么存在：
    把 A 形态 ../SKILL.md §2 的四层翻译成可执行的 Python 函数。
    L1/L2/L4 调 LLM；L3 调执行器（executor.py）。
    整套节奏由 __main__.py 串起来。

跨形态一致性保障：
    这里的 TaskBook/Procedure/Acceptance 字段命名与 A 形态 templates/ 完全一致。
    任何一形态出的任务书 JSON 能被另一形态消费。

注释规范提示：
    - 每个函数 docstring 三行
    - 关键判定显式注释（"如果 X 则 Y"）
    - HARD: 标记不可绕过的硬约束
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import llm
from .registry import SkillEntry


@dataclass
class TaskBook:
    """政令任务书（来自通译层 L1）。

    与 A 形态 templates/政令任务书.md 字段完全等价。
    """

    what: str
    why: str
    scope_in: list[str]
    scope_out: list[str]
    accept: list[str]
    unknowns: list[str]
    intent_tags: list[str] = field(default_factory=list)


@dataclass
class Step:
    """工序单里一步工序。"""

    index: int
    skill_id: str
    input: str = ""
    output: str = ""
    check: str = ""


@dataclass
class Procedure:
    """执行工序单（来自流转层 L2）。"""

    main_skill: str
    cooperative: list[str]
    meta_delegate: str
    steps: list[Step]
    stop_points: list[int]
    fallbacks: dict[str, str]


@dataclass
class Acceptance:
    """验收确认单（来自验收层 L4）。

    HARD: 如果结论是 "未达标" 但 deviations 为空 → 视为不合规，自动补一行说明
    """

    result: str
    per_item: list[dict]
    deviations: list[str]
    subjective: list[str]
    deliverables: list[dict]


# ============ 层 1：通译司 ============

_SYSTEM_L1 = """你是「政令台·通译司」。你的唯一工作是：
1) 把用户模糊的口语指令翻译成结构化"政令任务书"JSON
2) 不要扩写需求，只通译补全
3) intent_tags 字段从下面词表里选词（不要自造）：

{catalog}

任务书 schema：
{{
  "what": "一句话说清要做的事",
  "why": "为什么要做（决定验收的'好坏'标准）",
  "scope_in": ["本次覆盖的内容"],
  "scope_out": ["明确排除的内容（至少 1 条）"],
  "accept": ["可勾选的达成条件", "至少 1 条"],
  "unknowns": ["阻塞项；可空"],
  "intent_tags": ["从此词表选词", "至少 1 个"]
}}

只输出 JSON。"""


def layer1_translate(
    cfg: llm.LLMConfig,
    user_input: str,
    intent_tags_catalog: list[str],
) -> TaskBook:
    """层 1：通译 → TaskBook JSON。"""
    catalog_md = "\n".join(f"- {t}" for t in intent_tags_catalog)
    system = _SYSTEM_L1.format(catalog=catalog_md)
    data = llm.chat_json(cfg, system, user_input)
    return _parse_taskbook(data)


def layer1_translate_offline(user_input: str) -> TaskBook:
    """层 1 确定性通译（--offline）：不调 LLM，规则构造最小任务书。

    Why this exists:
        评审建议：纪律层在无 LLM 环境（CI / 离线 / 无 API key）也应能端到端跑通。
        本函数是 L1 的确定性替代——不解析意图（那需要 LLM），只做最小包装。

    口径（与 L1"只通译不扩写"原则一致）：
    - what = 原始指令原文，不扩写
    - why / unknowns 显式标注"未经 LLM 通译"——不假装解析过
    - intent_tags = [] → 流转层必走通用模式（§3.4），不硬猜意图
    """
    text = user_input.strip()
    return TaskBook(
        what=text,
        why="（offline 模式：未经 LLM 通译，目的未解析——验收以机器契约为准）",
        scope_in=[text],
        scope_out=["（offline 模式：未声明排除项）"],
        accept=["产物文件存在且非空"],
        unknowns=["任务书未经 LLM 通译与用户确认"],
        intent_tags=[],
    )


def _parse_taskbook(data: dict[str, Any]) -> TaskBook:
    """LLM 输出 JSON → TaskBook。校验必填字段。"""
    # HARD: 关键字段缺/空就 raise，让上层做错误处理
    for k in ("what", "why", "accept", "intent_tags"):
        v = data.get(k)
        if not v:
            raise ValueError(f"任务书缺关键字段或为空：{k}")

    return TaskBook(
        what=str(data["what"]),
        why=str(data["why"]),
        scope_in=list(data.get("scope_in") or []),
        scope_out=list(data.get("scope_out") or []),
        accept=list(data.get("accept") or []),
        unknowns=list(data.get("unknowns") or []),
        intent_tags=list(data.get("intent_tags") or []),
    )


# ============ 层 2：流转司 ============

_SYSTEM_L2 = """你是「政令台·流转司」。你的工作是：
读"通译层产出的任务书 JSON"和"候选 skill 列表"，输出"执行工序单"JSON。

路由规则（参见 ../SKILL.md §3）：
- 多个候选 output_types 不重叠 → 协同，按工序串行
- 多个候选 output_types 撞同一产出 → 冲突，按"最具体优先"消解
- 候选全无 / query 为空 → 转"通用模式"：所有工序标 skill_id="(无登记)"

候选 skill：
{skills}

工序单 schema：
{{
  "main_skill": "<id 或 (无登记)>",
  "cooperative": ["<id>", ...],
  "meta_delegate": "<id 或 空>",
  "steps": [{{"index": 1, "skill_id": "<id>", "input": "...", "output": "...", "check": "..."}}],
  "stop_points": [步骤编号],
  "fallbacks": {{ "<skill_id>": "<兜底策略>" }}
}}

只输出 JSON。"""


def layer2_route_deterministic(
    task: TaskBook,
    candidate_entries: list[SkillEntry],
) -> Procedure:
    """层 2 确定性路由：纯算法，不调 LLM。

    用 registry.score() 排序 + §3.7 冲突消解规则。
    用于 CI / 离线 / --route-mode=deterministic。

    Why this exists:
        旧 layer2_route 全交给 LLM 选 skill——不稳定、不可复现。
        本函数把"选 skill"和"编工序"拆开：
        选 skill 靠确定性算法；编工序的 input/output 文案才可能需要 LLM。
    """
    from . import registry as reg

    # HARD: 空 query 或空登记册 → 通用模式
    if not task.intent_tags or not candidate_entries:
        return _generic_mode_procedure(task)

    scored = reg.score(candidate_entries, task.intent_tags, [])
    if not scored:
        return _generic_mode_procedure(task)

    top_entry, top_score = scored[0]

    # 如果 top1 是 meta-skill → 整条委托
    if top_entry.is_meta:
        return Procedure(
            main_skill="(meta委托)",
            cooperative=[],
            meta_delegate=top_entry.id,
            steps=[Step(
                index=1, skill_id=top_entry.id,
                input=task.what,
                output="(meta-skill 自行产出)",
                check="验收司对照 task.accept 逐条查",
            )],
            stop_points=[],
            fallbacks={},
        )

    # 非 meta：检查协同（output_types 不重叠 → 串行）
    cooperative: list[str] = []
    used_outputs = set(top_entry.output_types)
    for entry, score_val in scored[1:]:
        if entry.is_meta:
            continue
        # 如果 output_types 与已有候选不重叠 → 协同
        overlap = set(entry.output_types) & used_outputs
        if not overlap:
            cooperative.append(entry.id)
            used_outputs |= set(entry.output_types)

    # 构造 steps
    all_skills = [top_entry] + [
        e for e, _ in scored[1:] if e.id in cooperative
    ]
    steps = []
    for i, entry in enumerate(all_skills, 1):
        steps.append(Step(
            index=i,
            skill_id=entry.id,
            input=f"(见任务书: {task.what[:50]})" if i == 1 else f"(上一步产出)",
            output=f"产出({', '.join(entry.output_types) or 'md'})",
            check=f"对照 task.accept[{i-1}]" if i <= len(task.accept) else "验收司查",
        ))

    return Procedure(
        main_skill=top_entry.id,
        cooperative=cooperative,
        meta_delegate="",
        steps=steps,
        stop_points=[i for i in range(1, len(steps))],
        fallbacks={e.id: f"通用模式兜底" for e in all_skills},
    )


def _generic_mode_procedure(task: TaskBook) -> Procedure:
    """通用模式工序单：无 skill 匹配时走这里。"""
    return Procedure(
        main_skill="(无登记)",
        cooperative=[],
        meta_delegate="",
        steps=[Step(
            index=1, skill_id="(无登记)",
            input=task.what,
            output="(AI 直接产出)",
            check="验收司对照 task.accept 逐条查",
        )],
        stop_points=[],
        fallbacks={},
    )


def layer2_route(
    cfg: llm.LLMConfig,
    task: TaskBook,
    candidate_entries: list[SkillEntry],
    mode: str = "auto",
) -> Procedure:
    """层 2：路由 → Procedure JSON。

    mode:
        "auto"          (默认) 先跑确定性算法选 skill；多 skill 需编排时才调 LLM
        "deterministic"  纯算法，不调 LLM（CI / 离线 / 测试用）
        "llm"           纯 LLM 选 skill（旧行为，用于对照）
    """
    # 确定性模式：纯算法
    if mode == "deterministic":
        return layer2_route_deterministic(task, candidate_entries)

    # auto 模式：先跑确定性算法
    det_proc = layer2_route_deterministic(task, candidate_entries)

    # auto 模式决策：
    # - 如果确定性结果只有 1 个 skill 且无协同 → 直接用（不需要 LLM）
    # - 如果需要编排（多 skill 协同 / meta 委托）→ 调 LLM 做编排
    # - 如果通用模式 → 直接用
    if mode == "auto":
        if (det_proc.main_skill == "(无登记)"
                or (det_proc.main_skill != "(meta委托)"
                    and not det_proc.cooperative
                    and len(det_proc.steps) <= 1)):
            return det_proc
        # 需要 LLM 做编排——但 LLM 拿到的候选已经是确定性排序后的
        # 这样 LLM 只负责写 input/output/check 文案，不负责选 skill

    # LLM 模式或 auto 需要编排
    skills_md = "\n".join(
        f"- id={s.id} intent_tags={s.intent_tags} output_types={s.output_types} is_meta={s.is_meta}"
        for s in candidate_entries
    ) or "（无可路由 skill，自动转通用模式）"

    system = _SYSTEM_L2.format(skills=skills_md)
    user_payload = json.dumps(task.__dict__, ensure_ascii=False)
    data = llm.chat_json(cfg, system, user_payload)
    return _parse_procedure(data)


def _parse_procedure(data: dict[str, Any]) -> Procedure:
    """LLM 输出 JSON → Procedure。"""
    steps_raw = data.get("steps") or []
    steps = [
        Step(
            index=int(s.get("index", i + 1)),
            skill_id=str(s.get("skill_id") or "(无登记)"),
            input=str(s.get("input") or ""),
            output=str(s.get("output") or ""),
            check=str(s.get("check") or ""),
        )
        for i, s in enumerate(steps_raw)
    ]
    return Procedure(
        main_skill=str(data.get("main_skill") or "(无登记)"),
        cooperative=list(data.get("cooperative") or []),
        meta_delegate=str(data.get("meta_delegate") or ""),
        steps=steps,
        stop_points=list(data.get("stop_points") or []),
        fallbacks=dict(data.get("fallbacks") or {}),
    )


# ============ 层 4：督查验收司 ============

_SYSTEM_L4 = """你是「政令台·督查验收司」。你的工作是：
对照「任务书的 Accept 字段」逐条审查执行结果，输出"验收确认单"JSON。

封驳规则：
- 任何关键项不达标 → result="未达标"，per_item 标 fail，deviations 必须填
- 主观项 → 写在 subjective 字段，**绝不**算 ok

验收单 schema：
{{
  "result": "达标" / "未达标",
  "per_item": [{{"item": "...", "status": "ok/fail", "evidence": "...", "deviation": "..."}}],
  "deviations": ["补救建议"],
  "subjective": ["主观项"],
  "deliverables": [{{"path": "...", "type": "...", "summary": "..."}}]
}}

只输出 JSON。"""


def layer4_verify(
    cfg: llm.LLMConfig,
    task: TaskBook,
    proc: Procedure,
    produced_files: list[dict],
) -> Acceptance:
    """层 4：验收 → Acceptance JSON。

    v1.0.3 修复：proc.__dict__ 里嵌着 Step 对象，json.dumps 直接抛
    TypeError——真实 LLM 路径下 L4 从未走通（集成测试抓出）。改 asdict 递归转换。
    """
    from dataclasses import asdict
    system = _SYSTEM_L4
    user_payload = json.dumps(
        {
            "task": asdict(task),
            "procedure": asdict(proc),
            "produced_files": produced_files,
        },
        ensure_ascii=False,
    )
    data = llm.chat_json(cfg, system, user_payload)
    return _parse_acceptance(data)


def _parse_acceptance(data: dict[str, Any]) -> Acceptance:
    """LLM 输出 JSON → Acceptance。

    HARD: result=未达标 但 deviations 为空 → 自动补说明
    """
    result = str(data.get("result") or "未达标")
    deviations = list(data.get("deviations") or [])
    if result == "未达标" and not deviations:
        deviations.append("（验收单里 deviations 为空——LLM 输出不合规，请复核）")
    return Acceptance(
        result=result,
        per_item=list(data.get("per_item") or []),
        deviations=deviations,
        subjective=list(data.get("subjective") or []),
        deliverables=list(data.get("deliverables") or []),
    )


# ============ 层 4 确定性验收（--offline，v1.1.0） ============

def layer4_verify_deterministic(
    task: TaskBook,
    proc: Procedure,
    produced_files: list[dict],
    work_dir: str | Path = ".",
) -> Acceptance:
    """层 4 确定性验收：不调 LLM，按 ../SKILL.md §5 机器契约逐项校验。

    判定口径（与 SKILL.md §5 的 HARD 一致）：
    - 可机器判定 → per_item：产物物理属性（存在/非空）+ 类型特定检查
      （pptx 页数 / xlsx sheet 数 / md 字数 / py 语法编译）
      + accept 中可正则提取的阈值（页数 ≥ N / 字数 ≥ N）
    - 不可机器判定 → subjective：accept 的语义条目（含某段/有出处/文风…）
      全部标"需用户主观确认"，绝不替用户拍板达标
    - produced 为空 → 未达标（无产物却宣称达标，是幻觉的温床）
    """
    if not produced_files:
        return Acceptance(
            result="未达标",
            per_item=[{
                "item": "产物存在性", "status": "fail", "evidence": "无产物",
                "deviation": "执行层未产出任何文件——offline 通用模式（noop）下本属预期；"
                             "若要真实产出，请配置 capabilities 或改用 LLM 模式",
            }],
            deviations=["无产物可供机器验收"],
            subjective=list(task.accept),
            deliverables=[],
        )

    per_item: list[dict] = []
    deviations: list[str] = []
    deliverables: list[dict] = []
    all_ok = True

    for item in produced_files:
        path_str = str(item.get("path", ""))
        ptype = str(item.get("type", "")).lower()
        p = Path(path_str)
        if not p.is_absolute():
            p = Path(work_dir) / p
        evidence, deviation = _check_file_contract(p, ptype, task.accept)
        if deviation:
            all_ok = False
            deviations.append(f"{path_str}：{deviation}")
        per_item.append({
            "item": f"产物 {path_str}（{ptype or '未知类型'}）",
            "status": "fail" if deviation else "ok",
            "evidence": evidence,
            "deviation": deviation,
        })
        deliverables.append({
            "path": path_str, "type": ptype,
            "summary": str(item.get("summary") or ""),
        })

    return Acceptance(
        result="达标" if all_ok else "未达标",
        per_item=per_item,
        deviations=deviations,
        subjective=list(task.accept),
        deliverables=deliverables,
    )


def _check_file_contract(p: Path, ptype: str, accept: list[str]) -> tuple[str, str]:
    """单产物机器契约校验。

    返回 (evidence, deviation)；deviation 为空串即通过。
    类型特定检查全部用标准库实现（zipfile/re/py_compile），不引新依赖。
    """
    if not str(p):
        return "", "产物缺少 path 字段"
    if not p.exists():
        return "", "文件不存在"
    size = p.stat().st_size
    if size == 0:
        return "", "文件为空（0 字节）"
    evidence = f"存在，{size} B"

    if ptype == "pptx":
        n = _count_zip_members(p, r"ppt/slides/slide\d+\.xml")
        if n is None:
            return evidence, "pptx 无法解析（不是有效的 zip 容器）"
        evidence += f"，{n} 页"
        want = _extract_threshold(accept, r"页数\s*[≥>=]\s*(\d+)")
        if want is not None and n < want:
            return evidence, f"页数 {n} < 任务书要求 ≥ {want}"
    elif ptype == "xlsx":
        n = _count_zip_members(p, r"xl/worksheets/sheet\d+\.xml")
        if n is None:
            return evidence, "xlsx 无法解析（不是有效的 zip 容器）"
        evidence += f"，{n} 个 sheet"
    elif ptype in ("md", "txt"):
        text_len = len(p.read_text(encoding="utf-8", errors="ignore"))
        evidence += f"，{text_len} 字符"
        want = _extract_threshold(accept, r"字数\s*[≥>=]\s*(\d+)")
        if want is not None and text_len < want:
            return evidence, f"字数 {text_len} < 任务书要求 ≥ {want}"
    elif ptype == "py":
        import os
        import py_compile
        import tempfile
        # cfile 指向临时文件：只校验不落 __pycache__（避免污染工作目录）。
        # 注意不能指向 os.devnull——Windows 上 py_compile 拒绝写 nul 设备。
        fd, cfile = tempfile.mkstemp(suffix=".pyc")
        os.close(fd)
        try:
            py_compile.compile(str(p), cfile=cfile, doraise=True)
            evidence += "，语法检查通过"
        except py_compile.PyCompileError as e:
            return evidence, f"语法检查失败：{str(e).splitlines()[0] if str(e) else e}"
        finally:
            Path(cfile).unlink(missing_ok=True)
    return evidence, ""


def _count_zip_members(p: Path, pattern: str) -> int | None:
    """数 zip 容器里匹配 pattern 的成员数；无法解析返回 None。"""
    import re
    import zipfile
    try:
        with zipfile.ZipFile(p) as z:
            rx = re.compile(pattern)
            return sum(1 for n in z.namelist() if rx.fullmatch(n))
    except (zipfile.BadZipFile, OSError):
        return None


def _extract_threshold(accept: list[str], pattern: str) -> int | None:
    """从 accept 自由文本里抠数值阈值（如"页数 ≥ 10"）；无则 None。"""
    import re
    for a in accept:
        m = re.search(pattern, str(a))
        if m:
            return int(m.group(1))
    return None
