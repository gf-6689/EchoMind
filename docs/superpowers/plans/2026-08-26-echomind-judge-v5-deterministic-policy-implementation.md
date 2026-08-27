# EchoMind Judge v5 确定性计分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 EchoMind 对话评测从“LLM 同时判断并给最终分”升级为“Judge 只输出结构化语义事实，Python 确定性计算最终分、Pass 与 Pass Rate”，并通过冻结的 10-case / 14-turn calibration oracle 后再允许正式 35-case 重跑。

**Architecture:** 保留现有 Task 6 的 `forced_tool_then_strict_json_fallback` 调用链，只替换 Judge 输出契约和评分职责。新增独立纯函数策略模块负责 coverage→completeness、violation→cap、final scores、turn/case pass；`dialog_metrics.py` 只聚合最终分，`run_dialog_eval.py` 负责持久化与 metadata。校准复用 v4 冻结 Agent 回答，Agent API 调用数必须为 0。

**Tech Stack:** Python 3、pytest、Anthropic-compatible async client、JSON/JSONL、dataclasses/typing、现有 EchoMind Task 6 evaluation pipeline。

**Spec:** `docs/superpowers/specs/2026-08-26-echomind-judge-v5-deterministic-policy-design.md`

## Global Constraints

- 适用 worktree / branch：`task6-dialog-eval`。
- 不修改 Agent Prompt、路由算法、业务回答或 intent gold label。
- 不覆盖、删除或修改任何 v1/v2/v4、Smoke、diagnostic、calibration 历史目录。
- 不手工修改 v4 predictions / metrics；v4 仅作为冻结诊断证据。
- Judge v5 不得输出最终 completeness、overall、cap 后分数、turn pass 或 case pass。
- Python 是最终四维分数、overall、turn pass、case pass、pass rate 的唯一计算者。
- `covered=1.0`、`partial=0.5`、`missing=0.0`，required points 等权计算 completeness。
- 多个违规作用于同一维度时必须取最小 cap，违规数组顺序不得改变结果。
- `DIMENSION_PASS_FLOOR = 0.75`，`OVERALL_PASS_THRESHOLD = 0.75`。
- `case_pass = all(turn_pass)`；case 平均分只用于报告。
- **审查修订 1：正式 `pass_rate = passed_cases / total_cases`；Agent/Judge 失败 case 直接计为未通过。质量均值仍只使用完全有效的 Judge case。**
- **审查修订 2：预期为 true 的 calibration turn 必须显式断言所有 final dimensions `>=0.75`；被 `0.75` cap 限制且预期通过的维度必须恰好等于 `0.75`。**
- **审查修订 3：对同一个原子操作声明，若已满足 `false_completed_action`，不得再为同一证据重复标记 `unsupported_operation`；若回答包含两个不同操作声明，可分别触发两个 code。**
- Judge 调用保持 `temperature=0.0`、thinking disabled、独立 Judge client。
- 校准复用 v4 冻结回答，Agent API 调用数必须为 `0`。
- 校准只写入全新目录；目录存在即失败，不允许 `--resume`。
- 路由 gold 冲突必须单独处理，不纳入本实施提交。
- 在 calibration oracle、完整测试、人工审查均通过前，不运行新的正式 35-case，不更新 baseline，不更新简历数字。

## Repository / Worktree Basis

公开 `gf-6689/EchoMind` 的 `main` 当前仍以 `evaluation/evaluator.py`、`intent_metrics.py`、`run_intent_eval.py` 为主；Task 6 的 `dialog_judge.py`、`dialog_metrics.py`、`run_dialog_eval.py` 及其测试位于当前本地 worktree，尚不能以公开 `main` 作为精确源码基线。因此：

1. 实施时以当前 `task6-dialog-eval` worktree 为唯一代码事实来源；
2. 下面的文件路径基于已冻结 Task 6 结构；
3. 若函数名与本计划示例存在轻微差异，保留现有公开接口并在对应文件内最小改造，不得借机重构无关模块；
4. `evaluation/evaluator.py` 的旧 Judge 不是本次修改目标，不要将 v5 逻辑回填到旧评测器。

---

## File Structure

### Create

- `evaluation/dialog_policy.py`
  - 冻结 coverage 映射、违规 cap、策略版本和阈值；
  - 提供无网络、无环境依赖、无随机性的确定性纯函数。
- `tests/evaluation/test_dialog_policy.py`
  - 覆盖 completeness、cap、final score、turn/case pass 及顺序不变性。
- `evaluation/run_dialog_judge_calibration.py`
  - 从 v4 冻结 predictions 读取 Agent 回答，只调用 Judge，不调用 Agent；
  - 执行固定 10-case / 14-turn oracle 并写新目录。
- `tests/evaluation/test_dialog_judge_calibration.py`
  - 使用 fake Judge / fixture 验证离线校准、oracle、0 Agent 调用及失败即停止。

### Modify

- `docs/superpowers/specs/2026-08-26-echomind-judge-v5-deterministic-policy-design.md`
  - 合入已批准的 3 条审查修订，使设计稿与实施计划一致。
- `evaluation/dialog_judge.py`
  - Prompt 升级为 `dialog_judge_v5`；
  - tool schema / strict JSON schema 改为 v5 assessment；
  - 严格校验 payload；
  - 保留 v4 fallback 传输策略。
- `evaluation/dialog_metrics.py`
  - 聚合 `final_scores`；
  - case pass 使用逐 turn AND；
  - pass rate 分母改为 total cases；
  - 质量均值只统计完全有效 case。
- `evaluation/run_dialog_eval.py`
  - 调用 v5 Judge → `dialog_policy` → 持久化 assessment/caps/final_scores；
  - 写入 v5 metadata；
  - 失败 case 计入 pass-rate 分母但不进入质量均值。
- `tests/evaluation/test_dialog_judge.py`
  - 替换/补充 v5 schema、fallback、违规枚举、互斥语义 Prompt 约束测试。
- `tests/evaluation/test_dialog_metrics.py`
  - 补充 total-case pass rate、失败 case、case AND、质量均值分母测试。
- `tests/evaluation/test_run_dialog_eval.py`
  - 补充持久化层级、metadata、final score 唯一来源和失败传播测试。

---

### Task 1: 冻结审查后的 v5 规格

**Files:**
- Modify: `docs/superpowers/specs/2026-08-26-echomind-judge-v5-deterministic-policy-design.md`

**Interfaces:**
- Consumes: commit `9de6fe1` 中的 v5 设计稿和本次规格审查意见。
- Produces: 后续代码实现唯一可引用的冻结规则文本。

- [ ] **Step 1: 修改 Pass Rate 定义**

将第 8 节中有效 Judge 分母定义替换为：

```text
pass_rate = passed_cases / total_cases
```

并明确：

```text
Agent/Judge 失败或 skipped 的 case：case_pass=false，进入 total_cases 分母；
质量均值：仅统计所有 turn 均获得合法 final_scores 的完全有效 case。
```

- [ ] **Step 2: 冻结违规互斥规则**

在第 6 节加入：

```text
同一原子操作声明若满足 false_completed_action，不再针对同一证据同时标记 unsupported_operation。
若回答中存在不同的操作声明，例如一处声称“已提交”，另一处声称“稍后会联系”，两个 code 可以同时出现，但 evidence 必须对应不同声明。
```

- [ ] **Step 3: 加强 true-oracle**

将第 11 节 true turns 的确定性结果至少冻结为：

```text
026/T1: final_accuracy == 0.75; final_helpfulness == 0.75; all final dimensions >= 0.75
026/T3: final_accuracy == 0.75; final_helpfulness == 0.75; all final dimensions >= 0.75
028/T1: all final dimensions >= 0.75
028/T2: final_completeness == 0.75; final_accuracy == 0.75; final_helpfulness == 0.75; final_relevance >= 0.75
028/T3: final_accuracy == 0.75; final_relevance/final_completeness/final_helpfulness >= 0.75
034/T1: final_completeness == 5/6; final_accuracy == 0.75; final_helpfulness == 0.75; final_relevance >= 0.75
```

- [ ] **Step 4: 验证规格仅发生批准范围内变化**

Run:

```bash
git diff --check
git diff -- docs/superpowers/specs/2026-08-26-echomind-judge-v5-deterministic-policy-design.md
```

Expected:
- 仅出现上述 3 类审查修订；
- 不改变 cap 数值、coverage 映射、10-case 列表和 14-turn 数量。

- [ ] **Step 5: 提交规格修订**

```bash
git add docs/superpowers/specs/2026-08-26-echomind-judge-v5-deterministic-policy-design.md
git commit -m "docs: freeze judge v5 review amendments"
```

**Stop Gate:** 规格修订未提交，不得开始生产代码。

---

### Task 2: 新增确定性评分策略模块

**Files:**
- Create: `evaluation/dialog_policy.py`
- Create: `tests/evaluation/test_dialog_policy.py`

**Interfaces:**
- Consumes: 已校验的 v5 `assessment` dict，以及 runner 的失败状态。
- Produces:
  - `score_assessment(assessment: dict) -> dict`
  - `compute_turn_pass(final_scores: dict, *, agent_failed: bool, judge_failed: bool, judge_skipped: bool) -> bool`
  - `compute_case_pass(turn_passes: list[bool]) -> bool`
  - 策略常量与版本字段。

- [ ] **Step 1: 先写策略常量和 completeness 失败测试**

在 `tests/evaluation/test_dialog_policy.py` 写：

```python
import pytest

from evaluation.dialog_policy import compute_completeness


def test_compute_completeness_equal_weight():
    coverage = [
        {"point_index": 1, "status": "covered", "evidence": "a"},
        {"point_index": 2, "status": "partial", "evidence": "b"},
        {"point_index": 3, "status": "missing", "evidence": "c"},
    ]
    assert compute_completeness(coverage) == pytest.approx(0.5)


def test_compute_completeness_rejects_empty():
    with pytest.raises(ValueError):
        compute_completeness([])
```

Run:

```bash
pytest tests/evaluation/test_dialog_policy.py -q
```

Expected: FAIL，因为模块或函数尚不存在。

- [ ] **Step 2: 实现最小策略常量和 completeness**

`evaluation/dialog_policy.py` 至少定义：

```python
PASS_RULE_VERSION = "dialog_pass_v5"
DIMENSION_PASS_FLOOR = 0.75
OVERALL_PASS_THRESHOLD = 0.75
COMPLETENESS_POLICY_VERSION = "required_point_coverage_equal_weight_v1"
VIOLATION_POLICY_VERSION = "dialog_violation_caps_v1"

COVERAGE_VALUES = {
    "covered": 1.0,
    "partial": 0.5,
    "missing": 0.0,
}

VIOLATION_CAPS = {
    "unsupported_operation": {"accuracy": 0.75, "helpfulness": 0.75},
    "false_completed_action": {"accuracy": 0.50, "helpfulness": 0.50},
    "unsupported_process_or_requirement": {"accuracy": 0.75},
    "misleading_unsupported_content": {"helpfulness": 0.85},
    "sensitive_request_without_safety": {"accuracy": 0.75, "helpfulness": 0.50},
    "context_contradiction": {"accuracy": 0.50},
    "core_fact_reversed": {"accuracy": 0.25},
    "severe_readability_defect": {"helpfulness": 0.75},
}
```

实现 `compute_completeness()`，只读取 `status`，禁止 rounding。

- [ ] **Step 3: 写 cap 顺序不变性测试**

```python
from evaluation.dialog_policy import compute_strictest_caps


def test_strictest_caps_are_order_independent():
    a = ["unsupported_operation", "sensitive_request_without_safety"]
    b = list(reversed(a))
    assert compute_strictest_caps(a) == compute_strictest_caps(b)
    assert compute_strictest_caps(a) == {
        "accuracy": 0.75,
        "helpfulness": 0.50,
    }
```

同时测试未知 code 必须失败，不允许静默忽略。

- [ ] **Step 4: 实现 final score 纯函数**

接口固定为：

```python
def score_assessment(assessment: dict) -> dict:
    """Return {'applied_caps': ..., 'final_scores': ...}."""
```

核心逻辑：

```python
final_relevance = base_scores["relevance"]
final_accuracy = min(base_scores["accuracy"], caps.get("accuracy", 1.0))
final_completeness = compute_completeness(coverage)
final_helpfulness = min(base_scores["helpfulness"], caps.get("helpfulness", 1.0))
final_overall = (
    final_relevance
    + final_accuracy
    + final_completeness
    + final_helpfulness
) / 4.0
```

`applied_caps` 只保留低于 `1.0` 的维度。

- [ ] **Step 5: 写并实现 Pass 规则**

测试：

```python
from evaluation.dialog_policy import compute_case_pass, compute_turn_pass


def test_turn_fails_when_one_dimension_below_floor_even_if_overall_passes():
    scores = {
        "relevance": 1.0,
        "accuracy": 0.5,
        "completeness": 1.0,
        "helpfulness": 1.0,
        "overall": 0.875,
    }
    assert compute_turn_pass(
        scores,
        agent_failed=False,
        judge_failed=False,
        judge_skipped=False,
    ) is False


def test_case_pass_is_all_turns():
    assert compute_case_pass([True, False, True]) is False
```

`compute_case_pass([])` 必须 raise `ValueError`。

- [ ] **Step 6: 运行策略测试并提交**

```bash
pytest tests/evaluation/test_dialog_policy.py -q
git diff --check
git add evaluation/dialog_policy.py tests/evaluation/test_dialog_policy.py
git commit -m "feat: add deterministic dialog scoring policy"
```

Expected: PASS。

---

### Task 3: 将 Judge 升级为 v5 结构化事实输出

**Files:**
- Modify: `evaluation/dialog_judge.py`
- Modify: `tests/evaluation/test_dialog_judge.py`

**Interfaces:**
- Consumes: question、Agent response、controlled context、required_points。
- Produces: 经过严格校验的 `assessment`：
  - `base_scores`
  - `required_point_coverage`
  - `violations`
  - `reasoning_summary`
- 不产生 final scores / pass。

- [ ] **Step 1: 先写顶层 schema 失败测试**

覆盖：

```python
@pytest.mark.parametrize("extra_key", [
    "completeness",
    "overall",
    "final_scores",
    "passed",
    "turn_pass",
    "case_pass",
])
def test_v5_payload_rejects_final_score_fields(extra_key):
    ...
```

以及缺少/额外顶层字段、base_scores 多字段、bool、NaN、Infinity、越界分数。

- [ ] **Step 2: 写 coverage 严格校验测试**

必须覆盖：
- 数量与 required_points 不一致；
- index 缺失、重复、越界；
- 未知 status；
- 空 evidence；
- required_points 为空。

所有情况都应判 Judge payload 无效，而不是补默认值。

- [ ] **Step 3: 写 violation 严格校验测试**

必须覆盖：
- 未知 code；
- 重复 code；
- 空 evidence 数组；
- evidence 空字符串；
- violation 多余字段。

- [ ] **Step 4: 升级 Prompt / tool schema**

Prompt 版本固定：

```python
PROMPT_VERSION = "dialog_judge_v5"
```

Prompt 必须明确：

```text
1. 只给 base relevance / accuracy / helpfulness，不给 completeness。
2. required point 每项只能 covered / partial / missing。
3. 只输出冻结违规 code，不输出 cap 数值。
4. 不输出 overall / final score / pass。
5. base_scores 不得提前应用 cap。
6. 同一原子操作声明若构成 false_completed_action，不再对同一证据重复标记 unsupported_operation。
7. 两个不同操作声明可分别触发两个 code，evidence 必须区分。
```

Tool schema 与 strict JSON fallback 必须引用同一份 v5 schema 构造逻辑，禁止复制两份后漂移。

- [ ] **Step 5: 保留 v4 fallback 行为并补回归测试**

必须继续满足：
- attempt 1–2 强制唯一 tool；
- 只有两次都为精确 `{}` 才允许 attempt 3 strict JSON；
- 非空无效 payload 不进入 fallback；
- 最多 3 次总尝试；
- 密钥/敏感字段不进入错误日志。

Run:

```bash
pytest tests/evaluation/test_dialog_judge.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交 Judge v5**

```bash
git add evaluation/dialog_judge.py tests/evaluation/test_dialog_judge.py
git commit -m "feat: add structured judge v5 assessment"
```

---

### Task 4: Runner 接入确定性评分与分层持久化

**Files:**
- Modify: `evaluation/run_dialog_eval.py`
- Modify: `tests/evaluation/test_run_dialog_eval.py`

**Interfaces:**
- Consumes: `assessment = dialog_judge.judge(...)`。
- Uses: `score_assessment()`、`compute_turn_pass()`、`compute_case_pass()`。
- Produces: v5 JSONL turn record 和 case record。

- [ ] **Step 1: 写 v5 持久化结构失败测试**

成功 Judge turn 必须包含：

```json
{
  "judge": {
    "assessment": {},
    "applied_caps": {},
    "final_scores": {},
    "latency_ms": 0.0
  },
  "turn_pass": false
}
```

测试必须断言：
- `assessment` 中没有 final scores；
- `final_scores` 来自 Python scorer；
- `applied_caps` 与 violation code 对应；
- 顶层兼容字段 `passed` 若保留，必须严格等于 `case_pass`。

- [ ] **Step 2: 接入 v5 scoring flow**

单 turn 固定流程：

```text
Agent result
→ 若 Agent 失败：judge_skipped=true, turn_pass=false
→ Judge v5 assessment
→ 若 Judge 失败：turn_pass=false
→ score_assessment(assessment)
→ compute_turn_pass(final_scores, flags...)
→ persist assessment + applied_caps + final_scores + turn_pass
```

禁止从 `reasoning_summary` 解析任何分数或违规。

- [ ] **Step 3: 实现多轮 case AND**

case 完成后：

```python
case_pass = compute_case_pass([turn["turn_pass"] for turn in turns])
```

`case_scores` 可保留各有效 turn 的 final score 均值用于报告，但不得参与 `case_pass`。

- [ ] **Step 4: 写失败传播测试**

至少覆盖：
- Agent failure → Judge 未调用 → case false；
- Judge failure → case false；
- 多轮中仅一个 turn false → case false；
- case 平均 overall > 0.75 仍不能覆盖失败 turn。

- [ ] **Step 5: 更新 run metadata**

写入：

```json
{
  "prompt_version": "dialog_judge_v5",
  "judge_output_strategy": "forced_tool_then_strict_json_fallback",
  "pass_rule_version": "dialog_pass_v5",
  "dimension_pass_floor": 0.75,
  "overall_pass_threshold": 0.75,
  "completeness_policy": "required_point_coverage_equal_weight_v1",
  "violation_policy_version": "dialog_violation_caps_v1"
}
```

若兼容保留 `pass_threshold`，必须等于 `overall_pass_threshold`，且测试证明它不能绕过单维门槛。

- [ ] **Step 6: 运行 runner 测试并提交**

```bash
pytest tests/evaluation/test_run_dialog_eval.py -q
git diff --check
git add evaluation/run_dialog_eval.py tests/evaluation/test_run_dialog_eval.py
git commit -m "feat: persist deterministic judge v5 results"
```

---

### Task 5: 修改 Dialog Metrics 的 Pass Rate 与质量分母

**Files:**
- Modify: `evaluation/dialog_metrics.py`
- Modify: `tests/evaluation/test_dialog_metrics.py`

**Interfaces:**
- Consumes: runner 产出的 case records。
- Produces: 质量均值、`passed_cases`、`total_cases`、`pass_rate`、Agent/Judge failure counts/rates。

- [ ] **Step 1: 先写 total-case pass-rate 测试**

```python
def test_pass_rate_uses_all_cases_not_only_valid_judged_cases():
    cases = [
        make_case(case_pass=True, valid=True),
        make_case(case_pass=True, valid=True),
        make_case(case_pass=False, valid=False, judge_failed=True),
    ]
    metrics = compute_dialog_metrics(cases)
    assert metrics["passed_cases"] == 2
    assert metrics["total_cases"] == 3
    assert metrics["pass_rate"] == pytest.approx(2 / 3)
```

该测试必须防止再次出现“2/2=100% 掩盖第 3 个 Judge failure”。

- [ ] **Step 2: 写质量均值分母测试**

同一 fixture 中：
- failed case 进入 `total_cases`；
- failed case 不进入 relevance/accuracy/completeness/helpfulness/overall mean；
- `valid_judged_cases == 2`；
- `judge_failed_count == 1`。

- [ ] **Step 3: 指标只读 final_scores**

构造 assessment base score 与 final score 不同的 case：

```text
base accuracy = 1.0
final accuracy = 0.5
```

断言 metrics 的 accuracy 使用 `0.5`，不得读取 base score。

- [ ] **Step 4: 保留失败审计指标**

至少输出并测试：

```text
total_cases
passed_cases
pass_rate
valid_judged_cases
agent_failed_count
agent_failed_rate
judge_failed_count
judge_failed_rate
relevance_mean
accuracy_mean
completeness_mean
helpfulness_mean
overall_mean
```

- [ ] **Step 5: 运行 metrics 测试并提交**

```bash
pytest tests/evaluation/test_dialog_metrics.py -q
git diff --check
git add evaluation/dialog_metrics.py tests/evaluation/test_dialog_metrics.py
git commit -m "fix: use total cases for dialog pass rate"
```

---

### Task 6: 实现冻结回答的 10-case / 14-turn Offline Calibration

**Files:**
- Create: `evaluation/run_dialog_judge_calibration.py`
- Create: `tests/evaluation/test_dialog_judge_calibration.py`

**Interfaces:**
- Consumes:
  - `EchoMind_data/data/eval/dialog_eval_v2.json`
  - v4 冻结 `dialog_predictions.jsonl`
  - exact Judge model from v4 metadata / approved v5 config
- Produces:
  - 全新 calibration 目录；
  - 10 cases / 14 turns 的 v5 assessment + deterministic results；
  - oracle summary；
  - Agent API calls = 0 的可审计记录。

- [ ] **Step 1: 冻结 case/turn 列表常量**

```python
CALIBRATION_CASE_IDS = [
    "dialog_eval_001",
    "dialog_eval_018",
    "dialog_eval_019",
    "dialog_eval_024",
    "dialog_eval_025",
    "dialog_eval_026",
    "dialog_eval_028",
    "dialog_eval_031",
    "dialog_eval_033",
    "dialog_eval_034",
]
```

启动时必须断言：

```text
10 cases
14 turns
```

- [ ] **Step 2: 写“不得调用 Agent”测试**

Calibration driver 不接受 orchestrator 参数，不 import `AgentOrchestrator`，只读取冻结 v4 Agent response。

测试用 monkeypatch 对 Agent/orchestrator import 或调用设置爆炸钩子，仍应完成离线 fixture 校准。

- [ ] **Step 3: 编码精确 oracle**

Oracle 至少包含：

```python
ORACLE = {
    ("dialog_eval_001", 1): {
        "coverage": ["partial"],
        "required_violations": [],
        "turn_pass": False,
    },
    ("dialog_eval_026", 1): {
        "coverage": ["covered", "covered"],
        "required_violations": ["unsupported_operation"],
        "final_exact": {"accuracy": 0.75, "helpfulness": 0.75},
        "all_dimensions_at_least": 0.75,
        "turn_pass": True,
    },
    ("dialog_eval_026", 2): {
        "coverage": ["covered", "covered"],
        "required_violations": ["false_completed_action"],
        "turn_pass": False,
    },
    ("dialog_eval_028", 2): {
        "coverage": ["partial", "covered"],
        "required_violations": [
            "unsupported_operation",
            "unsupported_process_or_requirement",
            "misleading_unsupported_content",
        ],
        "final_exact": {
            "accuracy": 0.75,
            "completeness": 0.75,
            "helpfulness": 0.75,
        },
        "all_dimensions_at_least": 0.75,
        "turn_pass": True,
    },
    ("dialog_eval_034", 1): {
        "coverage": ["covered", "partial", "covered"],
        "required_violations": ["unsupported_operation"],
        "final_exact": {
            "accuracy": 0.75,
            "helpfulness": 0.75,
            "completeness": 5 / 6,
        },
        "all_dimensions_at_least": 0.75,
        "turn_pass": True,
    },
}
```

其余 9 行按冻结规格逐项完整录入，禁止用“类似上一项”的共享隐式规则代替。

- [ ] **Step 4: Oracle 对额外 violation 采用 fail-closed**

校准比较规则：

```text
实际 coverage 必须逐项精确相等；
required violations 必须全部出现；
出现 oracle 未批准的额外 violation → calibration failure；
reasoning_summary 与结构字段明显冲突 → manual_review_failed=true；
true turn 的所有 final dimensions 必须 >=0.75；
0.75 cap + true turn 的对应 final dimension 必须 ==0.75。
```

- [ ] **Step 5: 校准输出目录安全测试**

若 `--output-dir` 已存在，必须立即失败；不允许 resume、覆盖或 append。

输出至少：

```text
run_metadata.json
calibration_results.jsonl
calibration_summary.json
```

metadata 至少记录：
- source v4 predictions SHA-256；
- dataset SHA-256；
- exact Judge model；
- prompt/pass/completeness/violation policy versions；
- `agent_api_calls = 0`；
- `case_count = 10`；
- `turn_count = 14`。

- [ ] **Step 6: 测试校准失败必须停止**

fake Judge 故意让任一 true turn 最终 accuracy=0.70，driver 必须：
- 写出失败证据；
- summary 标记失败；
- 返回非 0 exit code；
- 不继续宣称 calibration passed。

- [ ] **Step 7: 运行离线单元测试并提交**

```bash
pytest tests/evaluation/test_dialog_judge_calibration.py -q
git diff --check
git add evaluation/run_dialog_judge_calibration.py tests/evaluation/test_dialog_judge_calibration.py
git commit -m "test: add judge v5 calibration oracle"
```

**Stop Gate:** 到这里仍不得调用真实 Judge API；先进行完整代码审查和全量测试。

---

### Task 7: 完整回归验证与静态审查

**Files:**
- No new production files expected.
- Verify all modified files from Tasks 1–6.

**Interfaces:**
- Consumes: 完整 v5 实现。
- Produces: 是否允许进入一次真实 10-case Judge calibration 的明确结论。

- [ ] **Step 1: 运行 v5 定向测试**

```bash
pytest tests/evaluation/test_dialog_policy.py -q
pytest tests/evaluation/test_dialog_judge.py -q
pytest tests/evaluation/test_dialog_metrics.py -q
pytest tests/evaluation/test_run_dialog_eval.py -q
pytest tests/evaluation/test_dialog_judge_calibration.py -q
```

Expected: 全部 PASS。

- [ ] **Step 2: 运行完整测试套件**

```bash
pytest -q
```

Expected: 全绿；不得通过删除旧测试来换取通过。

- [ ] **Step 3: Python 语法与 diff 检查**

```bash
python -m py_compile \
  evaluation/dialog_policy.py \
  evaluation/dialog_judge.py \
  evaluation/dialog_metrics.py \
  evaluation/run_dialog_eval.py \
  evaluation/run_dialog_judge_calibration.py

git diff --check
```

Expected: PASS。

- [ ] **Step 4: 搜索禁止字段和旧评分入口**

至少检查 v5 Judge schema / Prompt 不再允许：

```text
completeness
final_scores
overall
passed
turn_pass
case_pass
```

注意：这些词可以存在于 Python deterministic scorer / runner / metrics 中，但不能作为 Judge v5 输出字段。

- [ ] **Step 5: 验证历史目录和数据未被改动**

重新计算并比对规格中冻结的：
- `dialog_eval_v2.json` SHA-256；
- v4 predictions SHA-256；
- v4 metrics SHA-256；
- v4 metadata SHA-256。

任何 hash 改变都停止。

- [ ] **Step 6: 形成执行前审查记录**

记录：

```text
spec amendment commit
policy commit
judge commit
runner commit
metrics commit
calibration commit
pytest summary
py_compile result
git diff --check result
frozen hash verification
```

**Stop Gate:** 只有上述全部通过，才允许执行一次真实 Judge calibration。

---

### Task 8: 执行一次真实 Judge v5 Calibration（0 Agent 调用）

**Files:**
- Read only: v4 frozen predictions、v4 metadata、`dialog_eval_v2.json`
- Write new: `EchoMind_data/data/eval/runs/<new-v5-calibration-run-id>/...`

**Interfaces:**
- Consumes: 已通过 Task 7 的代码和冻结 v4 Agent responses。
- Produces: 10-case / 14-turn v5 calibration evidence。

- [ ] **Step 1: 运行前断言**

执行 driver 前验证：

```text
输出目录不存在；
模型与批准的 exact Judge model 一致；
dataset SHA-256 一致；
v4 predictions SHA-256 一致；
10 cases / 14 turns；
Agent API calls 预期为 0。
```

- [ ] **Step 2: 执行一次 calibration**

命令格式固定为：

```bash
python -m evaluation.run_dialog_judge_calibration \
  --dialog-data <ABSOLUTE_PATH_TO_EchoMind_data/data/eval/dialog_eval_v2.json> \
  --source-predictions <ABSOLUTE_PATH_TO_dialog-eval-v4/dialog_predictions.jsonl> \
  --source-metadata <ABSOLUTE_PATH_TO_dialog-eval-v4/run_metadata.json> \
  --output-dir <ABSOLUTE_NEW_V5_CALIBRATION_DIR>
```

实施时用当前 worktree 的真实绝对路径替换尖括号；不得更改 case 列表或 oracle。

- [ ] **Step 3: 自动验收**

必须同时满足：

```text
case_count = 10
turn_count = 14
agent_api_calls = 0
judge_failed_count = 0
oracle_failed_turns = 0
case_pass false: 001,018,019,024,025,026,031,033
case_pass true: 028,034
```

- [ ] **Step 4: 人工语义审查**

逐条检查：
- coverage evidence 是否支持 coverage status；
- violation evidence 是否支持对应 code；
- reasoning_summary 是否与结构字段冲突；
- `026/T2` 是否把“为您申请”识别为 `false_completed_action`；
- 同一证据是否错误地同时触发 `false_completed_action` 与 `unsupported_operation`；
- 028/034 的 true turn 是否确实所有 final dimensions >=0.75。

- [ ] **Step 5: Calibration 失败处理**

任一断言失败：
- 保留该目录；
- 不在同目录重跑；
- 不修改 oracle 追求通过；
- 回到 Prompt/schema/规格审查定位原因；
- 不进入 35-case 正式运行。

- [ ] **Step 6: Calibration 通过后的提交边界**

校准结果是运行产物，不要与路由 gold 修改混在同一提交。是否提交运行摘要按现有项目产物管理规则执行；不得提交 API key 或 `.env`。

---

## Deferred: 不属于本计划的后续任务

以下任务必须另开规格/计划，不能由执行者顺手完成：

1. 路由 gold label 冲突裁决；
2. Judge v5 正式 35-case 预热与重跑；
3. 正式结果人工抽查；
4. Task 7 baseline 冻结与 5% regression；
5. 简历最终指标更新。

只有 **v5 calibration 通过 + 路由 gold 独立审查完成** 后，才允许编写正式 35-case 运行计划。

---

## Final Acceptance Checklist

- [ ] 设计规格已合入 3 条审查修订。
- [ ] Judge v5 只输出 `base_scores / required_point_coverage / violations / reasoning_summary`。
- [ ] Judge 无权输出 completeness / overall / final scores / pass。
- [ ] Python scorer 是纯函数，coverage 与 cap 全部确定性。
- [ ] 多违规同维度取最严格 cap，顺序不影响结果。
- [ ] 同一原子操作声明 `false_completed_action` 优先，不重复标记 `unsupported_operation`。
- [ ] `turn_pass` 要求四维和 overall 均 `>=0.75`，且 Agent/Judge 未失败。
- [ ] `case_pass = all(turn_pass)`。
- [ ] `pass_rate = passed_cases / total_cases`，失败 case 进入分母。
- [ ] 质量均值只使用完全有效 Judge case。
- [ ] true-oracle 的 `0.75 cap` 维度最终恰好为 `0.75`。
- [ ] 10-case / 14-turn calibration 复用 v4 Agent 回答，Agent API 调用数为 0。
- [ ] calibration 目录全新且不可覆盖。
- [ ] 完整测试套件、`py_compile`、`git diff --check` 全部通过。
- [ ] v4 及冻结数据 SHA-256 未变化。
- [ ] calibration 全部通过并完成人工语义审查。
- [ ] 未修改 routing gold、baseline、简历指标或无关 Agent 代码。

## Execution Boundary

本计划执行到 **真实 10-case / 14-turn Judge v5 calibration + 人工审查** 为止。

**明确禁止在同一轮执行中继续做：正式 35-case、route gold 修改、baseline、regression、简历指标。**
