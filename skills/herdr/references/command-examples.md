# Herdr Command Examples

## Start and Coordinate an Agent

```bash
herdr pane layout --pane "$HERDR_PANE_ID"
herdr pane split --current --direction right --cwd "$PWD" --no-focus
herdr agent start reviewer --kind codex --pane <pane-id-from-.result.pane.pane_id>
python3 scripts/herdr_send.py prompt reviewer --text "Review the current diff." --from-role implementer --reply
herdr agent wait reviewer --until done
herdr agent read reviewer --source recent-unwrapped --lines 120
```

## Run an Ordinary Command

```bash
herdr pane split --current --direction right --cwd "$PWD" --no-focus
herdr pane run <pane-id> "just test"
herdr pane wait-output <pane-id> --regex "test result" --timeout 120000
herdr pane read <pane-id> --source recent-unwrapped --lines 120
```

wait-output also matches output that already exists.

## Cross-Agent Messaging With `herdr_send.py`

Check a target is ready:

```bash
python3 scripts/herdr_send.py check reviewer
python3 scripts/herdr_send.py check reviewer --disable-working --wait 30
```

Send a message expecting a reply:

```bash
python3 scripts/herdr_send.py prompt reviewer \
  --text "Review the diff" \
  --from-role implementer \
  --reply
```

The default wait is 180 seconds; pass `--wait 600` to wait longer or `--wait 0` for one attempt.
A result such as `{"result": "timeout", "last_refusal": {"reason": "typed_text", ...}, "message_id": "...", ...}` means someone kept text in the input box; the message stays saved and the next `prompt` to that target delivers it first.

List and cancel saved messages:

```bash
python3 scripts/herdr_send.py pending list reviewer --yaml
python3 scripts/herdr_send.py pending drop 20261125T231502123456Z-7f3a9c
python3 scripts/herdr_send.py pending drop --target reviewer --all
```

Send a slash command without header:

```bash
echo "/goal-direct Fix the auth bug" | \
  python3 scripts/herdr_send.py prompt architect \
  --no-header \
  -
```

Send a task to Xorc:

```bash
python3 scripts/herdr_send.py prompt w1:p4 \
  --tui xorc \
  --text "Run the plan" \
  --from-role architect
```

Run a command in a shell pane:

```bash
python3 scripts/herdr_send.py run w1:p5 \
  --text "just test"
```
