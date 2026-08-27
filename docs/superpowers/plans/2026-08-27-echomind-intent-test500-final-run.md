# EchoMind Frozen Intent Test 500 Final Run Plan

日期：2026-08-27（本版为可执行性修订：双 revision 规则、dev 证据真实绝对路径与冻结哈希、可直接执行的身份验证与 metadata 独占创建命令）
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

## 2. 冻结输入身份与可直接执行的身份验证命令

| 文件 | 冻结值 |
|---|---|
| `E:\Desktop\简历项目\EchoMind_data\data\eval\intent_test_500.jsonl` | rows=500；labels=19；SHA-256 `24061ae0ee4caa50b573581a8f3ce15c2b331ed7165f46491d4e18376defc0c7`；`dataset_manifest.json` 中 `test.freeze_status=frozen`；normalized dev/test exact overlap=0 |
| `E:\Desktop\简历项目\EchoMind_data\data\eval\intent_dev.jsonl` | rows=190；SHA-256 `814578dd7c766b873d4730d801cbfdce62bde83a35361005459d93a3ca9a9cbb`（仅用于 dev smoke） |
| 19 类标签 | `query, complaint, request, greeting, escalation, technical, billing, account, feedback, order_status, logistics, refund, invoice, payment_issue, account_security, technical_login, technical_crash, human_handoff, other`（顺序与 `evaluation/intent_metrics.py` 的 `INTENT_LABELS` 一致） |

**以下命令直接执行（PowerShell；路径经环境变量传入，Python 正文保持 ASCII；只读，不写任何文件；不打印 `.env`/API key/Authorization）。退出码非 0 即停止：**

```powershell
$env:EI_TEST     = 'E:\Desktop\简历项目\EchoMind_data\data\eval\intent_test_500.jsonl'
$env:EI_DEV      = 'E:\Desktop\简历项目\EchoMind_data\data\eval\intent_dev.jsonl'
$env:EI_MANIFEST = 'E:\Desktop\简历项目\EchoMind_data\data\eval\dataset_manifest.json'
$py = @'
import hashlib
import json
import os
import re
from collections import Counter

TEST_SHA = "24061ae0ee4caa50b573581a8f3ce15c2b331ed7165f46491d4e18376defc0c7"
DEV_SHA = "814578dd7c766b873d4730d801cbfdce62bde83a35361005459d93a3ca9a9cbb"
LABELS = ["query","complaint","request","greeting","escalation","technical","billing",
          "account","feedback","order_status","logistics","refund","invoice","payment_issue",
          "account_security","technical_login","technical_crash","human_handoff","other"]
FILLERS = ["\u8bf7\u95ee", "\u9ebb\u70e6", "\u5e2e\u6211", "\u5e2e\u5fd9", "\u60f3\u95ee\u4e00\u4e0b", "\u60f3\u95ee\u4e0b", "\u6211\u60f3\u95ee", "\u6211\u60f3\u786e\u8ba4", "\u6211\u4e3b\u8981\u60f3\u786e\u8ba4", "\u6211\u8fd9\u8fb9", "\u6211\u6709\u70b9\u641e\u4e0d\u61c2", "\u6211\u8fd9\u8fb9\u6709\u70b9\u61f5", "\u6362\u4e2a\u8bf4\u6cd5", "\u5177\u4f53\u60f3\u4e86\u89e3\u7684\u662f", "\u5173\u4e8e\u8fd9\u4e2a\u60c5\u51b5", "\u8c22\u8c22", "\u611f\u8c22", "\u60a8\u597d", "\u4f60\u597d", "\u5ba2\u670d", "\u4e00\u4e0b", "\u8bf7\u5e2e\u6211", "\u80fd\u4e0d\u80fd", "\u53ef\u4ee5", "please", "pls", "help", "check", "\u5728\u7ebf\u7b49", "\u60f3\u54a8\u8be2\u4e00\u4e0b", "\u60f3\u4e86\u89e3", "\u80fd\u89e3\u91ca\u4e0b\u5417", "\u6709\u4e2a\u95ee\u9898", "\u6253\u6270\u4e00\u4e0b"]
TAILS = ["\u600e\u4e48\u529e", "\u600e\u4e48\u5904\u7406", "\u600e\u4e48\u5f04", "\u548b\u529e", "\u548b\u6574", "\u600e\u4e48\u641e", "\u8be5\u600e\u4e48\u529e", "\u80fd\u786e\u8ba4\u5417", "\u9ebb\u70e6\u8bf4\u660e"]

def sha256_of(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()

def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            assert line.strip(), "blank line not allowed: %s:%d" % (path, line_number)
            rows.append(json.loads(line))
    return rows

def normalize(text):
    text = text.lower()
    for filler in sorted(FILLERS, key=len, reverse=True):
        text = text.replace(filler, "")
    text = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
    for tail in TAILS:
        text = text.replace(tail, "")
    return text

test_path = os.environ["EI_TEST"]
dev_path = os.environ["EI_DEV"]
manifest_path = os.environ["EI_MANIFEST"]

test = load_jsonl(test_path)
dev = load_jsonl(dev_path)
manifest = json.load(open(manifest_path, "r", encoding="utf-8"))

assert sha256_of(test_path) == TEST_SHA, "test sha256 mismatch"
assert sha256_of(dev_path) == DEV_SHA, "dev sha256 mismatch"
assert len(test) == 500, "test rows != 500"
assert len(dev) == 190, "dev rows != 190"
assert len(set(row["id"] for row in test)) == 500, "test ids not unique"
for row in test:
    assert set(("id", "message", "gold_intent")) <= set(row), "test row missing required field"
    assert row.get("message", "").strip(), "test row has empty message"
gold = set(row["gold_intent"] for row in test)
assert gold == set(LABELS), "gold labels must cover exactly the frozen 19 labels, no extras"

mt = manifest["test"]
assert mt["rows"] == 500, "manifest test.rows != 500"
assert mt["sha256"] == TEST_SHA, "manifest test.sha256 mismatch"
assert mt["freeze_status"] == "frozen", "manifest freeze_status != frozen"
assert mt["normalized_exact_overlap_with_dev"] == 0, "manifest normalized overlap != 0"
dev_norm = set(normalize(row["message"]) for row in dev)
test_norm = [normalize(row["message"]) for row in test]
assert len(test_norm) == len(set(test_norm)), "normalized duplicate inside test"
assert not (dev_norm & set(test_norm)), "independently recomputed normalized dev/test overlap != 0"
actual_counts = dict(Counter(row["gold_intent"] for row in test))
assert actual_counts == mt["class_counts"], "manifest class_counts does not match test file"
print("[OK] test/dev sha256 exact; test 500 rows; dev 190 rows; test ids unique")
print("[OK] required fields; gold == frozen 19 labels exactly")
print("[OK] manifest rows/sha256/freeze_status/overlap; independent overlap == 0; class_counts match")
'@
& 'E:\conda_envs\echomind\python.exe' -X utf8 -c $py
if ($LASTEXITCODE -ne 0) { Write-Error 'intent identity verification FAILED'; exit $LASTEXITCODE }
Write-Output 'intent identity verification PASSED'
```

## 3. 双 revision 规则与执行起点硬门（全部通过才允许继续）

**双 revision：**

```text
code_revision    = 4bda2178a0a94c8c28d216b725fad61d4c0a4751
                   （Task 7 代码、测试、baseline 与 self-check 完成后的代码 revision，固定不变）
execution_revision = Codex 在正式执行命令中明确指定的起始 HEAD（本计划不硬编码）
```

**执行前验证（在 worktree 中执行；任一不满足即停止）：**

```text
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' -C 'E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' rev-parse HEAD
    → 输出必须与 Codex 执行命令指定的 execution_revision 完全一致
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' -C 'E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' merge-base --is-ancestor 4bda2178a0a94c8c28d216b725fad61d4c0a4751 HEAD
    → exit 0（code_revision 必须是当前 HEAD 的祖先）
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' -C 'E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' diff --name-only 4bda2178a0a94c8c28d216b725fad61d4c0a4751 HEAD
    → 输出仅允许为空，或只含 docs/superpowers/plans/2026-08-27-echomind-intent-test500-final-run.md；出现任何其他文件即停止
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' -C 'E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' status --short --untracked-files=no
    → 必须为空（tracked 树与索引洁净）
```

其余硬门：

1. 专用 pytest basetemp 不存在：`E:\Desktop\简历项目\echomind-intent-test500-pytest-temp`（已存在则**停止**，不得删除或复用）；
2. §6/§8 的全部 10 个输出目录均不存在（已存在则**停止**）；
3. Task 7 baseline 不变式（执行前后各验证一次）：
   - `data/eval/baseline.json` SHA-256 == `646de6e35aa898e60d653b3179f937627b28a31aef37de7609b9eedb6e2c44f3`
   - `data/eval/runs/dialog-v5-baseline-self-check-20260827.json` SHA-256 == `3cb0e9f89b0975ea1e7d8a6d9b1dbd9bcb2ad11913437beb1d4d16d7abe8a2ec`
   - 本阶段不得覆盖、更新或新增 baseline 文件；
4. 执行期间不得修改任何 tracked 文件；不新增代码；两个既有未跟踪 docs 文件保持未触碰、未 stage；不触碰 `.test-tmp/`、`.pytest_cache/`、历史评测目录、C 盘文件。

`run_metadata.json` 必须同时记录 `code_revision`（恒为上述常量）与 `execution_revision`（正式执行时的当前 HEAD），见 §7.1。

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

dev 交叉证据（真实绝对路径，主仓库目录，非 worktree）：

```text
E:\Desktop\简历项目\EchoMind所有代码+简历\EchoMind\data\eval\runs\dev-fusion-bge-conservative-190\
```

最终 dev 运行结果：180/190、Accuracy 94.74%、Macro-F1 94.35%；行错误 0、来源错误 0、预测含 `source_intents`；其 `error_analysis.md` §3 记录本轮未触发 `refined_by_consensus`。

**该目录三个文件冻结 SHA-256（执行前与全部结束后必须复核不变）：**

| 文件（绝对路径前缀同上目录） | SHA-256 |
|---|---|
| `intent_predictions.jsonl` | `43f725734986ce8b2a531aae35007b920012a52cf3ea4cba2c4f66209f9ad091` |
| `intent_metrics.json` | `fc80442cfc1eca7fc900f23ce8813913f947a13c6e8e33b004a5c5a843941cc4` |
| `error_analysis.md` | `3400dbf05df7c31869d680c9c4273452078a306aa8d6cbc183d8b6c82543bd7e` |

dev 四模式参考值（仅为 dev 调参证据，不参与正式口径；目录均为主仓库真实绝对路径 `E:\Desktop\简历项目\EchoMind所有代码+简历\EchoMind\data\eval\runs\` 下）：

| Mode | Accuracy | Macro-F1 | 目录 |
|---|---:|---:|---|
| `pattern_only` | 30.53% | 34.01% | `dev-pattern-190` |
| `embedding_only`（BGE） | 47.89% | 46.90% | `dev-bge-190` |
| `llm_only` | 93.68% | 93.07% | `dev-llm-190` |
| `fusion` | 94.74% | 94.35% | `dev-fusion-bge-conservative-190` |

如执行时发现代码、dev 产物或主计划任何记录与本表冲突：**立即停止并报告，禁止自行猜测**。

## 5. Preflight 与最小定向测试

在 §3 硬门通过后依次执行，任何一步非零退出即停止：

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
- 全部成功门通过后，用 §7.1 的命令在该目录**独占创建** `run_metadata.json` 并通过脚本自带的逐字段复核。

## 7.1 run_metadata.json：schema 冻结 + 独占创建命令

固定顶层字段（顺序即写入顺序）：

```text
schema_version       = "intent_test500_run_metadata_v1"
created_at           = UTC ISO 8601（Z 结尾）
candidate_only       = true
code_revision        = 4bda2178a0a94c8c28d216b725fad61d4c0a4751（恒定常量）
execution_revision   = 正式执行时当前 HEAD（由 Codex 批准；脚本强制校验 == git rev-parse HEAD）
dataset_path         = 正式 test 500 绝对路径
dataset_sha256       = 该文件实际 SHA-256（现算，禁止手填）
dataset_rows         = 500
labels               = 冻结 19 类同序
mode                 = pattern_only | embedding_only | llm_only | fusion
llm_model            = 按模式映射（见下）
embedding_model      = 按模式映射（见下）
confidence_threshold = 0.5
fusion_weights       = 按模式映射（见下）
predictions_sha256   = intent_predictions.jsonl 实际 SHA-256（现算）
metrics_sha256       = intent_metrics.json 实际 SHA-256（现算）
prediction_rows      = 500
row_error_count      = 0（从预测文件现算并断言为 0）
source_error_count   = 0（从预测文件现算并断言为 0）
```

四模式字段映射：

| mode | llm_model | embedding_model | fusion_weights |
|---|---|---|---|
| pattern_only | null | null | null |
| embedding_only | null | `BAAI/bge-small-zh-v1.5` | null |
| llm_only | `deepseek-v4-pro` | null | null |
| fusion | `deepseek-v4-pro` | `BAAI/bge-small-zh-v1.5` | `{"llm":0.7,"embedding":0.2,"pattern":0.1}` |

revision 规则：`code_revision` 恒为上述常量；`execution_revision` 必须是正式执行开始时的 HEAD；**不得**把正式运行目录创建时间或本计划编写时间冒充 revision。脚本同时校验 `execution_revision == git rev-parse HEAD`，不一致即失败。

生成命令（每个正式模式成功门通过后执行一次；目标存在立即失败，禁止覆盖/append/resume；失败保留现场并立即停止；不读取或记录 API key）：

```powershell
$env:EI_META_OUT      = '<模式目录>\run_metadata.json'
$env:EI_META_MODE     = '<mode: pattern_only | embedding_only | llm_only | fusion>'
$env:EI_META_PRED     = '<模式目录>\intent_predictions.jsonl'
$env:EI_META_METRICS  = '<模式目录>\intent_metrics.json'
$env:EI_META_DATASET  = 'E:\Desktop\简历项目\EchoMind_data\data\eval\intent_test_500.jsonl'
$env:EI_META_EXEC_REV = '<Codex 执行命令指定的 execution_revision>'
$env:EI_META_HEAD     = (git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' -C 'E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' rev-parse HEAD)
$py = @'
import hashlib
import json
import os
from datetime import datetime, timezone

CODE_REVISION = "4bda2178a0a94c8c28d216b725fad61d4c0a4751"
LABELS = ["query","complaint","request","greeting","escalation","technical","billing",
          "account","feedback","order_status","logistics","refund","invoice","payment_issue",
          "account_security","technical_login","technical_crash","human_handoff","other"]

mode = os.environ["EI_META_MODE"]
if mode == "pattern_only":
    llm_model, embedding_model, fusion_weights = None, None, None
elif mode == "embedding_only":
    llm_model, embedding_model, fusion_weights = None, "BAAI/bge-small-zh-v1.5", None
elif mode == "llm_only":
    llm_model, embedding_model, fusion_weights = "deepseek-v4-pro", None, None
elif mode == "fusion":
    llm_model, embedding_model = "deepseek-v4-pro", "BAAI/bge-small-zh-v1.5"
    fusion_weights = {"llm": 0.7, "embedding": 0.2, "pattern": 0.1}
else:
    raise SystemExit("unsupported mode: " + mode)

out_path = os.environ["EI_META_OUT"]
pred_path = os.environ["EI_META_PRED"]
metrics_path = os.environ["EI_META_METRICS"]
dataset_path = os.environ["EI_META_DATASET"]
execution_revision = os.environ["EI_META_EXEC_REV"].strip()
current_head = os.environ["EI_META_HEAD"].strip()
assert execution_revision == current_head, "HEAD does not match approved execution_revision"

def sha256_of(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()

rows = [json.loads(line) for line in open(pred_path, "r", encoding="utf-8")]
assert len(rows) == 500, "prediction rows != 500"
assert len(set(row["id"] for row in rows)) == 500, "prediction ids not unique"
row_errors = sum(1 for row in rows if row.get("error"))
source_errors = sum(1 for row in rows if row.get("source_errors"))
assert row_errors == 0, "row error count must be 0"
assert source_errors == 0, "source error count must be 0"

payload = {
    "schema_version": "intent_test500_run_metadata_v1",
    "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "candidate_only": True,
    "code_revision": CODE_REVISION,
    "execution_revision": execution_revision,
    "dataset_path": dataset_path,
    "dataset_sha256": sha256_of(dataset_path),
    "dataset_rows": 500,
    "labels": LABELS,
    "mode": mode,
    "llm_model": llm_model,
    "embedding_model": embedding_model,
    "confidence_threshold": 0.5,
    "fusion_weights": fusion_weights,
    "predictions_sha256": sha256_of(pred_path),
    "metrics_sha256": sha256_of(metrics_path),
    "prediction_rows": 500,
    "row_error_count": row_errors,
    "source_error_count": source_errors,
}
serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
try:
    with open(out_path, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)
except FileExistsError:
    raise SystemExit("run_metadata.json already exists, refusing to overwrite: " + out_path)

reread = json.load(open(out_path, "r", encoding="utf-8"))
assert reread == payload, "re-read metadata does not match written payload field-by-field"
print("[OK] run_metadata.json created exclusively and verified:", out_path)
'@
& 'E:\conda_envs\echomind\python.exe' -X utf8 -c $py
if ($LASTEXITCODE -ne 0) { Write-Error 'run_metadata.json creation FAILED'; exit $LASTEXITCODE }
Write-Output 'run_metadata.json creation PASSED'
```

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
- 重算已通过（§8）；每模式 `run_metadata.json` 存在且已由 §7.1 脚本验证；
- 输入终验：`intent_test_500.jsonl`、`intent_dev.jsonl` 哈希仍等于 §2 冻结值；Task 7 baseline 两文件哈希仍等于 §3 冻结值；
- dev 历史证据终验：§4 的 `dev-fusion-bge-conservative-190` 三个文件哈希仍等于 §4 冻结值；其余 dev 190 历史目录保持只读、未写入任何新文件。

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

- §2/§3/§5 任何前置硬门、身份验证或定向测试失败；
- 任何 smoke 或正式模式退出码非零；
- 任何 smoke 或正式模式的 §6/§7 成功门未满足（含 API/LLM failure 门）；
- §7.1 metadata 独占创建失败或其逐字段复核失败；
- 重算不一致、四模式一致性验证失败；
- 任一冻结输入或 dev 历史证据哈希发生变化。

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
