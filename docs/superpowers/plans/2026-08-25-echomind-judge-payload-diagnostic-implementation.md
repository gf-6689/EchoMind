# EchoMind Judge Payload Diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely capture the field names and value types returned by the real Judge for the two failed formal cases, without rerunning Agent generation or changing production behavior.

**Architecture:** A local, uncommitted diagnostic runner loads the frozen v2 dataset and the existing failed formal predictions, reconstructs the exact Judge input, and performs three direct Judge tool calls per failed case. It persists only bounded structural metadata and validation outcomes, never payload values or evaluated text.

**Tech Stack:** Python 3.12.13, Anthropic-compatible async client, DeepSeek `deepseek-v4-pro`, JSON, PowerShell, conda environment `echomind`.

**Spec:** `docs/superpowers/specs/2026-08-25-echomind-judge-payload-diagnostic-design.md`

## Global Constraints

- Work only in `E:\Desktop\简历项目\EchoMind所有代码+简历\EchoMind\.worktrees\task6-dialog-eval` on branch `task6-dialog-eval`.
- Use conda environment `echomind` and Python `E:\conda_envs\echomind\python.exe` 3.12.x.
- Use `git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' ...` for Git commands.
- Do not modify, delete, stage, inspect recursively, or commit `.test-tmp/`.
- Do not delete or modify files on drive C.
- Do not change tracked production code, tests, datasets, historical runs, Prompt text, Prompt version, validation behavior, metrics, or schemas.
- Do not call Agent. Make exactly three Judge calls for each of `dialog_eval_018` and `dialog_eval_031`, at most six calls total.
- Do not save payload values, evaluated text, reasoning text, API keys, Authorization headers, or environment-variable dumps.
- The output directory `data/eval/runs/dialog-judge-payload-diagnostic-v3` must not exist before execution. If it exists, stop; do not delete or overwrite it.
- Stop after the evidence report. Do not implement a fix or rerun the formal evaluation.

---

### Task 1: Verify immutable inputs and output boundary

**Files:**
- Read: `E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json`
- Read: `data/eval/runs/dialog-eval-v2/dialog_predictions.jsonl`
- Read: `data/eval/runs/dialog-eval-v2/run_metadata.json`

**Interfaces:**
- Consumes: failed v2 evidence at Git revision `081d1434989bd9aebe362c144d6cfe7cdb2eae42`.
- Produces: verified source identities before paid calls.

- [ ] **Step 1: Check environment, branch, revision, API presence, and unused directory**

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
```

Expected: branch `task6-dialog-eval`; current HEAD contains formal-run revision `081d1434989bd9aebe362c144d6cfe7cdb2eae42` as an ancestor; only `.test-tmp/` untracked; API present; diagnostic path `False`. Record the current HEAD separately.

- [ ] **Step 2: Verify source hashes and exact failed cases**

```powershell
python -X utf8 -c "import hashlib,json; from pathlib import Path; d=Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json'); p=Path('data/eval/runs/dialog-eval-v2/dialog_predictions.jsonl'); m=Path('data/eval/runs/dialog-eval-v2/run_metadata.json'); rows=[json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]; meta=json.loads(m.read_text(encoding='utf-8')); failed=[r['case_id'] for r in rows if r['judge_failed']]; assert hashlib.sha256(d.read_bytes()).hexdigest()=='cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2'; assert failed==['dialog_eval_018','dialog_eval_031']; assert meta['git_revision']=='081d1434989bd9aebe362c144d6cfe7cdb2eae42'; assert meta['prompt_version']=='dialog_judge_v3'; print({'dataset_sha256':hashlib.sha256(d.read_bytes()).hexdigest(),'predictions_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'failed_cases':failed})"
```

Expected: all assertions pass. Record the predictions SHA-256 printed by this command.

---

### Task 2: Run six bounded structural diagnostics

**Files:**
- Create locally, do not commit: `data/eval/runs/dialog-judge-payload-diagnostic-v3/run_diagnostic.py`
- Create locally, do not commit: `data/eval/runs/dialog-judge-payload-diagnostic-v3/diagnostic_results.json`

**Interfaces:**
- Consumes: `DialogJudge._build_prompt(...)`, `SYSTEM_RUBRIC`, `SCORE_TOOL`, `_extract_tool_payload(...)`, and `validate_judge_payload(...)` without changing them.
- Produces: exactly six attempt records containing only bounded structural metadata.

- [ ] **Step 1: Create the diagnostic runner with the editing tool**

Create `data/eval/runs/dialog-judge-payload-diagnostic-v3/run_diagnostic.py` with exactly:

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
OUTPUT = Path(__file__).with_name("diagnostic_results.json")
CASE_IDS = ("dialog_eval_018", "dialog_eval_031")
EXPECTED_FIELDS = {"relevance", "accuracy", "completeness", "helpfulness", "reasoning"}
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
    model = (
        os.environ.get("EVAL_JUDGE_MODEL", "").strip()
        or os.environ.get("ANTHROPIC_MODEL", "").strip()
        or "deepseek-v4-pro"
    )
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
        response = stored["turns"][0]["agent_response"]
        prompt = judge._build_prompt(
            turn["user_message"],
            response,
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
        "attempts_per_case": ATTEMPTS_PER_CASE,
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "predictions_sha256": hashlib.sha256(PREDICTIONS.read_bytes()).hexdigest(),
        "results": results,
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run exactly once and record the exit code**

```powershell
python -X utf8 'data\eval\runs\dialog-judge-payload-diagnostic-v3\run_diagnostic.py'
$LASTEXITCODE
```

Expected: exit code `0` and exactly six printed records. Do not rerun if any call is invalid, times out, or returns no tool payload; those outcomes are the diagnostic evidence.

- [ ] **Step 3: Enforce bounded output and secret/text safety**

```powershell
python -X utf8 -c "import json; from pathlib import Path; p=Path('data/eval/runs/dialog-judge-payload-diagnostic-v3/diagnostic_results.json'); x=json.loads(p.read_text(encoding='utf-8')); assert x['prompt_version']=='dialog_judge_v3'; assert x['attempts_per_case']==3; assert len(x['results'])==6; assert [(r['case_id'],r['attempt']) for r in x['results']]==[(c,a) for c in ('dialog_eval_018','dialog_eval_031') for a in (1,2,3)]; allowed={'case_id','attempt','payload_type','field_names','field_types','missing_fields','unexpected_fields','validation','validation_error','latency_ms'}; assert all(set(r)==allowed for r in x['results']); assert all(all(len(k)<=80 for k in r['field_names']) for r in x['results']); text=p.read_text(encoding='utf-8').lower(); assert 'api_key' not in text and 'authorization' not in text; assert '下单页面' not in text and '登录一直' not in text and '预计到账时间' not in text; print({'records':len(x['results']),'valid':sum(r['validation']=='valid' for r in x['results']),'invalid':sum(r['validation']=='invalid' for r in x['results']),'not_reached':sum(r['validation']=='not_reached' for r in x['results'])})"
```

Expected: all assertions pass and a 6-record summary is printed.

---

### Task 3: Classify evidence and stop

**Files:**
- Read: `data/eval/runs/dialog-judge-payload-diagnostic-v3/diagnostic_results.json`

**Interfaces:**
- Consumes: six bounded structural observations.
- Produces: a root-cause evidence report without a code change.

- [ ] **Step 1: Print a compact shape matrix**

```powershell
python -X utf8 -c "import json; from pathlib import Path; x=json.loads(Path('data/eval/runs/dialog-judge-payload-diagnostic-v3/diagnostic_results.json').read_text(encoding='utf-8')); [(print({'case_id':r['case_id'],'attempt':r['attempt'],'validation':r['validation'],'payload_type':r['payload_type'],'fields':r['field_names'],'types':r['field_types'],'missing':r['missing_fields'],'unexpected':r['unexpected_fields'],'error':r['validation_error'],'latency_ms':r['latency_ms']})) for r in x['results']]"
```

- [ ] **Step 2: Produce the handoff report**

Report:

1. branch, HEAD, and final `git status --short`;
2. source dataset/predictions hashes;
3. exact command and exit code;
4. six shape records;
5. counts of valid, invalid, and not-reached attempts;
6. whether invalid attempts share one missing/unexpected/type pattern;
7. whether the original failure reproduced;
8. confirmation that no payload values, evaluated text, secrets, production changes, Agent calls, formal reruns, baseline changes, or résumé updates occurred.

Stop after the report. Do not recommend a parser change unless the report clearly separates observed evidence from inference, and do not implement any fix.
