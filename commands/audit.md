---
description: Check your previous answer for unknown or unregistered concepts that lack an inline gloss
argument-hint: [extra term, ...]
---

Use the `calibrate` skill. Take your previous answer in this conversation, save its text to a temporary file, and run `kg.py audit --file <that file> --terms <the specialized terms the answer uses, including multi-word ones, plus: $ARGUMENTS>`. Report failures (an unknown or unregistered concept mentioned without an inline gloss) and warnings (suspected unregistered terms). If there are failures, give the corrected sentences with the missing glosses. Do not rewrite the whole answer.
