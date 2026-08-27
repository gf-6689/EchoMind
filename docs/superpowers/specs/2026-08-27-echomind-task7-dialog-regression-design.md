# EchoMind Task 7 Dialog Baseline and Regression Design

日期：2026-08-27
适用分支：`task6-dialog-eval`
性质：设计规格。本规格只冻结 Task 7 的设计口径与边界，不修改代码、不创建 baseline、不运行测试。

```text
Status: approved design pending implementation
Scope: dialog machine monitoring baseline and deterministic regression only
```

## 1. Task 6 输入口径

```text
machine_pass_rate = 24/35 = 0.6857142857142857
adjudicated_pass_rate = 22/35 = 0.6285714285714286
```

说明：

- machine metric 用于自动 regression monitoring；
- adjudicated metric 仅用于报告；
- 四维均值仍为 machine Judge metrics；
- 不修改任何 Task 6 原始产物；
- Task 6 已经 Codex 独立验证，可以进入 Task 7。

## 2. 架构

实现阶段新增独立模块：

```text
evaluation/regression.py
```

新增测试：

```text
tests/evaluation/test_regression.py
```

冻结 baseline：

```text
data/eval/baseline.json
```

禁止复用或修改旧 `evaluation/evaluator.py` 的自动 baseline 保存逻辑。

新模块必须是：

- 纯确定性；
- 不加载 Agent/Judge；
- 不读取 `.env`；
- 不调用网络；
- 不修改输入产物；
- baseline 创建与 regression 比较职责分离；
- 回归阈值判定使用标准库 `decimal.Decimal` 精确十进制比较（规则见 §6）。

## 3. CLI

冻结两个子命令：

```text
python -m evaluation.regression create-baseline ...
python -m evaluation.regression compare ...
```

`create-baseline` 输入至少包括：

- 正式 `dialog_metrics.json`
- 正式 `run_metadata.json`
- 正式 `dialog_predictions.jsonl`
- 最终 adjudication workbook
- 输出 baseline 路径

`compare` 输入至少包括：

- baseline
- current `dialog_metrics.json`
- current `run_metadata.json`
- current `dialog_predictions.jsonl`
- 全新 regression report 输出路径

## 4. baseline.json 身份字段

至少保存：

```text
schema_version
baseline_kind
created_at
execution_revision
dataset_sha256
predictions_sha256
metrics_sha256
judge_model
prompt_version
pass_rule_version
machine_overall_mean
machine_pass_rate
agent_failed_rate
judge_failed_rate
adjudicated_pass_rate
```

固定：

```text
schema_version = dialog_regression_baseline_v1
baseline_kind = dialog_machine_monitoring
```

`adjudicated_pass_rate` 必须带：

```text
usage = report_only
included_in_automatic_regression = false
reviewed_cases = 27
inherited_cases = 8
```

## 5. 身份兼容规则

创建 baseline 时，字段从正式 artifacts 读取并交叉校验，不能手填。

比较时必须相等：

```text
dataset_sha256
judge_model
prompt_version
pass_rule_version
```

任一不一致：

```text
comparison_valid = false
```

并非正常 regression，必须 fail closed。

以下字段只用于来源追踪，允许 current 与 baseline 不同：

```text
execution_revision
predictions_sha256
metrics_sha256
```

因为 regression 本来就是比较不同代码 revision 和不同运行产物。

## 6. 监控指标

自动 regression 只监控：

```text
machine_overall_mean
machine_pass_rate
```

公式与判定（使用标准库 `decimal.Decimal` 精确十进制判定）：

```text
baseline_decimal = Decimal(str(baseline))
current_decimal = Decimal(str(current))
relative_delta_decimal = (
    current_decimal - baseline_decimal
) / baseline_decimal

regression = relative_delta_decimal < Decimal("-0.05")
```

实现规则：

- 从已经解析出的数值构造 Decimal 时必须使用 `Decimal(str(value))`；禁止使用 `Decimal(value)`（二进制 float 直接转 Decimal 会保留 float 的表示误差）；
- 数学语义冻结：相对下降严格超过 5% 才告警；数学意义上恰好下降 5% 不告警；不使用四舍五入后的展示值进行判断；不使用含义不明确的任意 epsilon；
- report 中的 `relative_delta` 仍保存为普通 JSON number，可使用 `float(relative_delta_decimal)`；
- `regression` 布尔值必须根据 Decimal 比较结果生成，不能根据转换回 float 后的值生成；
- 边界语义示例：baseline=1.0、current=0.95 时 relative_delta 恰为 -0.05，不告警；current=0.949999 时低于 -0.05，告警；current=0.950001 时高于 -0.05，不告警。

不得把 adjudicated pass rate 纳入自动 regression。

## 7. failure 硬门

正式 baseline 的：

```text
agent_failed_rate = 0
judge_failed_rate = 0
```

比较时：

```text
current agent_failed_rate > 0 => regression
current judge_failed_rate > 0 => regression
```

该规则是硬门，不使用相对变化公式。

baseline 创建时若 Agent/Judge failure rate 非 0，必须拒绝创建。

## 8. 不可覆盖规则

```text
create-baseline
```

目标存在时必须立即失败，不得覆盖、清空、append 或自动更新。

后续更新必须显式指定新文件，例如：

```text
baseline_v2.json
```

禁止静默覆盖：

```text
data/eval/baseline.json
```

`compare` 也不得修改 baseline。

regression report 输出目标存在时同样失败，避免覆盖历史报告。

## 9. Intent 边界

本阶段不得写入：

```text
intent_accuracy
intent_macro_f1
```

正式 test 500 完成后，再通过新版本 baseline 补充；不得提前用 dev 190 代替。

## 10. regression report

至少包含：

```text
schema_version
baseline_path
baseline_sha256
current_execution_revision
current_predictions_sha256
current_metrics_sha256
comparison_valid
identity_checks
metric_comparisons
failure_gates
regressions
regression_detected
adjudicated_pass_rate_report_only
```

每个 metric comparison 包含：

```text
baseline
current
relative_delta
threshold
regression
```

## 11. TDD 要求

实现阶段必须 RED→GREEN，至少覆盖：

1. 合法正式 artifacts 能创建 baseline；
2. baseline 目标已存在立即失败且原文件哈希不变；
3. overall 相对下降超过 5% 告警；
4. pass rate 相对下降超过 5% 告警；
5. 恰好下降 5% 不告警（按 §6 的 Decimal 精确判定）；
6. current Agent failure rate >0 告警；
7. current Judge failure rate >0 告警；
8. dataset SHA 不匹配时 comparison_valid=false；
9. Judge model 不匹配时 fail closed；
10. Prompt/pass-rule 不匹配时 fail closed；
11. execution revision 不同仍允许比较；
12. adjudicated pass rate 不参与自动 regression；
13. compare 不修改 baseline；
14. regression report 目标已存在立即失败；
15. 不读取 `.env`、不创建网络 client。

测试只能使用 `tmp_path` 和 fake JSON artifacts，不得读取或写入真实正式目录，不得触碰 `.test-tmp/`、`.pytest_cache/`。

## 12. 正式 baseline 来源

后续实施通过后，才允许从以下只读产物创建正式 baseline：

```text
E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826\dialog_predictions.jsonl
E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826\dialog_metrics.json
E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826\run_metadata.json
data/eval/runs/v5-final-adjudication-workbook-20260827.json
```

设计规格阶段不得创建 baseline。

## 13. 禁止事项

- 不调用 API；
- 不运行测试或评测；
- 不修改生产代码；
- 不创建 baseline 或 regression report；
- 不修改 Task 6 artifacts；
- 不修改旧 evaluator；
- 不运行 test 500；
- 不更新主计划或简历；
- 不触碰 `.test-tmp/`、`.pytest_cache/`；
- 不删除 C 盘文件；
- 不处理 `.env` 历史；
- 不 push。
