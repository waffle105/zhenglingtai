"""CLI 主入口：zhengling run / verify / health / registry / translate / capabilities / migrate

用法：
    zhengling health                          - 自检（无 LLM 也能跑）
    zhengling registry                        - 列登记册里所有 skill
    zhengling translate "..."                 - 只跑通译（L1）
    zhengling run "..."                       - 跑完整四层
    zhengling verify --task=... --proc=...    - 单独跑验收（L4）
    zhengling capabilities init              - 生成 capabilities yaml 模板
    zhengling migrate scan                    - 扫描缺 capability 的 skill
    zhengling migrate suggest <skill_id>      - LLM 建议 intent_tags
    zhengling migrate batch --dry-run         - 批量生成迁移计划

为什么用 subcommand：
    子能力调试 / 单步测试都需要；用户能排查某一步。

退出码：
    0  达标
    2  流程错误（配置/网络/LLM 解析失败）
    3  封驳未达标
    4  子能力执行失败

注释规范：
    - subcommand 三行 docstring
    - 关键判定显式注释
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import discipline, executor, llm, logutil, migrator, registry


def cmd_health(args: argparse.Namespace) -> int:
    """自检：不调 LLM，验证环境是否就绪。

    子检查：
      1) Python ≥ 3.10
      2) ~/.workbuddy/skills 目录是否存在（不存在也 OK——通用模式能跑）
      3) LLM 配置是否能找到
      4) 至少检查到一个 capability 可路由的 skill
    """
    print("[health] Python:", sys.version.split()[0])
    print(f"[health] Python ≥ 3.10: {'✔' if sys.version_info >= (3, 10) else '✘'}")
    skills_dir = Path.home() / ".workbuddy" / "skills"
    print(f"[health] ~/.workbuddy/skills: {'存在' if skills_dir.exists() else '不存在（无妨）'}")

    cfg_path = Path("zlt.config.yaml")
    cfg_alt = Path.home() / ".config" / "zhenglingtai" / "config.yaml"
    cfg_present = cfg_path.exists() or cfg_alt.exists()
    print(f"[health] LLM config: {'已找到' if cfg_present else '未找到（run 子命令需要）'}")

    try:
        entries = registry.scan(skills_dir)
        capable = sum(1 for e in entries if e.intent_tags)
        print(f"[health] 可路由 skill：{len(entries)} 总/{capable} 已声明 capability")
        if capable == 0:
            print("[hint] 你的 skill 都没声明 capability → run 会进'通用模式'，纪律层仍生效。")
    except Exception as e:  # noqa: BLE001
        print(f"[health] 扫描失败：{e}")

    # v1.2.0：平台原生能力发现（即使啥都没装，stdlib 一向可用）
    try:
        from . import native as _native
        ready = _native.ready_ids()
        caps_total = len(_native.NATIVE_REGISTRY)
        print(f"[health] 原生能力：{len(ready)}/{caps_total} 就绪")
        if getattr(args, "verbose", False):
            all_caps = _native.discover()
            for c in all_caps.values():
                mark = "✔" if c.ready else "✘"
                miss = f"（缺 {c.missing_deps}）" if c.missing_deps else ""
                print(f"  {mark} {c.id}{miss}  — {c.description}")
        missing = _native.report_missing()
        if missing:
            print("[hint] 未就绪的可一行启用：")
            for line in missing:
                print(line)
    except Exception as e:  # noqa: BLE001
        print(f"[health] 原生能力探测失败：{e}")

    # D12: --verbose 显示最近政令
    if getattr(args, "verbose", False):
        print("\n[health] 最近政令（最多 10 条）：")
        recent = logutil.recent_runs(10)
        if not recent:
            print("  (暂无政令记录——跑一次 zhengling run 后再查)")
        for r in recent:
            levels = r.get("levels", {})
            print(f"  {r['started_at'][:19]}  {r['entry_count']}条  "
                  f"I:{levels.get('INFO',0)} W:{levels.get('WARN',0)} E:{levels.get('ERROR',0)}  "
                  f"最后:{r['last_event'][:40]}")

    return 0


def cmd_registry(args: argparse.Namespace) -> int:
    """列出本机登记册里所有可路由 skill。"""
    skills_dir = Path(args.skills_dir) if args.skills_dir else None
    entries = registry.scan(skills_dir)
    if not entries:
        print("(无可路由 skill —— 检查 SKILL.md frontmatter 是否有 metadata.capability 块)")
        return 0
    for e in entries:
        print(f"- {e.id}")
        print(f"    intent_tags: {e.intent_tags}")
        print(f"    input  → {e.input_types}")
        print(f"    output → {e.output_types}")
        print(f"    is_meta={e.is_meta}  priority={e.priority}")
        print(f"    from: {e.source_path}")
    return 0


def cmd_translate(args: argparse.Namespace) -> int:
    """只跑通译层（L1），打印任务书 JSON。"""
    cfg = llm.load_config(args.config)
    catalog = _builtin_intent_catalog()
    task = discipline.layer1_translate(cfg, args.prompt, catalog)
    print(json.dumps(task.__dict__, ensure_ascii=False, indent=2))
    return 0


# HARD: 打回升级阈值（参见 ../SKILL.md §2-④）——最多 3 轮，不无限重试
MAX_REJECT_ROUNDS = 3


def _execute_procedure(
    proc: discipline.Procedure,
    caps: dict,
    work_dir,
    log,
    last_deviations: list[str] | None = None,
    *,
    llm_cfg: "llm.LLMConfig | None" = None,  # noqa: F821 — 运行时仅查 llm 模块
) -> tuple[list[dict], bool]:
    """跑一遍 L3 全部工序。

    打回重跑时，上轮偏差清单会附加到每步 input 尾部——
    如果子能力是 LLM-based，它能看到"上次哪里不达标"并修正。

    v1.2.0 起 llm_cfg 透传给 executor.execute()，让 L3 fallback 能用 LLM 直接产产物。
    离线模式时 cfg=None，executor 跳过 L3 只走原生+cap 两层。

    返回 (产物列表, 是否有步骤失败)。
    """
    produced: list[dict] = []
    for step in proc.steps:
        step_dict = dict(step.__dict__)
        if last_deviations:
            step_dict["input"] = (
                f"{step_dict.get('input', '')}\n\n[上轮验收偏差，请修正："
                + "；".join(last_deviations) + "]"
            )
        res = executor.execute(
            capability_id=step.skill_id,
            step=step_dict,
            capabilities=caps,
            work_dir=work_dir,
            llm_cfg=llm_cfg,
        )
        if not res.ok:
            print(f"       步骤 {step.index} 失败：{res.error}")
            log.error("layer3_step_failed", step=step.index, skill_id=step.skill_id, error=res.error)
            return produced, True
        produced.extend(res.outputs)
        log.info("layer3_step_done", step=step.index, skill_id=step.skill_id, outputs=len(res.outputs))
    return produced, False


def cmd_run(args: argparse.Namespace) -> int:
    """跑完整四层：通译 → 流转 → 执行 → 验收（含封驳打回循环）。

    --offline（v1.1.0）：纯确定性端到端——L1 规则构造任务书 + L2 确定性路由
    + L4 机器契约验收，全程不调 LLM，因此也不需要 LLM config（无 key 可跑）。
    """
    offline = getattr(args, "offline", False)
    # HARD: offline 模式不加载 LLM 配置——它存在的意义就是"无 key 环境也能跑"
    cfg = None if offline else llm.load_config(args.config)
    skills_dir = Path(args.skills_dir) if args.skills_dir else None
    entries = registry.scan(skills_dir)

    # D12: 初始化 run.log（JSON Lines，可被 jq 解析）
    import datetime
    runs_dir = Path.home() / ".zhenglingtai" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    log_file = runs_dir / f"{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    log = logutil.get_logger("政令台", log_file=log_file)
    log.info("run_start", prompt=args.prompt[:80],
             route_mode=getattr(args, "route_mode", "auto"), offline=offline)

    print("[1/4] 通译中..." + ("（offline 规则构造）" if offline else ""))
    if offline:
        task = discipline.layer1_translate_offline(args.prompt)
    else:
        catalog = _builtin_intent_catalog()
        task = discipline.layer1_translate(cfg, args.prompt, catalog)
    print(f"       任务书：what={task.what[:40]}...")
    log.info("layer1_done", what=task.what[:80], intent_tags=task.intent_tags, offline=offline)

    print("[2/4] 路由中...")
    candidates = registry.filter_by_intent(entries, task.intent_tags)
    route_mode = getattr(args, "route_mode", "auto")
    # offline 强制确定性路由（本就不会调 LLM）
    if offline or route_mode == "deterministic":
        proc = discipline.layer2_route_deterministic(task, candidates)
    else:
        proc = discipline.layer2_route(cfg, task, candidates, mode=route_mode)
    print(f"       主 skill={proc.main_skill}, 工序数={len(proc.steps)} (mode={route_mode})")
    log.info("layer2_done", main_skill=proc.main_skill, steps=len(proc.steps), mode=route_mode)

    caps = executor.load_capabilities(args.capabilities)

    acc, deviation_history = _run_reject_loop(
        cfg, task, proc, caps, args.work_dir, log,
        offline=offline, llm_cfg=None if offline else cfg)
    if acc is None:  # L3 执行失败
        return 4

    print(json.dumps(acc.__dict__, ensure_ascii=False, indent=2))
    if acc.result == "达标":
        log.info("run_complete", log_file=str(log_file), rounds=len(deviation_history) + 1)
        return 0

    # HARD: 打满 3 轮仍未达标 → 停止重试，输出升级块升级给人（SKILL.md §2-④）
    flat_history = [d for devs in deviation_history for d in devs]
    print(f"\n【ESCALATE】已打回 {len(deviation_history)} 次未达标")
    print(f"卡点：{'; '.join(acc.deviations) or '(验收单未填偏差)' }")
    print(f"历史偏差：{'; '.join(flat_history)}")
    print("建议：缩小任务书 scope / 检查 capabilities 配置 / 人工接手")
    print("需用户决策：true")
    log.error("run_escalated", rounds=len(deviation_history), deviations=flat_history)
    return 3


def _run_reject_loop(
    cfg: llm.LLMConfig,
    task: discipline.TaskBook,
    proc: discipline.Procedure,
    caps: dict,
    work_dir,
    log,
    offline: bool = False,
    *,
    llm_cfg: "llm.LLMConfig | None" = None,  # noqa: F821 — v1.2.0 透传给 L3
) -> tuple[discipline.Acceptance | None, list[list[str]]]:
    """L3 + L4 封驳打回循环（参见 ../SKILL.md §2-④）。

    未达标 → 偏差清单反馈给 L3 重跑 → 重新验收，最多 MAX_REJECT_ROUNDS 轮。
    Why 独立成函数：cmd_run 里要做 LLM 配置/登记册/home 目录等副作用，
    循环本体抽出来才能离线单测（mock layer4_verify + executor 即可）。
    offline=True 时 L4 走机器契约（layer4_verify_deterministic），不调 LLM。

    v1.2.0：llm_cfg 默认 = cfg（向后兼容）；显式传 None 时彻底走离线链路。

    返回 (最终验收单, 各轮偏差历史)；L3 执行失败时验收单为 None。
    """
    # 默认让 L3 fallback 用同一条 cfg——历史调用无破坏
    if llm_cfg is None and not offline:
        llm_cfg = cfg
    acc: discipline.Acceptance | None = None
    deviation_history: list[list[str]] = []
    for round_no in range(1, MAX_REJECT_ROUNDS + 1):
        print(f"[3/4] 执行中...（第 {round_no}/{MAX_REJECT_ROUNDS} 轮）")
        last_devs = deviation_history[-1] if deviation_history else None
        produced, fail = _execute_procedure(proc, caps, work_dir, log, last_devs, llm_cfg=llm_cfg)
        if fail:
            return None, deviation_history

        print(f"[4/4] 验收中...（第 {round_no}/{MAX_REJECT_ROUNDS} 轮）"
              + ("（offline 机器契约）" if offline else ""))
        if offline:
            acc = discipline.layer4_verify_deterministic(task, proc, produced, work_dir)
        else:
            acc = discipline.layer4_verify(cfg, task, proc, produced)
        log.info("layer4_done", result=acc.result, deviations=len(acc.deviations),
                 round=round_no, offline=offline)

        if acc.result == "达标":
            break
        deviation_history.append(list(acc.deviations))
        if round_no < MAX_REJECT_ROUNDS:
            print(f"       封驳打回：{'; '.join(acc.deviations[:2]) or '(无偏差描述)'}"
                  f" → 带偏差清单重跑")
            log.warn("layer4_reject", round=round_no, deviations=acc.deviations)
    return acc, deviation_history


def cmd_verify(args: argparse.Namespace) -> int:
    """单独跑验收：传入已有的任务书 / 工序单 JSON + 实际产物。

    --offline（v1.1.0）：验收走机器契约（不调 LLM，无需 config）。
    """
    offline = getattr(args, "offline", False)
    cfg = None if offline else llm.load_config(args.config)
    with open(args.task, encoding="utf-8") as f:
        task_dict = json.load(f)
    with open(args.proc, encoding="utf-8") as f:
        proc_dict = json.load(f)

    task = discipline.TaskBook(
        what=task_dict.get("what", ""),
        why=task_dict.get("why", ""),
        scope_in=task_dict.get("scope_in", []),
        scope_out=task_dict.get("scope_out", []),
        accept=task_dict.get("accept", []),
        unknowns=task_dict.get("unknowns", []),
        intent_tags=task_dict.get("intent_tags", []),
    )
    from .discipline import Step, Procedure
    proc = Procedure(
        main_skill=proc_dict.get("main_skill", ""),
        cooperative=proc_dict.get("cooperative", []),
        meta_delegate=proc_dict.get("meta_delegate", ""),
        steps=[Step(**s) for s in proc_dict.get("steps", [])],
        stop_points=proc_dict.get("stop_points", []),
        fallbacks=proc_dict.get("fallbacks", {}),
    )
    # v1.1.0 修复：--produced 传的是 JSON 字符串，此前从未解析直接当 dict 用——
    # offline 机器契约调 item.get() 会炸。宽容解析：JSON 成功用 dict，失败按路径字符串包一层
    produced: list[dict] = []
    for raw in (args.produced or []):
        try:
            produced.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            produced.append({"path": str(raw), "type": Path(str(raw)).suffix.lstrip(".")})
    if offline:
        acc = discipline.layer4_verify_deterministic(task, proc, produced)
    else:
        acc = discipline.layer4_verify(cfg, task, proc, produced)
    print(json.dumps(acc.__dict__, ensure_ascii=False, indent=2))
    return 0 if acc.result == "达标" else 3


def cmd_capabilities_init(args: argparse.Namespace) -> int:
    """D7: 扫描登记册 → 生成 capabilities yaml 模板。"""
    skills_dir = Path(args.skills_dir) if args.skills_dir else None
    output = Path(args.output) if args.output else None
    msg = migrator.capabilities_init(skills_dir, output)
    print(msg)
    return 0


def cmd_migrate_scan(args: argparse.Namespace) -> int:
    """D8: 扫描缺 capability 的 skill。"""
    skills_dir = Path(args.skills_dir) if args.skills_dir else None
    results = migrator.migrate_scan(skills_dir)
    missing = [r for r in results if not r["has_capability"]]
    ok = [r for r in results if r["has_capability"]]
    print(f"总计: {len(results)} 个 skill")
    print(f"  已有 capability: {len(ok)}")
    print(f"  缺 capability:   {len(missing)}")
    for r in missing:
        print(f"    - {r['id']}  ({r['path']})")
    return 0


def cmd_migrate_suggest(args: argparse.Namespace) -> int:
    """D8: LLM 建议 intent_tags。"""
    cfg = llm.load_config(args.config)
    skills_dir = Path(args.skills_dir) if args.skills_dir else None
    catalog = _builtin_intent_catalog()
    result = migrator.migrate_suggest(cfg, args.skill_id, skills_dir, catalog)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_migrate_batch(args: argparse.Namespace) -> int:
    """D8: 批量迁移。"""
    cfg = llm.load_config(args.config)
    skills_dir = Path(args.skills_dir) if args.skills_dir else None
    catalog = _builtin_intent_catalog()
    msg = migrator.migrate_batch(cfg, skills_dir, catalog, dry_run=args.dry_run)
    print(msg)
    return 0


def _builtin_intent_catalog() -> list[str]:
    """内置一份精简意图标签 catalog（v1.0.1 起只含规范词）。

    Why this exists:
        v0.2.0 的 catalog 直接复制自 intent-tags.md 全文（精简版），
        后续会改成从 registry/intent-tags.md 运行时加载。
    Why no slide_deck:
        v1.0.1 起 slide_deck 为 make_ppt 的废弃别名（见 registry/intent-tags.md），
        通译选词表只推规范词，避免 LLM 继续产出废弃标签。
    """
    return [
        "content_produce", "article_pipeline", "video_pipeline",
        "write_copy", "write_copy_sales", "write_novel",
        "long_form_fiction", "write_book",
        "clean_excel", "normalize_table", "dedupe_rows", "data_analysis",
        "competitor_analysis", "market_insight", "web_research", "user_research",
        "training_doc", "courseware", "handbook", "instructional_design", "course_plan",
        "transcript_video", "extract_copy", "make_ppt",
        "poster_prompt", "image_gen", "video_gen", "edit_video",
        "prd", "requirement", "roadmap",
        "knowledge_frame", "kb_fetch",
        "skill_create", "skill_pack", "skill_audit",
        "summarize", "translate", "qa", "decree_mode", "orchestrate_skills",
    ]


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(
        prog="zlt",  # v1.0.3：pip 入口改名 zlt（zhengling 归 shim 专用）
        description="政令台 CLI（B 形态）—— 通用政令执行纪律层",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="cmd", required=False)

    p_h = sub.add_parser("health", help="自检")
    p_h.add_argument("--verbose", action="store_true", default=False, help="显示最近政令日志")
    p_h.set_defaults(func=cmd_health)

    p_r = sub.add_parser("registry", help="列出登记册")
    p_r.add_argument("--skills-dir", default=None, help="skill 目录（默认 ~/.workbuddy/skills）")
    p_r.set_defaults(func=cmd_registry)

    p_t = sub.add_parser("translate", help="只跑通译层（L1）")
    p_t.add_argument("prompt", help="用户原始指令")
    p_t.add_argument("--config", default=None, help="LLM config 路径")
    p_t.set_defaults(func=cmd_translate)

    p_run = sub.add_parser("run", help="跑完整四层")
    p_run.add_argument("prompt", help="用户原始指令")
    p_run.add_argument("--config", default=None, help="LLM config 路径")
    p_run.add_argument("--skills-dir", default=None, help="skill 目录")
    p_run.add_argument("--capabilities", default=None, help="子能力配置 YAML")
    p_run.add_argument("--work-dir", default=".", help="工作目录")
    p_run.add_argument(
        "--route-mode",
        choices=["auto", "deterministic", "llm"],
        default="auto",
        help="路由模式：auto(默认)=确定性选skill+LLM编排 / deterministic=纯算法 / llm=纯LLM(旧行为)",
    )
    p_run.add_argument(
        "--offline",
        action="store_true",
        default=False,
        help="纯确定性模式（v1.1.0）：L1 规则构造 + L2 确定性路由 + L4 机器契约验收，"
             "全程不调 LLM（无需 LLM config，CI/离线/无 key 环境可跑）",
    )
    p_run.set_defaults(func=cmd_run)

    p_v = sub.add_parser("verify", help="单独跑验收层（L4）")
    p_v.add_argument("--task", required=True, help="任务书 JSON 路径")
    p_v.add_argument("--proc", required=True, help="工序单 JSON 路径")
    p_v.add_argument("--produced", action="append", default=[], help="实际产物 dict(JSON)，可多次")
    p_v.add_argument("--config", default=None, help="LLM config 路径")
    p_v.add_argument("--offline", action="store_true", default=False,
                     help="验收走机器契约（v1.1.0，不调 LLM）")
    p_v.set_defaults(func=cmd_verify)

    # D7: capabilities 子命令
    p_cap = sub.add_parser("capabilities", help="子能力配置工具")
    cap_sub = p_cap.add_subparsers(dest="cap_cmd", required=True)
    p_cap_init = cap_sub.add_parser("init", help="扫描登记册 → 生成 capabilities yaml 模板")
    p_cap_init.add_argument("--skills-dir", default=None)
    p_cap_init.add_argument("--output", default=None)
    p_cap_init.set_defaults(func=cmd_capabilities_init)

    # D8: migrate 子命令
    p_mig = sub.add_parser("migrate", help="老 skill 迁移工具（补 capability 块）")
    mig_sub = p_mig.add_subparsers(dest="mig_cmd", required=True)
    p_mig_scan = mig_sub.add_parser("scan", help="扫描缺 capability 的 skill")
    p_mig_scan.add_argument("--skills-dir", default=None)
    p_mig_scan.set_defaults(func=cmd_migrate_scan)
    p_mig_suggest = mig_sub.add_parser("suggest", help="LLM 建议 intent_tags")
    p_mig_suggest.add_argument("skill_id")
    p_mig_suggest.add_argument("--config", default=None)
    p_mig_suggest.add_argument("--skills-dir", default=None)
    p_mig_suggest.set_defaults(func=cmd_migrate_suggest)
    p_mig_batch = mig_sub.add_parser("batch", help="批量迁移")
    p_mig_batch.add_argument("--config", default=None)
    p_mig_batch.add_argument("--skills-dir", default=None)
    p_mig_batch.add_argument("--dry-run", action="store_true", default=False)
    p_mig_batch.set_defaults(func=cmd_migrate_batch)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args(["health"])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
