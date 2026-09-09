#!/usr/bin/env bash
set -uo pipefail

MODE="${1:-}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
SCRIPT_REL="ai-work/executor/operator/WP9-d/wp9d-eval400-unified-verify/C2/run.sh"
EXPECTED_PARENT="8f54a0873c34a75c8140e3f0ddad9d1ff3f6291c"

VERIFIER="/home/dzy/wp9d-verifier-a-f17b4f6"
VERIFIER_COMMIT="f17b4f607daa3bb03b08682bbbd841118d36c4af"
OPEN_R1_COMMIT="1416fa0cf21595d2083b399a2a0bbddd7f6e9563"
DEPENDENCY_LOCK_SHA="4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf"
DATASET_DIR="/home/dzy/wp6d-b-export/required/formal-data/prepared"
DATASET_SHA="770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae"
ORDER_SHA="2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9"
EVAL_CONFIG_SHA="3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3"
PISTON_SHA="f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e"
WORKERS=64
SEED=42

RUN_NAME="wp9d-A-hidden-step300-eval400-b4-p1-seed42"
GENERATION_RUN="/home/dzy/wp9d-recipe-a-eval400-f17b4f6/generation/$RUN_NAME"
GENERATION_RUN_SHA="e2de319a2c629730bc1b0a6f2b15ee29d17868522e2e060b3c7d0a8c0fa9c120"
GENERATION_RECORDS_SHA="8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c"

C0_OP="/home/dzy/wp9d-eval400-operator/WP9-d/wp9d-eval400-unified-verify/C0"
C0_ROOT="/home/dzy/wp9d-eval400-verified/evaluation"
C0_EVIDENCE_SHA="92966897f3b705b11d95736ae47262d7be1ad6a44387342e4d6cd5a876e183e1"
C0_LOG_SHA="c7b1c8c55ba057cee2085e1178ba325b7fe67ff5243f4539949c0a9b756409ee"
C0_FAILED_RESULTS_SHA="a1f5d2b2dbd726edf48a435388b74eef463fb10ab85e1f6c999c80099704663f"

C1_OP="/home/dzy/wp9d-eval400-operator/WP9-d/wp9d-eval400-unified-verify/C1"
C1_ROOT="/home/dzy/wp9d-eval400-repair-c1/evaluation"
C1_RUN="$C1_ROOT/$RUN_NAME"
C1_EVIDENCE_SHA="778b18c4f4e797598159609f79ca6444747347a48cc91feb5d0d451720fc6852"
C1_LOG_SHA="f133b41e87ccafb35afd7edac50ed8cd627fb3e800d5a9e9295ba0488041af0e"
C1_RUN_SHA="bc8bfbfd806e7f372456262429719ab2e30f477155017b6398e872414ec491d5"
C1_RESULTS_SHA="60883c2b8a25c13ac6d92229fab9a74edbac95fc48241f07d48dd073bd82772e"
C1_SUMMARY_SHA="9bebd5a148c4c6a790b4c2d630d2dc3017f5d5a0b9b944082913e238b454bf28"
C1_CSV_SHA="7a4fc952e05e895d9d79cb8b1f9689bc8a56baafcb9c9882945b41e342426ffb"

OUTPUT_ROOT="/home/dzy/wp9d-eval400-stability-c2"
C2_RUN="$OUTPUT_ROOT/evaluation/$RUN_NAME"
FINAL_MANIFEST="$OUTPUT_ROOT/final-verification-manifest.json"
STABILITY_REPORT="$OUTPUT_ROOT/stability-report.json"
OP_ROOT="/home/dzy/wp9d-eval400-operator/WP9-d/wp9d-eval400-unified-verify/C2"
STATUS_FILE="$OP_ROOT/status"
LOG_FILE="$OP_ROOT/terminal.log"
EVIDENCE_FILE="$OP_ROOT/operator-evidence.json"
LOCK_FILE="$OP_ROOT/run.lock"
RUNTIME_PY="/home/dzy/open-r1-code-verifier/.venv/bin/python"

usage() {
  cat >&2 <<'EOF'
usage:
  run.sh preflight
  run.sh adjudicate

required environment:
  WP9D_C2_HANDOFF_COMMIT=<exact committed C2 operator checkpoint>
  WP9D_C2_SCRIPT_SHA256=<sha256 of this tracked run.sh>

C2 is a one-shot full-400 stability adjudication. It preserves C0 and C1 byte-for-byte,
runs a third full Hidden-step300 verification in a fresh namespace, and accepts only if:
  * C2 has zero sandbox/infrastructure errors;
  * C2 reproduces C1 verifier semantics for all 400 rows except runtime_ms;
  * therefore apps-4392 reproduces C1's passed outcome rather than C0's timeout.
If apps-4392 returns to timeout, C2 records the run but does not emit a final manifest.
EOF
  exit 64
}

sha256_file() { sha256sum "$1" | awk '{print $1}'; }
log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE"; }
fail_preflight() { printf 'preflight FAIL: %s\n' "$1" >&2; return 125; }

check_control_identity() {
  local handoff="${WP9D_C2_HANDOFF_COMMIT:-}" expected_sha="${WP9D_C2_SCRIPT_SHA256:-}"
  local head parent actual dirty
  [[ "$handoff" =~ ^[0-9a-f]{40}$ ]] || fail_preflight "set WP9D_C2_HANDOFF_COMMIT" || return $?
  [[ "$expected_sha" =~ ^[0-9a-f]{64}$ ]] || fail_preflight "set WP9D_C2_SCRIPT_SHA256" || return $?
  head="$(git -C "$REPO_ROOT" rev-parse HEAD)" || fail_preflight "cannot resolve control-plane HEAD" || return $?
  parent="$(git -C "$REPO_ROOT" rev-parse HEAD^)" || fail_preflight "cannot resolve C2 parent" || return $?
  [[ "$head" == "$handoff" ]] || fail_preflight "control-plane HEAD mismatch" || return $?
  [[ "$parent" == "$EXPECTED_PARENT" ]] || fail_preflight "C2 parent must be failed C1 checkpoint" || return $?
  actual="$(sha256_file "$REPO_ROOT/$SCRIPT_REL")"
  [[ "$actual" == "$expected_sha" ]] || fail_preflight "tracked C2 script SHA mismatch" || return $?
  dirty="$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=normal | grep -vE '^\?\? \.ai-bridge/' || true)"
  [[ -z "$dirty" ]] || fail_preflight "control-plane worktree must be clean outside .ai-bridge" || return $?
}

check_verifier() {
  local head open_r1 dirty
  head="$(git -C "$VERIFIER" rev-parse HEAD 2>/dev/null)" || fail_preflight "verifier checkout unavailable" || return $?
  [[ "$head" == "$VERIFIER_COMMIT" ]] || fail_preflight "verifier commit mismatch" || return $?
  open_r1="$(git -C "$VERIFIER/third_party/open-r1" rev-parse HEAD 2>/dev/null)" || fail_preflight "Open-R1 checkout unavailable" || return $?
  [[ "$open_r1" == "$OPEN_R1_COMMIT" ]] || fail_preflight "Open-R1 commit mismatch" || return $?
  dirty="$(git -C "$VERIFIER" status --porcelain=v1 --untracked-files=normal --ignore-submodules=none)"
  [[ -z "$dirty" ]] || fail_preflight "verifier checkout is not clean" || return $?
  [[ "$(sha256_file "$VERIFIER/configs/eval/base.yaml")" == "$EVAL_CONFIG_SHA" ]] || fail_preflight "eval config SHA mismatch" || return $?
  [[ "$(sha256_file "$VERIFIER/configs/execution/piston-local.yaml")" == "$PISTON_SHA" ]] || fail_preflight "Piston config SHA mismatch" || return $?
}

check_frozen_lineage() {
  "$RUNTIME_PY" - "$C0_OP" "$C0_ROOT" "$C1_OP" "$C1_RUN" "$GENERATION_RUN" <<'PY_LINEAGE'
import hashlib
import json
import sys
from pathlib import Path
c0_op, c0_root, c1_op, c1_run, generation = map(Path, sys.argv[1:])
RUN = "wp9d-A-hidden-step300-eval400-b4-p1-seed42"

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def rows(path: Path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]

def sandbox(r):
    sk=("execution_status","visible_execution_status","train_hidden_execution_status","eval_hidden_execution_status")
    ck=("visible_failure_counts","train_hidden_failure_counts","eval_hidden_failure_counts")
    return any(r.get(k)=="sandbox_error" for k in sk) or any(isinstance(r.get(k),dict) and r[k].get("sandbox_error",0) for k in ck)

expected={
    c0_op/'operator-evidence.json': '92966897f3b705b11d95736ae47262d7be1ad6a44387342e4d6cd5a876e183e1',
    c0_op/'terminal.log': 'c7b1c8c55ba057cee2085e1178ba325b7fe67ff5243f4539949c0a9b756409ee',
    c0_root/RUN/'samples/results.jsonl': 'a1f5d2b2dbd726edf48a435388b74eef463fb10ab85e1f6c999c80099704663f',
    c1_op/'operator-evidence.json': '778b18c4f4e797598159609f79ca6444747347a48cc91feb5d0d451720fc6852',
    c1_op/'terminal.log': 'f133b41e87ccafb35afd7edac50ed8cd627fb3e800d5a9e9295ba0488041af0e',
    c1_run/'run.json': 'bc8bfbfd806e7f372456262429719ab2e30f477155017b6398e872414ec491d5',
    c1_run/'samples/results.jsonl': '60883c2b8a25c13ac6d92229fab9a74edbac95fc48241f07d48dd073bd82772e',
    c1_run/'summary.json': '9bebd5a148c4c6a790b4c2d630d2dc3017f5d5a0b9b944082913e238b454bf28',
    c1_run/'main_results.csv': '7a4fc952e05e895d9d79cb8b1f9689bc8a56baafcb9c9882945b41e342426ffb',
    generation/'run.json': 'e2de319a2c629730bc1b0a6f2b15ee29d17868522e2e060b3c7d0a8c0fa9c120',
    generation/'samples/generations.jsonl': '8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c',
}
for path,wanted in expected.items():
    if not path.is_file() or sha(path)!=wanted:
        raise SystemExit(f'frozen lineage SHA drift: {path}')
if (c0_op/'status').read_text().strip()!='1' or (c1_op/'status').read_text().strip()!='1':
    raise SystemExit('C0/C1 frozen failure status drifted')
c0e=json.loads((c0_op/'operator-evidence.json').read_text())
c1e=json.loads((c1_op/'operator-evidence.json').read_text())
if (c0e.get('gate_status'),c0e.get('command_rc'),c0e.get('postcheck_rc')) != ('postcheck_failed',0,1):
    raise SystemExit('C0 failure identity drifted')
if (c1e.get('gate_status'),c1e.get('command_rc'),c1e.get('postcheck_rc')) != ('postcheck_failed',0,1):
    raise SystemExit('C1 failure identity drifted')
old=rows(c0_root/RUN/'samples/results.jsonl')
new=rows(c1_run/'samples/results.jsonl')
if len(old)!=400 or len(new)!=400:
    raise SystemExit('C0/C1 row count drifted')
old_bad=[i for i,r in enumerate(old,1) if sandbox(r)]
new_bad=[i for i,r in enumerate(new,1) if sandbox(r)]
if old_bad != [55,59] or new_bad:
    raise SystemExit(f'C0/C1 sandbox fingerprint drifted: old={old_bad} new={new_bad}')
changed=[]
for i,(a,b) in enumerate(zip(old,new),1):
    if i in {55,59}: continue
    aa={k:v for k,v in a.items() if k!='runtime_ms'}
    bb={k:v for k,v in b.items() if k!='runtime_ms'}
    if aa!=bb: changed.append(i)
if changed != [5]:
    raise SystemExit(f'C0/C1 semantic-drift fingerprint changed: {changed}')
r5=new[4]
if r5.get('problem_id')!='apps-4392' or r5.get('eval_hidden_execution_status')!='passed' or r5.get('eval_hidden_pass_rate')!=1.0:
    raise SystemExit('C1 apps-4392 adjudication fingerprint drifted')
print('frozen_lineage_preflight=PASS c0_sandbox_rows=2 c1_sandbox_rows=0 c0_c1_semantic_drift_rows=1 apps4392_c1=passed')
PY_LINEAGE
}

check_bundle() {
  env PYTHONPATH="$VERIFIER/src:$VERIFIER/third_party/open-r1/src" "$RUNTIME_PY" - "$VERIFIER" "$DATASET_DIR" "$GENERATION_RUN" <<'PY_BUNDLE'
import os,sys
from dataclasses import replace
from pathlib import Path
from code_verifier.environment import collect_environment
from code_verifier.evaluation.evaluate import dataset_hash, load_evaluation_config, load_evaluation_problems
from code_verifier.evaluation.staged import load_completed_generation_bundle, load_generation_bundle_source
root,dataset,run=map(Path,sys.argv[1:])
os.chdir(root)
env=collect_environment()
for k,w in {
 'project_commit':'f17b4f607daa3bb03b08682bbbd841118d36c4af',
 'open_r1_commit':'1416fa0cf21595d2083b399a2a0bbddd7f6e9563',
 'dependency_lock_hash':'4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf'}.items():
    if env.get(k)!=w: raise SystemExit(f'verifier environment mismatch: {k}')
source=load_generation_bundle_source(run)
cfg=replace(load_evaluation_config(root/'configs/eval/base.yaml'),dataset_dir=dataset,model_revision=source.model_revision,checkpoint=source.checkpoint)
problems=load_evaluation_problems(cfg)
if len(problems)!=400 or dataset_hash(problems)!='770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae':
    raise SystemExit('eval400 dataset identity mismatch')
identity,records=load_completed_generation_bundle(run,config=cfg,problems=problems,seed=42)
if identity.run_id!=run.name or len(records)!=400 or identity.records_sha256!='8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c':
    raise SystemExit('Hidden300 generation bundle identity mismatch')
print('bundle_preflight=PASS rows=400')
PY_BUNDLE
}

check_piston() {
  env NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost" PYTHONPATH="$VERIFIER/src:$VERIFIER/third_party/open-r1/src" "$RUNTIME_PY" - "$VERIFIER" <<'PY_PISTON'
import os,sys
from pathlib import Path
from code_verifier.execution.piston import PistonExecutor, load_piston_executor_config
root=Path(sys.argv[1]); os.chdir(root)
PistonExecutor(load_piston_executor_config(root/'configs/execution/piston-local.yaml')).validate_runtime()
print('piston_preflight=PASS endpoint=127.0.0.1:2000')
PY_PISTON
}

run_preflight() {
  mkdir -p "$OP_ROOT"
  [[ -x "$RUNTIME_PY" ]] || fail_preflight "runtime Python unavailable" || return $?
  [[ -d "$DATASET_DIR" ]] || fail_preflight "eval400 dataset unavailable" || return $?
  [[ ! -e "$OUTPUT_ROOT" ]] || fail_preflight "C2 output namespace already exists; preserve it and create a new tracked checkpoint if another run is needed" || return $?
  check_control_identity || return $?
  check_verifier || return $?
  check_frozen_lineage || fail_preflight "C0/C1 frozen lineage validation failed" || return $?
  check_bundle || fail_preflight "Hidden300 generation bundle validation failed" || return $?
  check_piston || fail_preflight "Piston runtime acceptance failed" || return $?
  "$RUNTIME_PY" - "$OUTPUT_ROOT" <<'PY_STORAGE'
import shutil,sys
from pathlib import Path
p=Path(sys.argv[1]); p.parent.mkdir(parents=True,exist_ok=True)
if shutil.disk_usage(p.parent).free < 1024**3: raise SystemExit('less than 1 GiB free')
print('storage_preflight=PASS')
PY_STORAGE
  [[ $? -eq 0 ]] || fail_preflight "storage preflight failed" || return $?
  printf 'WP9-d C2 stability preflight PASS: run=%s rows=400 workers=%s output=%s\n' "$RUN_NAME" "$WORKERS" "$OUTPUT_ROOT"
}

write_evidence() {
  local command_rc="$1" postcheck_rc="$2" gate_status="$3" note="$4"
  local end_time head script_sha report_sha manifest_sha run_sha results_sha summary_sha csv_sha
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"; head="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || printf unknown)"
  script_sha="$(sha256_file "$REPO_ROOT/$SCRIPT_REL" 2>/dev/null || true)"
  report_sha=""; manifest_sha=""; run_sha=""; results_sha=""; summary_sha=""; csv_sha=""
  [[ -f "$STABILITY_REPORT" ]] && report_sha="$(sha256_file "$STABILITY_REPORT")"
  [[ -f "$FINAL_MANIFEST" ]] && manifest_sha="$(sha256_file "$FINAL_MANIFEST")"
  [[ -f "$C2_RUN/run.json" ]] && run_sha="$(sha256_file "$C2_RUN/run.json")"
  [[ -f "$C2_RUN/samples/results.jsonl" ]] && results_sha="$(sha256_file "$C2_RUN/samples/results.jsonl")"
  [[ -f "$C2_RUN/summary.json" ]] && summary_sha="$(sha256_file "$C2_RUN/summary.json")"
  [[ -f "$C2_RUN/main_results.csv" ]] && csv_sha="$(sha256_file "$C2_RUN/main_results.csv")"
  "$RUNTIME_PY" - "$EVIDENCE_FILE.tmp" "$head" "$script_sha" "$command_rc" "$postcheck_rc" "$gate_status" "$note" "$START_TIME" "$end_time" "$ATTEMPT_ID" "$report_sha" "$manifest_sha" "$run_sha" "$results_sha" "$summary_sha" "$csv_sha" <<'PY_EVIDENCE'
import json,sys
from pathlib import Path
(out,commit,script_sha,crc,prc,status,note,start,end,attempt,report_sha,manifest_sha,run_sha,results_sha,summary_sha,csv_sha)=sys.argv[1:]
p={
 'schema_version':'wp9d-eval400-hidden300-stability-c2-evidence-v1','operator_handoff_mode':'control_plane_manual',
 'stage_id':'WP9-d','gate_id':'wp9d-eval400-unified-verify','checkpoint_id':'C2','operator_checkpoint_commit':commit,
 'operator_script':'ai-work/executor/operator/WP9-d/wp9d-eval400-unified-verify/C2/run.sh','operator_script_sha256':script_sha,
 'attempt_id':attempt,'started_at':start,'ended_at':end,'command_rc':int(crc),'postcheck_rc':int(prc),'gate_status':status,'note':note,
 'repair_policy':'third_full_400_stability_adjudication','verification_workers':64,'seed':42,
 'source_c0_operator_commit':'8717f6032c27117facbd996b7bce3ba8ec328143','source_c0_evidence_sha256':'92966897f3b705b11d95736ae47262d7be1ad6a44387342e4d6cd5a876e183e1',
 'source_c1_operator_commit':'8f54a0873c34a75c8140e3f0ddad9d1ff3f6291c','source_c1_evidence_sha256':'778b18c4f4e797598159609f79ca6444747347a48cc91feb5d0d451720fc6852',
 'source_c1_results_sha256':'60883c2b8a25c13ac6d92229fab9a74edbac95fc48241f07d48dd073bd82772e',
 'generation_records_sha256':'8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c',
 'stability_report_sha256':report_sha or None,'final_manifest_sha256':manifest_sha or None,
 'c2_run_json_sha256':run_sha or None,'c2_results_sha256':results_sha or None,'c2_summary_sha256':summary_sha or None,'c2_main_results_sha256':csv_sha or None,
 'acceptance_rule':'zero sandbox errors and C2 semantic equality with C1 for all 400 rows excluding runtime_ms; apps-4392 must therefore reproduce C1 passed outcome',
 'dataset_sha256':'770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae','ordered_problem_ids_sha256':'2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9',
 'piston_config_sha256':'f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e','verifier_project_commit':'f17b4f607daa3bb03b08682bbbd841118d36c4af'}
Path(out).write_text(json.dumps(p,indent=2,sort_keys=True)+'\n',encoding='utf-8')
PY_EVIDENCE
  mv "$EVIDENCE_FILE.tmp" "$EVIDENCE_FILE"
  local final_rc=1
  if [[ "$gate_status" == passed && "$command_rc" == 0 && "$postcheck_rc" == 0 ]]; then final_rc=0
  elif [[ "$command_rc" =~ ^[0-9]+$ ]] && (( command_rc > 0 && command_rc < 126 )); then final_rc="$command_rc"; fi
  printf '%s\n' "$final_rc" >"$STATUS_FILE.tmp"; mv "$STATUS_FILE.tmp" "$STATUS_FILE"
  log "attempt=$ATTEMPT_ID end command_rc=$command_rc postcheck_rc=$postcheck_rc gate_status=$gate_status note=$note"
  return "$final_rc"
}

run_verification() {
  local rc
  log "C2 verify start run=$RUN_NAME workers=$WORKERS output=$OUTPUT_ROOT"
  (
    cd "$VERIFIER" || exit 125
    env NO_PROXY="127.0.0.1,localhost" no_proxy="127.0.0.1,localhost" PYTHONPATH="$VERIFIER/src:$VERIFIER/third_party/open-r1/src" \
      "$RUNTIME_PY" -m code_verifier.cli verify-eval --config "$VERIFIER/configs/eval/base.yaml" --dataset-dir "$DATASET_DIR" \
      --generation-run-dir "$GENERATION_RUN" --run-name "$RUN_NAME" --seed "$SEED" --workers "$WORKERS" --output-dir "$OUTPUT_ROOT"
  ) 2>&1 | tee -a "$LOG_FILE"
  rc=${PIPESTATUS[0]}; log "C2 verify end rc=$rc"; [[ "$rc" -eq 0 ]] || return "$rc"
  log "C2 aggregate start"
  (
    cd "$VERIFIER" || exit 125
    env PYTHONPATH="$VERIFIER/src:$VERIFIER/third_party/open-r1/src" "$RUNTIME_PY" -m code_verifier.cli aggregate-eval --run-dir "$C2_RUN" --seed "$SEED"
  ) 2>&1 | tee -a "$LOG_FILE"
  rc=${PIPESTATUS[0]}; log "C2 aggregate end rc=$rc"; return "$rc"
}

strict_postcheck() {
  local checkpoint_commit; checkpoint_commit="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  "$RUNTIME_PY" - "$C0_ROOT" "$C1_RUN" "$C2_RUN" "$GENERATION_RUN" "$STABILITY_REPORT" "$FINAL_MANIFEST" "$checkpoint_commit" <<'PY_POST'
import csv,hashlib,json,math,os,sys,tempfile
from pathlib import Path
c0_root,c1,c2,generation,report_path,manifest_path=map(Path,sys.argv[1:7]); checkpoint=sys.argv[7]
RUN='wp9d-A-hidden-step300-eval400-b4-p1-seed42'; A='f17b4f607daa3bb03b08682bbbd841118d36c4af'; B='07ccc71968bedc25b1a8fd15aa0ee35a75e05389'
DATA='770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae'; ORDER='2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9'; PISTON='f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e'; DEP='4cd4ee4e9dacbaf6531c346e4c032485ffa7d22b7714538bd8bf4a5beace3acf'; OPEN='1416fa0cf21595d2083b399a2a0bbddd7f6e9563'
CLEAN={
'wp9d-B-eval400-b4-p1-seed42':(B,'a7816b606504e0c45d19c1a684533cfc9dc28c1f01f6e1b0fd13886090eed232','adad4e09f79e92d74c8438db66bb77e8b6a688d1aa91f7e6b03927fcc851fd3a','e2284c2f30dd691c0abdd6f752d8ab0c9f0f60eed394ab7c399c733e60816327','5c7471bb5a4e1d0e81ce8a8c0a1918fbd6659d14df52f8c01bce05bb95419487'),
'wp9d-A-public-step300-eval400-b4-p1-seed42':(A,'2f78060d3d7d6e08bb455d9dd7d0306edfeeeb9c0d5d67aebb122f0a44718968','671a1fc6a2691b3c9e22baa94d284865bc8ccbce027f5e4e8161b11dc6b201d9','0e544be88e1fce9778a0645ef2944f7bf8f771be1be4715dcbd6bda59a98b8c1','31ead1304714d9271c0505bf37009991656543fe3c9c3c18a147f129fc807fc8'),
'wp9d-A-public-step600-eval400-b4-p1-seed42':(A,'d6a57674530a3021d1cdba5eabcf72e2873ad1855af7b005ecb23645b02eefda','e4fea29ab783c59c251f4d642e74269cbbf065b8c08155afbe39e82c65800e38','6e41c45d8204286c48a082cc7e2a9d0daaf2dbb1d1ddd3d4816cc2c6c56883cb','d48a3df5cf5a3d1d9ddc0f15e178f331f8f6d3cb047e224af87bdb41e05d16d8'),
'wp9d-A-public-step900-eval400-b4-p1-seed42':(A,'6048d4025a6474597710a79c8a3bbb41acd41de412f729b8f764745b9be9679b','eb4e30828eec4d658b0f38222a55149e8e8bd78405ded189f6b2d0beff8815fa','0e7bf455f2e226cfd1b78a4b2c535bf724a66d8539a61eb486f7a4481b0ee076','8ee1a9c45a180aa5052c3367b5b26d30b344c5a33475c4a831429ae5c197afda'),
'wp9d-A-public-step1200-eval400-b4-p1-seed42':(A,'2e53cfb3a30b17db45fe0f5ce6449d153a3f750ee656c095f61afb7e917ac6fb','56dea4eb7b338febd87ea4575c136e3cc7ee5dacae792796bcee19fa548369fc','9541d0a44119efa142d453c18abb13a030bf1adf20d16af77659e04f81fe23ce','f5f7e5d2563d6bef0630bc2150f2ab80169d2c280c7bb07e93369072874ff975'),
'wp9d-A-hidden-step600-eval400-b4-p1-seed42':(A,'312ca538dac43120ad150a27d38a390d99134ffe06625f2adf99a9ec1d0ecd27','72625da6e7bd11e314fa202d77b421cae764eab06347d23ad2209fa28cb307de','5ef4a60ee05bc331febc3917cebef4d07558962d0bc6c184302c79e3fa6f2810','2770c0e2f8c2ccb4e678c0bc5bc1bbdd85df08c63c215b5bc3ad88d7498a4a41'),
'wp9d-A-hidden-step900-eval400-b4-p1-seed42':(A,'6c168ff63d7d47423e0644efe8a63f05f91c82b24d2f1b1f2665e477466d2003','274abdb79b2ad155ec8c81c4c81605299862e0f4a1ee38e247d6cc7730b35b75','17a5bc175a7ecb113e782130930191ae27641c76620899e1d8b4618baadd5cb7','81bc72937f988c9b212fbff30c7f57ebc3433771d933b5b07ea4b8f16c2d9fe6'),
'wp9d-A-hidden-step1200-eval400-b4-p1-seed42':(A,'80ace33594992ef73c7522c8a1dc0c924fbeb2b23e8d1277bb1e9804c3c78b49','fc06ddd7aa58b883a11bf044069440d3341b6ddd2ba34e08514eb3db0910c397','844bd4d0d4e687c3176ee228e83b23e6c69364005947535693c48fb0e21aa482','dcbf954491bfb8fd87e6fb198fb1b7e64b49ba09a2964eb7347ee3c44b4f8c44')}
SK=('execution_status','visible_execution_status','train_hidden_execution_status','eval_hidden_execution_status'); CK=('visible_failure_counts','train_hidden_failure_counts','eval_hidden_failure_counts'); GP=('problem_id','prompt_hash','completion','completion_tokens','generation_latency_ms','hit_max_new_tokens')
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
 return h.hexdigest()
def rows(p): return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def sandbox(r): return any(r.get(k)=='sandbox_error' for k in SK) or any(isinstance(r.get(k),dict) and r[k].get('sandbox_error',0) for k in CK)
def finite(v):
 if v is None or isinstance(v,(str,bool,int)): return True
 if isinstance(v,float): return math.isfinite(v)
 if isinstance(v,list): return all(finite(x) for x in v)
 if isinstance(v,dict): return all(isinstance(k,str) and finite(x) for k,x in v.items())
 return False
def aggregate(run,project):
 s=json.loads((run/'summary.json').read_text());
 if not finite(s) or s.get('run_id')!=run.name or s.get('project_commit')!=project or s.get('dataset_hash')!=DATA or s.get('seed')!=42 or s.get('bootstrap')!={'seed':42,'resamples':10000,'confidence_level':0.95}: raise SystemExit(f'aggregate identity mismatch: {run.name}')
 m=s.get('metrics');
 if not isinstance(m,dict) or m.get('total_problems')!=400: raise SystemExit(f'aggregate metrics invalid: {run.name}')
 with (run/'main_results.csv').open(newline='',encoding='utf-8') as f: cr=list(csv.DictReader(f))
 if len(cr)!=1 or cr[0].get('run_id')!=run.name: raise SystemExit(f'csv identity mismatch: {run.name}')
 return m
for p in (c2/'run.json',c2/'samples/results.jsonl',c2/'summary.json',c2/'main_results.csv'):
 if not p.is_file() or p.stat().st_size==0: raise SystemExit(f'missing C2 artifact: {p}')
meta=json.loads((c2/'run.json').read_text())
for k,w in {'status':'completed','run_id':RUN,'command':'code-verifier verify-eval','seed':42,'verification_workers':64,'project_commit':A,'open_r1_commit':OPEN,'dependency_lock_hash':DEP,'dataset_hash':DATA,'piston_config_sha256':PISTON,'generation_bundle_records_sha256':'8acc2d875b493db09b886293e5eaba1ed64a94c800e37e79545d65472a652d5c','generation_bundle_ordered_problem_ids_sha256':ORDER,'generation_batch_size':4}.items():
 if meta.get(k)!=w: raise SystemExit(f'C2 run identity mismatch: {k}')
gen=rows(generation/'samples/generations.jsonl'); r1=rows(c1/'samples/results.jsonl'); r2=rows(c2/'samples/results.jsonl')
if not (len(gen)==len(r1)==len(r2)==400): raise SystemExit('C1/C2/generation row count mismatch')
if [r.get('problem_id') for r in r2] != [r.get('problem_id') for r in gen] or len({r.get('problem_id') for r in r2})!=400: raise SystemExit('C2 order/uniqueness mismatch')
for i,(g,r) in enumerate(zip(gen,r2),1):
 for k in GP:
  if r.get(k)!=g.get(k): raise SystemExit(f'C2 generation payload drift row={i} field={k}')
if any(sandbox(r) for r in r2):
 bad=[(i,r.get('problem_id')) for i,r in enumerate(r2,1) if sandbox(r)]; raise SystemExit(f'C2 sandbox/infrastructure failure rows={bad}')
semantic_changed=[]
for i,(a,b) in enumerate(zip(r1,r2),1):
 aa={k:v for k,v in a.items() if k!='runtime_ms'}; bb={k:v for k,v in b.items() if k!='runtime_ms'}
 if aa!=bb: semantic_changed.append(i)
r5=r2[4]
report={'schema_version':'wp9d-hidden300-stability-report-v1','c2_checkpoint_commit':checkpoint,'c1_results_sha256':'60883c2b8a25c13ac6d92229fab9a74edbac95fc48241f07d48dd073bd82772e','c2_results_sha256':sha(c2/'samples/results.jsonl'),'sandbox_error_rows':0,'c1_c2_semantic_changed_rows':semantic_changed,'apps_4392':{'row':5,'problem_id':r5.get('problem_id'),'execution_status':r5.get('execution_status'),'eval_hidden_execution_status':r5.get('eval_hidden_execution_status'),'eval_hidden_pass_rate':r5.get('eval_hidden_pass_rate')},'acceptance_rule':'C2 must reproduce C1 semantics for all 400 rows excluding runtime_ms; apps-4392 must reproduce C1 passed outcome','accepted':semantic_changed==[] and r5.get('problem_id')=='apps-4392' and r5.get('eval_hidden_execution_status')=='passed' and r5.get('eval_hidden_pass_rate')==1.0}
report_content=json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n'; report_path.parent.mkdir(parents=True,exist_ok=True)
report_path.write_text(report_content,encoding='utf-8')
if not report['accepted']:
 raise SystemExit(f'C2 stability adjudication did not reproduce C1: semantic_changed_rows={semantic_changed} apps4392={report["apps_4392"]}')
metrics2=aggregate(c2,A); manifest=[]
for name,(project,runsha,resha,sumsha,csvsha) in CLEAN.items():
 run=c0_root/name; actual=(sha(run/'run.json'),sha(run/'samples/results.jsonl'),sha(run/'summary.json'),sha(run/'main_results.csv'))
 if actual!=(runsha,resha,sumsha,csvsha): raise SystemExit(f'C0 clean artifact drift: {name}')
 rr=rows(run/'samples/results.jsonl');
 if len(rr)!=400 or any(sandbox(x) for x in rr): raise SystemExit(f'C0 clean result no longer clean: {name}')
 m=aggregate(run,project); manifest.append({'run_name':name,'source':'C0_clean','verifier_project_commit':project,'run_json_sha256':runsha,'results_sha256':resha,'summary_sha256':sumsha,'main_results_sha256':csvsha,'metrics':{k:m[k] for k in ('visible_pass@1','train_hidden_pass@1','eval_hidden_pass@1','eval_hidden_average_test_pass_rate','runtime_error_rate','parse_success_rate')}})
manifest.append({'run_name':RUN,'source':'C2_stability_confirmed_full_400','verifier_project_commit':A,'run_json_sha256':sha(c2/'run.json'),'results_sha256':sha(c2/'samples/results.jsonl'),'summary_sha256':sha(c2/'summary.json'),'main_results_sha256':sha(c2/'main_results.csv'),'metrics':{k:metrics2[k] for k in ('visible_pass@1','train_hidden_pass@1','eval_hidden_pass@1','eval_hidden_average_test_pass_rate','runtime_error_rate','parse_success_rate')}}); manifest.sort(key=lambda x:x['run_name'])
payload={'schema_version':'wp9d-eval400-final-verification-manifest-v2','c2_checkpoint_commit':checkpoint,'repair_policy':'third_full_400_stability_adjudication','source_c0_operator_commit':'8717f6032c27117facbd996b7bce3ba8ec328143','source_c1_operator_commit':'8f54a0873c34a75c8140e3f0ddad9d1ff3f6291c','apps_4392_adjudication':'C1_passed_and_C2_passed; C0_timeout_classified_transient','dataset_sha256':DATA,'ordered_problem_ids_sha256':ORDER,'piston_config_sha256':PISTON,'verification_workers':64,'seed':42,'bundle_count':9,'result_count':3600,'sandbox_error_rows':0,'runs':manifest}
content=json.dumps(payload,indent=2,sort_keys=True,allow_nan=False)+'\n'; manifest_path.write_text(content,encoding='utf-8')
print('formal_c2_postcheck=PASS bundles=9 records=3600 repaired_run=hidden-step300 c1_c2_semantic_drift=0 apps4392=passed_twice sandbox_errors=0 aggregation=PASS')
PY_POST
}

run_adjudicate() {
  mkdir -p "$OP_ROOT"; exec 9>"$LOCK_FILE"
  if ! flock -n 9; then echo "operator lock is already held: $LOCK_FILE" >&2; exit 73; fi
  ATTEMPT_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"; START_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [[ -f "$STATUS_FILE" ]]; then cp -a "$STATUS_FILE" "$OP_ROOT/status.before-$ATTEMPT_ID"; fi
  if [[ -f "$EVIDENCE_FILE" ]]; then cp -a "$EVIDENCE_FILE" "$OP_ROOT/operator-evidence.before-$ATTEMPT_ID.json"; fi
  rm -f "$STATUS_FILE.tmp" "$EVIDENCE_FILE.tmp"
  log "attempt=$ATTEMPT_ID start checkpoint=C2 stability_adjudication run=$RUN_NAME workers=$WORKERS"
  run_preflight >>"$LOG_FILE" 2>&1; local rc=$?
  if [[ "$rc" -ne 0 ]]; then write_evidence 125 125 preflight_failed "C2 stability preflight failed"; exit $?; fi
  log "preflight PASS"
  run_verification; rc=$?
  if [[ "$rc" -ne 0 ]]; then write_evidence "$rc" 125 command_failed "C2 verify-eval/aggregate-eval failed"; exit $?; fi
  log "strict C2 postcheck start"
  strict_postcheck 2>&1 | tee -a "$LOG_FILE"; rc=${PIPESTATUS[0]}
  if [[ "$rc" -ne 0 ]]; then write_evidence 0 "$rc" postcheck_failed "C2 stability adjudication did not meet predeclared acceptance rule"; exit $?; fi
  log "strict C2 postcheck PASS"
  write_evidence 0 0 passed "C2 full-400 Hidden300 reproduced C1 semantics with zero sandbox errors; apps-4392 passed twice after C0 timeout; final 9-run manifest accepted"
  exit $?
}

case "$MODE" in
  preflight) mkdir -p "$OP_ROOT"; run_preflight ;;
  adjudicate) run_adjudicate ;;
  *) usage ;;
esac
