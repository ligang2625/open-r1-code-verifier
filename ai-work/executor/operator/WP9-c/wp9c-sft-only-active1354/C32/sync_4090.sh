#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-}"
SSH_TARGET="${WP9C_4090_SSH_TARGET:-}"
SSH_PORT="${WP9C_4090_SSH_PORT:-}"
HANDOFF_COMMIT="${WP9C_HANDOFF_COMMIT:-}"
C25_HANDOFF_COMMIT="322db1e1649d8c87b51352f57c0884b0b9a24bfc"
REPO_ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"
STAGE_REL="ai-work/executor/operator/WP9-c/wp9c-sft-only-active1354/C32"

[[ "$SSH_TARGET" =~ ^[A-Za-z0-9._@:-]+$ ]] || {
  echo "set WP9C_4090_SSH_TARGET, for example root@203.0.113.10" >&2
  exit 64
}
[[ "$SSH_PORT" =~ ^[0-9]+$ ]] && (( SSH_PORT >= 1 && SSH_PORT <= 65535 )) || {
  echo "set WP9C_4090_SSH_PORT to the current SSH port" >&2
  exit 64
}

SSH_OPTS=(-p "$SSH_PORT" -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30 -o ServerAliveCountMax=3)
RSYNC_RSH="ssh -p $SSH_PORT -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30 -o ServerAliveCountMax=3"

LOCAL_C31="/home/dzy/wp9c-hybrid1600-sft-selection-C31"
REMOTE_C31="/root/open-r1-code-verifier-data-4090/wp9c/hybrid1600-sft-selection-C31"
LOCAL_C32="/home/dzy/wp9c-sft-only-active1354-C32"
REMOTE_C32="/root/open-r1-code-verifier-data-4090/wp9c/sft-only-active1354-C32"
REMOTE_RUN="/root/sj-tmp/open-r1-code-verifier-outputs/sft/wp9c-sft-only-active1354-seed42"
REMOTE_EVIDENCE="/root/sj-tmp/open-r1-code-verifier-outputs/operator/WP9-c/wp9c-sft-only-active1354/C32"
LOCAL_RUN="/home/dzy/wp9c-sft-only-active1354-run-C32"
LOCAL_EVIDENCE="/home/dzy/wp9c-operator-evidence/WP9-c/wp9c-sft-only-active1354/C32"

C31_REPORT_SHA="68bed6b3dfe774a1fedabed2b2684e6aa0e2283ece7b31b60ce252167ebf600f"
C31_SELECTED_SHA="c966a4c9b7f3e878600a0647178c1cdf781719adb60dd02d8a231a187a20e6e6"
C31_RESERVE_SHA="96a60c822001a4fe3ffbffc268b95a12783c0e2c68273ec1496e31a04baba93d"
C31_ORDER_SHA="e9253c7859acb703aba35fd58147c6fa78e012f46acfbc595b21606208cdbeee"
C32_REPORT_SHA="fb8a6eb053cf76ab947caeeff68a7328e5b6fd10c4e6d06936c1d8b64cd73e99"
C32_PREVALIDATION_SHA="c40fc3fdf35faf98fa85bc4c021c31fa6b471718547cce81d8557cb4f160cc86"
C32_TRAIN_SHA="de72d223f6722fd70d855526be5a27bb635baf3128fc1faae7635a59f7109582"
C32_VALIDATION_SHA="7f143a85859486d918ebb405adce3e87d9bdddf8b9831b7e9feaba04aa1ecec2"
C32_PROVENANCE_SHA="802bf96d3df5c53e2f1238db56dc122ac52ed7fec13ac5cc65d99a99d3edd94f"
C32_ORDER_SHA="82a58dcb6283d85149d7715675639a7782c4ed9a7c3d17646287a390719dd986"

require_handoff() {
  [[ "$HANDOFF_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
    echo "set WP9C_HANDOFF_COMMIT to the exact C31/C32 handoff commit" >&2
    exit 64
  }
}

check_local_data() {
  printf '%s  %s\n' "$C31_REPORT_SHA" "$LOCAL_C31/report.json" | sha256sum -c -
  printf '%s  %s\n' "$C31_SELECTED_SHA" "$LOCAL_C31/selected_sft_overlap.jsonl" | sha256sum -c -
  printf '%s  %s\n' "$C31_RESERVE_SHA" "$LOCAL_C31/reserve_sft_overlap.jsonl" | sha256sum -c -
  printf '%s  %s\n' "$C31_ORDER_SHA" "$LOCAL_C31/hybrid_problem_order.jsonl" | sha256sum -c -
  printf '%s  %s\n' "$C32_REPORT_SHA" "$LOCAL_C32/report.json" | sha256sum -c -
  printf '%s  %s\n' "$C32_PREVALIDATION_SHA" "$LOCAL_C32/prevalidation.json" | sha256sum -c -
  printf '%s  %s\n' "$C32_TRAIN_SHA" "$LOCAL_C32/training/sft.jsonl" | sha256sum -c -
  printf '%s  %s\n' "$C32_VALIDATION_SHA" "$LOCAL_C32/training/sft_validation.jsonl" | sha256sum -c -
  printf '%s  %s\n' "$C32_PROVENANCE_SHA" "$LOCAL_C32/manifest/target_provenance.jsonl" | sha256sum -c -
  printf '%s  %s\n' "$C32_ORDER_SHA" "$LOCAL_C32/manifest/problem_order.jsonl" | sha256sum -c -
}

case "$MODE" in
  probe)
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'printf "C32_SSH_OK\n"'
    ;;

  push-code)
    require_handoff
    LOCAL_HEAD="$(git -C "$REPO_ROOT" rev-parse HEAD)"
    [[ "$LOCAL_HEAD" == "$HANDOFF_COMMIT" ]] || {
      echo "local HEAD does not equal WP9C_HANDOFF_COMMIT" >&2
      exit 65
    }
    git -C "$REPO_ROOT" merge-base --is-ancestor "$C25_HANDOFF_COMMIT" "$HANDOFF_COMMIT" || {
      echo "C32 handoff commit is not descended from accepted C25" >&2
      exit 65
    }
    BUNDLE="/home/dzy/wp9c-c32-handoff.bundle"
    rm -f "$BUNDLE"
    git -C "$REPO_ROOT" bundle create "$BUNDLE" HEAD "^$C25_HANDOFF_COMMIT"
    git -C "$REPO_ROOT" bundle verify "$BUNDLE"
    rsync -a --info=progress2 -e "$RSYNC_RSH" "$BUNDLE" "$SSH_TARGET:/root/wp9c-c32-handoff.bundle"
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
      "cd /root/open-r1-code-verifier && test -z \"\$(git status --porcelain --ignore-submodules=none)\" && git fetch /root/wp9c-c32-handoff.bundle HEAD:refs/wp9c-c32-handoff && git checkout --detach refs/wp9c-c32-handoff && test \"\$(git rev-parse HEAD)\" = '$HANDOFF_COMMIT' && test -z \"\$(git status --porcelain --ignore-submodules=none)\""
    ;;

  push-data)
    check_local_data
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "mkdir -p '$REMOTE_C31' '$REMOTE_C32'"
    rsync -a --info=progress2 -e "$RSYNC_RSH" "$LOCAL_C31/" "$SSH_TARGET:$REMOTE_C31/"
    rsync -a --info=progress2 -e "$RSYNC_RSH" "$LOCAL_C32/" "$SSH_TARGET:$REMOTE_C32/"
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
      "printf '%s  %s\\n%s  %s\\n%s  %s\\n%s  %s\\n%s  %s\\n%s  %s\\n%s  %s\\n%s  %s\\n%s  %s\\n%s  %s\\n' \
      '$C31_REPORT_SHA' '$REMOTE_C31/report.json' \
      '$C31_SELECTED_SHA' '$REMOTE_C31/selected_sft_overlap.jsonl' \
      '$C31_RESERVE_SHA' '$REMOTE_C31/reserve_sft_overlap.jsonl' \
      '$C31_ORDER_SHA' '$REMOTE_C31/hybrid_problem_order.jsonl' \
      '$C32_REPORT_SHA' '$REMOTE_C32/report.json' \
      '$C32_PREVALIDATION_SHA' '$REMOTE_C32/prevalidation.json' \
      '$C32_TRAIN_SHA' '$REMOTE_C32/training/sft.jsonl' \
      '$C32_VALIDATION_SHA' '$REMOTE_C32/training/sft_validation.jsonl' \
      '$C32_PROVENANCE_SHA' '$REMOTE_C32/manifest/target_provenance.jsonl' \
      '$C32_ORDER_SHA' '$REMOTE_C32/manifest/problem_order.jsonl' | sha256sum -c -"
    ;;

  run-sft)
    require_handoff
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
      "cd /root/open-r1-code-verifier && WP9C_HANDOFF_COMMIT='$HANDOFF_COMMIT' bash '$STAGE_REL/run.sh'"
    ;;

  pull-output)
    mkdir -p "$LOCAL_RUN" "$LOCAL_EVIDENCE"
    rsync -a --info=progress2 -e "$RSYNC_RSH" "$SSH_TARGET:$REMOTE_RUN/" "$LOCAL_RUN/"
    rsync -a --info=progress2 -e "$RSYNC_RSH" "$SSH_TARGET:$REMOTE_EVIDENCE/" "$LOCAL_EVIDENCE/"
    echo "C32 run pulled to: $LOCAL_RUN"
    echo "C32 evidence pulled to: $LOCAL_EVIDENCE"
    ;;

  *)
    cat >&2 <<'EOF'
usage:
  sync_4090.sh probe
  sync_4090.sh push-code
  sync_4090.sh push-data
  sync_4090.sh run-sft
  sync_4090.sh pull-output

required environment:
  WP9C_4090_SSH_TARGET=root@HOST
  WP9C_4090_SSH_PORT=PORT
  WP9C_HANDOFF_COMMIT=<40-hex>   # required for push-code and run-sft
EOF
    exit 64
    ;;
esac
