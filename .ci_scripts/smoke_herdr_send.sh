#!/usr/bin/env bash
# End-to-end smoke test of the herdr_send.py CLI.
#
# Uses a fake herdr on PATH emitting realistic JSON and text.
# Tests every command, flag, and exit code, plus waiting, saved messages, and pending.
# Uses $PYTHON, else .venv/bin/python, else python3.
# On failure, keeps the temporary directory and prints its path and log.

set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SCRIPTS=$ROOT/skills/herdr/scripts
CLI=$SCRIPTS/herdr_send.py

if [[ -n ${PYTHON:-} ]]; then
  PY=$PYTHON
elif [[ -x $ROOT/.venv/bin/python ]]; then
  PY=$ROOT/.venv/bin/python
else
  PY=python3
fi
PY=$(command -v "$PY")

WORK=$(mktemp -d)
LOG=$WORK/log.txt
FAKE_HERDR=$WORK/herdr
pass=0
fail=0

cat >"$FAKE_HERDR" <<'FAKE_HERDR_EOF'
#!/usr/bin/env bash
set -uo pipefail
cmd=$1
shift

case "$cmd" in
  agent)
    sub=$1
    shift
    case "$sub" in
      list)
        cat <<'JSON'
{"result": {"agents": [
  {"pane_id": "w1:p1", "name": "self", "agent": "claude", "agent_session": {"kind": "id"}},
  {"pane_id": "w1:p2", "name": "coder", "agent": "claude", "agent_session": {"kind": "id"}},
  {"pane_id": "w1:p3", "name": "xorc_agent", "agent": "xorc", "agent_session": {"kind": "id"}}
]}}
JSON
        ;;
      get)
        pane=$1
        if [[ ${HERDR_AGENT_STATE:-idle} == blocked ]]; then
          cat <<'JSON'
{"result": {"agent": {
  "pane_id": "w1:p2",
  "agent_status": "blocked",
  "interactive_ready": true,
  "state_change_seq": 10
}}}
JSON
        elif [[ ${HERDR_AGENT_STATE:-idle} == unknown ]]; then
          cat <<'JSON'
{"result": {"agent": {
  "pane_id": "w1:p2",
  "agent_status": "unknown",
  "interactive_ready": true,
  "state_change_seq": 10
}}}
JSON
        elif [[ ${HERDR_AGENT_STATE:-idle} == working ]]; then
          cat <<'JSON'
{"result": {"agent": {
  "pane_id": "w1:p2",
  "agent_status": "working",
  "interactive_ready": true,
  "state_change_seq": 10
}}}
JSON
        else
          cat <<'JSON'
{"result": {"agent": {
  "pane_id": "w1:p2",
  "agent_status": "idle",
  "interactive_ready": true,
  "state_change_seq": 10
}}}
JSON
        fi
        ;;
      read)
        echo "Approve this change?"
        ;;
      prompt)
        ;;
      *)
        echo "Unknown agent subcommand: $sub" >&2
        exit 1
        ;;
    esac
    ;;
  pane)
    sub=$1
    shift
    case "$sub" in
      read)
        pane=$1
        screen=${HERDR_SCREEN:-empty}
        if [[ $screen == typed_until ]]; then
          # Typed for the first HERDR_TYPED_READS reads, then empty: someone finishes and sends their text.
          reads=$(($(cat "$HERDR_READS_FILE" 2>/dev/null || echo 0) + 1))
          echo "$reads" >"$HERDR_READS_FILE"
          if ((reads <= HERDR_TYPED_READS)); then screen=busy; else screen=empty; fi
        fi
        if [[ $screen == busy ]]; then
          cat <<'TEXT'
──────────────────────
> 
/goal-dire
──────────────────────
TEXT
        elif [[ $screen == slash_draft ]]; then
          cat <<'TEXT'
──────────────────────
> 
/comp
──────────────────────
TEXT
        else
          cat <<'TEXT'
──────────────────────
> 
──────────────────────
TEXT
        fi
        ;;
      run)
        ;;
      *)
        echo "Unknown pane subcommand: $sub" >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    exit 1
    ;;
esac
FAKE_HERDR_EOF

chmod +x "$FAKE_HERDR"
export PATH=$WORK:$PATH

step() {
  local want=$1 pattern=$2 out rc
  shift 2
  out=$(PATH=${CLI_PATH:-$PATH} "$PY" "$CLI" "$@" 2>&1)
  rc=$?
  printf '$ herdr_send %s\n%s\n[rc=%s]\n\n' "$*" "$out" "$rc" >>"$LOG"
  if [[ $rc == "$want" ]]; then
    if grep -Eq "$pattern" <<<"$out"; then
      pass=$((pass + 1))
    else
      fail=$((fail + 1))
      printf 'FAIL: herdr_send %s (rc=%s, want %s, /%s/)\n%s\n' "$*" "$rc" "$want" "$pattern" "$out"
    fi
  else
    fail=$((fail + 1))
    printf 'FAIL: herdr_send %s (rc=%s, want %s, /%s/)\n%s\n' "$*" "$rc" "$want" "$pattern" "$out"
  fi
}

export HERDR_ENV=1
export HERDR_PANE_ID=w1:p1
# Saved messages stay in the temporary directory, never the real state directory.
export HERDR_SEND_STATE_DIR=$WORK/state

step 0 '"result": "ready"' check coder
step 0 '"result": "ready"' check coder --tui claude
step 0 '"result": "ready"' check coder --expect-kind claude
step 13 'Expected kind' check coder --expect-kind xorc

export HERDR_SCREEN=empty
step 0 'ready' check w1:p2

export HERDR_SCREEN=busy
step 10 'unsubmitted text' check coder

export HERDR_SCREEN=slash_draft
step 10 'unsubmitted text' check coder

export HERDR_SCREEN=empty
export HERDR_AGENT_STATE=blocked
step 11 'blocked' check coder

export HERDR_AGENT_STATE=unknown
step 12 'unknown.*refusing' check coder

export HERDR_AGENT_STATE=working
step 0 'ready' check coder
step 12 'working.*refusing' check coder --disable-working

export HERDR_AGENT_STATE=idle
export HERDR_SCREEN=empty
step 13 'not found' check ghost
step 13 'own pane' check w1:p1

unset HERDR_ENV
step 14 'Not running inside Herdr' check coder

export HERDR_ENV=1

step 0 '"result": "sent"' prompt coder --text "Review this" --from-role coder
step 0 '"result": "sent"' prompt coder --text "Review" --from-role implementer
step 0 '"result": "sent"' prompt coder --text "Review" --reply --from-role coder
step 0 '"result": "sent"' prompt coder --text "Review" --no-reply --from-role coder
step 0 '"result": "sent"' prompt coder --text "/goal-direct Fix" --no-header

echo "Test message" >"$WORK/msg.txt"
step 0 '"result": "sent"' prompt coder --file "$WORK/msg.txt" --from-role coder

step 0 '"result": "sent"' prompt coder - --from-role coder <<<"Stdin message"

step 0 'dry_run' prompt coder --text "Dry" --dry-run --from-role coder

step 0 '"result": "sent"' prompt xorc_agent --text "Build" --tui xorc --no-header

step 21 'empty' prompt coder - <<<""
step 21 'only newlines' prompt coder --text $'\n\n'
step 21 'empty' prompt coder --text "" <<<"ignored"

step 21 'Failed to read file' prompt coder --file /nonexistent

unset HERDR_PANE_ID
step 21 'required' prompt coder --text "Test" --from-role coder

export HERDR_PANE_ID=w1:p1
step 21 'required' prompt coder --text "Test"

step 0 '"result": "sent"' run w1:p4 --text "just test"
step 0 'dry_run' run w1:p4 --text "just test" --dry-run
step 13 'owned by an agent' run w1:p2 --text "command"

step 0 '^result: ready$' check coder --yaml

# Waiting: the box holds typed text for three reads, then empties; the send goes out after it clears.
export HERDR_SCREEN=typed_until HERDR_TYPED_READS=3 HERDR_READS_FILE=$WORK/reads
step 0 '"attempts": 4' prompt coder --text "After typing" --interval 0.05 --no-header
rm -f "$WORK/reads"

# A wait that runs out keeps the message saved with its reason, and the stderr summary says so.
export HERDR_SCREEN=busy
step 10 '"result": "timeout".*"reason": "typed_text"' prompt coder --text "Kept" --wait 0.3 --interval 0.05 --no-header
step 10 'Error: timeout on w1:p2 \(typed_text\).*kept' prompt coder --text "Kept too" --wait 0.1 --interval 0.05 --no-header
step 0 '"waiting": \[\{"message_id"' pending list coder
step 0 'waiting:' pending list --yaml
step 10 '"pending_for_target": \[\{' check w1:p2

# The next send delivers the saved messages first, oldest first.
export HERDR_SCREEN=empty
step 0 '"delivered_first": \["[^"]+", "[^"]+"\]' prompt coder --text "Newest" --no-header
step 0 '"waiting": \[\]' pending list w1:p2

# Dropping saved messages.
export HERDR_SCREEN=busy
step 10 'timeout' prompt coder --text "To drop" --wait 0 --no-header
step 0 '"result": "dropped"' pending drop --target coder --all
step 13 '"not_found": \["nope"\]' pending drop nope
step 21 'needs --target' pending drop --all
export HERDR_SCREEN=empty

unset HERDR_ENV
step 14 'Not running inside Herdr' prompt coder --text "x"
step 14 'Not running inside Herdr' run w1:p4 --text "x"
step 14 'Not running inside Herdr' check coder

# Hide every herdr, including a real one on a herdr host, behind an empty PATH.
rm -f "$FAKE_HERDR"
mkdir -p "$WORK/no-herdr"
export PATH="${PATH#"$WORK":}"
CLI_PATH="$WORK/no-herdr"
export HERDR_ENV=1

step 20 'not found in PATH' check coder

echo "smoke_herdr_send: passed=$pass failed=$fail"
if ((fail > 0)); then
  echo "smoke_herdr_send: kept $WORK; see $LOG"
  exit 1
fi
rm -rf "$WORK"
