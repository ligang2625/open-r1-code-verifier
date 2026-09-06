#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-}"
SSH_TARGET="${WP9C_4090_SSH_TARGET:-}"
SSH_PORT="${WP9C_4090_SSH_PORT:-}"
HANDOFF_COMMIT="${WP9C_HANDOFF_COMMIT:-}"
C25_HANDOFF_COMMIT="322db1e1649d8c87b51352f57c0884b0b9a24bfc"
REPO_ROOT="/home/dzy/open-r1-code-verifier/.worktrees/wp9-c"

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

LOCAL_RETRY_BUNDLE="/home/dzy/wp9c-fresh-calibration-retry-input-C27"
REMOTE_RETRY_BUNDLE="/root/open-r1-code-verifier-data-4090/wp9c/fresh-calibration-retry-input-C27"
LOCAL_GENERATION="/home/dzy/wp9c-fresh-calibration-retry-generation-C27"
REMOTE_GENERATION="/root/sj-tmp/open-r1-code-verifier-outputs/wp9c/calibration/fresh-reduced-retry-C27"
LOCAL_EVIDENCE="/home/dzy/wp9c-operator-evidence/WP9-c/wp9c-fresh-reduced-calibration-retry-generation/C27"
REMOTE_EVIDENCE="/root/sj-tmp/open-r1-code-verifier-outputs/operator/WP9-c/wp9c-fresh-reduced-calibration-retry-generation/C27"

RETRY_IDS_SHA="f0c03e55771bc86dd3f9966214ade7d34a9734cff133bdbdd1e6d1d8071c2eb5"
RETRY_INPUT_MANIFEST_SHA="e9d896de8ad51e54fcbaaf0d04edf691a742e6168ed63908795305d5df22ab33"

case "$MODE" in
  probe)
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'printf "C27_SSH_OK\n"'
    ;;

  push-code)
    [[ "$HANDOFF_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
      echo "set WP9C_HANDOFF_COMMIT to the exact C27 handoff commit" >&2
      exit 64
    }
    LOCAL_HEAD="$(git -C "$REPO_ROOT" rev-parse HEAD)"
    [[ "$LOCAL_HEAD" == "$HANDOFF_COMMIT" ]] || {
      echo "local HEAD does not equal WP9C_HANDOFF_COMMIT" >&2
      exit 65
    }
    git -C "$REPO_ROOT" merge-base --is-ancestor "$C25_HANDOFF_COMMIT" "$HANDOFF_COMMIT" || {
      echo "C27 handoff commit is not descended from accepted C25" >&2
      exit 65
    }
    BUNDLE="/home/dzy/wp9c-c27-handoff.bundle"
    rm -f "$BUNDLE"
    git -C "$REPO_ROOT" bundle create "$BUNDLE" HEAD "^$C25_HANDOFF_COMMIT"
    git -C "$REPO_ROOT" bundle verify "$BUNDLE"
    rsync -a --info=progress2 -e "$RSYNC_RSH" "$BUNDLE" "$SSH_TARGET:/root/wp9c-c27-handoff.bundle"
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
      "cd /root/open-r1-code-verifier && test -z \"\$(git status --porcelain --ignore-submodules=none)\" && git fetch /root/wp9c-c27-handoff.bundle HEAD:refs/wp9c-c27-handoff && git checkout --detach refs/wp9c-c27-handoff && test \"\$(git rev-parse HEAD)\" = '$HANDOFF_COMMIT' && test -z \"\$(git status --porcelain --ignore-submodules=none)\""
    ;;

  push-input)
    [[ -f "$LOCAL_RETRY_BUNDLE/retry_problem_ids.jsonl" ]] || { echo "missing local C27 retry IDs" >&2; exit 66; }
    [[ -f "$LOCAL_RETRY_BUNDLE/retry-input-manifest.json" ]] || { echo "missing local C27 retry input manifest" >&2; exit 66; }
    printf '%s  %s\n' "$RETRY_IDS_SHA" "$LOCAL_RETRY_BUNDLE/retry_problem_ids.jsonl" | sha256sum -c -
    printf '%s  %s\n' "$RETRY_INPUT_MANIFEST_SHA" "$LOCAL_RETRY_BUNDLE/retry-input-manifest.json" | sha256sum -c -
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "mkdir -p '$REMOTE_RETRY_BUNDLE'"
    rsync -a --info=progress2 -e "$RSYNC_RSH" "$LOCAL_RETRY_BUNDLE/" "$SSH_TARGET:$REMOTE_RETRY_BUNDLE/"
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
      "printf '%s  %s\\n%s  %s\\n' '$RETRY_IDS_SHA' '$REMOTE_RETRY_BUNDLE/retry_problem_ids.jsonl' '$RETRY_INPUT_MANIFEST_SHA' '$REMOTE_RETRY_BUNDLE/retry-input-manifest.json' | sha256sum -c -"
    ;;

  pull-output)
    mkdir -p "$LOCAL_GENERATION" "$LOCAL_EVIDENCE"
    rsync -a --info=progress2 -e "$RSYNC_RSH" "$SSH_TARGET:$REMOTE_GENERATION/" "$LOCAL_GENERATION/"
    rsync -a --info=progress2 -e "$RSYNC_RSH" "$SSH_TARGET:$REMOTE_EVIDENCE/" "$LOCAL_EVIDENCE/"
    echo "C27 output pulled to: $LOCAL_GENERATION"
    echo "C27 evidence pulled to: $LOCAL_EVIDENCE"
    ;;

  *)
    cat >&2 <<'EOF'
usage:
  sync_4090.sh probe
  sync_4090.sh push-code
  sync_4090.sh push-input
  sync_4090.sh pull-output

required environment:
  WP9C_4090_SSH_TARGET=root@HOST
  WP9C_4090_SSH_PORT=PORT
  WP9C_HANDOFF_COMMIT=<40-hex>   # required for push-code and target run
EOF
    exit 64
    ;;
esac
