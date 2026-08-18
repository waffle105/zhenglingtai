"""平台原生能力发现 / 调度（v1.2.0）。

Why this exists:
    旧 executor 只查用户声明的 cap 配置——cap 缺失时只能 noop 然后升升级给人。
    实际很多常见操作本机就能跑：Python stdlib（json/yaml/csv/hashlib）一直有，
    python-pptx / openpyxl / Pillow 装了就现成。

    这个模块的职责：
      1. 声明每个原生能力 + 它的依赖（库 or 命令）
      2. 运行时扫"哪些已装"
      3. 给一个 cap_id，决策"原生能不能干、能就调 native、不能就回 None 让上层 fallback"

注释规范沿用 ../SKILL.md：
  - 每个函数三行 docstring
  - Why 描述设计动机
  - HARD 标记不可绕过的约束
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .executor import SubcapabilityResult


# ============ 1. 能力声明表 ============

@dataclass
class NativeCapability:
    """一个原生能力。

    字段表：
      id            str                调用方使用的名字
      kind          str                'py' / 'cli'
      fn            Callable           执行函数（py 时）/ 命令模板（cli 时）
      deps          list[str]          运行时依赖（py=模块名 / cli=命令名）
      description   str                一句话功能描述
      ready         bool               运行时 discover() 填充
      missing_deps  list[str]          运行时 discover() 填充
    """

    id: str
    kind: str
    fn: Callable
    deps: list[str] = field(default_factory=list)
    description: str = ""
    ready: bool = False
    missing_deps: list[str] = field(default_factory=list)


# ----------- py 函数们（实现尽量小而准，避免重型 import 报错） -----------

def _read_text(step: dict, work_dir) -> SubcapabilityResult:
    """读文本文件（任意 utf-8 文本格式）。"""
    p = Path(work_dir) / step.get("input", "")
    if not p.exists():
        return SubcapabilityResult(ok=False, outputs=[], logs="", error=f"文件不存在：{p}")
    text = p.read_text(encoding="utf-8", errors="ignore")
    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "text", "path": str(p), "bytes": len(text.encode("utf-8"))}],
        logs=f"[native.read_text] {len(text)} chars from {p.name}",
    )


def _write_text(step: dict, work_dir) -> SubcapabilityResult:
    """写文本到指定 output 路径；input 当作正文。"""
    p = Path(work_dir) / step.get("output", "out.txt")
    p.parent.mkdir(parents=True, exist_ok=True)
    content = step.get("input", "")
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, indent=2)
    p.write_text(content, encoding="utf-8")
    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "text", "path": str(p), "bytes": len(content.encode("utf-8"))}],
        logs=f"[native.write_text] wrote {p.name}",
    )


def _read_json(step: dict, work_dir) -> SubcapabilityResult:
    """读 JSON 文件。"""
    p = Path(work_dir) / step.get("input", "")
    if not p.exists():
        return SubcapabilityResult(ok=False, outputs=[], logs="", error=f"文件不存在：{p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return SubcapabilityResult(ok=False, outputs=[], logs="", error=f"JSON 解析失败：{e}")
    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "json", "path": str(p), "summary": f"{len(data) if isinstance(data, (list, dict)) else 1} 项"}],
        logs=f"[native.read_json] parsed {p.name}",
    )


def _write_json(step: dict, work_dir) -> SubcapabilityResult:
    """写 JSON 文件。input 可以是 dict 或已序列化字符串。"""
    p = Path(work_dir) / step.get("output", "out.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    content = step.get("input", {})
    if isinstance(content, str):
        # 已经是字符串，尽力解析再 dump（保证合法 JSON）
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return SubcapabilityResult(ok=False, outputs=[], logs="",
                error=f"input 是字符串但不是合法 JSON：{content[:80]}")
    payload = json.dumps(content, ensure_ascii=False, indent=2)
    p.write_text(payload, encoding="utf-8")
    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "json", "path": str(p), "bytes": len(payload.encode("utf-8"))}],
        logs=f"[native.write_json] wrote {p.name}",
    )


def _csv_read(step: dict, work_dir) -> SubcapabilityResult:
    """读 CSV 为 list[dict]。"""
    p = Path(work_dir) / step.get("input", "")
    if not p.exists():
        return SubcapabilityResult(ok=False, outputs=[], logs="", error=f"文件不存在：{p}")
    with open(p, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "csv", "path": str(p), "rows": len(rows), "summary": f"{len(rows)} 行"}],
        logs=f"[native.csv_read] {len(rows)} rows from {p.name}",
    )


def _csv_write(step: dict, work_dir) -> SubcapabilityResult:
    """写 CSV。input 是 list[dict] 序列化的 JSON 字符串 or list[dict]。"""
    p = Path(work_dir) / step.get("output", "out.csv")
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = step.get("input", [])
    if isinstance(rows, str):
        rows = json.loads(rows)
    if not rows:
        return SubcapabilityResult(ok=False, outputs=[], logs="", error="input 必须是非空 list[dict]")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "csv", "path": str(p), "rows": len(rows), "summary": f"{len(rows)} 行"}],
        logs=f"[native.csv_write] wrote {p.name}",
    )


def _hash_sha256(step: dict, work_dir) -> SubcapabilityResult:
    """算文件 SHA256。"""
    p = Path(work_dir) / step.get("input", "")
    if not p.exists():
        return SubcapabilityResult(ok=False, outputs=[], logs="", error=f"文件不存在：{p}")
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    digest = h.hexdigest()
    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "hash", "path": str(p), "summary": digest}],
        logs=f"[native.hash_sha256] {digest[:12]}…",
    )


def _yaml_read(step: dict, work_dir) -> SubcapabilityResult:
    """读 YAML（依赖：pyyaml）。"""
    import yaml
    p = Path(work_dir) / step.get("input", "")
    if not p.exists():
        return SubcapabilityResult(ok=False, outputs=[], logs="", error=f"文件不存在：{p}")
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "yaml", "path": str(p), "summary": "parsed"}],
        logs=f"[native.read_yaml] parsed {p.name}",
    )


def _yaml_write(step: dict, work_dir) -> SubcapabilityResult:
    """写 YAML（依赖：pyyaml）。"""
    import yaml
    p = Path(work_dir) / step.get("output", "out.yaml")
    p.parent.mkdir(parents=True, exist_ok=True)
    content = step.get("input", {})
    if isinstance(content, str):
        try:
            content = yaml.safe_load(content)
        except Exception:
            return SubcapabilityResult(ok=False, outputs=[], logs="",
                error="input 是字符串但不是合法 YAML")
    payload = yaml.safe_dump(content, allow_unicode=True, sort_keys=False)
    p.write_text(payload, encoding="utf-8")
    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "yaml", "path": str(p), "bytes": len(payload.encode("utf-8"))}],
        logs=f"[native.write_yaml] wrote {p.name}",
    )


def _pptx_create(step: dict, work_dir) -> SubcapabilityResult:
    """出 PPT（依赖：python-pptx）。

    input 是 list[{"title":..., "bullets":[...]}]
    """
    from pptx import Presentation
    p = Path(work_dir) / step.get("output", "out.pptx")
    p.parent.mkdir(parents=True, exist_ok=True)
    slides_data = step.get("input", [])
    if isinstance(slides_data, str):
        slides_data = json.loads(slides_data)
    if not isinstance(slides_data, list):
        return SubcapabilityResult(ok=False, outputs=[], logs="",
            error="pptx_create 需要 list[dict] 作为 input")
    prs = Presentation()
    blank = prs.slide_layouts[6]
    for s in slides_data:
        slide = prs.slides.add_slide(blank)
        title = s.get("title", "")
        bullets = s.get("bullets", [])
        tx = slide.shapes.add_textbox(0.5, 0.4, 9, 0.8)
        tx.text_frame.text = title
        tx.text_frame.paragraphs[0].runs[0].font.size = None  # default
        tx.text_frame.paragraphs[0].runs[0].font.bold = True
        bx = slide.shapes.add_textbox(0.5, 1.5, 9, 7)
        bf = bx.text_frame
        for i, b in enumerate(bullets):
            p_obj = bf.add_paragraph() if i else bf.paragraphs[0]
            p_obj.text = str(b)
    prs.save(str(p))
    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "pptx", "path": str(p), "slides": len(slides_data)}],
        logs=f"[native.pptx_create] {len(slides_data)} slides → {p.name}",
    )


def _xlsx_read(step: dict, work_dir) -> SubcapabilityResult:
    """读 xlsx 第一 sheet 为 list[dict]（依赖：openpyxl）。"""
    from openpyxl import load_workbook
    p = Path(work_dir) / step.get("input", "")
    if not p.exists():
        return SubcapabilityResult(ok=False, outputs=[], logs="", error=f"文件不存在：{p}")
    wb = load_workbook(filename=str(p), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(c) if c is not None else f"col_{i}" for i, c in enumerate(rows[0])]
    body = [dict(zip(headers, r)) for r in rows[1:] if any(c is not None for c in r)]
    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "xlsx", "path": str(p), "rows": len(body)}],
        logs=f"[native.xlsx_read] {len(body)} rows from {p.name}",
    )


def _xlsx_write(step: dict, work_dir) -> SubcapabilityResult:
    """写 xlsx（依赖：openpyxl）。input 是 list[dict]，第一行为表头。"""
    from openpyxl import Workbook
    p = Path(work_dir) / step.get("output", "out.xlsx")
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = step.get("input", [])
    if isinstance(rows, str):
        rows = json.loads(rows)
    if not rows or not isinstance(rows, list):
        return SubcapabilityResult(ok=False, outputs=[], logs="", error="需要 list[dict]")
    wb = Workbook()
    ws = wb.active
    headers = list(rows[0].keys())
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h, "") for h in headers])
    wb.save(str(p))
    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "xlsx", "path": str(p), "rows": len(rows)}],
        logs=f"[native.xlsx_write] {len(rows)} rows → {p.name}",
    )


def _image_resize(step: dict, work_dir) -> SubcapabilityResult:
    """缩放图片（依赖：Pillow）。input 是 src 路径，args.size 是 (w,h) 或 output 带 _WxH。"""
    from PIL import Image
    src = Path(work_dir) / step.get("input", "")
    if not src.exists():
        return SubcapabilityResult(ok=False, outputs=[], logs="", error=f"文件不存在：{src}")
    out_rel = step.get("output", "")
    if "_" in out_rel and "x" in out_rel.split("_")[-1]:
        # 约定：output = "thumb_300x300.jpg"
        size_str = out_rel.split("_")[-1].split(".")[0]
        try:
            w, h = [int(x) for x in size_str.split("x")]
        except ValueError:
            w, h = 300, 300
    else:
        size = step.get("size", [300, 300])
        if isinstance(size, str):
            size = json.loads(size)
        w, h = int(size[0]), int(size[1])
    out = Path(work_dir) / (out_rel or f"{src.stem}_{w}x{h}{src.suffix}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im.thumbnail((w, h))
        im.save(out)
    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "image", "path": str(out), "width": w, "height": h}],
        logs=f"[native.image_resize] {src.name} → {out.name} ({w}x{h})",
    )


# ============ 2. 注册表 ============

NATIVE_REGISTRY: dict[str, NativeCapability] = {
    cap.id: cap for cap in [
        NativeCapability(id="read_text",    kind="py", fn=_read_text,    deps=[],
                        description="读文本文件（任意 utf-8 格式）"),
        NativeCapability(id="write_text",   kind="py", fn=_write_text,   deps=[],
                        description="写文本到 output 路径"),
        NativeCapability(id="read_json",    kind="py", fn=_read_json,    deps=[],
                        description="读 JSON 解析为对象"),
        NativeCapability(id="write_json",   kind="py", fn=_write_json,   deps=[],
                        description="写 JSON 到 output 路径"),
        NativeCapability(id="csv_read",     kind="py", fn=_csv_read,     deps=[],
                        description="读 CSV 为 list[dict]"),
        NativeCapability(id="csv_write",    kind="py", fn=_csv_write,    deps=[],
                        description="写 list[dict] 到 CSV"),
        NativeCapability(id="hash_sha256",  kind="py", fn=_hash_sha256,  deps=[],
                        description="算文件 SHA256"),
        NativeCapability(id="read_yaml",    kind="py", fn=_yaml_read,    deps=["yaml"],
                        description="读 YAML（PyYAML）"),
        NativeCapability(id="write_yaml",   kind="py", fn=_yaml_write,   deps=["yaml"],
                        description="写 YAML（PyYAML）"),
        NativeCapability(id="pptx_create",  kind="py", fn=_pptx_create,  deps=["pptx"],
                        description="出 PPT（python-pptx）"),
        NativeCapability(id="xlsx_read",    kind="py", fn=_xlsx_read,    deps=["openpyxl"],
                        description="读 xlsx（openpyxl）"),
        NativeCapability(id="xlsx_write",   kind="py", fn=_xlsx_write,   deps=["openpyxl"],
                        description="写 xlsx（openpyxl）"),
        NativeCapability(id="image_resize", kind="py", fn=_image_resize, deps=["PIL"],
                        description="缩放图片（Pillow）"),
    ]
}


# ============ 3. 依赖探测 ============

def _has_py_module(name: str) -> bool:
    """检测 Python 模块是否可 import。

    Why find_spec 而非 import：
        find_spec 不触发副作用 import（如 numpy 早期会打印版本信息），
        同时能区分 "装了但 import 时报错"和"没装"。
    """
    if name in sys_builtin_modules():  # noqa: F821 — checked below
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ValueError, ImportError):
        return False


def sys_builtin_modules():
    """sys.stdlib_module_names 的延迟拉取——不在顶层 import sys 以加快 native 模块加载。"""
    import sys as _s
    return set(_s.stdlib_module_names)


def _has_cli(cmd: str) -> bool:
    """检测系统命令是否存在（用 shutil.which）。"""
    return shutil.which(cmd) is not None


def discover() -> dict[str, NativeCapability]:
    """扫一遍所有原生能力，标记 ready。

    返回 dict 的副本（不污染 NATIVE_REGISTRY）。每次调用都重扫，
    因此用户中途装库后再调一次即可识别——无需重启进程。
    """
    out: dict[str, NativeCapability] = {}
    for cap in NATIVE_REGISTRY.values():
        c = NativeCapability(
            id=cap.id, kind=cap.kind, fn=cap.fn,
            deps=list(cap.deps), description=cap.description,
        )
        missing: list[str] = []
        for d in c.deps:
            if c.kind == "py":
                if d in sys_builtin_modules():
                    continue
                if not _has_py_module(d):
                    missing.append(d)
            else:
                if not _has_cli(d):
                    missing.append(d)
        c.missing_deps = missing
        c.ready = len(missing) == 0
        out[c.id] = c
    return out


def ready_ids() -> list[str]:
    """返回当前已就绪的能力 id 列表（按 declared 顺序）。

    用于 health 子命令输出 / docs 提示 / 测试断言。
    """
    return [c.id for c in discover().values() if c.ready]


def report_missing() -> list[str]:
    """给用户报告"开一行 pip 启用 X"。

    格式：每条 '  • <cap_id>: pip install <pkg>'（py 类的 cap）
    cli 类不报告（避免提示用户装 brew/apt）。
    """
    lines: list[str] = []
    for c in discover().values():
        if not c.ready and c.kind == "py" and c.missing_deps:
            lines.append(f"  • {c.id}: pip install {c.missing_deps[0]}")
    return lines


# ============ 4. 调度入口 ============

def invoke_if_ready(capability_id: str, step: dict, work_dir) -> SubcapabilityResult | None:
    """如果 cap_id 在原生表且就绪，调用并返回结果；否则返回 None 让上层 fallback。

    Why 返回 None 而非 raise：
        executor 的 4 层 fallback 链路需要"轻提示符"表示"这层不管，请下一层接手"。
        None 即可表达这语义，比让上层 try/except 干净。

    Why 每次调用都 discover：
        1) 用户可能在中途 pip install 新库——无需重启；
        2) discover() 内部开销小（12 项 stdlib 自带 stdlib_module_names 缓存）。
    """
    caps = discover()
    cap = caps.get(capability_id)
    if cap is None or not cap.ready:
        return None
    try:
        return cap.fn(step, Path(work_dir))
    except Exception as e:  # noqa: BLE001
        # 原生调用也允许失败——比如文件路径错、IO 错。
        # 但失败语义不应该被 swallow：告诉上层"原生失败，回退到 B/C 层"而非"已成功"。
        return SubcapabilityResult(
            ok=False, outputs=[],
            logs=f"[native.{capability_id}] 失败：{e}",
            error=f"原生能力执行失败：{e}",
        )
