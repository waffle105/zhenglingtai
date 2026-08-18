# 政令台 · CHANGELOG

> 版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)：`MAJOR.MINOR.PATCH`。
> - MAJOR 不兼容改动
> - MINOR 新增功能（向后兼容）
> - PATCH 修复 / 文案收紧

## 维护规范

- 每个版本号只出现一次
- 新版本加在最上方（最新在上）
- 同一版本的 `Added` / `Changed` / `Fixed` / `Removed` 分组写
- 不在历史版本段补写新条目——新条目永远开新版本段

---

## [1.2.0] - 2026-07-22

> 第二个 MINOR。新功能来自用户反馈："政令台被安装到其他工具时，
> 不会自动获取平台原生能力进行本地化，一些常规操作和平台原生能力在 CLI 里
> 没有就被停止了。这个逻辑不对，应该先获取原生能力进行本地化，并优先使用原生能力。"

### Added

- **平台原生能力发现**（`cli/zhenglingtai_cli/native.py`）
  - 12 个原生能力：read_text / write_text / read_json / write_json / csv_read /
    csv_write / hash_sha256（stdlib）+ read_yaml / write_yaml（PyYAML）+
    pptx_create / xlsx_read / xlsx_write（按需 pip）+ image_resize（Pillow）
  - `discover()` 用 `importlib.util.find_spec` + `shutil.which` 探测依赖
  - `ready_ids()` 返回当前已就绪 ID；`report_missing()` 给"pip install 一行"
- **LLM fallback**（`cli/zhenglingtai_cli/llm_fallback.py`）
  - L3 层：当原生+cap 都不接，文本类产出由 LLM 直接落盘
  - 后缀判定：`.md/.txt/.json/.yaml/.py/.html/.sh` 等文本类才接管
  - 非文本（`.pptx/.xlsx/.png`）一律返回 None 让上层走 noop
- **executor 4 层 fallback 链路**（`cli/zhenglingtai_cli/executor.py`）
  - L1 原生 → L2 declared cap → L3 LLM 直干 → L4 noop + 升级给人
  - 各层在 products.logs 留下可追溯的标记：`[native.xxx]` / `[exec_local]` /
    `[llm.fallback]` / `[noop]`
  - `_hint_for()` 生成可执行 hint：cap_id 命中未装原生时含"pip install x"，
    否则含 yaml 路径
- **`zlt health` 报告原生能力数**：默认显示"原生能力：N/14 就绪"；
  `--verbose` 逐条打印每项 ready 状态和缺失的依赖

### Changed

- `executor.execute()` 加 `llm_cfg=None` kw-only 参数
- `_execute_procedure()` 同步加 `llm_cfg=None` kw，**默认透传 cfg**
  （向后兼容：老调用无感）
- `_run_reject_loop()` 默认让 L3 fallback 用同一条 cfg（明确需离线时传 None）

### Compatibility

- `executor.execute(cap_id, step, caps, *, work_dir=".")` 老调用全兼容
- 4 层 fallback 是"先新后旧"——现有 cap 配置照旧优先命中 L2
- 无 LLM config 的老用户行为不变（只是新增了"原生能力也能干"的副作用）

### Tests

- 127 个测试全过（107 → **+20**）；总覆盖率 74%
- 新增 `tests/test_fallback.py`：4 层链路逐层命中 + 跨层 fallback + 健康输出
- 真实冒烟（cmd_health --verbose）：10 个原生能力已就绪，3 个待装（pptx/openpyxl）

---

## [1.1.0] - 2026-07-22

> 首个 MINOR。新功能来自评审建议"补一个纯确定性模式的端到端路径，
> 让纪律层在无 LLM 时也能跑（至少做格式校验）"。
> 本轮照例抓出两个隐藏问题：`cmd_verify` 的 `--produced` JSON 字符串从未解析；
> SKILL.md §3.2 宣称的两个路由加权项在真实路径从未生效（调用方恒传空集）。

### Added

- **`--offline` 纯确定性端到端模式**（`zlt run --offline` / `zlt verify --offline`）：
  - L1：`discipline.layer1_translate_offline()`——规则构造最小任务书
    （what=原文不扩写，why/unknowns 诚实标注"未经 LLM 通译"，intent_tags 空 → 通用模式）
  - L4：`discipline.layer4_verify_deterministic()`——SKILL.md §5 机器契约：
    文件存在/非空 + 类型特定检查（pptx 页数 zip 成员计数 / xlsx sheet 数 /
    md 字数 / py_compile 语法）+ accept 中可正则提取的阈值（页数 ≥ N / 字数 ≥ N）；
    accept 语义条目全部进 `subjective` 等用户确认（不替用户拍板，与 §5 HARD 一致）；
    无产物直接未达标（不产出却宣称达标是幻觉温床）
  - **全程零 LLM 调用、无需 LLM config**——CI 冒烟、无 key 环境、
    验证 capabilities 物理产出的场景从此可跑
  - 全部用标准库实现，零新依赖
- **测试 `tests/test_offline.py`（14 个）**：L1 构造口径 / L4 机器契约 9 场景 /
  offline 端到端（load_config 被调即炸的方式证明无 LLM）/ cmd_verify --offline
- **`docs/INTERNALS.md` §3.5 路由加权系数的设计依据**：
  系数表（召回率基底 / priority tie-break 的生效依据）、预留项现状勘误、
  "改系数的合法流程"（先补基准用例 → 基准全绿 → CHANGELOG 注用例编号）

### Fixed

- **`cmd_verify --produced` 从未解析 JSON 字符串**：API.md 示例传的是
  `'{"path":"...","type":"md"}'` 字符串，代码直接当 dict 用——offline 机器契约
  调 `.get()` 会炸。改宽容解析（JSON 失败按裸路径包一层、后缀推类型）
- **路由算法"宣称与实现不符"（第三轮教训）**：SKILL.md §3.2 宣称
  "output_types 命中 +0.3、input_types 命中 +0.2"，但 TaskBook schema 无
  `expected_outputs` 字段，调用方恒传空集——加权项在真实路由**从未生效**
  （input_types 甚至从未实现）。SKILL.md / INTERNALS.md 已按实际生效公式
  （召回率 + 0.01×priority）对齐，预留能力与启用路径（TaskBook 加字段）如实标注
- **Windows 上 py_compile 写 devnull 炸**：`cfile=os.devnull` 在 Windows
  被拒绝（nul 非 regular file）——改 `tempfile.mkstemp` 用后删除

### Changed

- **版本号六处统一** → `1.1.0`（MINOR：新增 --offline，向后兼容）
- `argparse prog` 显示名 `zhengling` → `zlt`（v1.0.3 改名的收尾）
- 测试 93 → **107 个**（全部通过）；文件总数 61 → **62**（新增 test_offline.py）

---

## [1.0.3] - 2026-07-22

> 第三轮修复，来自一份覆盖 shim / 测试覆盖率 / 路由基准 / schema 漂移的评审。
> 本轮最大的教训：**集成测试一写，真 bug 就现形**——`layer4_verify` 的 Step 序列化
> 错误意味着 CLI 的 `run` 在真实 LLM 路径下从未走通到验收层；
> `zhengling` 双入口冲突意味着新用户第一条命令 `doctor` 就可能翻车。
> 两个"第一入口"同时是坏的，而 56 个单测一个都没抓到。

### Changed（含一项接口变更）

- **pip console_script `zhengling` → `zlt`（P0，接口变更）**：
  - 原因：pip 入口与 install.sh 装的 bash shim 同名，pip 的 bin 常排在 PATH 前——
    pip 入口没有 `doctor` 子命令（doctor 属 shim 层），新用户装完跑 `zhengling doctor` 必翻车
  - 现在：`zhengling` = shim 独占（含 doctor/uninstall，聚合派发）；`zlt` = pip 直连入口
  - 兼容路径：pip 包名 `zhenglingtai-cli` 不变（守住 v1.0.0 承诺）；
    装了 shim 的用户 `zhengling run` 等用法不变（shim 转发），直连用户改用 `zlt`
  - 同步更新：API.md（子命令全部改 zlt + 两入口说明）/ INSTALL.md / README.md /
    TROUBLESHOOTING.md / EXTENDING.md / INTERNALS.md / cli/README.md /
    run_demo.py 提示 / detect.py（`_probe_cli` 改查 `zlt`）/ SKILL.md §10

### Added

- **集成测试 `tests/test_integration.py`（21 个）**：
  - `cmd_run` 四层端到端（mock LLM 按层分发）：达标链路 / 打满 3 轮 ESCALATE / L3 失败短路
  - `llm.chat`：payload 结构 / 重试 / 超上限抛错；`chat_json` 三条退路（纯 JSON / ```json 围栏 / 无标注围栏）+ 解析失败 ValueError
  - executor http kind：headers env 展开 + body 模板替换 + 非 JSON 响应 + HTTPError
  - executor cli kind：真实子进程 happy path / 非零退出 / 命令不存在
  - 子命令薄集成：cmd_translate / cmd_verify / cmd_registry / cmd_health / cmd_capabilities_init
- **路由基准 `tests/benchmark_routing.json` + `test_routing_benchmark.py`（P2）**：
  15 个典型场景（单中 / 冲突最具体优先 / 协同串行 / meta 委托与meta非最高分 /
  空登记册 / 空标签 / 零交集 / 自指排除 / priority 加权 / 部分命中 / 协同去重 /
  数据任务 / 培训场景 / 同分确定性），另加规模守卫（不得少于 15 例）
- **三形态 schema 一致性检查 `scripts/check_schema_sync.py`（P3）**：
  对比 discipline.py dataclass 字段 ↔ SCHEMA.md 分节字段表 ↔ cli/templates 三模板，
  代码字段缺失即判漂移；已接入 CI（"跑测试"之前）

### Fixed

- **`layer4_verify` 真实路径必炸**：`json.dumps(procedure=proc.__dict__)` 嵌 Step 对象
  抛 TypeError——**CLI 的 run 在真实 LLM 路径下从未走通到验收层**（集成测试抓出）；改 `dataclasses.asdict`
- **`_exec_cli` 静默丢 stdout**：返回 `{"stdout": ...}` 不符合子能力契约
  （`_wrap_outcome` 只认 ok/outputs/logs/error），stdout 被丢弃、logs 永远为空（cli mock 测试抓出）
- **schema 漂移（检查脚本首跑即抓）**：`cli/templates/zhengling-gongxu-dan.md`
  字段表缺 Step 子字段（index/skill_id/input/output/check），已补

### Coverage

- 测试 56 → **93 个**（全部通过）
- 总覆盖率 ~50% → **74%**：`__main__.py` 23% → 64%，`llm.py` 28% → 79%，
  discipline 96% / registry 88% / executor 87%

### 文件数勘误（又一次"宣称与实物不符"）

- v1.0.1 / v1.0.2 的 zip 里混入了 `cli/.pytest_cache/` 的 4 个缓存文件
  （打包排除清单没覆盖它），此前段的"60 / 61"均为被污染数字
- 本版 zip 干净，真实文件总数 **61**（v1.0.2 真实 57 + 本版新增 4：
  test_integration.py / test_routing_benchmark.py / benchmark_routing.json /
  check_schema_sync.py）；`release.sh` 排除清单已补 `.pytest_cache` / `.coverage` / `.git`

---

## [1.0.2] - 2026-07-22

> 第二轮深度走查（v1.0.1 发布后再验）的发现。本轮核心：**把"宣称了但没实现"的承诺补齐**——
> 最典型的是"打回 ≥ 3 次升级给人"：README / 验收单模板 / prompts / 示例五处引用
> SKILL.md §2-④，但 §2-④ 根本没写这条、CLI 也没有打回循环。本版把纪律和代码都补上。

### Added

- **封驳打回循环（3 次升级阈值的真正实现）**：
  - `SKILL.md` §2-④ 补"升级阈值"硬约束段（最多 3 轮 + 【ESCALATE】升级块格式 + 设计理由）
  - CLI `cmd_run` 新增 `_run_reject_loop()`：未达标 → 偏差清单注入下轮 step input 重跑 → 重新验收，最多 3 轮；打满输出【ESCALATE】块（卡点 / 历史偏差 / 建议）并 return 3
  - 循环本体抽为独立函数便于离线单测
- **headers 环境变量展开**：`executor._expand_env_in_headers()`——EXTENDING.md 示例 `Authorization: "Bearer $MY_API_KEY"` 此前会原样发送字面量（必 401），现做 `os.path.expandvars`
- **测试 +9（56 个）**：新增 `tests/test_reject_loop.py`——打回循环 4 场景（首过 / 重试过 / 打满 ESCALATE / L3 失败短路）+ 偏差注入 + headers 展开 + run_demo 冒烟

### Fixed

- **`run_demo.py` 运行时必炸**：`json.dumps(proc.__dict__)` 遇 Step 对象抛 `TypeError: not JSON serializable`（新用户第一个会跑的脚本）——改 `dataclasses.asdict`，并加冒烟测试防回归
- **shim 拷贝后必失效**：`install.sh` / `install.ps1` 裸拷 shim 到 USER_BIN，shim 用 `SCRIPT_DIR/..` 定位 BUNDLE_ROOT，拷后指向 `~/.local` / `%USERPROFILE%`（detect.py 必找不到）——安装时改为注入 BUNDLE_ROOT 绝对路径；.cmd 用 `Encoding Default`（GBK）写出防中文 echo 变问号
- **`detect.py` 三处**：`_probe_wb` / `_count_capable_skills` 裸字符串扫全文 → 只查 frontmatter（与 v1.0.1 修的 migrate_scan 同款误判）；探测证据文本此前被丢弃 → 进 notes 展示；删人类可读输出里的调试残留行 `CLI: {res.cli_available}`
- **示例不符合自己的 schema**：`examples/示例-竞品分析.md` 的 META.json history 用 `step`/`result`，而 `META.schema.json` 要求 `action`/`timestamp`——示例已修正并加注
- **模板夹带真实 skill 名**：`templates/政令档-META.md` 示例写 `marketing-insight` / `guizang-ppt`（CI pattern 覆盖不到的私有名残留）——改 `example-*` 占位并加通用版承诺说明
- **兼容性承诺措辞方向错误**：SCHEMA.md / GOVERNANCE.md 写"v1.0.0 **前**只加不删"→ 改为"v1.0.0 **起**"
- **文档过时批量更新**：INSTALL.md（软链→拷贝模式 / 卸载说明 / 升级段 v0.3+→现行 / config 路径）、TROUBLESHOOTING.md（软链解法→拷贝）、registry/README.md（删从未实现的 `deps` 字段、悬空引用改指包内）、examples（"开发文档 §3.7"→SKILL.md §3.7）、prompts/zhengling-kuai-cha.md（安装后相对引用悬空→给两处实际路径）、API.md（注明 doctor 属 shim 层，`python -m zhenglingtai_cli doctor` 不存在）、META.schema.json（history 描述兼容打回多轮）
- **`GOVERNANCE.md` 发布 Checklist 扩充**：补 v1.0.0/v1.0.1 两轮教训——CI 全绿、run_demo 冒烟、版本号六处一致、文件数核对、zip UTF-8 验证、SHA256SUMS LF 实测
- **`zhengling.cmd`**：ARGS 显式初始化（不再依赖未定义变量隐式展开为空）

### Changed

- **版本号六处统一** → `1.0.2`：SKILL.md frontmatter / `__init__.py` / `pyproject.toml` / CHANGELOG / `test_smoke.py` 断言 / docs 六份"适用版本"；install 脚本与 detect.py、bin shim 注释同步
- 文件总数 60 → **61**（新增 `cli/tests/test_reject_loop.py`）

---

## [1.0.1] - 2026-07-22

> 本次 PATCH 全部来自一次外部评审（47 测试复跑 + 全文件走查）发现的问题。
> 教训：v1.0.0 发布没过自己的"验收司"——从本版起，发布前把"CI 全绿 / 文件数核对 /
> SHA256SUMS 随包 / 版本号五处一致"写进发布 checklist 并逐项打勾。

### Fixed

- **CI 通用版承诺扫描自伤**：
  - `SKILL.md` §3.5 与 `templates/执行工序单.md` 里的"营销全链路"字样改为泛化描述（不再命中扫描 pattern）
  - 扫描命令加 `--exclude-dir=.github -E`（pattern 字面量写在 workflow 自身，不排必自命中）
- **`__main__.py` 重复行**：`cmd_run` 末尾 `return 0 if acc.result == "达标" else 3` 误写两遍，删一行
- **`cli/` 缺 README.md**：`pyproject.toml` 声明了 `readme = "README.md"` 但文件不存在，`pip install` 会告警/失败；已补 `cli/README.md`
- **`install.ps1` 两处**：
  - pip install 被外层 `if ($LASTEXITCODE -eq 0)` 误包裹（检查的是无关前序命令的退出码），CLI 可能永远装不上；已拆
  - uninstall 删目录缺 `-Recurse`（拷补安装后目录非空删不掉）；已加
- **安装方式改拷贝优先**：`install.sh` / `install.ps1` 的元 Skill 安装从目录软链/junction 改为 `cp -r` / `Copy-Item -Recurse`——Windows 软链需管理员权限且源目录一删 skill 即挂；拷贝后独立存在，升级重跑脚本会自动备份旧版为 `.bak`
- **`migrate scan` 误判**：`"capability:" in text` 裸字符串扫全文 → 只查 YAML frontmatter 块（正文提到该词不再误判为已声明）
- **悬空引用**：`SKILL.md` / `README.md` 引用的 `../政令执行工具-通用版开发文档.md` 未随包发布，改为指向包内 `docs/` 六份文档并加注说明
- **zip 中文文件名乱码**：v1.0.0 的 zip 未置 UTF-8 标志位，标准 unzip 解压中文名乱码；本版起 `scripts/release.sh` 打 zip 强制 UTF-8（ZipInfo flag_bits | 0x800），并排除 `__pycache__` / `.bak` 等运行产物
- **SHA256SUMS 行尾**：Windows 上 Python `print` 默认输出 CRLF，`sha256sum -c` 会把 `\r` 当文件名导致校验失败；`release.sh` 的 Python fallback 分支强制 LF 行尾
- **`test_smoke.py` 版本断言**：硬编码 `1.0.0` 导致升版必挂——这正是"发布 checklist 要含版本号五处一致"的活例；已更新为 `1.0.1`

### Changed

- **词表自违例修正**：`slide_deck` 标记为 `make_ppt` 的 ⚠️ 废弃别名（按"删词需 MAJOR"承诺保留词条、仅作兼容），`registry/intent-tags.md` 新增"废弃别名归一化"规则；CLI 两处内置 catalog（`__main__.py` / `migrator.py`）同步移除 `slide_deck`，通译选词只推规范词
- **版本号五处统一** → `1.0.1`：SKILL.md frontmatter / `__init__.py`（含 docstring 残留 v0.2.1 修正）/ `pyproject.toml` / CHANGELOG / install 脚本注释
- **README 清理**：删除"验证完整性"小节后残留的重复 uninstall 行；`certutil` 示例版本号更新；`.templates/` 误写改 `templates/`
- **文件数勘误**：v1.0.0 段写"47 → 55"，实际发布包为 59 个文件（统计口径漏算）；本版含新增 `cli/README.md` 共 **60** 个文件，已按实际核对

---

## [1.0.0] - 2026-07-22

### Added

- **D12 可观测性**：
  - 新增 `logutil.py`：轻量 JSON Lines 日志（不引外部依赖）
  - 每次跑 `zhengling run` 自动生成 `~/.zhenglingtai/runs/YYYYMMDD-HHMMSS.log`
  - `zhengling health --verbose` 显示最近 10 条政令摘要
  - 日志可被 `jq` 解析
- **P3-5 文档 6 份**：
  - `docs/API.md`：CLI 子命令完整参考
  - `docs/SCHEMA.md`：四 schema 字段详解
  - `docs/EXTENDING.md`：如何写 capability 块、加 intent_tags、写子能力
  - `docs/GOVERNANCE.md`：版本号策略、兼容性承诺、词表 PR 流程
  - `docs/TROUBLESHOOTING.md`：常见错误 + 排查思路
  - `docs/INTERNALS.md`：四层时序图、自发现机制、路由模式对比
- **CI 配置**：`.github/workflows/test.yml`
  - Python 3.10/3.11/3.12 × ubuntu/macos/windows 矩阵
  - AST 检查 + YAML frontmatter 检查 + 通用版承诺扫描 + pytest + 覆盖率

### Changed

- 版本号统一更新到 `1.0.0`
- 文件总数 47 → **55**（新增 logutil.py + 6 份文档 + CI 配置 + default_capabilities.yaml）

### Stability Commitment

v1.0.0 起进入稳定版：
- TaskBook / Procedure / Acceptance 三 schema **只加字段不删字段**
- intent-tags 词表加词随时可做，删词需 MAJOR 版本
- pip 包名 `zhenglingtai-cli` 不再变更

---

## [0.4.0] - 2026-07-22

### Added

- **D7 执行层默认配置**：
  - `executor.py` 未配置 skill 时从 error → noop+hint（不再阻断流程）
  - 新增 `default_capabilities.yaml` 模板
  - 新增 `zhengling capabilities init` 子命令：扫描登记册 → 生成 yaml 模板
- **D8 老 skill 迁移脚本**：
  - 新增 `migrator.py`（280 行）
  - `zhengling migrate scan`：扫描缺 capability 的 skill
  - `zhengling migrate suggest <skill_id>`：LLM 读 SKILL.md → 建议 intent_tags
  - `zhengling migrate batch --dry-run`：批量生成 migration_plan.md
  - `zhengling migrate batch`（不加 --dry-run）：逐个写入 + 自动备份 .bak
- **D10 SHA256 校验**：
  - 新增 `scripts/release.sh`：打包后自动生成 SHA256SUMS
  - README 加"验证完整性"小节
- **D11 测试覆盖**：测试从 18 → **45 个用例**（5 个测试文件）
  - `test_discipline.py`：TaskBook/Procedure/Acceptance 构造 + JSON 往返 + HARD 约束（12 个）
  - `test_executor.py`：4 种 kind + D7 noop+hint + D9 安全 + _wrap_outcome（9 个）
  - `test_migrator.py`：capabilities_init + migrate_scan + migrate_apply 备份（6 个）

### Changed

- D7 改进：executor 未配置 skill 不再返回 error，走 noop+hint
- 版本号统一更新到 `0.4.0`
- 文件总数 41 → **47**

---

## [0.3.0] - 2026-07-22

### Added

- **D2 路由算法闭环**：`registry.score()` 不再是死代码
  - 新增 `layer2_route_deterministic()` 纯函数路由（不调 LLM）
  - `layer2_route()` 拆成确定性选 skill + LLM 编排两阶段
  - `__main__.py` 加 `--route-mode` 参数：`auto`(默认) / `deterministic` / `llm`
  - 新增 `tests/test_route.py`（8 个测试用例）
- **D3 META.json schema 落地**：
  - `templates/META.schema.json`（JSON Schema draft 2020-12）
  - `templates/政令档-META.md` 字段表（沿用四列规范）

### Fixed

- **D9 安全加固**：`executor.py` 的 `str.format` → `string.Template`
  - `_exec_http` body_template 改用 `$input` / `$output` 占位符
  - `_exec_cli` args 同上
  - 新增 `test_format_string_attack` 防注入测试

### Changed

- 版本号统一更新到 `0.3.0`（SKILL.md / `__init__.py` / `pyproject.toml`）
- 文件总数 38 → 41（新增 META.schema.json + 政令档-META.md + test_route.py）

---

## [0.2.1] - 2026-07-22

### Fixed

- **D1 包名拼写修正**：pip 包名 `zhenlingtai-cli` → `zhenglingtai-cli`（原 v0.2.0 误写少了一个 e，已全包替换；旧名仅保留在本 CHANGELOG 历史记录中）
- **D4 CHANGELOG 去重**：v0.1.0 段落此前重复出现两次，已删掉重复的第二段
- **D5 删冗余依赖**：`pyproject.toml` 移除 `rich>=13.0`（代码零 import，属冗余声明）
- **D6 自指套娃修复**（提前从 v0.3.0）：政令台自身 `is_meta: true` + `intent_tags` 含 `decree_mode` 会导致路由发现并委托自己 → 无限递归。修复方式：
  - `SKILL.md` §3.5 加硬约束：`id == "zhenglingtai"` 永不参与 meta 委托
  - `registry.py` `filter_by_intent` 加 `META_SELF_IDS = {"zhenglingtai"}` 排除
  - 新增测试 `test_self_id_excluded`

### Changed

- `__init__.py` 版本号 → `0.2.1`
- `pyproject.toml` 版本号 → `0.2.1`
- `SKILL.md` frontmatter version → `0.2.1`
- `doctor/detect.py` CLI 显示名 → `zhenglingtai-cli`

---

## [0.2.0] - 2026-07-22

### **重大重构：变成一个标准 SKILL 包**

**动机：** 之前是把 A/B/C 三形态散在 4 个顶层目录（`zhenglingtai/`、`zhenglingtai-cli/`、`zhenglingtai-prompt/`、`zhenglingtai-bundle/`）——不是标准 skills 结构。本版本合并成单一 `zhenglingtai/` 目录。

**变更：**
- ❌ **删除** 顶层目录 `zhenglingtai-cli/` `zhenglingtai-prompt/` `zhenglingtai-bundle/`
- ✅ **保留** `zhenglingtai/` 为唯一顶层目录
- ✅ `cli/` 作为可选附件 → `zhenglingtai/cli/`
- ✅ `prompts/` 作为可选附件 → `zhenglingtai/prompts/`
- ✅ `doctor/` `bin/` 整合进 `zhenglingtai/`
- ✅ 安装脚本 `install.sh` `install.ps1` 放进 `zhenglingtai/`

### Added

- **CLI 附件** `cli/`：完整 Python 包 ~~`zhenlingtai-cli`~~（v0.2.1 已修正为 `zhenglingtai-cli`）
  - 含 `zhenglingtai_cli` Python 包（llm / registry / discipline / executor / `__main__`）
  - 含 `templates/` 三个 JSON schema 模板
  - 含 `tests/test_smoke.py` 冒烟测试
  - 含 `examples/run_demo.py` 无 LLM 演示
  - 含 `config.example.yaml` + `pyproject.toml`
  - **纪律层与 A 形态 100% 相同**（共用 schema）

- **提示词附件** `prompts/`：从原 `zhenglingtai-prompt/` 平移
  - `zhengling-jiaocheng.md` + `zhengling-kuai-cha.md`
  - 4 个角色 profiles（tongyi/liuzhuan/zhixing/yanshou）
  - 3 个跨厂商 fans（Claude / DeepSeek / ChatGPT Custom GPT）

- **聚合入口** `bin/zhengling`（bash + cmd 跨平台 smart shim）
  - `zhengling doctor` 自检（不调 LLM）
  - `zhengling run "..."` 跑完整四层（自动派发）
  - `zhengling uninstall` 反向安装
  - 通过 `doctor/detect.py` 自动选 WB / CLI / 提示词

- **`doctor/detect.py`** 环境探测器
  - 4 个探测项：WB 内 SKILL.md / CLI 命令 / 提示词副本
  - 输出 `--json` 给 shim 用 / 人类可读给用户看

- **`install.sh` / `install.ps1`** 一键装
  - 软链 / pip install / cp 三件事 best-effort
  - `--uninstall` 反向卸
  - 自检在最后（doctor）

### Known Issues (resolved in later versions)

- ~~pip 包名 `zhenlingtai-cli` 少了 e~~ → v0.2.1 已修
- ~~CHANGELOG v0.1.0 重复~~ → v0.2.1 已修
- ~~`rich>=13.0` 冗余依赖~~ → v0.2.1 已删
- ~~`is_meta: true` 自指套娃~~ → v0.2.1 已修
- 路由算法 `score()` 未接入 CLI 主链路 → v0.3.0 修
- META.json schema 未定义 → v0.3.0 修
- `_exec_http` str.format 安全隐患 → v0.3.0 修

---

## [0.1.0] - 2026-07-22

### Added

- 首次发布通用版元 Skill 骨架
- 四层纪律（通译→流转→执行→验收）实现路径固化在 `SKILL.md`
- 三套模板：`templates/政令任务书.md` / `templates/执行工序单.md` / `templates/验收确认单.md`，字段表均按"键名 / 类型 / 必填 / 含义"四列规范
- 受控意图标签词表 `registry/intent-tags.md`，含 9 大类、35+ 词
- 登记册自发现机制说明 `registry/README.md`
- 跑通示例 `examples/示例-竞品分析.md`，演示重任务全四层 + 多 skill 协同 + 多产出
- 包级 `README.md`（安装/使用/扩展/卸载）
- 路由算法步骤化（含 step 0 除零边界）
- 冲突 vs 协同判定显式写出（原通用版文档 §3.3 已加，独立提炼到 `SKILL.md` §3.3）

### Design Decisions

- 形态 = A（WorkBuddy 元 Skill）
- 命名 = 政令台（DecreeHub）
- 登记册 = 路 A（skill 自描述 + 运行时聚合）
- 不预填任何 skill 名（通用版承诺底线）

### Known Issues (resolved in later versions)

- ~~路由匹配算法停留在"说明文档"~~ → v0.2.0 CLI 已含 `score()`，v0.3.0 接入主链路
- ~~自学习（用档案反哺路由）尚未实现~~ → Phase 5 留口
- ~~多产出契约未枚举完~~ → 后续版本补
