# EchoMind Judge JSON Fallback Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministically verify that `dialog_judge_v4` recovers from two empty tool payloads by obtaining and strictly validating one plain-JSON judgment for each of the two frozen failure cases.

**Architecture:** Reuse the frozen Agent responses from `dialog-eval-v2`; do not call any Agent. A local calibration wrapper injects the already-observed `input={}` boundary condition for attempts 1 and 2, then forwards attempt 3 unchanged to the exact formal Judge model. This exercises the production `DialogJudge.judge_turn(...)` fallback branch while making exactly two external Judge requests in total.

**Tech Stack:** Python 3.12.13, pytest, Anthropic-compatible async client, DeepSeek `deepseek-v4-pro`, JSON, PowerShell, conda environment `echomind`.

**Spec:** Approved bounded Solution A in the Codex conversation on 2026-08-25, implemented by commit `95c23733b06c8950a30b681a8a582141614cc2a8`.

## Global Constraints

- Work only in `E:\Desktop\简历项目\EchoMind所有代码+简历\EchoMind\.worktrees\task6-dialog-eval` on branch `task6-dialog-eval`.
- Use conda environment `echomind` and `E:\conda_envs\echomind\python.exe` 3.12.x.
- Do not modify, delete, stage, inspect recursively, or commit `.test-tmp/` or `.pytest_cache/`.
- Do not delete or modify any file on drive C.
- Preserve every historical run, including `dialog-eval-v2`, both payload diagnostics, and all Smoke runs.
- The new directory `data/eval/runs/dialog-judge-json-fallback-calibration-v4` must not exist before execution. If it exists, stop; do not delete, rename, reuse, or overwrite it.
- The new pytest base directory `data/eval/tmp/dialog-judge-json-fallback-calibration-v4-tests` must not exist before execution. If it exists, stop; do not delete or reuse it.
- Read the Judge model only from `data/eval/runs/dialog-eval-v2/run_metadata.json`; assert exact equality with `deepseek-v4-pro`. Ignore `EVAL_JUDGE_MODEL` and `ANTHROPIC_MODEL` for model selection.
- Reuse only the frozen Agent answers for `dialog_eval_018` and `dialog_eval_031`; make zero Agent calls.
- Inject exactly two local empty tool responses per case, then permit exactly one external strict-JSON Judge request per case: two external Judge requests total.
- Run the calibration command exactly once. Do not rerun it regardless of success, partial failure, timeout, or nonzero exit code.
- Do not persist evaluated questions, Agent answers, context, reference answers, required points, Judge reasoning, raw model responses, payload values, secrets, headers, or environment-variable values.
- Do not change production code, tests, datasets, prompts, validation, metric schemas, baseline, résumé claims, or historical artifacts during this calibration.
- Stop after evidence reporting. Do not run the formal 35-case evaluation.

---

### Task 1: Freeze implementation and source inputs

**Files:**
- Read: `evaluation/dialog_judge.py`
- Read: `tests/evaluation/test_dialog_judge.py`
- Read: `data/eval/runs/dialog-eval-v2/run_metadata.json`
- Read: `data/eval/runs/dialog-eval-v2/dialog_predictions.jsonl`
- Read: `E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json`

**Interfaces:**
- Consumes: committed v4 Judge, frozen v2 dataset, frozen formal Agent answers, and formal model identity.
- Produces: proof that the exact implementation and immutable source files are being calibrated.

- [ ] **Step 1: Verify environment, branch, committed implementation, tracked cleanliness, and unused output path**

Run each command separately:

```powershell
conda activate echomind
Set-Location -LiteralPath 'E:\Desktop\简历项目\EchoMind所有代码+简历\EchoMind\.worktrees\task6-dialog-eval'
python -c "import sys; print({'python':sys.executable,'version':sys.version}); assert sys.executable.lower()==r'E:\conda_envs\echomind\python.exe'.lower(); assert sys.version_info[:2]==(3,12)"
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' branch --show-current
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' rev-parse HEAD
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' merge-base --is-ancestor 95c23733b06c8950a30b681a8a582141614cc2a8 HEAD
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' diff --quiet
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' diff --cached --quiet
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' status --short
python -X utf8 -c "from evaluation.dialog_judge import PROMPT_VERSION,JUDGE_OUTPUT_STRATEGY; assert PROMPT_VERSION=='dialog_judge_v4'; assert JUDGE_OUTPUT_STRATEGY=='forced_tool_then_strict_json_fallback'; print({'prompt_version':PROMPT_VERSION,'judge_output_strategy':JUDGE_OUTPUT_STRATEGY})"
python -c "from dotenv import load_dotenv; import os; load_dotenv(); assert os.getenv('ANTHROPIC_API_KEY'), 'ANTHROPIC_API_KEY is missing'; print('API configuration present')"
Test-Path -LiteralPath 'data\eval\runs\dialog-judge-json-fallback-calibration-v4'
Test-Path -LiteralPath 'data\eval\tmp\dialog-judge-json-fallback-calibration-v4-tests'
```

Expected:

- branch is `task6-dialog-eval`;
- implementation commit is an ancestor of `HEAD`;
- both `git diff --quiet` commands exit `0`;
- `status --short` may show only the pre-existing untracked `.test-tmp/` and `.pytest_cache/` warnings/entries;
- Prompt and strategy assertions pass;
- API configuration is present;
- both new calibration and pytest-temp paths print `False`.

If any expected condition fails, stop without creating the directory.

- [ ] **Step 2: Re-run the full local test suite**

```powershell
python -m pytest -q -p no:cacheprovider --basetemp 'data\eval\tmp\dialog-judge-json-fallback-calibration-v4-tests'
$LASTEXITCODE
```

Expected: `97 passed` and exit code is `0`. If not, stop; do not make any API call. Keep the new pytest-temp directory; do not delete it.

- [ ] **Step 3: Verify immutable source identities**

```powershell
python -X utf8 -c "import hashlib,json; from pathlib import Path; d=Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json'); p=Path('data/eval/runs/dialog-eval-v2/dialog_predictions.jsonl'); m=Path('data/eval/runs/dialog-eval-v2/run_metadata.json'); rows={r['case_id']:r for r in map(json.loads,p.read_text(encoding='utf-8').splitlines())}; meta=json.loads(m.read_text(encoding='utf-8')); assert hashlib.sha256(d.read_bytes()).hexdigest()=='cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2'; assert hashlib.sha256(p.read_bytes()).hexdigest()=='cb9b86e07c6cafeaeaacbd1af7e0bebf942151e5df74a0b88f35c319524c638d'; assert meta['judge_model']=='deepseek-v4-pro'; assert meta['prompt_version']=='dialog_judge_v3'; assert [rows[x]['judge_failed'] for x in ('dialog_eval_018','dialog_eval_031')]==[True,True]; assert all(len(rows[x]['turns'])==1 for x in ('dialog_eval_018','dialog_eval_031')); print({'dataset_sha256':hashlib.sha256(d.read_bytes()).hexdigest(),'predictions_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'formal_metadata_sha256':hashlib.sha256(m.read_bytes()).hexdigest(),'model':meta['judge_model'],'frozen_cases':['dialog_eval_018','dialog_eval_031']})"
```

Expected: every assertion passes. The formal v2 Prompt remains v3 because it is immutable source evidence; the current implementation is v4.

---

### Task 2: Execute the deterministic two-case live fallback calibration

**Files:**
- Create locally, do not commit: `data/eval/runs/dialog-judge-json-fallback-calibration-v4/run_calibration.py`
- Create locally, do not commit: `data/eval/runs/dialog-judge-json-fallback-calibration-v4/calibration_results.json`

**Interfaces:**
- Consumes: `DialogJudge.judge_turn(...)`, `PROMPT_VERSION`, `JUDGE_OUTPUT_STRATEGY`, frozen Agent answers, frozen cases, and the exact model recorded by formal metadata.
- Produces: two bounded records proving whether the production JSON fallback accepts exact-model output after two injected empty tool payloads.

- [ ] **Step 1: Create the new directory and runner using an editing tool**

Create the directory only after Task 1 passes. Create `run_calibration.py` with exactly this content:

```python
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from evaluation.dialog_judge import (
    JUDGE_OUTPUT_STRATEGY,
    JSON_FALLBACK_INSTRUCTION,
    PROMPT_VERSION,
    SCORE_TOOL,
    DialogJudge,
)
from evaluation.dialog_metrics import DIMENSIONS
from evaluation.run_dialog_eval import build_controlled_context


DATASET = Path(r"E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json")
PREDICTIONS = Path("data/eval/runs/dialog-eval-v2/dialog_predictions.jsonl")
FORMAL_METADATA = Path("data/eval/runs/dialog-eval-v2/run_metadata.json")
OUTPUT = Path(__file__).with_name("calibration_results.json")
CASE_IDS = ("dialog_eval_018", "dialog_eval_031")
EXPECTED_MODEL = "deepseek-v4-pro"
IMPLEMENTATION_REVISION = "95c23733b06c8950a30b681a8a582141614cc2a8"
EXPECTED_DATASET_SHA256 = "cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2"
EXPECTED_PREDICTIONS_SHA256 = "cb9b86e07c6cafeaeaacbd1af7e0bebf942151e5df74a0b88f35c319524c638d"
EXPECTED_MODES = ["synthetic_empty_tool", "synthetic_empty_tool", "live_strict_json"]


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", f"safe.directory={REPO.resolve().as_posix()}", *args],
        cwd=REPO,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class FallbackCalibrationMessages:
    def __init__(self, real_messages: object) -> None:
        self.real_messages = real_messages
        self.calls = 0
        self.real_calls = 0
        self.modes: list[str] = []

    async def create(self, **kwargs: object) -> object:
        self.calls += 1
        if self.calls <= 2:
            if kwargs.get("tools") != [SCORE_TOOL]:
                raise RuntimeError("synthetic attempts must use the frozen score tool")
            if kwargs.get("tool_choice") != {"type": "tool", "name": SCORE_TOOL["name"]}:
                raise RuntimeError("synthetic attempts must force the score tool")
            self.modes.append("synthetic_empty_tool")
            return SimpleNamespace(
                content=[SimpleNamespace(type="tool_use", name=SCORE_TOOL["name"], input={})]
            )
        if self.calls != 3:
            raise RuntimeError("calibration exceeded three total attempts")
        if "tools" in kwargs or "tool_choice" in kwargs:
            raise RuntimeError("fallback request must not include tool configuration")
        if JSON_FALLBACK_INSTRUCTION not in str(kwargs.get("system", "")):
            raise RuntimeError("fallback request is missing the strict JSON instruction")
        self.modes.append("live_strict_json")
        self.real_calls += 1
        return await self.real_messages.create(**kwargs)


class FallbackCalibrationClient:
    def __init__(self, real_messages: object) -> None:
        self.messages = FallbackCalibrationMessages(real_messages)


async def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"calibration output already exists: {OUTPUT}")
    if PROMPT_VERSION != "dialog_judge_v4":
        raise RuntimeError("current Prompt version is not dialog_judge_v4")
    if JUDGE_OUTPUT_STRATEGY != "forced_tool_then_strict_json_fallback":
        raise RuntimeError("current Judge output strategy is not frozen v4 strategy")
    if git("merge-base", "--is-ancestor", IMPLEMENTATION_REVISION, "HEAD", check=False).returncode != 0:
        raise RuntimeError("implementation revision is not an ancestor of HEAD")
    if git("diff", "--quiet", check=False).returncode != 0:
        raise RuntimeError("tracked working tree is not clean")
    if git("diff", "--cached", "--quiet", check=False).returncode != 0:
        raise RuntimeError("index is not clean")

    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip()

    formal_metadata = json.loads(FORMAL_METADATA.read_text(encoding="utf-8"))
    model = formal_metadata["judge_model"]
    if model != EXPECTED_MODEL:
        raise RuntimeError("formal Judge model is not the frozen expected model")
    if formal_metadata["prompt_version"] != "dialog_judge_v3":
        raise RuntimeError("formal source metadata was unexpectedly modified")
    if hashlib.sha256(DATASET.read_bytes()).hexdigest() != EXPECTED_DATASET_SHA256:
        raise RuntimeError("dataset hash changed")
    if hashlib.sha256(PREDICTIONS.read_bytes()).hexdigest() != EXPECTED_PREDICTIONS_SHA256:
        raise RuntimeError("predictions hash changed")

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

    options: dict[str, object] = {"api_key": api_key}
    if base_url:
        options["base_url"] = base_url
    real_client = AsyncAnthropic(**options)

    records = []
    for case_id in CASE_IDS:
        case = cases[case_id]
        stored = predictions[case_id]
        if len(case["turns"]) != 1 or len(stored["turns"]) != 1:
            raise RuntimeError(f"{case_id} must contain exactly one turn")
        turn = case["turns"][0]
        calibration_client = FallbackCalibrationClient(real_client.messages)
        judge = DialogJudge(calibration_client, model, secrets=(api_key,))
        result = await judge.judge_turn(
            question=turn["user_message"],
            response=stored["turns"][0]["agent_response"],
            context=build_controlled_context(case["context"]),
            reference_answer=turn["reference_answer"],
            required_points=turn["required_points"],
            history=[],
        )
        messages = calibration_client.messages
        judge_payload = result.get("judge") or {}
        reasoning = judge_payload.get("reasoning")
        passed = (
            result.get("judge_failed") is False
            and result.get("judge_attempts") == 3
            and messages.calls == 3
            and messages.real_calls == 1
            and messages.modes == EXPECTED_MODES
            and isinstance(reasoning, str)
            and bool(reasoning.strip())
            and all(name in judge_payload for name in (*DIMENSIONS, "overall"))
        )
        records.append({
            "case_id": case_id,
            "passed": passed,
            "judge_failed": result.get("judge_failed"),
            "judge_error": result.get("judge_error"),
            "judge_attempts": result.get("judge_attempts"),
            "request_modes": messages.modes,
            "external_judge_calls": messages.real_calls,
            "score_fields": (
                list((*DIMENSIONS, "overall"))
                if all(name in judge_payload for name in (*DIMENSIONS, "overall"))
                else []
            ),
            "score_types": {
                name: type(judge_payload[name]).__name__
                for name in (*DIMENSIONS, "overall")
                if name in judge_payload
            },
            "scores_in_range": (
                all(
                    isinstance(judge_payload[name], (int, float))
                    and not isinstance(judge_payload[name], bool)
                    and 0 <= float(judge_payload[name]) <= 1
                    for name in (*DIMENSIONS, "overall")
                )
                if all(name in judge_payload for name in (*DIMENSIONS, "overall"))
                else False
            ),
            "reasoning_length": len(reasoning.strip()) if isinstance(reasoning, str) else 0,
            "latency_ms": judge_payload.get("latency_ms"),
        })

    output = {
        "prompt_version": PROMPT_VERSION,
        "judge_output_strategy": JUDGE_OUTPUT_STRATEGY,
        "model": model,
        "model_source": "data/eval/runs/dialog-eval-v2/run_metadata.json",
        "implementation_revision": IMPLEMENTATION_REVISION,
        "execution_revision": git("rev-parse", "HEAD").stdout.strip(),
        "formal_source_revision": formal_metadata["git_revision"],
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "predictions_sha256": hashlib.sha256(PREDICTIONS.read_bytes()).hexdigest(),
        "external_judge_calls": sum(record["external_judge_calls"] for record in records),
        "passed": all(record["passed"] for record in records),
        "results": records,
    }
    serialized = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    lowered = serialized.lower()
    if api_key in serialized or "authorization" in lowered or "api_key" in lowered:
        raise RuntimeError("calibration output contains sensitive configuration")
    for forbidden in ("下单页面", "登录一直", "预计到账时间"):
        if forbidden in serialized:
            raise RuntimeError("calibration output contains evaluated text")
    OUTPUT.write_text(serialized, encoding="utf-8", newline="\n")
    print(serialized, end="")
    if not output["passed"] or output["external_judge_calls"] != 2:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Inspect the runner without printing secrets or evaluated text**

```powershell
python -m py_compile 'data\eval\runs\dialog-judge-json-fallback-calibration-v4\run_calibration.py'
$LASTEXITCODE
```

Expected: exit code `0`. Do not print `.env`, request bodies, frozen Agent answers, or raw responses.

- [ ] **Step 3: Run the calibration exactly once**

```powershell
python -X utf8 'data\eval\runs\dialog-judge-json-fallback-calibration-v4\run_calibration.py'
$calibrationExitCode = $LASTEXITCODE
$calibrationExitCode
```

Expected success condition: exit code `0`. Regardless of the exit code, do not invoke `run_calibration.py` a second time.

---

### Task 3: Verify bounded evidence and stop

**Files:**
- Read: `data/eval/runs/dialog-judge-json-fallback-calibration-v4/calibration_results.json`
- Read: Git status and committed history.

**Interfaces:**
- Consumes: the single calibration output.
- Produces: an auditable pass/fail report and a hard stop before formal evaluation.

- [ ] **Step 1: Validate artifact schema, provenance, call count, and safety**

Run only if `calibration_results.json` exists:

```powershell
python -X utf8 -c "import hashlib,json; from pathlib import Path; p=Path('data/eval/runs/dialog-judge-json-fallback-calibration-v4/calibration_results.json'); x=json.loads(p.read_text(encoding='utf-8')); expected=['relevance','accuracy','completeness','helpfulness','overall']; assert x['prompt_version']=='dialog_judge_v4'; assert x['judge_output_strategy']=='forced_tool_then_strict_json_fallback'; assert x['model']=='deepseek-v4-pro'; assert x['implementation_revision']=='95c23733b06c8950a30b681a8a582141614cc2a8'; assert x['dataset_sha256']=='cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2'; assert x['predictions_sha256']=='cb9b86e07c6cafeaeaacbd1af7e0bebf942151e5df74a0b88f35c319524c638d'; assert x['external_judge_calls']==2; assert [r['case_id'] for r in x['results']]==['dialog_eval_018','dialog_eval_031']; assert all(r['passed'] and not r['judge_failed'] and r['judge_attempts']==3 for r in x['results']); assert all(r['request_modes']==['synthetic_empty_tool','synthetic_empty_tool','live_strict_json'] and r['external_judge_calls']==1 for r in x['results']); assert all(r['score_fields']==expected and set(r['score_types'])==set(expected) and r['scores_in_range'] for r in x['results']); assert all(r['reasoning_length']>0 for r in x['results']); text=p.read_text(encoding='utf-8').lower(); assert 'api_key' not in text and 'authorization' not in text; print({'artifact_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'passed':x['passed'],'external_judge_calls':x['external_judge_calls'],'results':[{'case_id':r['case_id'],'attempts':r['judge_attempts'],'modes':r['request_modes'],'score_fields':r['score_fields'],'score_types':r['score_types'],'scores_in_range':r['scores_in_range'],'reasoning_length':r['reasoning_length'],'latency_ms':r['latency_ms']} for r in x['results']]})"
```

Expected: all assertions pass, `passed=True`, exactly two external Judge calls, and each case reaches `live_strict_json` on attempt 3.

- [ ] **Step 2: Confirm no tracked mutation and preserve all historical artifacts**

```powershell
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' diff --quiet
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' diff --cached --quiet
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' status --short
Get-ChildItem -LiteralPath 'data\eval\runs\dialog-judge-json-fallback-calibration-v4' | Select-Object Name,Length
```

Expected: tracked worktree and index remain clean; only ignored calibration files and pre-existing untracked cache directories are outside Git.

- [ ] **Step 3: Produce the handoff report and stop**

Report:

1. branch, `HEAD`, implementation ancestor check, and tracked cleanliness;
2. Python path/version and full test count;
3. dataset, predictions, formal metadata, and calibration output SHA-256 values;
4. exact model source and exact model name;
5. the single calibration command, saved exit code, and explicit no-rerun statement;
6. for each case: attempt count, request mode sequence, external Judge call count, score field names/types/range status, reasoning length, latency, and pass/fail state;
7. total external Judge calls (`2`) and Agent calls (`0`);
8. confirmation that no evaluated text, reasoning text, raw response, payload value, secret, header, or environment-variable value was persisted;
9. confirmation that production code, tests, datasets, historical runs, baseline, résumé claims, `.test-tmp/`, and C-drive files were not modified during calibration.

Stop after reporting. Do not run or authorize the formal 35-case evaluation until Codex independently reviews this calibration evidence.
