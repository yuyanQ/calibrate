---
name: calibrate
description: Use when answering technical, scientific or conceptual questions where specialized terms may be unfamiliar to the user. Checks the terms in a draft answer against the user's personal concept graph (mastery states), glosses unfamiliar ones, lightly marks half-known ones, caps new concepts per answer, and records feedback. Also handles the verbs init, unclear, learned, quiz, stats, audit and hook (marking concepts, quiz verification, gloss audit).
---

# Calibrate

The user's knowledge is uneven: deep in some areas, thin in others, and you cannot guess which. This skill grounds your answers in an explicit per-concept record instead of guessing. It changes how an answer is presented, never what is true.

The script is `scripts/kg.py`, next to this file (use the skill's base directory shown when it loads). Run it with `python3 -I <base>/scripts/kg.py <command>`. Data lives in `$PERSONAL_KG_DIR` (default `~/personal-kg`), one markdown file per concept.

States: `queued` (deferred) → `unknown` (not understood) → `seen` (user says they understand) → `verified` (passed a quick check; decays after 90 days).

## Answering protocol

1. **Draft at expert level.** Write the answer normally. Do not simplify up front, that loses precision.
2. **List the terms.** From the draft, list specialized concepts a reader outside that sub-area might not know (canonical names, at most about 15). Skip everyday words and baseline knowledge of the user's field; the graph learns that baseline from feedback.
3. **Look them up:** `kg.py lookup "term 1" "term 2" ... --max-new 3`. The script is deterministic: do not re-judge its decisions.
4. **Render by `action`:**
   - `plain` (verified): leave as written.
   - `light` (seen): append `°` to the first mention. No explanation.
   - `gloss` (unknown): explain inline at first mention in one short clause, reusing the stored `gloss` and, when helpful, an analogy built from the concept's `related` neighbors that are verified.
   - `introduce` (new, within the cap): gloss inline, then register it: `kg.py mark "<term>" unknown --gloss "<one line>" [--related "<neighbor>"]`.
   - `defer` (over the cap): do not gloss. Rephrase around the term if that is easy; otherwise leave it. The script already queued it.
5. **Footer, only if something was introduced or marked:** one line, `New concepts: A, B. Reply /learned A B when clear, or /unclear X if not.`
6. **Quiz at most one concept per answer.** If any result has `quiz_due: true`, ask one short check question about it at the very end. When the user answers, run `kg.py verify "<term>" pass|fail`.

## Marking feedback

- User says a term was not understood (`/unclear X`, or plainly in chat): `kg.py mark "X" unknown --gloss "<one line from context>"`, then explain X using verified neighbors.
- User says they now understand (`/learned X`): `kg.py mark "X" seen`. Never set `verified` from self-report; `verified` comes from `kg.py verify` after a check, or from an explicit bulk import the user asked for.
- Other commands: `kg.py list [--status S]`, `kg.py due`, `kg.py stats`.
- Bulk bootstrap: `kg.py import file.json` loads a JSON list of `{name, status, gloss, aliases, related, source}`. Existing concepts are kept, `verified` is downgraded to `seen` unless `--allow-verified`, and imports are not counted in the unclear-per-day metric. Derive candidates from the user's own code and notes, mark only strong evidence as `seen`, and let the user classify the rest.

## Audit

`kg.py audit --file <answer.txt> [--terms ...]` checks that every `unknown` concept, and every term in `--terms` that is not in the graph, has an inline gloss (parenthetical or `, i.e.`) at its first mention. When the audit hook is on, it runs after each answer; if it reports missing glosses, add them in parentheses at first mention and change nothing else. Pass multi-word specialized terms via `--terms`, since the script only detects acronyms and CamelCase on its own.

## Verbs

Explicit invocations. In Claude Code they are the slash commands `/calibrate:<verb>`, in Codex write `$calibrate <verb> <arguments>`. Run `kg.py` as described above.

- `init`: run `kg.py init`. Report in two lines where the data folder is and what `graph_colors` says. If it says `pending`, tell the user to quit Obsidian completely (Cmd+Q) and run `init` again. If `ok`, they can open the folder as an Obsidian vault.
- `unclear X[, Y]`: for each term, `kg.py mark "<term>" unknown --gloss "<one line from the conversation if available>"`, then explain each briefly, anchored on concepts the graph says are `verified`. Keep it short.
- `learned X[, Y]`: for each term, `kg.py mark "<term>" seen`, never `verified`. Reply with one line saying what was updated and that a quick check will come up the next time the concept appears.
- `quiz [n]`: run `kg.py due --limit <n, default 3>`. For each concept returned, ask one short question that tests understanding, not recall of the definition. Ask one at a time and wait for the answer. Judge it, run `kg.py verify "<term>" pass|fail`, and give one line of feedback. If nothing is due, say so.
- `stats`: run `kg.py stats` and summarize in two or three lines: counts per state, and whether the number of concepts marked `unknown` per day is trending down.
- `audit [terms]`: save the text of your previous answer to a temporary file and run `kg.py audit --file <file> --terms <the specialized terms the answer used, including multi-word ones, plus any terms in the arguments>`. Report failures (an unknown or unregistered concept mentioned without an inline gloss) and warnings (suspected unregistered terms). If there are failures, give only the corrected sentences with the missing glosses, not a rewrite of the whole answer.
- `hook on [block] | off | status` (Claude Code only): run `kg.py hook` with the action, adding `--mode block` only for `on block`. Explain in one line what the resulting mode does: `warn` shows findings after each answer, `block` asks for missing glosses before finishing, `off` does nothing. In Codex there is no automatic audit, say so and point to `audit`.

## Rules

- Match the language of the conversation for glosses and the footer.
- Prefer under-marking to over-marking. A wrongly marked term erodes trust; a missed one just equals normal behavior.
- If the script fails or the data directory is unreadable, answer normally and say so in one line. Never block the answer on the graph.
- Never alter facts, caveats or citations to make an answer easier. Adapt presentation only.
