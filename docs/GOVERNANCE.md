# 治理文档

> **最后更新：** 2026-07-22 · **适用版本：** v1.2.0

---

## 1. 版本号策略

遵循 [SemVer](https://semver.org/lang/zh-CN/)：

| 改动类型 | 版本号 | 例子 |
|---|---|---|
| 仅修瑕疵、文档勘误 | PATCH | v0.4.0 → v0.4.1 |
| 新增功能、向后兼容 | MINOR | v0.4.1 → v0.5.0 |
| 不兼容改动（删字段、改语义） | MAJOR | v0.4.x → v1.0.0 |

---

## 2. 向后兼容承诺

### Schema 字段

v1.0.0 起，TaskBook / Procedure / Acceptance 三 schema **只加字段不删字段、不改字段名**。新增字段必须有默认值，老 JSON 仍能解析。

### intent-tags 词表

- **加词**：任意版本可加，不影响老 skill
- **删词 / 改义**：MAJOR 版本才允许，且需提供迁移工具
- **deprecated 标记**：v0.4.0 起，被替换的词标 `deprecated: true`，保留 2 个 MINOR 版本后删

### pip 包名

- v0.2.1：`zhenglingtai-cli`（新名），旧名 `zhenlingtai-cli` 已废弃
- v1.0.0：旧名从文档完全移除（仅保留在 CHANGELOG 历史记录中）

---

## 3. intent-tags 词表 PR 流程

1. 编辑 `registry/intent-tags.md`，在对应类别下加新词
2. 提 PR（或自行维护），说明：
   - 新词名 + 所属类别
   - 使用场景（哪个 skill 需要这个标签）
   - 与已有词的区别（防同义不同词）
3. 合并后新词立即生效（下次会话自动发现）

**命名规范：** `动词_名词`（如 `clean_excel`），小写下划线，英文。

---

## 4. 发布前 Checklist

> v1.0.2 扩充 + v1.2.0 又加——前两轮发布事故的教训：
> 光跑测试不够，"宣称与实物一致"也要逐项打勾。

- [ ] 所有 P1/P2 改进项的验收标准全过
- [ ] `pytest tests/ -v` 全过
- [ ] **CI 全绿**（含通用版承诺扫描——注意排除 `.github` 与 `CHANGELOG.md`）
- [ ] `python cli/examples/run_demo.py` 冒烟通过（演示脚本也是用户入口）
- [ ] `zhengling doctor` 在干净环境返回 NONE 不崩溃
- [ ] **`zlt health --verbose`** 显示当前 venv 原生能力数（v1.2.0 起增加这条）
- [ ] `install.sh` 在 Git Bash + Linux + macOS 各跑一次
- [ ] `install.ps1` 在 Windows PowerShell 5.1 + 7 各跑一次
- [ ] CHANGELOG 新版本段已写
- [ ] **版本号六处一致**：SKILL.md frontmatter / `cli/zhenglingtai_cli/__init__.py` / `cli/pyproject.toml` / CHANGELOG 新段 / `cli/tests/test_smoke.py` 版本断言 / docs 六份的"适用版本"
- [ ] **文件数核对**：CHANGELOG 写的文件总数 = `find zhenglingtai -type f | wc -l` 实际值
- [ ] SHA256SUMS 已生成（LF 行尾，`sha256sum -c` 实测通过）
- [ ] **zip 中文文件名验证**：Python `zipfile` 读回 namelist，中文名正确且 flag_bits 含 0x800
- [ ] 通用版承诺扫描零命中（含 `example-*` 以外的真实 skill 名抽查）
