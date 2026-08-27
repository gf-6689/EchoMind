# EchoMind Dialog Evaluation v4 Formal Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a fresh, end-to-end, auditable 35-case/43-turn dialog evaluation using the committed `dialog_judge_v4` fallback protocol.

**Architecture:** A local, ignored same-process driver creates dependencies once, runs one non-counted warm-up case, enforces a hard warm-up gate, and only then runs all 35 cases. It reads credentials and base URL only from the project `.env`, pins both Agent and Judge to `deepseek-v4-pro`, records v4 metadata, preserves every historical run, and stops before baseline or résumé updates.

**Tech Stack:** Python 3.12.13, pytest, Anthropic-compatible async client, DeepSeek `deepseek-v4-pro`, BGE-small-zh-v1.5, JSON/JSONL, PowerShell, conda environment `echomind`.

**Spec:** Approved full end-to-end 35-case design in the Codex conversation on 2026-08-25; Judge implementation commit `95c23733b06c8950a30b681a8a582141614cc2a8`; v4 calibration evidence `data/eval/runs/dialog-judge-json-fallback-calibration-v4/calibration_results.json`.

## Global Constraints

- Work only in `E:\Desktop\简历项目\EchoMind所有代码+简历\EchoMind\.worktrees\task6-dialog-eval` on branch `task6-dialog-eval`.
- Use `E:\conda_envs\echomind\python.exe` 3.12.x. Activating conda is optional when that exact executable is invoked.
- Do not modify, delete, stage, inspect recursively, or commit `.test-tmp/`, `.pytest_cache/`, existing pytest-temp directories, or any historical run.
- Do not delete or modify any file on drive C.
- Preserve `dialog-eval-v1`, `dialog-eval-v2`, all Smoke runs, diagnostics, calibration artifacts, and every existing hash.
- New paths `data/eval/runs/run_dialog_eval_v4.py`, `data/eval/runs/dialog-warmup-v4`, and `data/eval/runs/dialog-eval-v4` must not exist before execution. If any exists, stop; do not delete, rename, reuse, resume, or overwrite it.
- The new pytest base directory `E:\Desktop\简历项目\echomind-dialog-v4-formal-pytest-temp` must not exist before testing. If it exists, stop; do not delete or reuse it.
- Make real Agent and Judge calls. Do not reuse Agent answers from `dialog-eval-v2`.
- Read API key and base URL only from the worktree root `.env`; never print their values. Ignore shell/harness values of `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL`, and `EVAL_JUDGE_MODEL`.
- Pin both `agent_model` and `judge_model` to exact `deepseek-v4-pro`; do not use suffixed aliases such as `deepseek-v4-pro[1m]`.
- Use dataset `E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json` with SHA-256 `cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2`.
- Use `dialog_judge_v4`, temperature `0.0`, maximum three Judge attempts, and strategy `forced_tool_then_strict_json_fallback`.
- Execute `run_dialog_eval_v4.py` exactly once. A nonzero exit, timeout, partial output, Agent failure, Judge failure, or latency-gate failure is evidence: preserve it and stop without rerunning.
- Warm-up is non-counted evidence and must never be merged into formal metrics.
- Do not update the master plan, baseline, regression thresholds, résumé metrics, or final claims during this run.
- Do not run intent `test 500` in this task.

---

### Task 1: Freeze environment, revision, dataset, calibration, and output boundaries

**Files:**
- Read: `.env` without printing values
- Read: `evaluation/dialog_judge.py`
- Read: `evaluation/run_dialog_eval.py`
- Read: `data/eval/runs/dialog-judge-json-fallback-calibration-v4/calibration_results.json`
- Read: `E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json`

**Interfaces:**
- Consumes: committed v4 code, passing calibration evidence, exact model configuration, and frozen dataset.
- Produces: preflight proof that a new formal run is safe to start.

- [ ] **Step 1: Verify Python, branch, implementation ancestry, and tracked cleanliness**

Run each command separately:

```powershell
Set-Location -LiteralPath 'E:\Desktop\简历项目\EchoMind所有代码+简历\EchoMind\.worktrees\task6-dialog-eval'
E:\conda_envs\echomind\python.exe -c "import sys; print({'python':sys.executable,'version':sys.version}); assert sys.executable.lower()==r'E:\conda_envs\echomind\python.exe'.lower(); assert sys.version_info[:2]==(3,12)"
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' branch --show-current
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' rev-parse HEAD
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' merge-base --is-ancestor 95c23733b06c8950a30b681a8a582141614cc2a8 HEAD
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' diff --quiet
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' diff --cached --quiet
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' status --short
```

Expected: branch is `task6-dialog-eval`; implementation commit is an ancestor; tracked tree and index are clean. `status --short` may show only pre-existing untracked `.test-tmp/`; do not touch it.

- [ ] **Step 2: Verify project `.env`, v4 constants, frozen dataset, and calibration evidence**

```powershell
E:\conda_envs\echomind\python.exe -X utf8 -c "import hashlib,json; from pathlib import Path; from dotenv import dotenv_values; from evaluation.dialog_judge import PROMPT_VERSION,JUDGE_OUTPUT_STRATEGY; env=dotenv_values('.env'); assert env.get('ANTHROPIC_API_KEY'); assert env.get('ANTHROPIC_BASE_URL'); assert PROMPT_VERSION=='dialog_judge_v4'; assert JUDGE_OUTPUT_STRATEGY=='forced_tool_then_strict_json_fallback'; d=Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json'); cases=json.loads(d.read_text(encoding='utf-8')); c=json.loads(Path('data/eval/runs/dialog-judge-json-fallback-calibration-v4/calibration_results.json').read_text(encoding='utf-8')); assert hashlib.sha256(d.read_bytes()).hexdigest()=='cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2'; assert len(cases)==35 and sum(len(x['turns']) for x in cases)==43; assert c['passed'] is True and c['external_judge_calls']==2 and c['model']=='deepseek-v4-pro'; print({'prompt_version':PROMPT_VERSION,'judge_output_strategy':JUDGE_OUTPUT_STRATEGY,'dataset_sha256':hashlib.sha256(d.read_bytes()).hexdigest(),'cases':len(cases),'turns':sum(len(x['turns']) for x in cases),'calibration_passed':c['passed'],'project_env_present':True})"
```

Expected: all assertions pass without printing any `.env` value.

- [ ] **Step 3: Verify all new paths are unused**

```powershell
Test-Path -LiteralPath 'data\eval\runs\run_dialog_eval_v4.py'
Test-Path -LiteralPath 'data\eval\runs\dialog-warmup-v4'
Test-Path -LiteralPath 'data\eval\runs\dialog-eval-v4'
Test-Path -LiteralPath 'E:\Desktop\简历项目\echomind-dialog-v4-formal-pytest-temp'
```

Expected: all four values are `False`. If any is `True`, stop without deleting anything.

- [ ] **Step 4: Run the complete test suite in a fresh E-drive temp directory**

Before this command, remove inherited shell variables without printing their values:

```powershell
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_BASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_MODEL -ErrorAction SilentlyContinue
Remove-Item Env:EVAL_JUDGE_MODEL -ErrorAction SilentlyContinue
E:\conda_envs\echomind\python.exe -m pytest tests -q -p no:cacheprovider --basetemp 'E:\Desktop\简历项目\echomind-dialog-v4-formal-pytest-temp'
$LASTEXITCODE
```

Expected: `97 passed`, exit code `0`. Keep the pytest-temp directory afterward; do not delete or reuse it. If tests fail, stop before creating the driver or making API calls.

---

### Task 2: Create and execute the same-process v4 driver exactly once

**Files:**
- Create locally, do not commit: `data/eval/runs/run_dialog_eval_v4.py`
- Create locally, do not commit: `data/eval/runs/dialog-warmup-v4/dialog_predictions.jsonl`
- Create locally, do not commit: `data/eval/runs/dialog-warmup-v4/dialog_metrics.json`
- Create locally, do not commit: `data/eval/runs/dialog-warmup-v4/run_metadata.json`
- Create locally, do not commit: `data/eval/runs/dialog-eval-v4/dialog_predictions.jsonl`
- Create locally, do not commit: `data/eval/runs/dialog-eval-v4/dialog_metrics.json`
- Create locally, do not commit: `data/eval/runs/dialog-eval-v4/run_metadata.json`

**Interfaces:**
- Consumes: `_load_validated_dataset(...)`, `resolve_config(...)`, `_create_dependencies(...)`, and `run_evaluation(...)` from the committed runner.
- Produces: one non-counted warm-up and one fresh formal 35-case run using one shared dependency set.

- [ ] **Step 1: Create `run_dialog_eval_v4.py` using an editing tool**

Create the file with exactly this content:

```python
import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from evaluation.dialog_judge import JUDGE_OUTPUT_STRATEGY, PROMPT_VERSION
from evaluation.run_dialog_eval import (
    _create_dependencies,
    _load_validated_dataset,
    resolve_config,
    run_evaluation,
)


DATASET = Path(r"E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json")
WARMUP_DIR = Path("data/eval/runs/dialog-warmup-v4")
FORMAL_DIR = Path("data/eval/runs/dialog-eval-v4")
EXPECTED_MODEL = "deepseek-v4-pro"
EXPECTED_DATASET_SHA256 = "cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2"
IMPLEMENTATION_REVISION = "95c23733b06c8950a30b681a8a582141614cc2a8"
EXPECTED_CASE_IDS = [f"dialog_eval_{index:03d}" for index in range(1, 36)]


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", f"safe.directory={REPO.resolve().as_posix()}", *args],
        cwd=REPO,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def load_artifacts(directory: Path) -> tuple[list[dict], dict, dict]:
    required = {
        "dialog_predictions.jsonl",
        "dialog_metrics.json",
        "run_metadata.json",
    }
    names = {path.name for path in directory.iterdir() if path.is_file()}
    if names != required:
        raise RuntimeError(f"artifact set mismatch for {directory}: {sorted(names)}")
    rows = [
        json.loads(line)
        for line in (directory / "dialog_predictions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    metrics = json.loads((directory / "dialog_metrics.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "run_metadata.json").read_text(encoding="utf-8"))
    return rows, metrics, metadata


def verify_common(
    rows: list[dict],
    metrics: dict,
    metadata: dict,
    expected_count: int,
    execution_revision: str,
) -> None:
    if len(rows) != expected_count:
        raise RuntimeError("prediction count mismatch")
    if metrics["total_cases"] != expected_count or metadata["case_count"] != expected_count:
        raise RuntimeError("artifact case counts disagree")
    if metadata["dataset_sha256"] != EXPECTED_DATASET_SHA256:
        raise RuntimeError("dataset hash mismatch")
    if metadata["git_revision"] != execution_revision:
        raise RuntimeError("metadata Git revision mismatch")
    if metadata["agent_model"] != EXPECTED_MODEL or metadata["judge_model"] != EXPECTED_MODEL:
        raise RuntimeError("model identity mismatch")
    if metadata["prompt_version"] != "dialog_judge_v4":
        raise RuntimeError("Prompt version mismatch")
    if metadata["judge_output_strategy"] != "forced_tool_then_strict_json_fallback":
        raise RuntimeError("Judge output strategy mismatch")
    if metadata["temperature"] != 0.0 or metadata["max_attempts"] != 3:
        raise RuntimeError("Judge runtime configuration mismatch")
    if metadata["context_mode"] != "controlled_context" or metadata["retrieval_evaluated"] is not False:
        raise RuntimeError("evaluation scope metadata mismatch")
    if metrics["agent_failed_count"] != 0 or metrics["judge_failed_count"] != 0:
        raise RuntimeError("Agent or Judge failure gate failed")
    if metrics["valid_judged_cases"] != expected_count:
        raise RuntimeError("valid judged case count mismatch")
    if any(not turn.get("agent_response", "").strip() for row in rows for turn in row["turns"]):
        raise RuntimeError("blank Agent response found")
    if any(turn.get("judge_skipped") or not turn.get("judge") for row in rows for turn in row["turns"]):
        raise RuntimeError("missing valid Judge result")


def verify_warmup(execution_revision: str) -> None:
    rows, metrics, metadata = load_artifacts(WARMUP_DIR)
    verify_common(rows, metrics, metadata, 1, execution_revision)
    if [row["case_id"] for row in rows] != ["dialog_eval_001"]:
        raise RuntimeError("warm-up case identity mismatch")


def verify_formal(execution_revision: str) -> None:
    rows, metrics, metadata = load_artifacts(FORMAL_DIR)
    verify_common(rows, metrics, metadata, 35, execution_revision)
    if [row["case_id"] for row in rows] != EXPECTED_CASE_IDS:
        raise RuntimeError("formal case IDs/order mismatch")
    if sum(len(row["turns"]) for row in rows) != 43:
        raise RuntimeError("formal turn count mismatch")
    if not 0 <= metrics["pass_rate"] <= 1:
        raise RuntimeError("formal pass rate is invalid")
    if metrics["agent_latency_p95_ms"] > 30000:
        raise RuntimeError("formal Agent p95 latency gate failed")


async def main() -> None:
    if Path(__file__).resolve().parent != (REPO / "data/eval/runs").resolve():
        raise RuntimeError("driver must remain under data/eval/runs")
    if WARMUP_DIR.exists() or FORMAL_DIR.exists():
        raise FileExistsError("warm-up or formal output path already exists")
    if PROMPT_VERSION != "dialog_judge_v4":
        raise RuntimeError("current Prompt version is not dialog_judge_v4")
    if JUDGE_OUTPUT_STRATEGY != "forced_tool_then_strict_json_fallback":
        raise RuntimeError("current Judge strategy is not v4")
    if git("merge-base", "--is-ancestor", IMPLEMENTATION_REVISION, "HEAD", check=False).returncode != 0:
        raise RuntimeError("implementation revision is not an ancestor of HEAD")
    if git("diff", "--quiet", check=False).returncode != 0:
        raise RuntimeError("tracked working tree is not clean")
    if git("diff", "--cached", "--quiet", check=False).returncode != 0:
        raise RuntimeError("index is not clean")
    execution_revision = git("rev-parse", "HEAD").stdout.strip()

    project_env = {
        key: value
        for key, value in dotenv_values(REPO / ".env").items()
        if isinstance(value, str)
    }
    args = SimpleNamespace(
        base_url=None,
        agent_model=EXPECTED_MODEL,
        judge_model=EXPECTED_MODEL,
    )
    config = resolve_config(args, project_env)
    if config["agent_model"] != EXPECTED_MODEL or config["judge_model"] != EXPECTED_MODEL:
        raise RuntimeError("resolved models are not exact expected model")
    if not config["base_url"]:
        raise RuntimeError("project .env base URL is missing")

    cases, dataset_sha256 = _load_validated_dataset(DATASET)
    if dataset_sha256 != EXPECTED_DATASET_SHA256:
        raise RuntimeError("dataset SHA-256 changed")
    if len(cases) != 35 or sum(len(case["turns"]) for case in cases) != 43:
        raise RuntimeError("dataset must contain 35 cases and 43 turns")

    orchestrator, judge = _create_dependencies(config)
    await run_evaluation(
        cases=cases[:1],
        output_dir=WARMUP_DIR,
        orchestrator=orchestrator,
        judge=judge,
        config=config,
        dataset_path=DATASET,
        dataset_sha256=dataset_sha256,
    )
    verify_warmup(execution_revision)

    await run_evaluation(
        cases=cases,
        output_dir=FORMAL_DIR,
        orchestrator=orchestrator,
        judge=judge,
        config=config,
        dataset_path=DATASET,
        dataset_sha256=dataset_sha256,
    )
    verify_formal(execution_revision)
    _, metrics, _ = load_artifacts(FORMAL_DIR)
    print(json.dumps({
        "formal_cases": metrics["total_cases"],
        "valid_judged_cases": metrics["valid_judged_cases"],
        "agent_failed_count": metrics["agent_failed_count"],
        "judge_failed_count": metrics["judge_failed_count"],
        "pass_rate": metrics["pass_rate"],
        "overall_mean": metrics["overall_mean"],
        "agent_latency_p95_ms": metrics["agent_latency_p95_ms"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
```

Do not add resume logic, output deletion, exception suppression, fallback scores, a second dependency construction, or copied v2 predictions.

- [ ] **Step 2: Verify runner syntax and exact source before API execution**

```powershell
E:\conda_envs\echomind\python.exe -m py_compile 'data\eval\runs\run_dialog_eval_v4.py'
$LASTEXITCODE
```

Expected: exit code `0`. This may create ignored `__pycache__`; preserve it.

- [ ] **Step 3: Execute the same-process driver exactly once**

```powershell
E:\conda_envs\echomind\python.exe -X utf8 'data\eval\runs\run_dialog_eval_v4.py'
$formalExitCode = $LASTEXITCODE
$formalExitCode
```

Expected success condition: exit code `0`. Regardless of exit code, do not execute `run_dialog_eval_v4.py` a second time. On failure, preserve all partial artifacts and immediately proceed only to read-only evidence reporting.

---

### Task 3: Audit warm-up and formal artifacts without mutation

**Files:**
- Read: `data/eval/runs/dialog-warmup-v4/*`
- Read: `data/eval/runs/dialog-eval-v4/*`

**Interfaces:**
- Consumes: artifacts from the single driver execution.
- Produces: structural, metric, routing, latency, safety, and human-audit evidence.

- [ ] **Step 1: List artifact sets and sizes**

```powershell
Get-ChildItem -LiteralPath 'data\eval\runs\dialog-warmup-v4' | Select-Object Name,Length,LastWriteTime
Get-ChildItem -LiteralPath 'data\eval\runs\dialog-eval-v4' | Select-Object Name,Length,LastWriteTime
```

Expected after exit `0`: each directory contains exactly `dialog_predictions.jsonl`, `dialog_metrics.json`, and `run_metadata.json`.

- [ ] **Step 2: Verify warm-up identity and separation**

```powershell
E:\conda_envs\echomind\python.exe -X utf8 -c "import hashlib,json; from pathlib import Path; p=Path('data/eval/runs/dialog-warmup-v4'); d=Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json'); rows=[json.loads(x) for x in (p/'dialog_predictions.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]; m=json.loads((p/'dialog_metrics.json').read_text(encoding='utf-8')); meta=json.loads((p/'run_metadata.json').read_text(encoding='utf-8')); assert len(rows)==1==m['total_cases']==meta['case_count']; assert rows[0]['case_id']=='dialog_eval_001'; assert m['agent_failed_count']==0 and m['judge_failed_count']==0 and m['valid_judged_cases']==1; assert meta['prompt_version']=='dialog_judge_v4'; assert meta['judge_output_strategy']=='forced_tool_then_strict_json_fallback'; assert meta['agent_model']==meta['judge_model']=='deepseek-v4-pro'; assert meta['dataset_sha256']==hashlib.sha256(d.read_bytes()).hexdigest(); print({'warmup_case':rows[0]['case_id'],'agent_latency_ms':[t['agent_latency_ms'] for t in rows[0]['turns']],'judge_attempts':[t['judge_attempts'] for t in rows[0]['turns']],'judge_latency_ms':[t['judge']['latency_ms'] for t in rows[0]['turns']]})"
```

- [ ] **Step 3: Enforce formal count, provenance, failure, and latency gates**

```powershell
E:\conda_envs\echomind\python.exe -X utf8 -c "import hashlib,json; from pathlib import Path; p=Path('data/eval/runs/dialog-eval-v4'); d=Path(r'E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json'); rows=[json.loads(x) for x in (p/'dialog_predictions.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]; m=json.loads((p/'dialog_metrics.json').read_text(encoding='utf-8')); meta=json.loads((p/'run_metadata.json').read_text(encoding='utf-8')); expected=[f'dialog_eval_{i:03d}' for i in range(1,36)]; assert [r['case_id'] for r in rows]==expected; assert len(rows)==35==m['total_cases']==meta['case_count']; assert sum(len(r['turns']) for r in rows)==43; assert m['agent_failed_count']==0 and m['judge_failed_count']==0 and m['valid_judged_cases']==35; assert meta['prompt_version']=='dialog_judge_v4'; assert meta['judge_output_strategy']=='forced_tool_then_strict_json_fallback'; assert meta['agent_model']==meta['judge_model']=='deepseek-v4-pro'; assert meta['dataset_sha256']==hashlib.sha256(d.read_bytes()).hexdigest(); assert meta['context_mode']=='controlled_context' and meta['retrieval_evaluated'] is False; assert m['agent_latency_p95_ms']<=30000; assert all(t['agent_response'] and t['agent_response'].strip() and not t['judge_skipped'] and t['judge'] for r in rows for t in r['turns']); text=json.dumps(meta).lower(); assert 'api_key' not in text and 'authorization' not in text; print({'cases':len(rows),'turns':sum(len(r['turns']) for r in rows),'valid':m['valid_judged_cases'],'agent_failed':m['agent_failed_count'],'judge_failed':m['judge_failed_count'],'prompt':meta['prompt_version'],'strategy':meta['judge_output_strategy'],'revision':meta['git_revision'],'dataset_sha256':meta['dataset_sha256'],'agent_p95_ms':m['agent_latency_p95_ms']})"
```

Expected success gate: 35 cases, 43 turns, 35 valid judged cases, zero Agent failures, zero Judge failures, and Agent p95 no greater than 30,000 ms.

- [ ] **Step 4: Print metrics, Judge-attempt distribution, and latency outliers**

```powershell
Get-Content -Raw -Encoding UTF8 'data\eval\runs\dialog-eval-v4\dialog_metrics.json'
E:\conda_envs\echomind\python.exe -X utf8 -c "import json; from collections import Counter; from pathlib import Path; rows=[json.loads(x) for x in Path('data/eval/runs/dialog-eval-v4/dialog_predictions.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]; turns=[t for r in rows for t in r['turns']]; attempts=Counter(t['judge_attempts'] for t in turns); slow=sorted([{'case_id':r['case_id'],'turn_id':t['turn_id'],'agent_latency_ms':t['agent_latency_ms'],'judge_latency_ms':t['judge']['latency_ms'],'judge_attempts':t['judge_attempts']} for r in rows for t in r['turns'] if t['agent_latency_ms']>30000 or t['judge']['latency_ms']>15000],key=lambda x:max(x['agent_latency_ms'],x['judge_latency_ms']),reverse=True); print(json.dumps({'judge_attempt_distribution':dict(sorted(attempts.items())),'latency_outliers':slow},ensure_ascii=False,indent=2))"
```

- [ ] **Step 5: Calculate the separate routing audit**

```powershell
E:\conda_envs\echomind\python.exe -X utf8 -c "import json; from pathlib import Path; rows=[json.loads(x) for x in Path('data/eval/runs/dialog-eval-v4/dialog_predictions.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]; intent=sum(r['routing_audit']['intent_match'] for r in rows); agent=sum(r['routing_audit']['agent_match'] for r in rows); mismatches=[{'case_id':r['case_id'],'expected':r['expected_routing'],'actual':{'intent':r['turns'][0]['intent'],'agent_type':r['turns'][0]['primary_agent']},'audit':r['routing_audit']} for r in rows if not all(r['routing_audit'].values())]; print(json.dumps({'intent_match':intent,'intent_rate':intent/len(rows),'agent_match':agent,'agent_rate':agent/len(rows),'mismatches':mismatches},ensure_ascii=False,indent=2))"
```

Routing remains a separate audit and must not be silently added to `dialog_metrics.json`.

- [ ] **Step 6: Print every low, failed, or routing-mismatched case for later human review**

```powershell
E:\conda_envs\echomind\python.exe -X utf8 -c "import json; from pathlib import Path; rows=[json.loads(x) for x in Path('data/eval/runs/dialog-eval-v4/dialog_predictions.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]; selected=[r for r in rows if r['agent_failed'] or r['judge_failed'] or not all(r['routing_audit'].values()) or r['passed'] is not True or any(t.get('judge') and (t['judge']['accuracy']<1 or t['judge']['completeness']<1 or t['judge']['helpfulness']<1) for t in r['turns'])]; [(print('\n===',r['case_id'],'passed=',r['passed'],'route=',r['routing_audit'],'scores=',r['case_scores'],'==='),[(print('TURN',t['turn_id']),print('USER:',t['user_message']),print('AGENT:',t['agent_response']),print('JUDGE:',t['judge'])) for t in r['turns']]) for r in selected]; print('\nselected_cases=',len(selected))"
```

Do not declare semantic correctness based only on aggregate metrics; Codex will inspect these cases after handoff.

---

### Task 4: Verify immutability and produce the handoff

**Files:**
- Read: Git status, source hashes, v4 artifacts, and historical artifact timestamps/hashes.

**Interfaces:**
- Consumes: all run evidence.
- Produces: one review report; no baseline or documentation mutation.

- [ ] **Step 1: Compute v4 artifact hashes and verify tracked cleanliness**

```powershell
E:\conda_envs\echomind\python.exe -X utf8 -c "import hashlib; from pathlib import Path; paths=[Path('data/eval/runs/run_dialog_eval_v4.py'),*[Path('data/eval/runs/dialog-warmup-v4')/n for n in ('dialog_predictions.jsonl','dialog_metrics.json','run_metadata.json')],*[Path('data/eval/runs/dialog-eval-v4')/n for n in ('dialog_predictions.jsonl','dialog_metrics.json','run_metadata.json')]]; print({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()})"
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' diff --quiet
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' diff --cached --quiet
git -c safe.directory='E:/Desktop/简历项目/EchoMind所有代码+简历/EchoMind/.worktrees/task6-dialog-eval' status --short
```

- [ ] **Step 2: Produce the evidence report and stop**

Report:

1. branch, HEAD, implementation ancestry, and tracked Git cleanliness;
2. Python executable/version and `97 passed` evidence;
3. `.env` source confirmation without values, exact Agent/Judge models, Prompt version, strategy, temperature, and max attempts;
4. dataset/calibration identities and all new driver/warm-up/formal SHA-256 values;
5. exact one-time driver command, saved exit code, start/completion timestamps, and explicit no-rerun statement;
6. warm-up case identity, Agent/Judge latency, Judge attempts, and zero failures;
7. formal case/turn counts, Agent/Judge failure counts, valid denominator, all quality metrics, pass rate, and latency metrics;
8. Judge-attempt distribution and every latency outlier;
9. separate routing counts/rates and every mismatch;
10. every selected low, failed, non-passing, or routing-mismatched case needed for human audit;
11. confirmation that no API key, Authorization value, `.env` value, or secret was persisted or printed;
12. confirmation that no production code, tests, datasets, historical runs, baseline, résumé metric, master plan, `.test-tmp/`, previous pytest-temp directory, or C-drive file was modified or deleted.

Stop after reporting. Do not rerun, repair, delete, update baseline, edit the master plan, or write résumé claims until Codex independently audits the artifacts.
