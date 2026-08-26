# EchoMind Judge v5 正式 35-case / 43-turn 最终运行实施计划（修订版）

日期：2026-08-26（修订）
状态：计划待人工审查。本文件只描述执行方案，本身不调用任何 API、不执行任何评测。
适用分支：`task6-dialog-eval`

**Goal：** 使用已冻结的 Judge v5（`dialog_judge_v5` / `dialog_pass_v5`）对 `dialog_eval_v2.json` 执行一次全新、可审计的 35-case / 43-turn 端到端正式运行：同进程驱动先完成一次不计入指标的预热并强制通过预热门，再运行全部 35 case。驱动与离线测试先通过 TDD、本地提交并冻结 SHA-256，正式运行使用提交后的新 HEAD。完成后只做自动验证、生成审核包与初步审核意见，结束状态为 `awaiting_independent_human_review`。

**依据（全部只读）：**

- 设计规格：`docs/superpowers/specs/2026-08-26-echomind-judge-v5-deterministic-policy-design.md`
- 校准最终裁决：`docs/superpowers/diagnostics/2026-08-26-echomind-judge-v5-calibration-final-adjudication.md`
- 路由 gold 审计：`docs/superpowers/diagnostics/2026-08-26-echomind-routing-gold-audit.md`
- 生产代码：`evaluation/dialog_judge.py`、`evaluation/dialog_policy.py`、`evaluation/dialog_metrics.py`、`evaluation/run_dialog_eval.py`
- 完整套件全绿历史证据：`docs/superpowers/plans/2026-08-26-echomind-judge-v5-deterministic-policy-implementation.md`（Task 8 Step 2 记录 `pytest -q` 全绿）

---

## 0. 已批准评测口径（冻结，不得改变）

| 项 | 冻结值 |
|---|---|
| 数据 | `E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json`；35 cases / 43 turns |
| 数据 SHA-256 | `cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2` |
| Judge | `dialog_judge_v5`；`forced_tool_then_strict_json_fallback`；temperature 0.0；thinking disabled；最多 3 次尝试 |
| Pass rule | `dialog_pass_v5`：`turn_pass` = agent_failed==false 且 judge_failed==false 且 judge_skipped==false 且 relevance/accuracy/completeness/helpfulness/overall 均 >= 0.75；`case_pass = all(turn_pass)`；`pass_rate = passed_cases / total_cases`（分母 35，失败 case 计入分母） |
| 模型 | agent_model = judge_model = `deepseek-v4-pro`（精确值，禁用带后缀别名） |
| known variance | `024/T1`、`028/T2`；不手工改分，人工复核，报告允许注明 LLM Judge 存在有限细粒度 semantic variance |
| routing gold | KEEP 6 / AMBIGUOUS 2（015、023）/ CHANGE 0；不创建 `dialog_eval_v3.json`；不通过修改 gold 追求更高准确率 |
| 发布门 | Agent failure = 0、Judge failure = 0（结构门）；**不要求 pass_rate = 100%** |
| 运行后 | 禁止自动执行 baseline / regression / test 500 / 简历 / 主计划最终数字 / `.env` 历史处理 / `git push` |

## 0.1 正式运行目录（全新，执行时必须再次断言不存在）

```text
预热：E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-warmup-v5-20260826
正式：E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826
```

禁止：覆盖、删除、清空、append、`--resume`、复用 r1/r2/r3 calibration 目录、复用 `dialog-eval-v4` 目录。

## 0.2 工作树状态规则（不得假设）

执行前必须重新读取 `git status --short`，不得假设工作树状态。当前已知未跟踪项至少包括：

```text
.test-tmp/（多个 task6-* 子目录；git 可能对其中若干目录报 Permission denied 警告）
.pytest_cache/
docs/superpowers/diagnostics/2026-08-26-echomind-judge-v5-calibration-failure-analysis.md
docs/superpowers/plans/2026-08-26-echomind-judge-v5-deterministic-policy-implementation.md
docs/superpowers/plans/2026-08-26-echomind-dialog-v5-final-35case-run.md（本计划）
```

`.test-tmp/` 与 `.pytest_cache/` **不得读取、修改、删除、stage**；其 Permission denied 警告直接忽略，绝不尝试进入或修复权限。预检只要求 tracked 树与索引洁净（`git diff --quiet` / `git diff --cached --quiet` 退出码 0），未跟踪项逐项列出但不触碰。

---

## Task 1：执行前身份检查（Preflight）

以下命令使用 PowerShell，在 worktree 根目录执行；若执行环境为 Git Bash，用 `powershell -NoProfile -Command "<命令>"` 执行。Python `-c` 内部只用单引号，外部用 PowerShell 双引号包裹；任何命令不得打印 `.env` 值或 API key。

- [ ] **Step 1：Python、分支、HEAD、tracked 洁净与真实工作树状态**

```powershell
Set-Location -LiteralPath 'E:\Desktop\简历项目\EchoMind所有代码+简历\EchoMind\.worktrees\task6-dialog-eval'
E:\conda_envs\echomind\python.exe -c "import sys; assert sys.executable.lower()==r'E:\conda_envs\echomind\python.exe'.lower() and sys.version_info[:2]==(3,12); print(sys.version)"
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' branch --show-current
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' rev-parse HEAD
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' diff --quiet
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' diff --cached --quiet
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' status --short
```

预期：分支 `task6-dialog-eval`；tracked 树与索引洁净；`status --short` 输出与 §0.2 已知集合核对（允许存在其他未跟踪项，逐项记录，不触碰 `.test-tmp/`）。记录 HEAD 为本次 `execution_revision`。

- [ ] **Step 2：冻结常量、项目 `.env` 与数据身份（不打印任何密钥值）**

```powershell
E:\conda_envs\echomind\python.exe -X utf8 -c "import hashlib,json; from pathlib import Path; from dotenv import dotenv_values; from evaluation.dialog_judge import PROMPT_VERSION,JUDGE_OUTPUT_STRATEGY; from evaluation.dialog_policy import PASS_RULE_VERSION,DIMENSION_PASS_FLOOR,OVERALL_PASS_THRESHOLD,COMPLETENESS_POLICY_VERSION,VIOLATION_POLICY_VERSION; env=dotenv_values('.env'); assert env.get('ANTHROPIC_API_KEY'); assert env.get('ANTHROPIC_BASE_URL'); assert PROMPT_VERSION=='dialog_judge_v5'; assert JUDGE_OUTPUT_STRATEGY=='forced_tool_then_strict_json_fallback'; assert PASS_RULE_VERSION=='dialog_pass_v5'; assert DIMENSION_PASS_FLOOR==0.75 and OVERALL_PASS_THRESHOLD==0.75; assert COMPLETENESS_POLICY_VERSION=='required_point_coverage_equal_weight_v1'; assert VIOLATION_POLICY_VERSION=='dialog_violation_caps_v1'; d=Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json'); cases=json.loads(d.read_text(encoding='utf-8')); assert hashlib.sha256(d.read_bytes()).hexdigest()=='cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2'; assert len(cases)==35 and sum(len(x['turns']) for x in cases)==43; print({'prompt':PROMPT_VERSION,'pass_rule':PASS_RULE_VERSION,'strategy':JUDGE_OUTPUT_STRATEGY,'cases':35,'turns':43,'dataset_sha256':'cb895c1f...ee51b2','project_env_present':True})"
```

预期：全部断言通过。

- [ ] **Step 3：全部新路径未被占用**

```powershell
Test-Path -LiteralPath 'data\eval\runs\run_dialog_eval_v5_final.py'
Test-Path -LiteralPath 'tests\evaluation\test_dialog_final_driver.py'
Test-Path -LiteralPath 'data\eval\runs\v5-final-historical-snapshot-pre-20260826.json'
Test-Path -LiteralPath 'E:\Desktop\简历项目\echomind-dialog-v5-final-pytest-temp'
Test-Path -LiteralPath 'E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-warmup-v5-20260826'
Test-Path -LiteralPath 'E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826'
```

预期：六项全部 `False`；任何一项 `True` 则停止，不删除任何东西。

- [ ] **Step 4：历史目录快照（pre）**

```powershell
E:\conda_envs\echomind\python.exe -X utf8 -c "import hashlib,json; from pathlib import Path; out={}; [out.update({str(p):hashlib.sha256(p.read_bytes()).hexdigest()}) for root in (Path('data/eval/runs'),Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval')) for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]; Path('data/eval/runs/v5-final-historical-snapshot-pre-20260826.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print('snapshot_files',len(out))"
```

快照范围：worktree `data/eval/runs`（排除 `__pycache__`）与 `E:\Desktop\简历项目\EchoMind_data\data\eval` 全部既有文件。**明确排除 `.test-tmp/`、`.pytest_cache/`**——快照命令不得触碰它们。

---

## Task 2：定向测试（不执行完整套件）

不运行完整 pytest 套件（完整套件的 fixture 会创建/删除 `.test-tmp/`，本任务禁止触碰）。完整套件全绿以 v5 deterministic-policy implementation 任务的记录（Task 8 Step 2 `pytest -q` 全绿）为历史回归证据，本次不再次执行。

- [ ] **Step 1：只运行对话评测直接相关的 5 个测试文件**

先移除继承的 shell 变量（不打印其值）：

```powershell
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_BASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_MODEL -ErrorAction SilentlyContinue
Remove-Item Env:EVAL_JUDGE_MODEL -ErrorAction SilentlyContinue
E:\conda_envs\echomind\python.exe -m pytest tests/evaluation/test_dialog_policy.py tests/evaluation/test_dialog_judge.py tests/evaluation/test_dialog_metrics.py tests/evaluation/test_dialog_runner.py tests/evaluation/test_dialog_judge_calibration.py -q -p no:cacheprovider --basetemp 'E:\Desktop\简历项目\echomind-dialog-v5-final-pytest-temp'
$LASTEXITCODE
```

预期：全部通过、退出码 `0`（记录实际通过数）。`--basetemp` 指向 E 盘全新目录（Task 1 Step 3 已断言不存在）；保留该目录，不删除、不复用。任何失败 → 停止。

- [ ] **Step 2：确认 `.test-tmp/` 未被触碰**

```powershell
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' status --short
```

预期：`.test-tmp/` 相关条目与 Task 1 Step 1 完全一致（仅可能继续出现 Permission denied 警告），无新增修改。

---

## Task 3：驱动 TDD、冻结与提交

**禁止：** 创建一个未经测试、只靠 `py_compile` 执行的数百行一次性驱动。驱动必须是**受测试 + 本地提交 + 冻结 SHA-256** 的执行代码。

- [ ] **Step 1：编写驱动（只做 orchestration）**

文件：`data/eval/runs/run_dialog_eval_v5_final.py`。

接口要求（计划只定接口，不内嵌源码）：

- 驱动只负责 orchestration：预检（输出目录不存在、tracked 洁净、模型/版本常量身份、数据集 SHA-256 与 35/43）→ 运行前记录身份 → 预热 → 预热门 → 正式 runner 调用 → 自动验证 → 证据汇总。
- **严禁重新实现** completeness、cap、final_scores、turn_pass、case_pass、pass_rate、metrics aggregation。
- **必须调用生产逻辑**：`dialog_policy.score_assessment` / `compute_turn_pass` / `compute_case_pass`；`dialog_metrics.compute_dialog_metrics`；`run_dialog_eval` 的 `resolve_config` / `_load_validated_dataset` / `run_evaluation` / `_create_dependencies`。
- 判定只做四种：失败、跳过、边界、输出齐全——不得重写任何判定公式或阈值。
- 依赖注入：预检、预热、正式运行与验证的函数必须接受可注入的 dependencies / runner / client（离线测试注入 fake），`main()` 仅在真实执行时才调用生产 `_create_dependencies`。
- 配置只从项目 `.env` 读取（`dotenv_values`），模型经显式参数传入并断言等于 `deepseek-v4-pro`；shell 环境变量不可能静默改变模型。
- 身份记录：预热硬门通过后、正式运行开始前，写 `WARMUP_DIR/formal_model_identity.json`，必须包含 `git_revision`、`driver_sha256`、`dataset_sha256`、`judge_model`、`prompt_version`、`pass_rule_version`、`judge_output_strategy`（另有 temperature 0.0、thinking disabled、max_attempts 3 等既有字段）。`run_metadata.json` 由生产代码生成（已含 git revision / dataset SHA-256 / 模型 / 版本），driver SHA-256 由 identity record 携带并在验证时与 `git show HEAD:data/eval/runs/run_dialog_eval_v5_final.py` 的文件哈希交叉核对。

- [ ] **Step 2：离线测试（TDD，使用 fake dependencies）**

新文件：`tests/evaluation/test_dialog_final_driver.py`。测试只使用 fake orchestrator / fake judge / fake runner / fake client 与 `tmp_path`，**不得创建真实** `dialog-warmup-v5-20260826` / `dialog-eval-v5-final-20260826` 目录，不得发起任何网络调用，不得触碰 `.test-tmp/`。

至少覆盖 5 个行为：

1. 预热失败（fake runner 使预热出现 judge failure）→ 正式 runner 调用次数 == 0；
2. 身份检查失败（模型身份不符）→ API 调用数 == 0（fake client 计数），且未创建任何目录；
3. 正式目录已存在 → 立即停止并报错；
4. 预热目录已存在 → 立即停止并报错；
5. 正式阶段只在预热硬门通过后才启动（调用顺序断言：预检 → 预热 → 硬门 → 正式）。

- [ ] **Step 3：冻结与提交**

```powershell
E:\conda_envs\echomind\python.exe -m pytest tests/evaluation/test_dialog_policy.py tests/evaluation/test_dialog_judge.py tests/evaluation/test_dialog_metrics.py tests/evaluation/test_dialog_runner.py tests/evaluation/test_dialog_judge_calibration.py tests/evaluation/test_dialog_final_driver.py -q -p no:cacheprovider --basetemp 'E:\Desktop\简历项目\echomind-dialog-v5-final-pytest-temp'
E:\conda_envs\echomind\python.exe -m py_compile 'data\eval\runs\run_dialog_eval_v5_final.py'
git diff --check
```

预期：全部通过。然后：

```powershell
E:\conda_envs\echomind\python.exe -X utf8 -c "import hashlib; from pathlib import Path; print(hashlib.sha256(Path('data/eval/runs/run_dialog_eval_v5_final.py').read_bytes()).hexdigest())"
```

记录驱动 SHA-256（冻结值，进入证据报告与 identity record）。

```powershell
git add data/eval/runs/run_dialog_eval_v5_final.py tests/evaluation/test_dialog_final_driver.py
git commit -m "feat: add tested dialog v5 final run driver"
git rev-parse HEAD
```

- 本地 commit 驱动与测试；正式运行的 `execution_revision` = 该新 HEAD。
- 提交信息与文件清单写入证据报告；**禁止 git push**；不提交快照文件、不提交 `.test-tmp/`。

---

## Task 4：预热（与正式运行同进程、不同目录）

- 复用 v4 已验证的同进程预热模式：驱动只调用一次 `_create_dependencies`，预热与正式运行共享同一 Orchestrator / Judge / HTTP client / 模型加载状态。
- 预热 = 仅 `dialog_eval_001`（1 case），结果写入独立预热目录；不计入正式指标；正式运行用全量 35 case 重新执行（不读取预热 predictions）。
- 预热不得修改正式数据：数据集只读，不向 `dialog_eval_v2.json` 路径写入任何内容。
- 预热硬门：1 个 case 且 `case_id == dialog_eval_001`；Agent/Judge 失败均为 0；`valid_judged_cases == 1`；每个 turn 的 Agent 响应非空、Judge assessment / applied_caps / final_scores / latency 齐全；Python 重算逐字段一致；数据集 SHA-256 / git revision / 模型 / 版本身份全部正确。任一失败 → 驱动抛错退出，**正式运行不启动**，预热产物保留。

---

## Task 5：正式 35-case / 43-turn

- 严格 35 cases / 43 turns，调用真实 `AgentOrchestrator` 与 Judge v5（`DialogJudge`），逐 case 顺序执行。
- 每个 turn 持久化（生产 `evaluate_case` 落盘）：`agent_response`、`agent_latency_ms`、Judge `assessment`（base_scores / required_point_coverage / violations / reasoning_summary）、`applied_caps`、`final_scores`、`turn_pass`、Agent/Judge 失败状态。
- 每个 case 持久化：`case_scores`（仅报告用）、`case_pass`（与 `passed` 别名严格相等）、`routing_audit`（routing result）。
- 正式运行中不修改任何 Judge 结果：024/T1、028/T2 的原始结构化结果照常保存，Python deterministic score 照常计算，不手工覆盖任何分数，不修改 cap、阈值或历史 calibration。

---

## Task 6：只读自动验证

- [ ] **Step 1：结构、身份与失败门**

```powershell
E:\conda_envs\echomind\python.exe -X utf8 -c "import hashlib,json; from pathlib import Path; p=Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826'); d=Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json'); rows=[json.loads(x) for x in (p/'dialog_predictions.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]; m=json.loads((p/'dialog_metrics.json').read_text(encoding='utf-8')); meta=json.loads((p/'run_metadata.json').read_text(encoding='utf-8')); expected=[f'dialog_eval_{i:03d}' for i in range(1,36)]; assert [r['case_id'] for r in rows]==expected; assert len(rows)==35==m['total_cases']==meta['case_count']; assert sum(len(r['turns']) for r in rows)==43; assert m['agent_failed_count']==0 and m['judge_failed_count']==0 and m['valid_judged_cases']==35; assert meta['prompt_version']=='dialog_judge_v5' and meta['judge_output_strategy']=='forced_tool_then_strict_json_fallback' and meta['pass_rule_version']=='dialog_pass_v5'; assert meta['dimension_pass_floor']==0.75 and meta['overall_pass_threshold']==0.75; assert meta['completeness_policy']=='required_point_coverage_equal_weight_v1' and meta['violation_policy_version']=='dialog_violation_caps_v1'; assert meta['agent_model']==meta['judge_model']=='deepseek-v4-pro'; assert meta['dataset_sha256']==hashlib.sha256(d.read_bytes()).hexdigest()=='cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2'; assert meta['context_mode']=='controlled_context' and meta['retrieval_evaluated'] is False; assert all(t['agent_response'] and t['agent_response'].strip() and not t['judge_skipped'] and not t['judge_failed'] and t['judge'] and t['judge'].get('assessment') and 'final_scores' in t['judge'] and 'applied_caps' in t['judge'] for r in rows for t in r['turns']); text=json.dumps(meta).lower(); assert 'api_key' not in text and 'authorization' not in text; print({'cases':35,'turns':43,'valid':m['valid_judged_cases'],'agent_failed':m['agent_failed_count'],'judge_failed':m['judge_failed_count'],'judge_model':meta['judge_model'],'revision':meta['git_revision']})"
```

- [ ] **Step 2：Python 确定性重算逐字段一致**

```powershell
E:\conda_envs\echomind\python.exe -X utf8 -c "import json; from pathlib import Path; from evaluation.dialog_policy import score_assessment,compute_turn_pass,compute_case_pass; rows=[json.loads(x) for x in Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826','dialog_predictions.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]; bad=[]; [bad.append(r['case_id']+'/T'+str(t['turn_id'])) for r in rows for t in r['turns'] if (score_assessment(t['judge']['assessment'])['final_scores']!=t['judge']['final_scores'] or score_assessment(t['judge']['assessment'])['applied_caps']!=t['judge']['applied_caps'] or compute_turn_pass(t['judge']['final_scores'],agent_failed=bool(t['agent_failed']),judge_failed=bool(t['judge_failed']),judge_skipped=bool(t['judge_skipped']))!=t['turn_pass'])]; [bad.append(r['case_id']) for r in rows if compute_case_pass([bool(t['turn_pass']) for t in r['turns']])!=r['case_pass'] or r['case_pass']!=r['passed']]; print({'python_recompute_mismatch':len(bad),'mismatches':bad}); assert not bad"
```

预期：`python_recompute_mismatch == 0`。

- [ ] **Step 3：指标与 routing**

```powershell
Get-Content -Raw -Encoding UTF8 'E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826\dialog_metrics.json'
E:\conda_envs\echomind\python.exe -X utf8 -c "import json; from pathlib import Path; rows=[json.loads(x) for x in Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826','dialog_predictions.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]; intent=sum(bool(r['routing_audit']['intent_match']) for r in rows); agent=sum(bool(r['routing_audit']['agent_match']) for r in rows); mismatches=[r['case_id'] for r in rows if not all(r['routing_audit'].values())]; print(json.dumps({'total_turns':sum(len(r['turns']) for r in rows),'intent_routing_exact_match':intent,'agent_routing_exact_match':agent,'routing_mismatch_cases':mismatches,'ambiguous_taxonomy_cases':['dialog_eval_015','dialog_eval_023'],'gold_modified':False},ensure_ascii=False,indent=2))"
```

必须输出（`dialog_metrics.json` + 本步统计）：total_cases、total_turns、passed_cases、pass_rate、valid_judged_cases、五个质量均值、agent/judge failed count/rate、六项 latency、intent/agent routing exact match。routing 是独立审计，不写入 `dialog_metrics.json`；AMBIGUOUS 案例（015、023）不通过修改 gold 追求准确率。

- [ ] **Step 4：驱动 SHA-256 与身份记录交叉核对**

```powershell
E:\conda_envs\echomind\python.exe -X utf8 -c "import hashlib,json,subprocess; from pathlib import Path; ident=json.loads(Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-warmup-v5-20260826','formal_model_identity.json').read_text(encoding='utf-8')); meta=json.loads(Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826','run_metadata.json').read_text(encoding='utf-8')); committed=subprocess.run(['git','show','HEAD:data/eval/runs/run_dialog_eval_v5_final.py'],capture_output=True).stdout; driver_sha=hashlib.sha256(committed).hexdigest(); assert ident['driver_sha256']==driver_sha; assert ident['git_revision']==meta['git_revision']; assert ident['judge_model']==meta['judge_model']=='deepseek-v4-pro'; assert ident['prompt_version']==meta['prompt_version']=='dialog_judge_v5'; assert ident['pass_rule_version']==meta['pass_rule_version']=='dialog_pass_v5'; assert ident['judge_output_strategy']==meta['judge_output_strategy']=='forced_tool_then_strict_json_fallback'; assert ident['dataset_sha256']==meta['dataset_sha256']; print({'driver_sha256_match':True,'identity_consistent':True,'driver_sha256':driver_sha})"
```

预期：执行文件 == 提交文件（driver SHA-256 一致），identity record 与正式 metadata 逐项一致。

- [ ] **Step 5：历史快照（post）与 Git 终检**

```powershell
E:\conda_envs\echomind\python.exe -X utf8 -c "import hashlib,json; from pathlib import Path; pre=json.loads(Path('data/eval/runs/v5-final-historical-snapshot-pre-20260826.json').read_text(encoding='utf-8')); now={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for root in (Path('data/eval/runs'),Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval')) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}; missing=[k for k in pre if k not in now]; changed=[k for k in pre if k in now and now[k]!=pre[k]]; print({'historical_unchanged':bool(not missing and not changed),'missing':missing,'changed':changed})"
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' diff --quiet
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' diff --cached --quiet
```

预期：`historical_unchanged == True`；tracked 树与索引洁净（预热/正式目录是快照之后新增的，不在基线内）。最后计算全部新产物 SHA-256（驱动、测试文件、预热 4 文件、正式 3 文件、快照文件）并记录。

---

## Task 7：审核包生成与职责分层

- [ ] **Step 1：生成必审集合与抽查集合**

必审（判定规则）：`case_pass == false`；任一 final dimension == 0.75（边界）；含 `sensitive_request_without_safety`；含 `false_completed_action`；多轮 case；routing mismatch；024 类替代流程、028 类脱敏标识符（含任何 coverage 非 covered 的 case）。抽查：从通过且不在必审集合中的 case 按 `case_id` 升序取前 5 个（固定规则，确定性）。

- [ ] **Step 2：生成审核包**

审核包 = 必审集合 + 抽查集合 + 每个 case 的 user_message / agent_response / Judge assessment / applied_caps / final_scores / turn_pass 证据摘录 + 024/T1、028/T2 的 Judge 原始 payload + 初步语义审查意见。审核包只读生成，不修改任何产物。

**职责分层（必须遵守）：**

| 职责 | 负责方 |
|---|---|
| 执行正式评测、自动结构验证、Python recompute、生成必审 case 集合、生成审核包 | DeepSeek（执行方） |
| 提供初步语义审查意见（标注为初步、非结论） | DeepSeek（执行方） |
| 返回完整证据 | DeepSeek（执行方） |
| 独立人工语义审核；判断 known semantic variance 是否可接受 | Codex / 用户 |
| 最终决定正式结果是否发布 | Codex / 用户 |

DeepSeek **不得自行宣告"人工审核通过"或"正式结果最终批准"**。正式运行结束后的状态只能是：

```text
awaiting_independent_human_review
```

不得使用 `published`、`approved`、`final` 等状态词。人工审核只确认语义标签与结果是否合理并记录 known variance；禁止手工改分、改 pass、改数据、调 Prompt。若发现严重语义错误：正式结果不得发布，停止并人工审查。

---

## Task 8：自动停止条件（任一触发 → 停止发布，失败产物保留、不覆盖不重跑）

| # | 条件 | 检测点 |
|---|---|---|
| 1 | Agent failure > 0 | 驱动验证 / Task 6 Step 1 |
| 2 | Judge failure > 0 | 驱动验证 / Task 6 Step 1 |
| 3 | 非法 Judge payload（缺 assessment / applied_caps / final_scores，或 skip） | 驱动验证 / Task 6 Step 1 |
| 4 | Python recompute mismatch > 0 | 驱动验证 / Task 6 Step 2 |
| 5 | 正式输出缺失（三件套缺失、数量/顺序不符） | 驱动验证 / Task 6 Step 1 |
| 6 | 数据集 SHA-256 不匹配 | Task 1 Step 2 / Task 6 Step 1 |
| 7 | Judge 模型身份不匹配 | 驱动断言 / Task 6 Step 1、Step 4 |
| 8 | Prompt / pass rule 版本不匹配 | 驱动断言 / Task 6 Step 1、Step 4 |
| 9 | 历史目录被修改 | Task 6 Step 5 |
| 10 | 预热或正式目录已存在 | Task 1 Step 3 / 驱动预检 |

---

## Task 9：结构发布门（人工批准是外部步骤，不在此列）

- [ ] 35/35 Agent 有有效最终响应；35/35 Judge 有合法结果（43 个 turn 全部）
- [ ] Agent failure = 0；Judge failure = 0；Python recompute mismatch = 0
- [ ] 数据 SHA-256 / 模型 / `dialog_judge_v5` / `dialog_pass_v5` / strategy 身份全部正确；driver SHA-256 与提交一致
- [ ] 历史目录未被修改
- [ ] 审核包已生成，状态 = `awaiting_independent_human_review`

不要求 `pass_rate = 100%`。最终发布决定权在 Codex / 用户。

---

## Task 10：最终证据报告格式

1. branch、`execution_revision`（driver 提交后的新 HEAD）、tracked 洁净状态（运行前后）；运行前实际 `git status --short` 输出；
2. Python 版本；定向 6 个测试文件（5 个评测测试 + 驱动离线测试）通过数与退出码；完整套件全绿历史证据引用；
3. `.env` 来源确认（只声明键存在，绝不输出值）；模型 / Prompt / pass rule / strategy / temperature / thinking / max_attempts；
4. 数据集身份（路径、SHA-256、35/43）；六个新路径预检为 `False` 的证明；
5. 驱动：接口说明、离线测试 5 个行为全绿、`py_compile`、`git diff --check`、驱动 SHA-256（冻结值）、commit hash 与提交文件清单、未 push 声明；
6. 运行前身份记录（`formal_model_identity.json` 内容，含 driver_sha256 / git_revision / dataset_sha256 / judge_model / prompt / pass rule / strategy）；
7. 驱动精确命令、退出码、`started_at` / `completed_at`、只执行一次的声明；
8. 预热：case 身份、失败数、attempts、latency、与正式指标隔离声明；
9. 正式指标：§0 口径 + 全部必须指标（含 total_turns=43、pass_rate 分母 35、routing exact match）；
10. Python recompute 结果；routing mismatch 列表与 AMBIGUOUS 说明（gold_modified=False）；历史快照 pre/post 对比；
11. 审核包内容与初步语义审查意见（标注为初步）；024/T1、028/T2 未做手工覆盖的声明；
12. 最终状态：`awaiting_independent_human_review`；确认未打印/落盘任何密钥；确认未修改生产代码、测试、数据集、历史目录、baseline、简历、主计划、`.test-tmp/`、`.pytest_cache/`。

---

## Task 11：正式运行后仍然禁止

- [ ] 冻结 baseline
- [ ] 实现 regression
- [ ] 运行 intent `test 500`
- [ ] 修改简历 / 主计划最终数字
- [ ] 处理 `.env` Git 历史
- [ ] `git push`

DeepSeek 执行完成后只生成：自动验证结果、正式指标、审核包、初步审核意见，然后停止，等待独立人工审核。

## 本任务自身的禁止事项

本计划只描述执行方案。计划修订阶段禁止：调用 Agent API、调用 Judge API、执行预热、运行正式 35-case、修改生产代码、修改测试、修改数据、修改 Judge Prompt、修改 routing gold、更新 baseline、运行 `test 500`、修改简历、触碰 `.test-tmp/`、`git push`。
