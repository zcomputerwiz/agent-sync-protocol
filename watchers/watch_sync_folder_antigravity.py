#!/usr/bin/env python3
"""Event-driven watcher for D:\ProjectSync using filesystem change detection."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

WATCH_DIR = Path("D:/ProjectSync")
IGNORE_NAMES = {
    ".stfolder",
    ".stversions",
    "AGENT_ANTIGRAVITY.md",
    "JOB_STATUS_AMPERE.md",
    "STOP_READ_FIRST.md",
    "STOP_READ_FIRST.md.sha256",
    "WATCHER_SETUP_GUIDE.md",
    "WATCHER_SETUP_GUIDE.md.sha256",
    "REQUEST_BENCHMARK_TASKS.md",
    "REQUEST_BENCHMARK_TASKS.md.sha256",
    "BENCHMARK_TASKS_TURING.md",
    "BENCHMARK_TASKS_TURING.md.sha256",
    "_selftest.md",
    "_selftest.md.sha256",
    "TASK_GEMINI_KERNEL_REGISTRATION.md",
    "TASK_GEMINI_KERNEL_REGISTRATION.md.sha256",
    "COORDINATION_PROTOCOL_DRAFT.md",
    "COORDINATION_PROTOCOL_DRAFT.md.sha256",
    "report_benchmarks_turing_rtx2070.md",
    "report_benchmarks_turing_rtx2070.md.sha256",
    "REVIEW_TURING_BENCHMARKS.md",
    "REVIEW_TURING_BENCHMARKS.md.sha256",
    "REPLY_CLAUDE_TASK_ROUTING.md",
    "REPLY_CLAUDE_TASK_ROUTING.md.sha256",
    "sequential_task_v1_sample.json",
    "sequential_task_v1_sample.json.sha256",
    "TASK_GEMINI_SHORTCUT_AUDIT.md",
    "TASK_GEMINI_SHORTCUT_AUDIT.md.sha256",
    "GPU_WORK_AVAILABLE_TURING.md",
    "GPU_WORK_AVAILABLE_TURING.md.sha256",
    "report_exp1_shortcut_audit.md",
    "report_exp1_shortcut_audit.md.sha256",
    "sequential_task_v2_sample.json",
    "sequential_task_v2_sample.json.sha256",
    "REPLY_AUDIT_V2.md",
    "REPLY_AUDIT_V2.md.sha256",
    "report_exp1_v2_re_audit.md",
    "report_exp1_v2_re_audit.md.sha256",
    "REPLY_AUDIT_V2_FLOOR.md",
    "REPLY_AUDIT_V2_FLOOR.md.sha256",
    "report_rwkv7_kernel_registration_benchmarks.md",
    "report_rwkv7_kernel_registration_benchmarks.md.sha256",
    "REPLY_KERNEL_REGISTRATION.md",
    "REPLY_KERNEL_REGISTRATION.md.sha256",
    "NOTE_REPLICATION_INSTRUCTIONS.md",
    "NOTE_REPLICATION_INSTRUCTIONS.md.sha256",
    "prototype_custom_op.py",
    "prototype_custom_op.py.sha256",
    "reproduce_dynamo_breaks.py",
    "reproduce_dynamo_breaks.py.sha256",
    "VERIFY_BREAKS_ON_ADA.md",
    "VERIFY_BREAKS_ON_ADA.md.sha256",
    "reproduce_grouped_dispatch_and_profile.py",
    "reproduce_grouped_dispatch_and_profile.py.sha256",
    "TASK_GEMINI_OVERFIT_GATE.md",
    "TASK_GEMINI_OVERFIT_GATE.md.sha256",
    "overfit_gate_turing.json",
    "overfit_gate_turing.json.sha256",
    "BUG_SEED_QUEUE_RUNID_GUARD.md",
    "BUG_SEED_QUEUE_RUNID_GUARD.md.sha256",
    "TASK_GEMINI_BUDGET_SIZING.md",
    "TASK_GEMINI_BUDGET_SIZING.md.sha256",
    "REPLY_RUNID_GUARD_STATUS_AMPERE.md",
    "REPLY_RUNID_GUARD_STATUS_AMPERE.md.sha256",
    "REPLY_AMPERE_RUNID_CROSSCHECK.md",
    "REPLY_AMPERE_RUNID_CROSSCHECK.md.sha256",
    "TASK_GEMINI_SYNC_BARRIER.md",
    "TASK_GEMINI_SYNC_BARRIER.md.sha256",
    "eval_n36_seed_44.json",
    "eval_n36_seed_44.json.sha256",
    "rwkv_len6_N36_fmt_mix_50_50_cd865b1f9c9b1089.json",
    "rwkv_len6_N36_fmt_mix_50_50_cd865b1f9c9b1089.json.sha256",
    "REPLY_AMPERE_SEED44_AUC.md",
    "REPLY_AMPERE_SEED44_AUC.md.sha256",
    "eval_rwkv_n36_seed_44.json",
    "eval_rwkv_n36_seed_44.json.sha256",
    "REPLY_AUC_AND_NAMING_UPDATE.md",
    "REPLY_AUC_AND_NAMING_UPDATE.md.sha256",
    "CONFIRM_AUC_CROSSCHECK.md",
    "CONFIRM_AUC_CROSSCHECK.md.sha256",
    "budget_sizing_turing.json",
    "budget_sizing_turing.json.sha256",
    "report_exp1_budget_sizing_turing.md",
    "report_exp1_budget_sizing_turing.md.sha256",
    "report_sync_barrier_benchmarks_turing.md",
    "report_sync_barrier_benchmarks_turing.md.sha256",
    "TASK_GEMINI_NULL_DIAGNOSIS.md",
    "TASK_GEMINI_NULL_DIAGNOSIS.md.sha256",
    "exp1_budget_sizing.py",
    "exp1_budget_sizing.py.sha256",
    "ADDENDUM_NULL_DIAGNOSIS.md",
    "ADDENDUM_NULL_DIAGNOSIS.md.sha256",
    "report_control_memorization_turing.md",
    "report_control_memorization_turing.md.sha256",
    "REPLY_CONTROL_PASSED.md",
    "REPLY_CONTROL_PASSED.md.sha256",
    "density_sweep_turing.json",
    "density_sweep_turing.json.sha256",
    "report_exp1_density_sweep_turing.md",
    "report_exp1_density_sweep_turing.md.sha256",
    "REPLY_DENSITY_SWEEP.md",
    "REPLY_DENSITY_SWEEP.md.sha256",
    "AGENT_OPENCODE_DIJKSTRA.md",
    "AGENT_OPENCODE_DIJKSTRA.md.sha256",
    "TASK_OPENCODE_FLOOR_RECONCILIATION.md",
    "TASK_OPENCODE_FLOOR_RECONCILIATION.md.sha256",
    "compute_floors_dijkstra.py",
    "compute_floors_dijkstra.py.sha256",
    "REPORT_FLOOR_RECONCILIATION_DIJKSTRA.md",
    "REPORT_FLOOR_RECONCILIATION_DIJKSTRA.md.sha256",
    "VERIFIED_FLOOR_AND_REVISED_DENSITY.md",
    "VERIFIED_FLOOR_AND_REVISED_DENSITY.md.sha256",
    "eval_n36_seed_45.json",
    "eval_n36_seed_45.json.sha256",
    "eval_rwkv_n36_seed_45.json",
    "eval_rwkv_n36_seed_45.json.sha256",
    "rwkv_len6_N36_fmt_mix_50_50_cf9e58a1052dc20a.json",
    "rwkv_len6_N36_fmt_mix_50_50_cf9e58a1052dc20a.json.sha256",
    "REPLY_SEED45_STATUS_AMPERE.md",
    "REPLY_SEED45_STATUS_AMPERE.md.sha256",
    "audit_budget_shortfall_dijkstra.py",
    "audit_budget_shortfall_dijkstra.py.sha256",
    "REPORT_BUDGET_SIZING_AUDIT_DIJKSTRA.md",
    "REPORT_BUDGET_SIZING_AUDIT_DIJKSTRA.md.sha256",
    "VERIFIED_AUDIT_AND_REJECTION_CONFOUND.md",
    "VERIFIED_AUDIT_AND_REJECTION_CONFOUND.md.sha256",
    "sequential_task.py",
    "sequential_task.py.sha256",
    "REPLY_GENERATOR_PROVENANCE_TURING.md",
    "REPLY_GENERATOR_PROVENANCE_TURING.md.sha256",
    "CLOSED_REPRODUCIBILITY_GAP.md",
    "CLOSED_REPRODUCIBILITY_GAP.md.sha256",
    "TASK_OPENCODE_POWER_AND_IDENTITY.md",
    "TASK_OPENCODE_POWER_AND_IDENTITY.md.sha256",
    "zero_distractor_budget_turing.json",
    "zero_distractor_budget_turing.json.sha256",
    "report_exp1_zero_distractor_budget_turing.md",
    "report_exp1_zero_distractor_budget_turing.md.sha256",
    "REPLY_ZERO_DISTRACTOR_BUDGET.md",
    "REPLY_ZERO_DISTRACTOR_BUDGET.md.sha256",
    "REPLY_CLIFF_SEARCH_LAUNCHED_TURING.md",
    "REPLY_CLIFF_SEARCH_LAUNCHED_TURING.md.sha256",
    "CAUTION_PLATEAU_EARLY_STOP.md",
    "CAUTION_PLATEAU_EARLY_STOP.md.sha256",
    "exp1_depth_cliff_sweep.py",
    "exp1_depth_cliff_sweep.py.sha256",
    "NOTE_CLIFF_SWEEP_FLOOR_FIELD.md",
    "NOTE_CLIFF_SWEEP_FLOOR_FIELD.md.sha256",
    "compute_power_k5_dijkstra.py",
    "compute_power_k5_dijkstra.py.sha256",
    "REPORT_SEED_STUDY_POWER_DIJKSTRA.md",
    "REPORT_SEED_STUDY_POWER_DIJKSTRA.md.sha256",
    "PREREGISTRATION_0B_SEED_STUDY.md",
    "PREREGISTRATION_0B_SEED_STUDY.md.sha256",
    "PUB_SMOKE_TEST.md",
    "PUB_SMOKE_TEST.md.sha256",
    "NOTE_AUTHOR_IN_OUTBOX.md",
    "NOTE_AUTHOR_IN_OUTBOX.md.sha256",
    "audit_runid_identity_dijkstra.py",
    "audit_runid_identity_dijkstra.py.sha256",
    "REPORT_RUNID_IDENTITY_AUDIT_DIJKSTRA.md",
    "REPORT_RUNID_IDENTITY_AUDIT_DIJKSTRA.md.sha256",
    "REPLY_RUNID_AUDIT_FIXES_LANDED.md",
    "REPLY_RUNID_AUDIT_FIXES_LANDED.md.sha256",
    "INTEGRATION_CLAUDE_CODE.md",
    "INTEGRATION_CLAUDE_CODE.md.sha256",
    "watch_sync_folder_claudecode.py",
    "watch_sync_folder_claudecode.py.sha256",
    "FINDING_EVAL_BATCH_DEPENDENCE.md",
    "FINDING_EVAL_BATCH_DEPENDENCE.md.sha256",
    "eval_rwkv_n36_seed_42_epoch_001.json",
    "eval_rwkv_n36_seed_42_epoch_001.json.sha256",
    "eval_rwkv_n36_seed_42_epoch_002.json",
    "eval_rwkv_n36_seed_42_epoch_002.json.sha256",
    "eval_rwkv_n36_seed_42_epoch_003.json",
    "eval_rwkv_n36_seed_42_epoch_003.json.sha256",
    "eval_rwkv_n36_seed_42_epoch_004.json",
    "eval_rwkv_n36_seed_42_epoch_004.json.sha256",
    "eval_rwkv_n36_seed_42_epoch_005.json",
    "eval_rwkv_n36_seed_42_epoch_005.json.sha256",
    "REQUEST_PER_EPOCH_EVALS.md",
    "REQUEST_PER_EPOCH_EVALS.md.sha256",
    "eval_rwkv_n36_seed_44_epoch_001.json",
    "eval_rwkv_n36_seed_44_epoch_001.json.sha256",
    "eval_rwkv_n36_seed_44_epoch_002.json",
    "eval_rwkv_n36_seed_44_epoch_002.json.sha256",
    "eval_rwkv_n36_seed_44_epoch_003.json",
    "eval_rwkv_n36_seed_44_epoch_003.json.sha256",
    "eval_rwkv_n36_seed_44_epoch_004.json",
    "eval_rwkv_n36_seed_44_epoch_004.json.sha256",
    "eval_rwkv_n36_seed_44_epoch_005.json",
    "eval_rwkv_n36_seed_44_epoch_005.json.sha256",
    "eval_rwkv_n36_seed_45_epoch_001.json",
    "eval_rwkv_n36_seed_45_epoch_001.json.sha256",
    "eval_rwkv_n36_seed_45_epoch_002.json",
    "eval_rwkv_n36_seed_45_epoch_002.json.sha256",
    "eval_rwkv_n36_seed_45_epoch_003.json",
    "eval_rwkv_n36_seed_45_epoch_003.json.sha256",
    "eval_rwkv_n36_seed_45_epoch_004.json",
    "eval_rwkv_n36_seed_45_epoch_004.json.sha256",
    "eval_rwkv_n36_seed_45_epoch_005.json",
    "eval_rwkv_n36_seed_45_epoch_005.json.sha256",
    "eval_rwkv_n36_seed_46_epoch_001.json",
    "eval_rwkv_n36_seed_46_epoch_001.json.sha256",
    "eval_rwkv_n36_seed_46_epoch_002.json",
    "eval_rwkv_n36_seed_46_epoch_002.json.sha256",
    "eval_rwkv_n36_seed_46_epoch_003.json",
    "eval_rwkv_n36_seed_46_epoch_003.json.sha256",
    "eval_rwkv_n36_seed_46_epoch_004.json",
    "eval_rwkv_n36_seed_46_epoch_004.json.sha256",
    "eval_rwkv_n36_seed_46_epoch_005.json",
    "eval_rwkv_n36_seed_46_epoch_005.json.sha256",
    "REPLY_PER_EPOCH_EVALS_PUBLISHED_AMPERE.md",
    "REPLY_PER_EPOCH_EVALS_PUBLISHED_AMPERE.md.sha256",
    "TASK_PROTOCOL_REPO_PINNING.md",
    "TASK_PROTOCOL_REPO_PINNING.md.sha256",
    "REPLY_PROTOCOL_PIN_AND_INTEGRATION.md",
    "REPLY_PROTOCOL_PIN_AND_INTEGRATION.md.sha256",
    "REPLY_PROTOCOL_INTEGRATION_MERGED_DIJKSTRA.md",
    "REPLY_PROTOCOL_INTEGRATION_MERGED_DIJKSTRA.md.sha256",
    "AGENT_ANTIGRAVITY.md",
    "AGENT_ANTIGRAVITY.md.sha256",
    "AGENT_CLAUDE.md",
    "AGENT_CLAUDE.md.sha256",
    "UPDATE_CLAUDE_CODE_INTEGRATION_V2.md",
    "UPDATE_CLAUDE_CODE_INTEGRATION_V2.md.sha256",
    "REQUEST_DEPLOYED_WATCHER_IMPLEMENTATIONS_DIJKSTRA.md",
    "REQUEST_DEPLOYED_WATCHER_IMPLEMENTATIONS_DIJKSTRA.md.sha256",
    "watch_sync_folder_antigravity.py",
    "watch_sync_folder_antigravity.py.sha256",
    "INTEGRATION_ANTIGRAVITY.md",
    "INTEGRATION_ANTIGRAVITY.md.sha256",
    "REPLY_WATCHER_IMPLEMENTATION_AMPERE.md",
    "REPLY_WATCHER_IMPLEMENTATION_AMPERE.md.sha256",
    "REPLY_BATCH128_PER_EPOCH_EVALS_AMPERE.md",
    "REPLY_BATCH128_PER_EPOCH_EVALS_AMPERE.md.sha256",
    "REPLY_WATCHER_IMPLEMENTATION_TURING.md",
    "REPLY_WATCHER_IMPLEMENTATION_TURING.md.sha256",
    "REPLY_ANTIGRAVITY_MERGED_DIJKSTRA.md",
    "REPLY_ANTIGRAVITY_MERGED_DIJKSTRA.md.sha256",
    "ACTION_REEVALUATE_AT_PINNED_SETTINGS.md",
    "ACTION_REEVALUATE_AT_PINNED_SETTINGS.md.sha256",
    "AGENT_CODEX_SHANNON.md",
    "AGENT_CODEX_SHANNON.md.sha256",
    "depth_cliff_sweep_turing.json",
    "depth_cliff_sweep_turing.json.sha256",
    "REPORT_EXP1_DEPTH_CLIFF_SWEEP_TURING.md",
    "REPORT_EXP1_DEPTH_CLIFF_SWEEP_TURING.md.sha256",
    "REVIEW_0B_CHAIN_DIJKSTRA.md",
    "REVIEW_0B_CHAIN_DIJKSTRA.md.sha256",
    "UPDATE_CLAUDECODE_WATCHER_V3.md",
    "UPDATE_CLAUDECODE_WATCHER_V3.md.sha256",
    "REPLY_CLAUDECODE_V3_MERGED_DIJKSTRA.md",
    "REPLY_CLAUDECODE_V3_MERGED_DIJKSTRA.md.sha256",
    "REPLY_DEPTH_CLIFF_SWEEP_ADA.md",
    "REPLY_DEPTH_CLIFF_SWEEP_ADA.md.sha256",
    "REPLY_TRUE_FLOOR_DEPTH_INVARIANCE_DIJKSTRA.md",
    "REPLY_TRUE_FLOOR_DEPTH_INVARIANCE_DIJKSTRA.md.sha256",
    "REPLY_CLIFF_DEFECTS_AND_L8_PROBE_TURING.md",
    "REPLY_CLIFF_DEFECTS_AND_L8_PROBE_TURING.md.sha256",
    "exp1_depth_cliff_sweep.py",
    "exp1_depth_cliff_sweep.py.sha256",
    "TASK_DIJKSTRA_SUPERSESSION_MANIFEST_PROTOCOL_REVIEW.md",
    "TASK_DIJKSTRA_SUPERSESSION_MANIFEST_PROTOCOL_REVIEW.md.sha256",
    "REPLY_SUPERSESSION_MANIFEST_TURING.md",
    "REPLY_SUPERSESSION_MANIFEST_TURING.md.sha256",
    "REPLY_SUPERSESSION_MANIFEST_AMPERE.md",
    "REPLY_SUPERSESSION_MANIFEST_AMPERE.md.sha256",
    "REVIEW_SUPERSESSION_MANIFEST_DIJKSTRA.md",
    "REVIEW_SUPERSESSION_MANIFEST_DIJKSTRA.md.sha256",
    "REPLY_SUPERSESSION_MANIFEST_ADA.md",
    "REPLY_SUPERSESSION_MANIFEST_ADA.md.sha256",
    "REPLY_SUPERSESSION_CONSOLIDATED_DIJKSTRA.md",
    "REPLY_SUPERSESSION_CONSOLIDATED_DIJKSTRA.md.sha256",
    "analyze_0b_seed_study.py",
    "analyze_0b_seed_study.py.sha256",
    "CLOSURE_ANALYSIS_CHAIN_PUBLISHED_ADA.md",
    "CLOSURE_ANALYSIS_CHAIN_PUBLISHED_ADA.md.sha256",
    "exp0_checkpoint_analysis.py",
    "exp0_checkpoint_analysis.py.sha256",
    "exp0_config.py",
    "exp0_config.py.sha256",
    "exp0_evaluate.py",
    "exp0_evaluate.py.sha256",
    "REVIEW_0B_ADDENDUM_CODE_DIJKSTRA.md",
    "REVIEW_0B_ADDENDUM_CODE_DIJKSTRA.md.sha256",
    "VERIFIED_SUPERSESSION_MANIFEST_CLASS_C.md",
    "VERIFIED_SUPERSESSION_MANIFEST_CLASS_C.md.sha256",
    "TASK_DIJKSTRA_IMPLEMENT_SUPERSESSION_MANIFEST_PROTOCOL.md",
    "TASK_DIJKSTRA_IMPLEMENT_SUPERSESSION_MANIFEST_PROTOCOL.md.sha256",
    "FIX_ANALYZER_BUGS_ADA.md",
    "FIX_ANALYZER_BUGS_ADA.md.sha256",
    "NOTE_PER_NODE_ARCHIVES_DIJKSTRA.md",
    "NOTE_PER_NODE_ARCHIVES_DIJKSTRA.md.sha256",
    "eval_rwkv_n36_seed_46_epoch_002.json",
    "eval_rwkv_n36_seed_46_epoch_002.json.sha256",
    "eval_rwkv_n36_seed_46_epoch_003.json",
    "eval_rwkv_n36_seed_46_epoch_003.json.sha256",
    "NOTE_TABLE_VS_ARTIFACTS.md",
    "NOTE_TABLE_VS_ARTIFACTS.md.sha256",
    "TASK_DIJKSTRA_REVIEW_BEFORE_RESULTS.md",
    "TASK_DIJKSTRA_REVIEW_BEFORE_RESULTS.md.sha256",
    "JOB_STATUS_AMPERE.md",
    "JOB_STATUS_AMPERE.md.sha256",
    "evaluate_structural_challenge.py",
    "evaluate_structural_challenge.py.sha256",
}


def is_ignored(path: Path) -> bool:
    for part in path.parts:
        if part in {".stfolder", ".stversions", "__pycache__"} or part.endswith(".tmp") or part.startswith("~") or ".sync-conflict-" in part or part.endswith(".pyc"):
            return True
    if path.name in IGNORE_NAMES or path.name.endswith(".tmp") or path.name.startswith("~") or ".sync-conflict-" in path.name or path.name.endswith(".pyc"):
        return True
    return False


def scan_state(root: Path) -> dict[str, tuple[int, int]]:
    state: dict[str, tuple[int, int]] = {}
    if not root.exists():
        return state
    try:
        for p in root.rglob("*"):
            if not is_ignored(p) and p.is_file():
                try:
                    st = p.stat()
                    state[str(p)] = (st.st_mtime_ns, st.st_size)
                except OSError:
                    pass
    except OSError:
        pass
    return state


def main() -> int:
    timeout_sec = int(sys.argv[1]) if len(sys.argv) > 1 else 86400  # Default 24h
    print(f"Monitoring {WATCH_DIR} for incoming agent events...", flush=True)

    initial_state = scan_state(WATCH_DIR)
    start_time = time.time()

    while (time.time() - start_time) < timeout_sec:
        time.sleep(1.0)
        current_state = scan_state(WATCH_DIR)

        # Check for new or modified files
        changed = []
        for path_str, (mtime, size) in current_state.items():
            if path_str not in initial_state:
                changed.append(f"CREATED: {Path(path_str).name} ({size} bytes)")
            elif initial_state[path_str] != (mtime, size):
                changed.append(f"MODIFIED: {Path(path_str).name} ({size} bytes)")

        # Check for deleted files
        for path_str in initial_state:
            if path_str not in current_state:
                changed.append(f"DELETED: {Path(path_str).name}")

        if changed:
            print("\n" + "=" * 60, flush=True)
            print("EVENT DETECTED in D:\\ProjectSync:", flush=True)
            for c in changed:
                print(f"  - {c}", flush=True)
            print("=" * 60, flush=True)

            # Brief settle time in case a multi-file sync is in flight
            time.sleep(1.0)
            print("\nCurrent D:\\ProjectSync Files:", flush=True)
            for p in sorted(WATCH_DIR.rglob("*")):
                if not is_ignored(p) and p.is_file():
                    try:
                        st = p.stat()
                        print(f"  {p.name:<30} {st.st_size:>10} bytes   (last modified {time.ctime(st.st_mtime)})", flush=True)
                    except OSError:
                        pass
            return 0

    print("Watcher reached timeout without events.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
