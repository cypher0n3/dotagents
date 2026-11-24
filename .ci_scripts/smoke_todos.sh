#!/usr/bin/env bash
# End-to-end smoke test of the task-management CLI.
#
# Runs every todos.py command and flag against a fresh file in a temporary
# directory, checking each exit code and output, then validates the final file
# against the schema and checks that no empty list was left behind.
# Uses $PYTHON, else .venv/bin/python, else python3.
# On failure, it keeps the temporary directory and prints its path and log.
#
# Usage: .ci_scripts/smoke_todos.sh
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SCRIPTS=$ROOT/skills/task-management/scripts
CLI=$SCRIPTS/todos.py
if [[ -n ${PYTHON:-} ]]; then
  PY=$PYTHON
elif [[ -x $ROOT/.venv/bin/python ]]; then
  PY=$ROOT/.venv/bin/python
else
  PY=python3
fi

WORK=$(mktemp -d)
export TODOS_FILE=$WORK/todos.yaml
LOG=$WORK/log.txt
pass=0
fail=0

# step EXPECTED_RC EXPECTED_OUTPUT_REGEX -- todos.py args...
step() {
  local want=$1 pattern=$2 out rc
  shift 3
  out=$("$PY" "$CLI" "$@" 2>&1)
  rc=$?
  printf '$ todos %s\n%s\n[rc=%s]\n\n' "$*" "$out" "$rc" >>"$LOG"
  if [[ $rc == "$want" ]] && grep -Eq -- "$pattern" <<<"$out"; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    printf 'FAIL: todos %s (rc=%s, want %s, /%s/)\n%s\n' "$*" "$rc" "$want" "$pattern" "$out"
  fi
}

# check DESCRIPTION -- command...
check() {
  local what=$1
  shift 2
  if "$@" >>"$LOG" 2>&1; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    echo "FAIL: $what"
  fi
}

no_empty_lists() {
  ! grep -q '\[\]' "$1"
}

# Help
step 0 'init.*list.*show.*add.*update' -- --help
step 0 'requires-human-review' -- update --help

# Create
step 1 'File not found' -- list
step 0 'Created' -- init --title "Smoke"
step 1 'already exists' -- init

# Meta
step 0 'title: Smoke' -- meta --show
step 0 "title='Smoke test'" -- meta --title "Smoke test"
step 0 "created='2026-11-01T00:00:00Z'" -- meta --created 2026-11-01T00:00:00Z
step 1 'ISO 8601' -- meta --created yesterday
step 0 'No action' -- meta

# Add
step 0 "Added task 'design'" -- add "Design schema" --id design --priority critical --description "Schema first" \
  --assignee-kind human --assignee-name Ann --tags spec --acceptance-criteria "Schema validates" --due 2026-12-01
step 0 "Added task 'build-cli'" -- add "Build CLI" --priority high --depends-on design \
  --assignee-kind agent --agent-type coder --requires-human-review \
  --files 'src/cli.py:create' 'C:\win\path.py:update' --file-reason 'src/cli.py=Entry point'
step 0 "Added task 'write-tests'" -- add "Write tests" --id write-tests --parent build-cli --status in_progress
step 0 "status=blocked|Added task 'wait'" -- add "Wait on vendor" --id wait --blocked-reason "Vendor reply"
step 0 'Dry run: would add' -- add "Not added" --dry-run
step 1 'already exists' -- add "Dup" --id design
step 1 'not found' -- add "Orphan" --parent ghost
step 1 "Dependency 'ghost' not found" -- add "Bad dep" --depends-on ghost
step 1 'YYYY-MM-DD' -- add "Bad due" --due 2026-02-30
step 1 'cannot be combined' -- add "Conflict" --status pending --blocked-reason x
step 1 'agent-type required' -- add "No agent type" --assignee-kind agent
step 1 'Invalid file op' -- add "Bad op" --files 'a.py:move'

# Read
step 0 'Open todos' -- list
step 0 'pending +design' -- list
step 0 'Design schema' -- list human
step 0 'Build CLI' -- list agent
step 0 'Wait on vendor' -- list unassigned
step 0 'wait' -- list --status blocked
step 0 'design' -- list --priority critical
step 0 'design' -- list --tag spec
step 0 'No todos found' -- list --status 'done'
step 0 'src/cli.py \(create\): Entry point' -- show build-cli
step 0 'Requires human review: Yes' -- show build-cli
step 0 'write-tests' -- show build-cli
step 0 'Due: 2026-12-01' -- show design
step 1 'not found' -- show ghost

# Update scalars
step 0 "title='Design the schema'" -- update design --title "Design the schema"
step 0 'priority removed' -- update design --clear-priority
step 0 "description removed" -- update design --description ""
step 0 "due='2027-01-15'" -- update design --due 2027-01-15
step 0 "created='2026-10-01T09:00:00Z'" -- update design --created 2026-10-01T09:00:00Z
step 1 'ISO 8601' -- update design --created "last week"
step 0 'status=blocked' -- update build-cli --blocked-reason "Waiting on design"
step 0 'blocked_reason removed' -- update build-cli --status in_progress --blocked-reason ""
step 0 'No updates specified' -- update build-cli
step 0 'Dry run: would update' -- update build-cli --title "Not applied" --dry-run

# Update assignee
step 0 'assignee=human' -- update design --assignee-name Bob
step 0 'assignee=agent' -- update build-cli --no-requires-human-review
step 0 'assignee=agent' -- update build-cli --agent-type reviewer
step 1 'only to human' -- update build-cli --assignee-name Bob
step 1 'no assignee' -- update wait --assignee-name Bob
step 0 'No updates specified' -- update wait --clear-assignee
step 0 'assignee cleared' -- update design --clear-assignee

# Update lists
step 0 'depends_on added' -- update wait --add-depends-on design build-cli
step 0 'depends_on removed' -- update wait --remove-depends-on build-cli
step 1 'cannot depend on itself' -- update wait --add-depends-on wait
step 0 'tags added' -- update design --add-tags spec core
step 0 'tags removed' -- update design --remove-tags core
step 0 'acceptance_criteria added' -- update design --add-acceptance-criteria "Reviewed"
step 0 'acceptance_criteria cleared' -- update design --clear-acceptance-criteria
step 0 'tags cleared' -- update design --clear-tags

# Update files
step 0 "added file 'docs/x.md'" -- update build-cli --add-file 'docs/x.md:create'
step 0 "op='delete'" -- update build-cli --file-op 'docs/x.md=delete'
step 0 "renamed_to='src/main.py'" -- update build-cli --file-renamed-to 'src/cli.py=src/main.py'
step 0 'reason removed' -- update build-cli --file-reason 'src/cli.py='
step 0 'removed 1 file' -- update build-cli --remove-file 'docs/x.md'
step 1 'already exists' -- update build-cli --add-file 'src/cli.py:read'
step 1 'No file entry' -- update build-cli --file-reason 'nope.py=x'
step 0 "added file 'tmp.txt'" -- update wait --add-file 'tmp.txt:read'
step 0 'files cleared' -- update wait --clear-files

# Rename
step 0 "id renamed to 'design-v2'" -- update design --new-id design-v2
step 0 'Depends on: design-v2' -- show build-cli
step 1 'already exists' -- update wait --new-id build-cli

# Status shortcuts
step 0 'status=in_progress' -- start wait
step 0 'Dry run' -- 'done' wait --dry-run
step 0 'status=done, completed=now' -- 'done' write-tests
step 0 'status=pending, completed timestamp removed' -- update write-tests --status pending
step 0 'completed=now' -- 'done' design-v2
step 0 'design-v2' -- list --status 'done'

# Move
step 0 'subtask of wait' -- move write-tests --parent wait
step 0 'already a subtask' -- move write-tests --parent wait
step 0 'Dry run' -- move write-tests --root --dry-run
step 0 'root level' -- move write-tests --root
step 0 'already at root' -- move write-tests --root
step 1 'Must specify' -- move write-tests
step 1 'Cannot specify both' -- move write-tests --root --parent wait

# Remove
step 0 "Added task 'temp'" -- add "Temp" --id temp --parent wait
step 1 'has subtasks' -- remove wait
step 0 'Dry run: would remove' -- remove wait --recursive --dry-run
step 0 "Removed task 'wait' and 1 subtask" -- remove wait --recursive
step 1 'not found' -- remove ghost

# Clean
step 0 'design-v2' -- clean --dry-run
step 0 'Pruning .* dependency|build-cli: removed design-v2' -- clean
step 0 'No completed todos' -- clean

# Final state
step 0 'Smoke test' -- meta --show
step 0 '.' -- list
check "final file validates against the schema" -- "$PY" -c '
import sys
sys.path.insert(0, sys.argv[1])
from todos_lib import io_ops
io_ops.validate_schema(io_ops.load_yaml(sys.argv[2]), sys.argv[3])
' "$SCRIPTS" "$TODOS_FILE" "$SCRIPTS/../assets/todos-schema.json"
check "final file has no empty lists" -- no_empty_lists "$TODOS_FILE"

echo "smoke_todos: passed=$pass failed=$fail"
if ((fail > 0)); then
  echo "smoke_todos: kept $WORK; see $LOG"
  exit 1
fi
rm -rf "$WORK"
