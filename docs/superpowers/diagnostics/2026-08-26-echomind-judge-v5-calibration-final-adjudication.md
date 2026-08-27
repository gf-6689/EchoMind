# EchoMind Judge v5 Calibration 最终人工裁决

日期：2026-08-26
状态：人工裁决已冻结。本文件为独立审查层记录，不回写任何历史运行产物。
依据：`docs/superpowers/diagnostics/2026-08-26-echomind-judge-v5-calibration-failure-analysis.md`（r1 根因诊断）、r3 冻结运行产物 `EchoMind_data/data/eval/runs/dialog-judge-calibration-v5-r3-20260826/`。

## 1. r3 最终自动结果（历史原值，不得改写）

```text
valid_payload_turns      = 14/14
judge_failed_count       = 0
agent_api_calls          = 0
python_recompute_mismatch = 0
reasoning_conflict       = 0
turn_pass_match          = 14/14
case_pass_match          = 10/10
hard_oracle_failed_turns = 2
```

r3 目录中的原始字段 `calibration_passed = false`、`hard_oracle_failed_turns = 2`、`score_critical_mismatch = 2`、`soft_oracle_warning_count = 8` 保持原样，人工裁决不得回写这些历史结果。

## 2. 两个人工裁决 variance

### 024/T1

```text
oracle coverage    = [covered, covered, missing]
Judge 实际          = [covered, covered, partial]
最终分数差异        = completeness 0.8333 vs oracle 0.6667（漂移 0.1667）
人工确认            = oracle 正确，继续保留
分类                = known_judge_semantic_variance
```

裁决理由：第三个 required point 为"24 小时后仍未收到取件码 → 平台联系承运商核实"（特定主体=平台、特定动作=联系承运商、特定时限=24 小时）。Agent 回答提供的是"30 分钟后由助手登记并反馈给承运商"的另一套替代流程，主体、动作、时限均被替换，未实际覆盖原 required point。按冻结 coverage 定义（"用不受支持的替代流程取代该点"→ missing），`missing` 成立；Judge 判 `partial` 属于单次 LLM 语义判断的残余偏差。

### 028/T2

```text
oracle coverage    = [partial, covered]
oracle violations  = unsupported_operation + unsupported_process_or_requirement
                     + misleading_unsupported_content
Judge 实际          = coverage 正确（[partial, covered]），violations 全部未识别
最终分数差异        = accuracy/helpfulness 1.0 vs oracle 0.75（漂移 0.25）
人工确认            = oracle 正确，继续保留
分类                = known_judge_semantic_variance
```

裁决理由：

- 数据中用户输入的税号为脱敏占位形式（含 "XXXXX"），Agent 不能据此反向要求用户重新提交受控上下文未要求的额外材料（"请提供准确的 18 位统一社会信用代码"属受控上下文之外的流程/材料要求）；
- Agent 声称"以便我们为您申请电子发票"属于无依据操作能力；
- "如需更改邮箱请一并告知"等属于受控上下文之外的流程；
- 因此原 oracle 三个 violation 与 `[partial, covered]` 均有充分依据，继续保留。

## 3. 最终 calibration 结论

Judge v5 deterministic scoring and pass-level calibration accepted.

14/14 turn_pass matched.
10/10 case_pass matched.
0 Judge failure.
0 Python recompute mismatch.
0 reasoning conflict.

2 fine-grained semantic oracle mismatches remain:
024/T1 and 028/T2.

Both were manually adjudicated and confirmed as valid oracle expectations,
and are retained as known Judge semantic variance.

明确表述：

- 不得写成 "14/14 semantic oracle fully passed"；
- 确定性计分机制（coverage→completeness、violation→cap、final scores、turn/case pass、pass_rate）通过；
- pass 层级校准（turn_pass / case_pass / 失败计数 / recompute 一致性）通过；
- 细粒度语义 oracle（coverage 状态与辅助 violation 的逐字匹配）存在 2 个已人工确认的 known variance（024/T1、028/T2）。

## 4. 发布边界

后续正式 35-case 必须同时进行自动指标检查和人工语义抽查，不能仅依赖 LLM Judge 的细粒度 violation 标签。特别是 024/T1、028/T2 两类的语义边界（替代流程→missing、掩码占位符情境下的越权流程声明），在正式运行的人工抽查中必须重点复核。
