# EchoMind Exact-Model Judge Payload Diagnostic Retry 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repeat the two-case payload-shape diagnostic using exactly the Judge model recorded by the failed formal run, eliminating the model mismatch from the first diagnostic.

**Architecture:** A new local runner reads `judge_model` from the immutable formal `run_metadata.json`, asserts it equals `deepseek-v4-pro`, and ignores model-selection environment variables. It reconstructs the same two Judge inputs and records only six bounded payload-shape observations in a new retry directory.

**Tech Stack:** Python 3.12.13, Anthropic-compatible async client, DeepSeek `deepseek-v4-pro`, JSON, PowerShell, conda environment `echomind`.

**Spec:** `docs/superpowers/specs/2026-08-25-echomind-judge-payload-diagnostic-retry1-design.md`

## Global Constraints

- Work only in `E:\Desktop\简历项目\EchoMind所有代码+简历\EchoMind\.worktrees\task6-dialog-eval` on branch `task6-dialog-eval`.
- Use conda environment `echomind` and Python `E:\conda_envs\echomind\python.exe` 3.12.x.
- Do not modify, delete, stage, inspect recursively, or commit `.test-tmp/`.
- Do not delete or modify files on drive C.
- Preserve all historical runs, including `dialog-judge-payload-diagnostic-v3` and `dialog-eval-v2`.
- The new directory `data/eval/runs/dialog-judge-payload-diagnostic-v3-retry1` must not exist before execution. If it exists, stop; do not delete or overwrite it.
- Do not select the model from `EVAL_JUDGE_MODEL` or `ANTHROPIC_MODEL`; read it only from the formal metadata and assert exact equality with `deepseek-v4-pro`.
- Call no Agent. Make exactly three Judge calls for each of `dialog_eval_018` and `dialog_eval_031`, six calls total.
- Do not save payload values, evaluated text, reasoning, secrets, headers, or environment-variable values.
- Do not change tracked code, tests, datasets, Prompt, validation, metrics, or schemas.
- Stop after evidence reporting; do not implement a fix or rerun 35 cases.

---

### Task 1: Prove the first diagnostic mismatch and freeze retry inputs

**Files:**
- Read: `data/eval/runs/dialog-eval-v2/run_metadata.json`
- Read: `data/eval/runs/dialog-judge-payload-diagnostic-v3/diagnostic_results.json`
- Read: `E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json`
- Read: `data/eval/runs/dialog-eval-v2/dialog_predictions.jsonl`

**Interfaces:**
- Consumes: formal metadata and first diagnostic evidence.
- Produces: explicit proof that retry1 corrects only the model source.

- [ ] **Step 1: Verify environment, ancestry, clean tracked state, and unused retry directory**

```powershell
conda activate echomind
Set-Location -LiteralPath 'E:\Desktop\简历项目\EchoMind所有代码+简历\EchoMind\.worktrees\task6-dialog-eval'
python -c "import sys; print(sys.executable); assert sys.executable.lower()==r'E:\conda_envs\echomind\python.exe'.lower(); assert sys.version_info[:2]==(3,12)"
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' branch --show-current
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' rev-parse HEAD
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' merge-base --is-ancestor 081d1434989bd9aebe362c144d6cfe7cdb2eae42 HEAD
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' status --short
python -c "from dotenv import load_dotenv; import os; load_dotenv(); assert os.getenv('ANTHROPIC_API_KEY'); print('API configuration present')"
Test-Path -LiteralPath 'data\eval\runs\dialog-judge-payload-diagnostic-v3'
Test-Path -LiteralPath 'data\eval\runs\dialog-judge-payload-diagnostic-v3-retry1'
```

Expected: formal revision is an ancestor; only `.test-tmp/` is untracked; first diagnostic exists; retry1 path is `False`.

- [ ] **Step 2: Prove the model mismatch and source identities**

```powershell
python -X utf8 -c "import hashlib,json; from pathlib import Path; meta_path=Path('data/eval/runs/dialog-eval-v2/run_metadata.json'); first_path=Path('data/eval/runs/dialog-judge-payload-diagnostic-v3/diagnostic_results.json'); data_path=Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json'); pred_path=Path('data/eval/runs/dialog-eval-v2/dialog_predictions.jsonl'); meta=json.loads(meta_path.read_text(encoding='utf-8')); first=json.loads(first_path.read_text(encoding='utf-8')); assert meta['judge_model']=='deepseek-v4-pro'; assert first['model']=='deepseek-v4-pro[1m]'; assert first['model']!=meta['judge_model']; assert meta['prompt_version']=='dialog_judge_v3'; assert hashlib.sha256(data_path.read_bytes()).hexdigest()=='cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2'; print({'formal_model':meta['judge_model'],'first_diagnostic_model':first['model'],'formal_metadata_sha256':hashlib.sha256(meta_path.read_bytes()).hexdigest(),'dataset_sha256':hashlib.sha256(data_path.read_bytes()).hexdigest(),'predictions_sha256':hashlib.sha256(pred_path.read_bytes()).hexdigest()})"
```

Expected: mismatch assertion passes and all source hashes print.

---

### Task 2: Execute six exact-model structural calls

**Files:**
- Create locally, do not commit: `data/eval/runs/dialog-judge-payload-diagnostic-v3-retry1/run_diagnostic.py`
- Create locally, do not commit: `data/eval/runs/dialog-judge-payload-diagnostic-v3-retry1/diagnostic_results.json`

**Interfaces:**
- Consumes: model and Prompt version from formal metadata, existing two failed Agent responses, and current Judge tool contract.
- Produces: six exact-model structural observations with formal-source provenance.

- [ ] **Step 1: Create the retry runner with the editing tool**

Create `data/eval/runs/dialog-judge-payload-diagnostic-v3-retry1/run_diagnostic.py` with exactly:

```python
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from time import monotonic

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from evaluation.dialog_judge import (
    PROMPT_VERSION,
    SCORE_TOOL,
    SYSTEM_RUBRIC,
    DialogJudge,
    _extract_tool_payload,
    sanitize_error,
    validate_judge_payload,
)
from evaluation.run_dialog_eval import build_controlled_context


DATASET = Path(r"E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json")
PREDICTIONS = Path("data/eval/runs/dialog-eval-v2/dialog_predictions.jsonl")
FORMAL_METADATA = Path("data/eval/runs/dialog-eval-v2/run_metadata.json")
OUTPUT = Path(__file__).with_name("diagnostic_results.json")
CASE_IDS = ("dialog_eval_018", "dialog_eval_031")
EXPECTED_FIELDS = {"relevance", "accuracy", "completeness", "helpfulness", "reasoning"}
EXPECTED_MODEL = "deepseek-v4-pro"
ATTEMPTS_PER_CASE = 3
MAX_KEY_LENGTH = 80


def bounded_key(value: object) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")[:MAX_KEY_LENGTH]


def payload_shape(payload: object) -> dict:
    if not isinstance(payload, dict):
        return {
            "payload_type": type(payload).__name__,
            "field_names": [],
            "field_types": {},
            "missing_fields": sorted(EXPECTED_FIELDS),
            "unexpected_fields": [],
        }
    names = {bounded_key(key) for key in payload}
    return {
        "payload_type": "dict",
        "field_names": sorted(names),
        "field_types": {
            bounded_key(key): type(value).__name__
            for key, value in sorted(payload.items(), key=lambda item: bounded_key(item[0]))
        },
        "missing_fields": sorted(EXPECTED_FIELDS - names),
        "unexpected_fields": sorted(names - EXPECTED_FIELDS),
    }


async def main() -> None:
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip()
    formal_metadata = json.loads(FORMAL_METADATA.read_text(encoding="utf-8"))
    model = formal_metadata["judge_model"]
    if model != EXPECTED_MODEL:
        raise RuntimeError("formal Judge model is not the frozen expected model")
    if formal_metadata["prompt_version"] != PROMPT_VERSION or PROMPT_VERSION != "dialog_judge_v3":
        raise RuntimeError("formal and current Prompt versions do not match")

    options = {"api_key": api_key}
    if base_url:
        options["base_url"] = base_url
    client = AsyncAnthropic(**options)
    judge = DialogJudge(client, model, secrets=(api_key,))
    cases = {
        case["case_id"]: case
        for case in json.loads(DATASET.read_text(encoding="utf-8"))
    }
    predictions = {
        row["case_id"]: row
        for row in (
            json.loads(line)
            for line in PREDICTIONS.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }

    results = []
    for case_id in CASE_IDS:
        case = cases[case_id]
        stored = predictions[case_id]
        if len(case["turns"]) != 1 or len(stored["turns"]) != 1:
            raise RuntimeError(f"{case_id} must contain exactly one turn")
        turn = case["turns"][0]
        prompt = judge._build_prompt(
            turn["user_message"],
            stored["turns"][0]["agent_response"],
            build_controlled_context(case["context"]),
            turn["reference_answer"],
            turn["required_points"],
            [],
        )
        for attempt in range(1, ATTEMPTS_PER_CASE + 1):
            started = monotonic()
            record = {"case_id": case_id, "attempt": attempt}
            try:
                api_response = await client.messages.create(
                    model=model,
                    max_tokens=512,
                    temperature=0.0,
                    system=SYSTEM_RUBRIC,
                    messages=[{"role": "user", "content": prompt}],
                    tools=[SCORE_TOOL],
                    tool_choice={"type": "tool", "name": SCORE_TOOL["name"]},
                    extra_body={"thinking": {"type": "disabled"}},
                    timeout=30.0,
                )
                payload = _extract_tool_payload(api_response.content)
                record.update(payload_shape(payload))
                try:
                    validate_judge_payload(payload)
                    record["validation"] = "valid"
                    record["validation_error"] = None
                except Exception as exc:
                    record["validation"] = "invalid"
                    record["validation_error"] = sanitize_error(exc, (api_key,))
            except Exception as exc:
                record.update({
                    "payload_type": None,
                    "field_names": [],
                    "field_types": {},
                    "missing_fields": [],
                    "unexpected_fields": [],
                    "validation": "not_reached",
                    "validation_error": type(exc).__name__,
                })
            record["latency_ms"] = (monotonic() - started) * 1000
            results.append(record)

    output = {
        "prompt_version": PROMPT_VERSION,
        "model": model,
        "model_source": "data/eval/runs/dialog-eval-v2/run_metadata.json",
        "formal_git_revision": formal_metadata["git_revision"],
        "attempts_per_case": ATTEMPTS_PER_CASE,
        "formal_metadata_sha256": hashlib.sha256(FORMAL_METADATA.read_bytes()).hexdigest(),
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "predictions_sha256": hashlib.sha256(PREDICTIONS.read_bytes()).hexdigest(),
        "results": results,
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run exactly once**

```powershell
python -X utf8 'data\eval\runs\dialog-judge-payload-diagnostic-v3-retry1\run_diagnostic.py'
$LASTEXITCODE
```

Expected: exit code `0`, exactly six records, and no second invocation regardless of outcome.

- [ ] **Step 3: Enforce exact-model provenance and safe structure**

```powershell
python -X utf8 -c "import hashlib,json; from pathlib import Path; out=Path('data/eval/runs/dialog-judge-payload-diagnostic-v3-retry1/diagnostic_results.json'); meta_path=Path('data/eval/runs/dialog-eval-v2/run_metadata.json'); x=json.loads(out.read_text(encoding='utf-8')); meta=json.loads(meta_path.read_text(encoding='utf-8')); assert x['model']=='deepseek-v4-pro'==meta['judge_model']; assert x['model_source']=='data/eval/runs/dialog-eval-v2/run_metadata.json'; assert x['prompt_version']=='dialog_judge_v3'==meta['prompt_version']; assert x['formal_git_revision']==meta['git_revision']=='081d1434989bd9aebe362c144d6cfe7cdb2eae42'; assert x['formal_metadata_sha256']==hashlib.sha256(meta_path.read_bytes()).hexdigest(); assert x['attempts_per_case']==3 and len(x['results'])==6; assert [(r['case_id'],r['attempt']) for r in x['results']]==[(c,a) for c in ('dialog_eval_018','dialog_eval_031') for a in (1,2,3)]; allowed={'case_id','attempt','payload_type','field_names','field_types','missing_fields','unexpected_fields','validation','validation_error','latency_ms'}; assert all(set(r)==allowed for r in x['results']); assert all(all(len(k)<=80 for k in r['field_names']) for r in x['results']); text=out.read_text(encoding='utf-8').lower(); assert 'api_key' not in text and 'authorization' not in text; assert '下单页面' not in text and '登录一直' not in text and '预计到账时间' not in text; print({'model':x['model'],'model_source':x['model_source'],'records':len(x['results']),'valid':sum(r['validation']=='valid' for r in x['results']),'invalid':sum(r['validation']=='invalid' for r in x['results']),'not_reached':sum(r['validation']=='not_reached' for r in x['results'])})"
```

Expected: every assertion passes and the model prints exactly `deepseek-v4-pro` without suffixes.

---

### Task 3: Compare exact-model evidence and stop

**Files:**
- Read: `data/eval/runs/dialog-judge-payload-diagnostic-v3/diagnostic_results.json`
- Read: `data/eval/runs/dialog-judge-payload-diagnostic-v3-retry1/diagnostic_results.json`

**Interfaces:**
- Consumes: first mismatched-model evidence and retry1 exact-model evidence.
- Produces: a separated comparison; it never merges the two runs into one failure-rate estimate.

- [ ] **Step 1: Print retry1 shape matrix**

```powershell
python -X utf8 -c "import json; from pathlib import Path; x=json.loads(Path('data/eval/runs/dialog-judge-payload-diagnostic-v3-retry1/diagnostic_results.json').read_text(encoding='utf-8')); [(print({'case_id':r['case_id'],'attempt':r['attempt'],'validation':r['validation'],'payload_type':r['payload_type'],'fields':r['field_names'],'types':r['field_types'],'missing':r['missing_fields'],'unexpected':r['unexpected_fields'],'error':r['validation_error'],'latency_ms':r['latency_ms']})) for r in x['results']]"
```

- [ ] **Step 2: Produce the final retry handoff**

Report:

1. branch, current HEAD, ancestry result, and final Git status;
2. formal metadata model, first diagnostic model, and retry1 model;
3. source hashes and retry output hash;
4. exact command, one-time execution statement, and exit code;
5. six retry1 structural records and valid/invalid/not-reached counts;
6. whether exact `deepseek-v4-pro` reproduced `input={}`;
7. first-run and retry1 findings in separate tables, with no combined rate;
8. facts separated from inference;
9. confirmation of zero Agent calls, zero production changes, zero formal reruns, zero payload values/evaluated text/secrets, and no baseline/résumé update.

Stop after reporting. Do not implement or recommend a parser/retry fix until Codex reviews the exact-model evidence.
