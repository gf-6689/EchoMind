# EchoMind Judge Payload 精确模型重诊断设计

日期：2026-08-25  
状态：设计已批准，等待执行

## 1. 背景

首次两案例结构诊断保存在 `data/eval/runs/dialog-judge-payload-diagnostic-v3`。它实际使用的模型标识为 `deepseek-v4-pro[1m]`，而正式失败运行 `dialog-eval-v2/run_metadata.json` 记录的 Judge 模型为 `deepseek-v4-pro`。两者不相等，因此首次诊断得到的 5 次空字典和 1 次有效 payload 只能描述错误模型标识下的行为，不能作为正式故障的严格根因证据。

首次诊断目录继续保留，不覆盖、不删除。本重诊断只修正模型来源这一变量。

## 2. 目标

重新诊断 `dialog_eval_018` 和 `dialog_eval_031`，并强制满足：

- Judge 模型直接读取 `dialog-eval-v2/run_metadata.json` 的 `judge_model`；
- 模型值必须严格等于 `deepseek-v4-pro`；
- 当前 `PROMPT_VERSION` 必须与正式元数据的 `dialog_judge_v3` 一致；
- 不使用 `EVAL_JUDGE_MODEL` 或 `ANTHROPIC_MODEL` 决定模型；
- 每个 case 3 次，共 6 次 Judge API 调用；
- 只保存 bounded payload 结构，不保存字段值或评测文本。

## 3. 输出边界

新目录固定为：

```text
data/eval/runs/dialog-judge-payload-diagnostic-v3-retry1
```

保存：

- `run_diagnostic.py`；
- `diagnostic_results.json`。

结果额外记录：

- `model_source`；
- 正式元数据 SHA-256；
- 正式 `git_revision`；
- 数据集与 predictions SHA-256。

## 4. 安全与非目标

继续遵守首次诊断的安全边界：不调用 Agent，不修改生产代码/测试/数据，不保存 payload 值、reasoning、问题、回答、上下文、密钥或 header。

本次不实施解析器修复、不增加默认分数、不更改 Prompt、不重跑 35-case、不更新 baseline 或简历。

## 5. 解释规则

只有本次 exact-model 结果可以用于下一步正式修复设计：

1. 若出现 `input={}`，则确认正式模型路径可以复现必填字段全部缺失；
2. 若出现其他 missing/unexpected/type 模式，按实际结构单独分析；
3. 若六次全部有效，说明本轮未复现，但不能抹除正式运行已发生的三次失败；
4. 首次错误模型诊断只作为对照，不与本次样本合并计算失败率；
5. 无论结果如何，完成 6 次后停止，等待 Codex 审核。
