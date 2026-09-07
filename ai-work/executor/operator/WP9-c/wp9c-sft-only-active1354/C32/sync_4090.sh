#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-sync-all}"
SSH_TARGET="${WP9C_4090_SSH_TARGET:-}"
SSH_PORT="${WP9C_4090_SSH_PORT:-}"
HANDOFF_COMMIT="${WP9C_HANDOFF_COMMIT:-}"
BASE_HANDOFF_COMMIT="322db1e1649d8c87b51352f57c0884b0b9a24bfc"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
LOCAL_C32="/home/dzy/wp9c-sft-only-active1354-C32"
LOCAL_PARENT_B="/home/dzy/wp8-formal-sync/outputs/sft/B-sft-formal-seed42"
REMOTE_C32="/root/open-r1-code-verifier-data-4090/wp9c/sft-only-active1354-C32"
REMOTE_PARENT_B="/root/sj-tmp/open-r1-code-verifier-outputs/sft/B-sft-formal-seed42"
REMOTE_RUN="/root/sj-tmp/open-r1-code-verifier-outputs/sft/wp9c-sft-only-active1354-seed42"
REMOTE_EVIDENCE="/root/sj-tmp/open-r1-code-verifier-outputs/operator/WP9-c/wp9c-sft-only-active1354/C32"
LOCAL_RUN="/home/dzy/wp9c-sft-only-active1354-run-C32"
LOCAL_EVIDENCE="/home/dzy/wp9c-operator-evidence/WP9-c/wp9c-sft-only-active1354/C32"
BUNDLE="/home/dzy/wp9c-c32-sft-handoff.bundle"

C32_REPORT_SHA="fb8a6eb053cf76ab947caeeff68a7328e5b6fd10c4e6d06936c1d8b64cd73e99"
C32_PREVALIDATION_SHA="c40fc3fdf35faf98fa85bc4c021c31fa6b471718547cce81d8557cb4f160cc86"
C32_TRAIN_SHA="de72d223f6722fd70d855526be5a27bb635baf3128fc1faae7635a59f7109582"
C32_VALIDATION_SHA="7f143a85859486d918ebb405adce3e87d9bdddf8b9831b7e9feaba04aa1ecec2"
C32_PROVENANCE_SHA="802bf96d3df5c53e2f1238db56dc122ac52ed7fec13ac5cc65d99a99d3edd94f"
C32_ORDER_SHA="82a58dcb6283d85149d7715675639a7782c4ed9a7c3d17646287a390719dd986"
PARENT_RUN_JSON_SHA="6d059ae271e176aaa2becfa131937e64c8e38bb883f358149010f367a5a62a73"

[[ "$SSH_TARGET" =~ ^[A-Za-z0-9._@:-]+$ ]] || {
  echo "set WP9C_4090_SSH_TARGET, e.g. root@183.222.230.10" >&2
  exit 64
}
[[ "$SSH_PORT" =~ ^[0-9]+$ ]] && (( SSH_PORT >= 1 && SSH_PORT <= 65535 )) || {
  echo "set WP9C_4090_SSH_PORT, e.g. 40038" >&2
  exit 64
}
[[ "$HANDOFF_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  echo "set WP9C_HANDOFF_COMMIT to the exact C32 handoff commit" >&2
  exit 64
}

SSH_OPTS=(-p "$SSH_PORT" -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30 -o ServerAliveCountMax=3)
RSYNC_RSH="ssh -p $SSH_PORT -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30 -o ServerAliveCountMax=3"

check_local_inputs() {
  printf '%s  %s\n' "$C32_REPORT_SHA" "$LOCAL_C32/report.json" | sha256sum -c -
  printf '%s  %s\n' "$C32_PREVALIDATION_SHA" "$LOCAL_C32/prevalidation.json" | sha256sum -c -
  printf '%s  %s\n' "$C32_TRAIN_SHA" "$LOCAL_C32/training/sft.jsonl" | sha256sum -c -
  printf '%s  %s\n' "$C32_VALIDATION_SHA" "$LOCAL_C32/training/sft_validation.jsonl" | sha256sum -c -
  printf '%s  %s\n' "$C32_PROVENANCE_SHA" "$LOCAL_C32/manifest/target_provenance.jsonl" | sha256sum -c -
  printf '%s  %s\n' "$C32_ORDER_SHA" "$LOCAL_C32/manifest/problem_order.jsonl" | sha256sum -c -
  printf '%s  %s\n' "$PARENT_RUN_JSON_SHA" "$LOCAL_PARENT_B/run.json" | sha256sum -c -
}

build_bundle() {
  LOCAL_HEAD="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  [[ "$LOCAL_HEAD" == "$HANDOFF_COMMIT" ]] || {
    echo "sync helper must be run from the exact C32 handoff checkout" >&2
    exit 65
  }
  git -C "$REPO_ROOT" merge-base --is-ancestor "$BASE_HANDOFF_COMMIT" "$HANDOFF_COMMIT"
  rm -f "$BUNDLE"
  git -C "$REPO_ROOT" bundle create "$BUNDLE" HEAD "^$BASE_HANDOFF_COMMIT"
  git -C "$REPO_ROOT" bundle verify "$BUNDLE"
  sha256sum "$BUNDLE"
}

case "$MODE" in
  probe)
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'printf "C32_SSH_OK\n"'
    ;;

  sync-all)
    check_local_inputs
    build_bundle
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
      "mkdir -p '$REMOTE_C32' '$REMOTE_PARENT_B' /root/tmp"
    rsync -a --info=progress2 -e "$RSYNC_RSH" "$BUNDLE" "$SSH_TARGET:/root/wp9c-c32-sft-handoff.bundle"
    rsync -a --info=progress2 -e "$RSYNC_RSH" "$LOCAL_C32/" "$SSH_TARGET:$REMOTE_C32/"
    rsync -a --info=progress2 -e "$RSYNC_RSH" "$LOCAL_PARENT_B/" "$SSH_TARGET:$REMOTE_PARENT_B/"
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
      "printf '%s  %s\\n%s  %s\\n%s  %s\\n%s  %s\\n%s  %s\\n%s  %s\\n%s  %s\\n' \
      '$C32_REPORT_SHA' '$REMOTE_C32/report.json' \
      '$C32_PREVALIDATION_SHA' '$REMOTE_C32/prevalidation.json' \
      '$C32_TRAIN_SHA' '$REMOTE_C32/training/sft.jsonl' \
      '$C32_VALIDATION_SHA' '$REMOTE_C32/training/sft_validation.jsonl' \
      '$C32_PROVENANCE_SHA' '$REMOTE_C32/manifest/target_provenance.jsonl' \
      '$C32_ORDER_SHA' '$REMOTE_C32/manifest/problem_order.jsonl' \
      '$PARENT_RUN_JSON_SHA' '$REMOTE_PARENT_B/run.json' | sha256sum -c -"
    echo "C32_SYNC_OK bundle=/root/wp9c-c32-sft-handoff.bundle"
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
  sync_4090.sh sync-all
  sync_4090.sh pull-output

required environment:
  WP9C_4090_SSH_TARGET=root@HOST
  WP9C_4090_SSH_PORT=PORT
  WP9C_HANDOFF_COMMIT=<40-hex C32 handoff commit>
EOF
    exit 64
    ;;
esac
