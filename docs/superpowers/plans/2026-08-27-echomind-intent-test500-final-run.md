# EchoMind Frozen Intent Test 500 Final Run Plan

日期：2026-08-27
适用 worktree：`E:\Desktop\简历项目\EchoMind所有代码+简历\EchoMind\.worktrees\task6-dialog-eval`
适用分支：`task6-dialog-eval`
性质：最终运行计划。本计划只冻结正式运行口径，不运行任何测试、smoke、API 调用或正式评测。

```text
Status: pending review (Codex)
Scope: frozen intent test 500, four-mode formal evaluation, one-shot only
```

## 1. 目标与边界

1. `intent_test_500.jsonl` 是**最终一次性正式评测集**。本次是它的唯一正式运行；任何模式或参数都不得依据 test 500 结果继续调整。
2. 四种模式 `pattern_only` / `embedding_only` / `llm_only` / `fusion` 必须使用**同一份**冻结 test 500。
3. 正式配置**继承 dev 190 已冻结的最终配置**（§4），不得根据 test 500 重新选择。
4. 结果只是**候选正式指标**：执行方不得直接写入简历、主计划或 baseline；必须等待 Codex/用户审核。
5. 本阶段不实现统一 CLI、不修改 `evaluation/regression.py`、不更新主计划和简历、不创建意图 baseline。

## 2. 冻结输入身份（执行前必须机械复验）

| 文件 | 冻结值 |
|---|---|
| `E:\Desktop\简历项目\EchoMind_data\data\eval\intent_test_500.jsonl` | rows=500；labels=19；SHA-256 `24061ae0ee4caa50b573581a8f3ce15c2b331ed7165f46491d4e18376defc0c7`；`dataset_manifest.json` 中 `freeze_status=frozen`；normalized dev/test exact overlap=0 |
| `E:\Desktop\简历项目\EchoMind_data\data\eval\intent_dev.jsonl` | rows=190；SHA-256 `814578dd7c766b873d4730d801cbfdce62bde83a35361005459d93a3ca9a9cbb`（仅用于 dev smoke） |
| 19 类标签 | `query, complaint, request, greeting, escalation, technical, billing, account, feedback, order_status, logistics, refund, invoice, payment_issue, account_security, technical_login, technical_crash, human_handoff, other`（顺序与 `evaluation/intent_metrics.py` 的 `INTENT_LABELS` 一致） |

执行前用以下检查机械复验（退出非零即停止）：

```text
sha256sum <intent_test_500.jsonl> <intent_dev.jsonl>
python -X utf8 -c "验证：test 500 行；gold 唯一标签 19 且均在冻结 19 类；id 无重复；
每条含 id/message/gold_intent；normalized exact overlap(dev,test)==0；
manifest freeze_status=='frozen'"
```

## 3. 执行起点硬门（全部通过才允许继续）

1. worktree HEAD == `4bda2178a0a94c8c28d216b725fad61d4c0a4751`，branch == `task6-dialog-eval`；
2. `git status --short --untracked-files=no` 为空（tracked 树与索引洁净）；两个既有未跟踪 docs 文件保持未触碰、未 stage；
3. 专用 pytest basetemp 不存在：`E:\Desktop\简历项目\echomind-intent-test500-pytest-temp`（已存在则**停止**，不得删除或复用）；
4. §6/§8 的全部 10 个输出目录均不存在（已存在则**停止**）；
5. Task 7 baseline 不变式（执行前后各验证一次）：
   - `data/eval/baseline.json` SHA-256 == `646de6e35aa898e60d653b3179f937627b28a31aef37de7609b9eedb6e2c44f3`
   - `data/eval/runs/dialog-v5-baseline-self-check-20260827.json` SHA-256 == `3cb0e9f89b0975ea1e7d8a6d9b1dbd9bcb2ad11913437beb1d4d16d7abe8a2ec`
   - 本阶段不得覆盖、更新或新增 baseline 文件；
6. 执行期间不得修改任何 tracked 文件；不新增代码；不触碰 `.test-tmp/`、`.pytest_cache/`、历史评测目录、C 盘文件。

## 4. 最终配置（从代码 + dev 证据 + 主计划恢复，三者一致，禁止手填或再调）

| 配置项 | 冻结值 | 来源 |
|---|---|---|
| LLM 模型 | `deepseek-v4-pro`（本阶段冻结；正式命令显式 `--model` 传入，不依赖 `.env`） | 阶段指令；对话正式运行同模型 |
| Fusion 权重 | LLM/Embedding/Pattern = `0.7 / 0.2 / 0.1` | `core/intent_recognizer.py` `_vote`（硬编码）；主计划 §dev 190 实测结果 |
| confidence threshold | `0.5`（`_single_source` 与 fusion 共用；低于阈值降级 `other`） | `core/intent_recognizer.py` 构造默认值；运行 CLI 无覆写路径 |
| 共识细化规则 | 仅当 `best∈GENERIC` 且 `llm∈GENERIC` 且 `llm_conf<0.8` 且 `emb==pat∈SPECIFIC` 且 `emb_conf>=0.65` 且 `pat_conf>=0.75` 时采用 pattern 意图（`refined_by_consensus`） | `core/intent_recognizer.py` `_vote`；主计划"保守规则"原文一致 |
| Pattern 分支 | specific 优先、generic 兜底；score=`min(1.0, 0.5+0.25*(hits-1))` | `core/intent_recognizer.py` `_pattern_recognize` |
| Embedding 分支 | `BAAI/bge-small-zh-v1.5`（sentence-transformers 6.0.0）；模板 19 类×3 条余弦相似度；`normalize_embeddings=True`；懒加载；缓存目录 `data/models/` | `core/intent_recognizer.py`；主计划 §Task 3 |
| LLM 分支 | `temperature=0.0`、`max_tokens=512`、forced tool `classify_intent`、thinking disabled、timeout 30s、最多 3 次（0.5s/1.0s 退避）、每类 1 条 few-shot、非法意图→`other`、confidence 截断 [0,1] | `core/intent_recognizer.py` `_llm_recognize` |
| 失败降级 | 单路 failed→`other`/0.0；fusion LLM failed→按 emb→pat 顺序兜底；行级异常记入 `error`/`source_errors` | `core/intent_recognizer.py`；`evaluation/run_intent_eval.py` |

dev 交叉证据：最终 dev 运行 `data/eval/runs/dev-fusion-bge-conservative-190/`（180/190，Accuracy 94.74%，Macro-F1 94.35%；行错误 0、来源错误 0、预测含 `source_intents`；`error_analysis.md` §3 记录本轮未触发 `refined_by_consensus`）。dev 四模式参考值：pattern 30.53%/34.01%、embedding(BGE) 47.89%/46.90%、llm 93.68%/93.07%、fusion 94.74%/94.35%（仅为 dev 调参证据，不参与正式口径）。

如执行时发现代码、dev 产物或主计划任何记录与本表冲突：**立即停止并报告，禁止自行猜测**。

## 5. Preflight 与最小定向测试

依次执行，任何一步非零退出即停止：

```text
cd <worktree 根目录>
E:\conda_envs\echomind\python.exe -m compileall -q evaluation core tests
E:\conda_envs\echomind\python.exe -m evaluation.run_intent_eval --help   (exit 0，无 API、无文件写入)
E:\conda_envs\echomind\python.exe -m pytest -q -p no:cacheprovider --basetemp "E:\Desktop\简历项目\echomind-intent-test500-pytest-temp" tests/evaluation/test_intent_metrics.py tests/evaluation/test_regression.py -k "not bge_encoder_is_loaded_once and not output_directory"
```

说明：

- `-k` 排除使用 `workspace_tmp_path` fixture 的 3 个测试（该 fixture 会在 cwd 创建 `.test-tmp/`，本阶段禁止触碰）；
- 定向测试只允许上述两文件命令；不得运行完整测试套件；
- pytest 只用冻结的 E 盘 basetemp；`-p no:cacheprovider` 禁止生成 `.pytest_cache/`；
- `test_regression.py` 用于守护 Task 7 不变式（不触碰 `.test-tmp/`，仅用 tmp_path+basetemp）。

## 6. dev smoke（仅 llm_only 与 fusion；只允许 dev 数据）

样本数均为 20（`--limit 20`，取 dev 前 20 条）；**禁止**用 test 500 前 20 条调试；smoke 不计入正式指标。

| Smoke | 输出目录（全新，互不覆盖） |
|---|---|
| llm_only | `E:\Desktop\简历项目\EchoMind_data\data\eval\runs\intent-dev-smoke-llm-20260827` |
| fusion | `E:\Desktop\简历项目\EchoMind_data\data\eval\runs\intent-dev-smoke-fusion-20260827` |

命令（cd 到 worktree 根目录）：

```text
E:\conda_envs\echomind\python.exe -X utf8 -m evaluation.run_intent_eval --intent-data "E:\Desktop\简历项目\EchoMind_data\data\eval\intent_dev.jsonl" --output-dir "E:\Desktop\简历项目\EchoMind_data\data\eval\runs\intent-dev-smoke-llm-20260827" --mode llm_only --model deepseek-v4-pro --limit 20

E:\conda_envs\echomind\python.exe -X utf8 -m evaluation.run_intent_eval --intent-data "E:\Desktop\简历项目\EchoMind_data\data\eval\intent_dev.jsonl" --output-dir "E:\Desktop\简历项目\EchoMind_data\data\eval\runs\intent-dev-smoke-fusion-20260827" --mode fusion --model deepseek-v4-pro --limit 20
```

每个 smoke 的成功门：

- 退出码 0；`intent_predictions.jsonl` 恰 20 行，id 与 dev 前 20 条顺序一致；
- 行级 `error != null` 数量 == 0（执行失败门）；
- `source_errors` 非空行数 == 0（**Agent/API failure 门**）；
- `intent_metrics.json` 可解析，`total==20`、`labels` 为冻结 19 类同序。

任一 smoke 失败 → 保留目录、立即停止、禁止删除后重跑，报告等待批准。

## 7. 四模式正式运行（同一份 test 500）

顺序：`pattern_only` → `embedding_only` → `llm_only` → `fusion`（前两者零 API，先验证管线与本地分支）。每模式使用全新目录，执行前已断言全部不存在。

| 模式 | 输出目录 |
|---|---|
| pattern_only | `E:\Desktop\简历项目\EchoMind_data\data\eval\runs\intent-test500-pattern-only-20260827` |
| embedding_only | `E:\Desktop\简历项目\EchoMind_data\data\eval\runs\intent-test500-embedding-only-20260827` |
| llm_only | `E:\Desktop\简历项目\EchoMind_data\data\eval\runs\intent-test500-llm-only-20260827` |
| fusion | `E:\Desktop\简历项目\EchoMind_data\data\eval\runs\intent-test500-fusion-20260827` |

命令模板（cd 到 worktree 根目录；llm_only/fusion 必须显式 `--model deepseek-v4-pro`；不传 `--api-key`，密钥仅经根目录 `.env` 读取，绝不打印或记录密钥/Authorization/环境变量值）：

```text
E:\conda_envs\echomind\python.exe -X utf8 -m evaluation.run_intent_eval --intent-data "E:\Desktop\简历项目\EchoMind_data\data\eval\intent_test_500.jsonl" --output-dir "<§7 表中目录>" --mode <mode> [--model deepseek-v4-pro]
```

每模式成功门（全部满足才算成功）：

- 退出码 0；
- `intent_predictions.jsonl` 恰 500 行；id 序列与 test 500 完全一致（同序、无缺失/重复/额外）；`gold_intent` 与 test 逐条一致；`predicted_intent` ∈ 冻结 19 类；
- 行级错误 0；`source_errors` 非空 0（llm_only/fusion 特别核对：任何 LLM/API 失败即失败）；
- `intent_metrics.json`：`total==500`、`labels` 冻结 19 类同序、`per_class` 19 项、`confusion_matrix` 19×19、`latency.count==500`（含 Mean/P50/P95）；
- 运行后由执行方在该目录**新增** `run_metadata.json`（不覆盖任何已有文件），内容至少含：`timestamp`（UTC）、`git_revision`（worktree HEAD）、`dataset_path`、`dataset_sha256`、`dataset_rows=500`、`labels`（冻结 19 类同序）、`model`（pattern/embedding 记 `null`）、`mode`、`temperature=0.0`、`embedding_model`（embedding/fusion）、`confidence_threshold=0.5`、`fusion_weights={"llm":0.7,"embedding":0.2,"pattern":0.1}`（仅 fusion）、`product_sha256`（两产物实际哈希）、`row_error_count=0`、`source_error_count=0`、`candidate_only=true`。

## 8. 保存预测重算（逐字段一致门）

每个模式用 `--predictions` 对已保存 predictions 重算，输出到**独立新目录**（CLI 拒绝写入非空目录，故绝不指向原运行目录）：

| 重算目录（全新） |
|---|
| `E:\Desktop\简历项目\EchoMind_data\data\eval\runs\intent-test500-pattern-only-recompute-20260827` |
| `E:\Desktop\简历项目\EchoMind_data\data\eval\runs\intent-test500-embedding-only-recompute-20260827` |
| `E:\Desktop\简历项目\EchoMind_data\data\eval\runs\intent-test500-llm-only-recompute-20260827` |
| `E:\Desktop\简历项目\EchoMind_data\data\eval\runs\intent-test500-fusion-recompute-20260827` |

```text
E:\conda_envs\echomind\python.exe -X utf8 -m evaluation.run_intent_eval --predictions "<模式目录>\intent_predictions.jsonl" --output-dir "<对应 recompute 目录>"
```

成功门：退出码 0；重算 `intent_metrics.json` 与原模式 `intent_metrics.json` **逐字段一致**（accuracy、macro_f1、per_class、confusion_matrix、labels、total、correct、latency 全部相等）。

## 9. 四模式一致性与终验（全部通过才允许进入报告阶段）

对四个正式模式目录机械验证：

- 四个 predictions 的 id 序列完全一致（同一 500 个 case_id、同序）；
- `gold_intent` 序列四模式逐条一致；
- 19 类 label 顺序一致；无缺失、重复或额外 prediction；
- 重算已通过（§8）；
- 输入终验：`intent_test_500.jsonl`、`intent_dev.jsonl` 哈希仍等于 §2 冻结值；Task 7 baseline 两文件哈希仍等于 §3 冻结值；dev 190 历史运行目录与文件哈希未被改动。

## 10. API 调用量与耗时估算

| 项目 | 计划调用量 | 失败上界（每次最多 3 次尝试） |
|---|---:|---:|
| dev smoke llm_only 20 | 20 | 60 |
| dev smoke fusion 20 | 20 | 60 |
| 正式 llm_only 500 | 500 | 1500 |
| 正式 fusion 500 | 500 | 1500 |
| pattern / embedding | 0 | 0 |
| 合计 | 1040 | 3120 |

耗时估算（顺序执行；依据 dev 190 实测：llm_only mean 1733 ms/条、fusion mean 2172 ms/条，含首条冷启动）：

```text
pattern 500        < 1 分钟
embedding 500      约 2–5 分钟（BGE 冷启动约 25 s）
smoke 2×20         约 2–4 分钟
llm_only 500       约 15–25 分钟
fusion 500         约 20–30 分钟
重算 + 终验        约 5–10 分钟
总耗时估算         约 45–75 分钟
```

失败影响：重试上界见上表；任何失败都只保留现场并停止，不产生额外调用。

## 11. 失败与停止条件

任一以下情况立即停止，保留目录与全部产物，禁止删除后重跑、禁止覆盖/append/resume，未经用户批准不得重新执行：

- §2/§3/§5 任何前置硬门或定向测试失败；
- 任何 smoke 或正式模式退出码非零；
- 任何 smoke 或正式模式的 §6/§7 成功门未满足（含 API/LLM failure 门）；
- 重算不一致、四模式一致性验证失败；
- 任一冻结输入哈希发生变化。

## 12. 结果发布边界

- test 500 结果仅是候选正式指标；执行方不得写入主计划、简历、wiki 或任何 baseline；
- 意图 baseline 的创建不在本计划范围（主计划 Phase 6 另行处理）；
- 报告按四模式给出 Accuracy、固定 19 类 Macro-F1、Per-class P/R/F1/support、Confusion Matrix、Mean/P50/P95、错误统计与来源统计，全部指向 §7 原始产物。

## 13. 禁止事项

- 不依据 test 500 结果调参、改 Prompt/规则/权重/标签；不用 test 500 任何子集做调试；
- 不调用与本次正式运行无关的 API；不打印密钥；
- 不修改代码、测试、冻结数据、历史评测目录、Task 7 baseline、主计划、简历；
- 不触碰 `.test-tmp/`、`.pytest_cache/`、两个既有未跟踪 docs 文件；不删除 C 盘文件；
- 不 `git add .` / `git add -A`、不 amend、不 push（本阶段只读运行，产物在仓库外数据目录）。

## 14. 停止点

四个正式模式 + 重算 + 一致性终验完成后停止：不创建意图 baseline、不更新主计划/简历，等待 Codex 审核候选指标与原始产物。
