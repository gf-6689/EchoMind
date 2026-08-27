# EchoMind Task 7 Dialog Baseline and Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

日期：2026-08-27
适用分支：`task6-dialog-eval`
性质：Task 7 实施计划。本计划只描述如何实施，不修改代码、不运行 pytest、不创建 baseline、不创建 self-check report。

## Goal

按已批准规格 `2026-08-27-echomind-task7-dialog-regression-design.md` 实现独立的确定性 dialog regression 模块，创建正式 baseline 与 same-run self-check evidence，并将 Task 6 的 `machine_pass_rate = 24/35`、`adjudicated_pass_rate = 22/35` 固化为监控与报告两个口径。

## Architecture

- 新模块 `evaluation/regression.py`：纯标准库、纯函数、无网络、无 `.env`、无 Agent/Judge 依赖；`build_baseline`（读产物、交叉校验、构建 baseline dict）、`create_baseline`（构建 + 独占写入）、`compare_against_baseline`（只读 baseline，产出 report dict）、`write_json_new`（独占写入）、`main`（argparse CLI，退出码 0/1/2）。
- 职责分离：baseline 创建与 regression 比较是两个互不调用的顶层入口；`compare_against_baseline` 永不写入任何文件；只有 `main` 经 `write_json_new` 落盘。
- 与旧代码的关系：`evaluation/evaluator.py` 的 `_load_baseline` / `_save_baseline`（`write_text` 静默覆盖）与 `_detect_regressions` 一律不复用、不修改。`evaluation/run_dialog_eval.py` 只作为字段命名参考（`run_metadata.json` 的 `git_revision`、`judge_model`、`prompt_version`、`pass_rule_version`、`dataset_sha256`），不 import。

## Tech Stack

- Python 3（`E:\conda_envs\echomind\python.exe`），仅标准库：`argparse`、`datetime`、`hashlib`、`json`、`pathlib`、`sys`、`typing`。
- 不新增任何依赖；不引入 anthropic / dotenv / requests / httpx / urllib / socket / subprocess。

## Spec 精确路径

`docs/superpowers/specs/2026-08-27-echomind-task7-dialog-regression-design.md`（本计划的唯一权威来源，字段与规则以该文件为准）。

## Global Constraints

- 纯确定性：相同输入 → 相同输出；无随机数、无时间依赖（`created_at` 唯一例外，见 §接口）；
- 不加载 Agent/Judge；不读取 `.env`；不调用网络；不修改任何输入产物；
- 不修改 `evaluation/evaluator.py`、`evaluation/run_dialog_eval.py`、`evaluation/dialog_metrics.py`、`evaluation/run_intent_eval.py`、Judge/Agent/Prompt/policy/rubric、冻结数据、intent test 500、主计划、简历；
- 不触碰 `.test-tmp/`、`.pytest_cache/`、既有未跟踪文件、C 盘文件；
- 不 push；不 amend。

## 冻结文件范围

实现阶段只允许：

- 创建 `evaluation/regression.py`
- 创建 `tests/evaluation/test_regression.py`
- 创建 `data/eval/baseline.json`（正式 baseline）
- 创建 `data/eval/runs/dialog-v5-baseline-self-check-20260827.json`（same-run self-check report）

不得修改上述四个新文件之外的任何 tracked 文件。若实施中发现必须修改其他 tracked 文件，立即停止并报告，不得自行扩展范围。

## 精确接口

```python
class RegressionInputError(ValueError):
    pass
```

```python
def build_baseline(
    *,
    metrics_path: Path,
    metadata_path: Path,
    predictions_path: Path,
    adjudication_path: Path,
    created_at: str | None = None,
) -> dict[str, object]:
    ...
```

输入：四个正式产物的路径；`created_at` 为可注入的时间戳（用于确定性测试），为 None 时使用 UTC 当前时间（ISO 8601，`Z` 结尾，格式与 `run_dialog_eval._utc_now` 一致）。
输出：baseline dict（字段见 §baseline schema）。
错误：任一文件不存在、JSON 无法解析、必需字段缺失、交叉校验不一致、Agent/Judge failure rate 非 0 → `RegressionInputError`。永不写文件。

```python
def create_baseline(
    *,
    metrics_path: Path,
    metadata_path: Path,
    predictions_path: Path,
    adjudication_path: Path,
    output_path: Path,
    created_at: str | None = None,
) -> dict[str, object]:
    ...
```

行为：调用 `build_baseline`，将结果经 `write_json_new` 写入 `output_path`，返回同一 dict。
错误：`build_baseline` 的错误直接传播；`output_path` 已存在 → `write_json_new` 抛 `FileExistsError`（传播，不吞掉）。

```python
def compare_against_baseline(
    *,
    baseline_path: Path,
    metrics_path: Path,
    metadata_path: Path,
    predictions_path: Path,
) -> dict[str, object]:
    ...
```

行为：只读 baseline 与 current 产物，返回 report dict（字段见 §report schema）。绝不写任何文件，绝不修改 baseline。
错误：baseline/current 文件不存在、JSON 无法解析、字段缺失、baseline `schema_version` 不是 `dialog_regression_baseline_v1` → `RegressionInputError`。
身份不兼容（§身份兼容）不抛异常：返回 `comparison_valid=false` 的 report。

```python
def write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    ...
```

行为：先完整序列化（`json.dumps(payload, ensure_ascii=False, indent=2) + "\n"`），再用文本模式 `x`（独占创建）写入 UTF-8、`newline="\n"`。
错误：目标已存在 → `FileExistsError`；父目录不存在 → `FileNotFoundError`（调用方负责保证父目录存在）。禁止 `write_text`、禁止 append、禁止 temp+`os.replace` 覆盖。

```python
def main(argv: Sequence[str] | None = None) -> int:
    ...
```

行为：argparse 解析两个子命令并分派（§CLI）；捕获 `(RegressionInputError, FileExistsError, FileNotFoundError, json.JSONDecodeError, OSError)`，打印 sanitized 信息到 stderr，返回 2。
模块尾：

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

## CLI

```text
python -m evaluation.regression create-baseline
  --metrics <dialog_metrics.json>
  --metadata <run_metadata.json>
  --predictions <dialog_predictions.jsonl>
  --adjudication <adjudication workbook>
  --output <new baseline.json>
  [--created-at <iso-z>]
```

```text
python -m evaluation.regression compare
  --baseline <baseline.json>
  --metrics <current dialog_metrics.json>
  --metadata <current run_metadata.json>
  --predictions <current dialog_predictions.jsonl>
  --output <new regression report.json>
```

退出码：

```text
0 = 创建成功，或合法比较且无 regression
1 = 合法比较且检测到 regression
2 = 输入非法、身份不兼容、目标已存在或其他 fail-closed 错误
```

`create-baseline` 成功（0）时 baseline 已落盘；`compare` 在身份不兼容时先写 `comparison_valid=false` 的 report，report 写入成功后返回 2；report 目标已存在时直接返回 2 且绝不覆盖。argparse 用法错误同样以 2 退出。

## baseline schema（字段来源，全部读取 + 交叉校验，禁止手填）

| 字段 | 来源 |
|---|---|
| `schema_version` | 常量 `"dialog_regression_baseline_v1"` |
| `baseline_kind` | 常量 `"dialog_machine_monitoring"` |
| `created_at` | `created_at` 参数，或 UTC 当前时间 |
| `execution_revision` | metadata `git_revision` |
| `dataset_sha256` | metadata `dataset_sha256`（必须为 64 位小写 hex） |
| `predictions_sha256` | predictions 文件实际 SHA-256 |
| `metrics_sha256` | metrics 文件实际 SHA-256 |
| `judge_model` | metadata `judge_model` |
| `prompt_version` | metadata `prompt_version` |
| `pass_rule_version` | metadata `pass_rule_version` |
| `machine_overall_mean` | metrics `overall_mean` |
| `machine_pass_rate` | metrics `pass_rate` |
| `agent_failed_rate` | metrics `agent_failed_rate` |
| `judge_failed_rate` | metrics `judge_failed_rate` |
| `adjudicated_pass_rate` | report-only 对象，见下 |

交叉校验（任一失败 → `RegressionInputError`）：

- predictions 逐行可解析，行数 == metrics `total_cases`；
- predictions 中 `case_pass == true` 的行数 == metrics `passed_cases`；
- metadata `case_count` == metrics `total_cases`；
- workbook `total_cases` == metrics `total_cases`；`reviewed_cases + inherited_cases == total_cases`；`machine_pass_rate == metrics["pass_rate"]`；`adjudicated_pass_rate == 0.6285714285714286`（22/35，与冻结裁决一致）；
- `agent_failed_rate == 0.0` 且 `judge_failed_rate == 0.0`，否则拒绝创建（failure 硬门，baseline 侧）。

`adjudicated_pass_rate` 保存为：

```json
{
  "value": 0.6285714285714286,
  "usage": "report_only",
  "included_in_automatic_regression": false,
  "reviewed_cases": 27,
  "inherited_cases": 8
}
```

其中 `value` = workbook `adjudicated_pass_rate`，`reviewed_cases` / `inherited_cases` = workbook 同名字段。

baseline 与 report 中均不得出现 `intent_accuracy`、`intent_macro_f1`。

## 身份兼容（fail closed）

比较时必须相等：`dataset_sha256`、`judge_model`、`prompt_version`、`pass_rule_version`。
任一不一致 → `comparison_valid=false` 的 report（`identity_checks` 逐项记录 `{field, baseline, current, match}`），`regressions=[]`、`regression_detected=false`，CLI 写盘后退出 2；baseline 不被修改。
只记录、不要求相等：`execution_revision`、`predictions_sha256`、`metrics_sha256`。

## 回归规则

只自动比较 `machine_overall_mean`、`machine_pass_rate`，使用未舍入值：

```text
relative_delta = (current - baseline) / baseline
regression = relative_delta < -0.05
```

实现直接写 `relative_delta < -0.05`，不四舍五入、不加 epsilon；边界测试用 `baseline=1.0, current=0.95`（浮点结果略大于 -0.05，不告警）验证 `== -0.05` 边界语义。

failure 硬门（不走相对公式）：

```text
current agent_failed_rate > 0 => regression
current judge_failed_rate > 0 => regression
```

adjudicated pass rate 不参与任何自动比较。

## report schema

顶层字段（顺序即写入顺序）：`schema_version`（常量 `"dialog_regression_report_v1"`，由本计划冻结）、`baseline_path`、`baseline_sha256`（baseline 文件实际哈希）、`current_execution_revision`、`current_predictions_sha256`、`current_metrics_sha256`、`comparison_valid`、`identity_checks`、`metric_comparisons`、`failure_gates`、`regressions`、`regression_detected`、`adjudicated_pass_rate_report_only`（复制 baseline 的 report-only 对象）。

每个 metric comparison 对象：

```json
{"metric": "machine_overall_mean", "baseline": 0.9232142857142858,
 "current": 0.92, "relative_delta": -0.0035, "threshold": -0.05, "regression": false}
```

每个 failure gate 对象：

```json
{"gate": "agent_failed_rate", "baseline": 0.0, "current": 0.0,
 "rule": "current > 0 => regression", "regression": false}
```

`regressions` 为字符串列表（如 `"machine_overall_mean: relative_delta=-0.06 < -0.05"`、`"judge_failed_rate: hard gate current=0.02 > 0"`）；`regression_detected = any(regressions)`。
求值顺序固定：身份检查 → failure 硬门 → 指标比较（身份失败时后两者仍计算落盘，但 `regressions=[]`、`regression_detected=false`）。

## 不可覆盖实现

`write_json_new` 独占创建语义：

- 先完整序列化（避免半写文件）；
- 文本模式 `x` 打开：目标存在 → `FileExistsError`；
- 禁止 `write_text` 静默覆盖；禁止 append；禁止 temp + `os.replace`；
- `compare` 不修改 baseline；baseline 更新必须用新文件名（如 `baseline_v2.json`）；
- regression report 目标存在同样失败。

## 测试隔离

- 实现开始前断言 `E:\Desktop\简历项目\echomind-task7-regression-pytest-temp` 不存在；若存在立即停止，不删除、不复用。
- 测试只用 `tmp_path` 与 fake JSON artifacts，不读不写真实正式目录，不触碰 `.test-tmp/`、`.pytest_cache/`。
- pytest 固定命令：

```text
E:\conda_envs\echomind\python.exe -m pytest -p no:cacheprovider --basetemp "E:\Desktop\简历项目\echomind-task7-regression-pytest-temp" tests/evaluation/test_regression.py tests/evaluation/test_dialog_metrics.py tests/evaluation/test_dialog_final_driver.py
```

- 不得运行会触碰 `.test-tmp/` 的完整测试套件。

## TDD 任务（每项：写失败测试 → 运行记录 RED → 最小实现 → 运行 GREEN → 相关回归测试 → commit）

测试文件内固定 helpers（写入 `tmp_path`）：`_write_fake_metrics(path, total_cases=35, passed_cases=24, overall_mean=0.9232142857142858, pass_rate=0.6857142857142857, agent_failed_rate=0.0, judge_failed_rate=0.0)`、`_write_fake_metadata(path, dataset_sha256=..., judge_model=..., prompt_version=..., pass_rule_version=..., git_revision=..., case_count=35)`、`_write_fake_predictions(path, total_cases, passed_cases)`、`_write_fake_adjudication(path, adjudicated_pass_rate=0.6285714285714286, reviewed_cases=27, inherited_cases=8, total_cases=35, machine_pass_rate=0.6857142857142857)`。

### Task 1：模块骨架与独占写入

- [ ] 创建 `evaluation/regression.py` 骨架：`RegressionInputError`、`write_json_new`、`main` stub、`if __name__ == "__main__"` 入口。
- [ ] RED：`test_write_json_new_creates_file_exclusively`（tmp_path 新路径 → 文件存在且内容解析为 JSON）、`test_write_json_new_fails_when_target_exists_and_preserves_content`（预写已知字节 → `FileExistsError`，重读字节完全相等）、`test_regression_input_error_is_value_error`。
- [ ] GREEN：实现 `write_json_new`（serialize 先行 + `open("x")`）。
- [ ] 回归：运行 `test_dialog_metrics.py` + `test_dialog_final_driver.py`（应全绿，未被波及）。
- [ ] commit。

### Task 2：build_baseline / create_baseline

- [ ] RED：`test_build_baseline_from_valid_artifacts`（合法 fake 产物 → 15 个顶层字段齐全；`schema_version`/`baseline_kind` 常量正确；`machine_overall_mean`/`machine_pass_rate`/failure rates 等于 metrics 值；provenance 字段等于 metadata 值；`adjudicated_pass_rate` 为 report-only 对象且 `value == 0.6285714285714286`、`reviewed_cases == 27`、`inherited_cases == 8`；注入 `created_at="2026-08-27T00:00:00Z"` 后原样落盘）。
- [ ] RED：`test_build_baseline_cross_checks_predictions_count_and_passed_cases`（predictions 行数或 passed 计数与 metrics 不一致 → `RegressionInputError`）；`test_build_baseline_rejects_nonzero_agent_failure_rate`、`test_build_baseline_rejects_nonzero_judge_failure_rate`（baseline 侧硬门）；`test_build_baseline_rejects_missing_metrics_fields`（缺 `overall_mean` → `RegressionInputError`）；`test_create_baseline_fails_when_output_exists_and_preserves_file`（目标预存在 → `FileExistsError` 且原文件字节不变）。
- [ ] GREEN：实现 `_load_metrics`/`_load_metadata`/`_load_predictions`/`_load_adjudication` 读取与校验、交叉校验、`build_baseline`、`create_baseline`。
- [ ] 回归：既有 dialog 测试 + Task 1 测试。
- [ ] commit。

### Task 3：compare_against_baseline

- [ ] RED：
  - `test_overall_mean_drop_over_5_percent_is_regression`（baseline 1.0 / current 0.94 → 该项 `regression==true`，`regression_detected==true`）；
  - `test_pass_rate_drop_over_5_percent_is_regression`（baseline 0.8 / current 0.75 → 告警）；
  - `test_exactly_5_percent_drop_is_not_regression`（baseline 1.0 / current 0.95 → `relative_delta >= -0.05`，不告警）；
  - `test_current_agent_failure_rate_positive_is_regression`、`test_current_judge_failure_rate_positive_is_regression`（current 0.02 → `failure_gates` 对应项 `regression==true`）；
  - `test_dataset_sha_mismatch_fails_closed_with_invalid_report`（current metadata dataset_sha256 不同 → `comparison_valid==false`、`regressions==[]`、`identity_checks` 记录 `match==false`）；
  - `test_judge_model_mismatch_fails_closed`、`test_prompt_version_mismatch_fails_closed`、`test_pass_rule_version_mismatch_fails_closed`（三个身份字段逐一验证）；
  - `test_execution_revision_and_artifact_hashes_may_differ`（不同 `git_revision` + 不同 predictions/metrics 内容 → `comparison_valid==true`）；
  - `test_adjudicated_pass_rate_not_in_automatic_regression`（report 的 `adjudicated_pass_rate_report_only` 等于 baseline 对象；`metric_comparisons`/`regressions`/`failure_gates` 中无 adjudicated 条目；adjudication workbook 完全不参与 compare 输入）；
  - `test_compare_does_not_modify_baseline`（compare 前后 baseline 文件 SHA-256 相同）；
  - `test_metric_comparison_records_baseline_current_delta_threshold_regression`（对象字段齐全）；
  - `test_report_contains_all_required_top_level_fields`（13 个字段齐全）；
  - `test_no_intent_fields_in_baseline_or_report`（两个 dict 均无 `intent_accuracy`/`intent_macro_f1`）。
- [ ] GREEN：实现 `compare_against_baseline`（身份检查 → 硬门 → 指标比较；未舍入 float 直接比较）。
- [ ] 回归：既有 dialog 测试 + Task 1/2 测试。
- [ ] commit。

### Task 4：CLI 与退出码

- [ ] RED：
  - `test_cli_create_baseline_end_to_end_exit_0`（`main([...])` 返回 0，baseline 文件存在可解析）；
  - `test_cli_compare_clean_exit_0`、`test_cli_compare_regression_exit_1`；
  - `test_cli_compare_identity_mismatch_exit_2_with_report_written`（report 已落盘、`comparison_valid==false`、返回 2、baseline 未变）；
  - `test_cli_report_output_exists_exit_2`（预建 report 目标 → 返回 2，原文件内容不变）；
  - `test_cli_invalid_json_exit_2`、`test_cli_missing_file_exit_2`；
  - `test_module_imports_stdlib_only_and_never_reads_env_or_network`（读取 `evaluation/regression.py` 源码，断言不含 `dotenv`/`load_dotenv`/`anthropic`/`httpx`/`requests`/`urllib`/`socket`/`subprocess`；再用 `monkeypatch` 清空相关环境变量后运行 `main` 创建流程仍返回 0）。
- [ ] GREEN：实现 `main`（子命令分派、sanitized stderr、退出码 0/1/2）。
- [ ] 回归：既有 dialog 测试 + Task 1–3 测试；记录全绿。
- [ ] commit。

### Task 5：正式 baseline 与 same-run self-check（CLI 步骤，非 pytest）

- [ ] 断言 `data/eval/baseline.json` 与 `data/eval/runs/dialog-v5-baseline-self-check-20260827.json` 均不存在。
- [ ] 重新核验正式输入哈希（冻结值见裁决协议 §0：dataset `cb895c1f…`、predictions `157dac32…`、metrics `7384c6c4…085af3f4…`、metadata `3fc866f4…`、审核包 `1e780e2e…`、阻塞裁决 `a3179947…`；workbook `9296b818…`）。
- [ ] `python -m evaluation.regression create-baseline --metrics <正式 metrics> --metadata <正式 metadata> --predictions <正式 predictions> --adjudication data/eval/runs/v5-final-adjudication-workbook-20260827.json --output data/eval/baseline.json`，退出码 0。
- [ ] 核对 baseline：`machine_overall_mean == 0.9232142857142858`、`machine_pass_rate == 0.6857142857142857`、`agent_failed_rate == 0.0`、`judge_failed_rate == 0.0`、`adjudicated_pass_rate.value == 0.6285714285714286`（27/8）、`execution_revision == 127ac799af2c16e3632580b846f153f4c1de382d`；记录 baseline SHA-256。
- [ ] `python -m evaluation.regression compare --baseline data/eval/baseline.json --metrics <正式 metrics> --metadata <正式 metadata> --predictions <正式 predictions> --output data/eval/runs/dialog-v5-baseline-self-check-20260827.json`，退出码 0。
- [ ] 核对 self-check report：`comparison_valid == true`、`regression_detected == false`、`regressions == []`、两个 metric comparison 的 `relative_delta == 0.0`、`machine_pass_rate` 记录 24/35、`adjudicated_pass_rate_report_only.value` 记录 22/35。
- [ ] 收尾核对：baseline SHA-256 在 compare 前后一致；全部正式输入哈希未变化；记录 self-check report SHA-256。

## 15 项规格 TDD → 测试函数映射

| # | 规格要求 | 测试函数 |
|---|---|---|
| 1 | 合法正式 artifacts 能创建 baseline | `test_build_baseline_from_valid_artifacts` |
| 2 | baseline 目标已存在立即失败且原文件哈希不变 | `test_create_baseline_fails_when_output_exists_and_preserves_file` |
| 3 | overall 相对下降超过 5% 告警 | `test_overall_mean_drop_over_5_percent_is_regression` |
| 4 | pass rate 相对下降超过 5% 告警 | `test_pass_rate_drop_over_5_percent_is_regression` |
| 5 | 恰好下降 5% 不告警 | `test_exactly_5_percent_drop_is_not_regression` |
| 6 | current Agent failure rate >0 告警 | `test_current_agent_failure_rate_positive_is_regression` |
| 7 | current Judge failure rate >0 告警 | `test_current_judge_failure_rate_positive_is_regression` |
| 8 | dataset SHA 不匹配时 comparison_valid=false | `test_dataset_sha_mismatch_fails_closed_with_invalid_report` |
| 9 | Judge model 不匹配时 fail closed | `test_judge_model_mismatch_fails_closed` |
| 10 | Prompt/pass-rule 不匹配时 fail closed | `test_prompt_version_mismatch_fails_closed`、`test_pass_rule_version_mismatch_fails_closed` |
| 11 | execution revision 不同仍允许比较 | `test_execution_revision_and_artifact_hashes_may_differ` |
| 12 | adjudicated pass rate 不参与自动 regression | `test_adjudicated_pass_rate_not_in_automatic_regression` |
| 13 | compare 不修改 baseline | `test_compare_does_not_modify_baseline` |
| 14 | regression report 目标已存在立即失败 | `test_cli_report_output_exists_exit_2` |
| 15 | 不读取 `.env`、不创建网络 client | `test_module_imports_stdlib_only_and_never_reads_env_or_network` |

## Commit 边界

1. 代码与测试：Task 1–4 各以一个本地 commit 收尾（`evaluation/regression.py` + `tests/evaluation/test_regression.py`）。
2. 正式 baseline 与 self-check 证据：Task 5 完成后一个 commit，仅含 `data/eval/baseline.json` 与 `data/eval/runs/dialog-v5-baseline-self-check-20260827.json`。

`data/` 被 `.gitignore` 忽略，只对精确文件执行：

```text
git add -f data/eval/baseline.json
git add -f data/eval/runs/dialog-v5-baseline-self-check-20260827.json
```

禁止 `git add .`、`git add -A`。禁止 amend、禁止 push。

## 最终停止点

Task 7 实施完成后停止：不运行 test 500；不更新主计划；不修改简历；不处理 `.env` 历史；不 push。等待 Codex 验证 baseline 与 self-check evidence。

## 计划自检清单（提交本计划前已执行）

- 无 TBD/待定/“类似上一步”等占位语句；
- 所有函数名、字段名与规格一致（`build_baseline`、`create_baseline`、`compare_against_baseline`、`write_json_new`、`main`、`RegressionInputError`；15 个 baseline 字段；13 个 report 字段）；
- 规格 15 项 TDD 要求全部映射到具体测试函数（见映射表）；
- 文件范围无扩张（仅 4 个新文件）；
- `git diff --check` 通过。
