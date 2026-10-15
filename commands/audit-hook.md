---
description: Turn the automatic answer audit on or off (on [block], off, status)
argument-hint: on [block] | off | status
---

Use the `calibrate` skill. Run `kg.py hook` with the action from `$ARGUMENTS` (`on`, `off` or `status`; default `status`). If the arguments contain `block` together with `on`, pass `--mode block`, otherwise `--mode warn`. Then explain in one line what the resulting mode does: `warn` shows findings after each answer without interrupting, `block` asks the assistant to add missing glosses before finishing, `off` does nothing.
