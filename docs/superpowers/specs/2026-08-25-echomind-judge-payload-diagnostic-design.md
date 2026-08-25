# EchoMind Judge Payload 两案例诊断设计

日期：2026-08-25  
状态：设计已批准，等待执行

## 1. 背景

正式候选运行 `data/eval/runs/dialog-eval-v2` 完成 35 case、43 turn，但 `dialog_eval_018` 和 `dialog_eval_031` 在 Judge 三次尝试后均以 `judge payload fields do not match schema` 失败。当前持久化错误只说明字段集合不等于固定 Schema，没有保存缺失字段、额外字段或字段类型，因此无法判断根因。

该运行只有 33 个有效 Judge case，不能发布，也不能据此冻结 baseline。

## 2. 目标

使用已落盘的两条 Agent 回答重新调用 Judge，每个 case 最多 3 次，仅记录安全的结构诊断信息：

- payload 是否为对象；
- 字段名称；
- 每个字段的值类型；
- 缺失字段；
- 额外字段；
- 现有 `validate_judge_payload` 的验证结果或脱敏错误；
- API/提取错误与调用耗时。

诊断结果用于区分字段缺失、字段冗余、类型错误和偶发服务异常，不在本阶段实施修复。

## 3. 数据与调用边界

- Agent 回答只读取 `dialog-eval-v2/dialog_predictions.jsonl`，不得重新调用 Agent；
- 受控上下文、参考答案和必答点只读取冻结的 `dialog_eval_v2.json`；
- 只诊断 `dialog_eval_018`、`dialog_eval_031`；
- 每个 case 固定 3 次，最多 6 次 Judge API 调用；
- 使用当前 `dialog_judge_v3`、同一 Judge 模型、temperature 0、tool choice 和 thinking-disabled 配置；
- 输出到新的 `data/eval/runs/dialog-judge-payload-diagnostic-v3`；
- 不覆盖、续跑或修改任何历史目录。

## 4. 安全与可审计性

诊断结果不得保存：

- API Key、Authorization header 或环境变量；
- tool payload 的字段值；
- Judge reasoning 正文；
- Agent 回答、上下文或用户问题的副本。

允许保存 case ID、attempt、字段名、字段类型、missing/unexpected 集合、验证状态、脱敏错误、延迟、模型名、Prompt 版本以及源文件 SHA-256。

字段名称也必须通过字符串化和长度限制后写入，避免兼容端把任意长内容放进 key。

## 5. 解释规则

诊断完成后按以下规则分类：

1. 出现 `unexpected_fields`：确认兼容端没有遵守 `additionalProperties=false`；在看到具体字段前不决定是否容忍；
2. 出现 `missing_fields`：确认模型/兼容端没有完成必需字段；不得补默认分数；
3. 字段集合正确但类型或取值验证失败：针对具体类型/范围继续分析；
4. 六次全部有效：说明原失败具有间歇性，本轮不能证明固定 payload 形状缺陷；不得据此放宽验证器；
5. API 或 tool payload 提取失败：作为独立外部调用问题保留，不与字段 Schema 问题混为一谈。

## 6. 停止条件

完成最多 6 次诊断并保存证据后立即停止。不得在同一执行中：

- 修改 `evaluation/dialog_judge.py`；
- 修改 Judge Prompt 或版本；
- 放宽字段验证；
- 重跑 35-case；
- 创建新的正式结果目录；
- 更新简历指标或 baseline。

下一项修复必须基于本诊断的实际字段证据另行设计和批准。
