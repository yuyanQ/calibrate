---
description: Quick check on concepts that are due for verification
argument-hint: [number of concepts, default 3]
---

Use the `calibrate` skill. Run `kg.py due --limit ${ARGUMENTS:-3}`. For each concept returned, ask one short question that tests understanding, not recall of the definition. Ask them one at a time and wait for the answer. Judge each answer, run `kg.py verify "<term>" pass|fail`, and give one line of feedback. If nothing is due, say so.
