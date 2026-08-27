# EchoMind Dialog v5 正式运行人工裁决协议（冻结）

日期：2026-08-27
状态：冻结
适用分支：`task6-dialog-eval`
执行版本（execution_revision）：`127ac799af2c16e3632580b846f153f4c1de382d`
冻结 rubric：`docs/superpowers/specs/2026-08-26-echomind-judge-v5-deterministic-policy-design.md`
关联工作表：`data/eval/runs/v5-final-adjudication-workbook-20260827.json`

本协议冻结指标命名、四类 adjudication 映射、多轮规则、指标边界、reviewed / inherited 集合、工作表 Schema 与机械验证清单。除已冻结的 `024/T1`、`031/T1`、`028/T2` 三个 turn 外，DeepSeek 不得代替 Codex/用户填写任何最终 adjudication。

## 0. 只读依据（身份冻结）

| 文件 | SHA-256 |
|---|---|
| `EchoMind_data/data/eval/dialog_eval_v2.json` | `cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2` |
| `dialog-eval-v5-final-20260826/dialog_predictions.jsonl` | `157dac323cf59b24ee88fc4bc89322b5c184755c5b558d0a9e51af94af1d993c` |
| `dialog-eval-v5-final-20260826/dialog_metrics.json` | `7384c6c4335e2988569384e6472c68a085af3f4a0f8e40cc0f7838b5efc51995` |
| `dialog-eval-v5-final-20260826/run_metadata.json` | `3fc866f4365da99d58403368df976e554a75a58bce4ecde6c201b08587d18e56` |
| `data/eval/runs/v5-final-review-package-20260826.json` | `1e780e2e1e38d771e382c420c694dfc9f85516d8fc2c3dbc66a895607294a868` |
| `docs/superpowers/diagnostics/2026-08-27-echomind-dialog-v5-final-blocking-adjudication.md` | `a31799476b716f197544c18bb0cda1874d4221447acb536d233cb96eb2c51cc1` |

冻结 rubric（`docs/superpowers/specs/2026-08-26-echomind-judge-v5-deterministic-policy-design.md`）在本协议冻结时的实测 SHA-256：`c43dab590b4a17e78888d47fec22964d66e6c5d1170f6d70d23281c4f160870c`。

哈希差异记录：任务冻结值中 `dialog_metrics.json` 的 SHA-256 原文为 `7384c6c4335e2988569384e6472c68a085aff3f4a0f8e40cc0f7838b5efc51995`（第 36 位多一个 `f`），与文件实际哈希不符。文件 mtime 为正式运行完成时刻（2026-08-26T21:29:03+08:00），内容与阻塞裁决文档 §4 的机器候选指标一致；sha256sum、Python hashlib、PowerShell Get-FileHash 三个独立实现均计算为 `7384c6c4335e2988569384e6472c68a085af3f4a0f8e40cc0f7838b5efc51995`。经用户于 2026-08-27 裁决，认定冻结值为笔误，按文件实际哈希冻结（见上表）。

所有输入只读。任一哈希不符立即停止。

## 1. 指标命名（冻结）

正式名称：

```text
machine_pass_rate
adjudicated_pass_rate
```

禁止使用：

```text
human_adjudicated_pass_rate
```

定义：

```text
reviewed_cases = 27
inherited_cases = 8
total_cases = 35

27 个 reviewed cases：
使用 adjudicated_case_pass

8 个 unreviewed cases：
继承 machine_case_pass

adjudicated_pass_rate =
(sum(adjudicated_case_pass for 27 reviewed cases)
 + sum(machine_case_pass for 8 inherited cases))
/ 35
```

口径必须完整表述为：

```text
adjudicated pass rate based on 27 pre-frozen manually reviewed cases and 8 inherited machine outcomes
```

## 2. 四类 adjudication 映射（逐 turn 冻结）

| adjudication | adjudicated_turn_pass |
|---|---|
| AGREE | 等于 machine_turn_pass |
| FALSE_POSITIVE | false |
| FALSE_NEGATIVE | true |
| NON_PASS_CRITICAL_VARIANCE | 等于 machine_turn_pass |

术语定义：

- `FALSE_POSITIVE`：machine_turn_pass=true，但人工按冻结 rubric 裁决应为 false；
- `FALSE_NEGATIVE`：machine_turn_pass=false，但人工按冻结 rubric 裁决应为 true；
- `NON_PASS_CRITICAL_VARIANCE`：存在语义标签、coverage、violation 或解释差异，但不改变 turn pass；
- `AGREE`：人工认可 machine turn pass，且没有需要单独记录的非 pass-critical variance。

## 3. 多轮规则（冻结）

一旦 case 被纳入 reviewed 集合，必须审核该 case 的全部 turns，不得只审核触发必审条件的 turn。

```text
adjudicated_case_pass =
all(adjudicated_turn_pass for every turn in the reviewed case)
```

## 4. 指标边界（冻结）

- 原始 predictions、metrics、metadata 永不修改；
- `machine_pass_rate = 24/35 = 0.6857142857142857` 永久保留；
- `adjudicated_pass_rate` 在全部 27-case / 35-turn 审核完成前必须为 null；
- 不人工重算或发布 relevance、accuracy、completeness、helpfulness、overall 均值；
- 四维均值继续只称为 machine Judge metrics；
- Task 7 自动 regression 使用 machine metric 作为 monitoring baseline；
- adjudicated pass rate 用作固定人工审核后的质量指标；
- 自动 regression 告警不自动证明真实质量退化，必须人工复核。

## 5. 冻结 reviewed / inherited 集合

### 5.1 Reviewed cases：27

```text
dialog_eval_001
dialog_eval_002
dialog_eval_003
dialog_eval_004
dialog_eval_005
dialog_eval_006
dialog_eval_010
dialog_eval_011
dialog_eval_014
dialog_eval_015
dialog_eval_016
dialog_eval_018
dialog_eval_019
dialog_eval_020
dialog_eval_023
dialog_eval_024
dialog_eval_025
dialog_eval_026
dialog_eval_027
dialog_eval_028
dialog_eval_029
dialog_eval_030
dialog_eval_031
dialog_eval_032
dialog_eval_033
dialog_eval_034
dialog_eval_035
```

必须断言：

```text
reviewed_cases = 27
reviewed_turns = 35
```

### 5.2 Inherited cases：8

```text
dialog_eval_007
dialog_eval_008
dialog_eval_009
dialog_eval_012
dialog_eval_013
dialog_eval_017
dialog_eval_021
dialog_eval_022
```

每个 inherited case 必须记录：

```text
review_status = NOT_MANUALLY_REVIEWED
outcome_source = INHERITED_MACHINE
adjudicated_case_pass = machine_case_pass
```

必须断言：

```text
inherited_cases = 8
total_cases = 35
total_turns = 43
```

## 6. 工作表 Schema（冻结）

路径：`data/eval/runs/v5-final-adjudication-workbook-20260827.json`

顶层至少包含：

```json
{
  "schema_version": "dialog_adjudication_v1",
  "status": "awaiting_manual_adjudication",
  "execution_revision": "127ac799af2c16e3632580b846f153f4c1de382d",
  "dataset_sha256": "...",
  "predictions_sha256": "...",
  "metrics_sha256": "...",
  "metadata_sha256": "...",
  "review_package_sha256": "...",
  "blocking_adjudication_sha256": "...",
  "machine_passed_cases": 24,
  "machine_pass_rate": 0.6857142857142857,
  "reviewed_cases": 27,
  "reviewed_turns": 35,
  "inherited_cases": 8,
  "total_cases": 35,
  "total_turns": 43,
  "adjudicated_passed_cases": null,
  "adjudicated_pass_rate": null,
  "classification_mapping": {},
  "reviewed_case_ids": [],
  "inherited_case_ids": [],
  "cases": []
}
```

### 6.1 Reviewed case 字段

每个 reviewed case 必须包含：

- case_id
- review_status
- machine_case_pass
- adjudicated_case_pass
- selection_reasons
- routing_audit
- turns

审核未完成时：

```text
review_status = PENDING
adjudicated_case_pass = null
```

### 6.2 Reviewed turn 字段

每个 turn 必须包含完整审核证据：

- turn_id
- user_message
- controlled_context
- reference_answer
- required_points
- agent_response
- Judge assessment
- applied_caps
- final_scores
- machine_turn_pass
- existing_review_evidence
- review_status
- adjudication
- adjudicated_turn_pass
- adjudication_reason
- rubric_references

普通待审核 turn 初始化为：

```text
review_status = PENDING
adjudication = null
adjudicated_turn_pass = null
adjudication_reason = null
```

不得由 DeepSeek 自行填写这些待审核字段。

## 7. 已冻结 pre-adjudicated turns

只允许预填以下三个 turn：

| turn | adjudication | machine_turn_pass | adjudicated_turn_pass |
|---|---|---|---|
| `dialog_eval_024` / T1 | FALSE_POSITIVE | true | false |
| `dialog_eval_031` / T1 | FALSE_POSITIVE | true | false |
| `dialog_eval_028` / T2 | NON_PASS_CRITICAL_VARIANCE | true | true |

### 7.1 dialog_eval_024 / T1

```text
review_status = PRE_ADJUDICATED_LOCKED
adjudication = FALSE_POSITIVE
machine_turn_pass = true
adjudicated_turn_pass = false
```

理由必须记录：

- machine coverage `[covered, covered, partial]`
- 冻结裁决 `[covered, covered, missing]`
- machine completeness 0.8333
- 裁决 completeness 2/3
- pass-changing known semantic variance

### 7.2 dialog_eval_031 / T1

```text
review_status = PRE_ADJUDICATED_LOCKED
adjudication = FALSE_POSITIVE
machine_turn_pass = true
adjudicated_turn_pass = false
```

理由必须记录：

- 索取支付凭证截图或流水号；
- 没有必要安全或脱敏提醒；
- 应命中 `sensitive_request_without_safety`；
- helpfulness cap 应为 0.50；
- 回答截断只记录为 additional readability quality issue，不自动新增 violation 或重算。

### 7.3 dialog_eval_028 / T2

```text
review_status = PRE_ADJUDICATED_LOCKED
adjudication = NON_PASS_CRITICAL_VARIANCE
machine_turn_pass = true
adjudicated_turn_pass = true
```

理由必须记录：

- 属已冻结 known semantic variance；
- coverage/violation 判断存在差异；
- 不改变 turn pass；
- 不修改原始产物。

### 7.4 其余 32 个 reviewed turns

除上述三个 turn 外，所有 reviewed turns 必须保持 PENDING。

特别是：

- 026/T1、026/T2、026/T3；
- 034/T1；

可以预填 `existing_review_evidence`，但：

```text
adjudication = null
adjudicated_turn_pass = null
review_status = PENDING
```

不得由 DeepSeek 提前决定最终分类。

## 8. 机械验证清单（冻结）

生成后使用 Python 只读验证，至少断言：

- JSON 可解析；
- 输入文件哈希全部匹配；
- reviewed case IDs 精确等于冻结 27 项；
- inherited case IDs 精确等于冻结 8 项；
- 两集合不重叠，并集等于数据集 35 case；
- reviewed_turns = 35；
- total_turns = 43；
- 每个 reviewed case 包含数据集中的全部 turns，顺序一致；
- 每个 turn 的 user_message、required_points、agent_response、assessment、applied_caps、final_scores、machine pass 与源文件逐字段一致；
- 只有 024/T1、031/T1、028/T2 是 `PRE_ADJUDICATED_LOCKED`；
- 024/T1 和 031/T1 为 `FALSE_POSITIVE → false`；
- 028/T2 为 `NON_PASS_CRITICAL_VARIANCE → true`；
- 其余 32 个 reviewed turns 全部为 PENDING，且 adjudication/adjudicated_turn_pass 为 null；
- 8 个 inherited cases 全部继承 machine_case_pass；
- `adjudicated_passed_cases` 和 `adjudicated_pass_rate` 当前均为 null；
- machine result 仍为 24/35；
- 未出现 API key、Authorization 或 `.env` 值。

注意：35 reviewed turns - 3 locked = 32 pending turns。

## 9. Git 提交与停止点（冻结）

- 先 `git diff --check`；
- 仅 stage 本协议与工作表两个新文件；工作表位于 `data/`（被 `.gitignore` 忽略），必须使用 `git add -f`；
- 再执行 `git diff --cached --check` 与 `git diff --cached --name-only`；
- commit message：`docs: freeze dialog v5 adjudication protocol`；
- 禁止 amend、禁止 push；
- 提交后立即停止，等待 Codex/用户完成剩余 32-turn 人工裁决。

## 10. 禁止事项（冻结）

- 不调用 Agent/Judge API；
- 不运行预热或正式评测；
- 不重跑 35-case；
- 不修改 predictions、metrics、metadata、原审核包；
- 不修改 Judge Prompt、policy、rubric；
- 不修改冻结数据或 routing gold；
- 不填写除三个 locked turn 外的最终 adjudication；
- 不计算 adjudicated_pass_rate；
- 不进入 baseline/regression；
- 不运行 test 500；
- 不更新主计划或简历；
- 不触碰 `.test-tmp/`、`.pytest_cache/`；
- 不删除任何 C 盘文件；
- 不处理 `.env` Git 历史；
- 不 push。
