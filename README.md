# Calibrate (personal-kg-plugin)

**An LLM plugin that knows what you already know.**

LLM answers often lose the reader, because the reader's knowledge is uneven (deep in some areas, thin in others) and the model cannot tell which is which. Calibrate keeps a personal concept graph with per-concept mastery states (not understood, seen, verified), grows it from your "I didn't get this" feedback, and uses it to adapt answers: familiar concepts stay as written, unfamiliar ones get a one-line gloss or an analogy built from things you already know, and the number of new concepts per answer is capped. Annotation is done by a deterministic script, so behavior stays consistent across runs. Notes are plain markdown, so you can browse the graph in Obsidian.

> **Limits, please read.** Calibrate adapts how an answer is *presented* to your mastery state. It does not check whether an answer is factually correct. Which terms count as specialized is decided by the model, so some are missed, and the skill is triggered by the model, so it can be skipped. The audit hook and the Obsidian setup were developed and tested on macOS with Obsidian 1.8; other setups may need adjustments. Details in [Limits](#limits).

## Contents

1. [How it works](#how-it-works)
2. [Requirements](#requirements)
3. [Install](#install)
4. [First-time setup](#first-time-setup)
5. [Daily use, step by step](#daily-use-step-by-step)
6. [Bootstrap the graph from your own work](#bootstrap-the-graph-from-your-own-work)
7. [Browse the graph in Obsidian](#browse-the-graph-in-obsidian)
8. [Audit and the optional Stop hook](#audit-and-the-optional-stop-hook)
9. [Command reference](#command-reference)
10. [Data and configuration](#data-and-configuration)
11. [Update, uninstall, troubleshooting](#update-uninstall-troubleshooting)
12. [Limits](#limits)
13. [License](#license)

## How it works

Each concept has one of four states:

| State | Meaning |
|---|---|
| `queued` | Deferred because an answer already introduced its quota of new concepts. Not shown to you yet. |
| `unknown` | You did not understand it, or it was just introduced. |
| `seen` | You say you understand it. Self-report only. |
| `verified` | You passed a quick check. Decays back to `seen` after 90 days. |

For a technical or conceptual question, Claude follows this protocol (defined in `skills/calibrate/SKILL.md`):

1. Draft an expert-level answer, without simplifying up front.
2. List the specialized terms in the draft.
3. Run `kg.py lookup`, a deterministic script, which returns one action per term.
4. Render the answer by action:

| Your state | Action | What you see |
|---|---|---|
| verified | `plain` | term left as is |
| seen | `light` | term marked with `°` |
| unknown | `gloss` | inline one-line gloss, reusing the stored gloss |
| new, within the cap (3 per answer) | `introduce` | inline gloss, saved as `unknown` |
| new, over the cap | `defer` | no gloss, saved as `queued` for later |

5. End with a footer such as `New concepts: A, B. Reply /learned A B when clear, or /unclear X if not.`
6. At most one quiz question per answer, when a concept is due for verification.

You feed back with `/calibrate:unclear` and `/calibrate:learned`. A concept becomes `verified` only after a check, never from self-report.

## Requirements

- [Claude Code](https://claude.com/claude-code) with plugin support (`claude plugin --help` should work).
- Python 3 on your `PATH` as `python3`. The scripts use only the standard library. Tested with Python 3.11 only. The code avoids newer syntax, so 3.8 should work, but that is untested.
- Optional: [Obsidian](https://obsidian.md) 1.4 or newer to browse the graph. Tested with 1.8.10.

## Install

**Option A, from GitHub (recommended).** In Claude Code:

```
/plugin marketplace add yuyanQ/calibrate
/plugin install calibrate@calibrate
```

Or from a terminal:

```bash
claude plugin marketplace add yuyanQ/calibrate
claude plugin install calibrate@calibrate
```

**Option B, from a local clone.**

```bash
git clone https://github.com/yuyanQ/calibrate.git ~/calibrate
claude plugin marketplace add ~/calibrate
claude plugin install calibrate@calibrate
```

**Option C, try it for one session without installing.**

```bash
claude --plugin-dir ~/calibrate
```

**Verify and restart.** Run `claude plugin list`, you should see `calibrate@calibrate` with status `enabled`. Restart Claude Code (or open a new session) so the skill and the slash commands load. The commands then appear as `/calibrate:unclear`, `/calibrate:learned`, and so on.

## First-time setup

1. Start a new Claude Code session and run:

   ```
   /calibrate:init
   ```

   This creates the data folder `~/personal-kg` (override with `PERSONAL_KG_DIR`, see [Data and configuration](#data-and-configuration)).
2. If you use Obsidian, **quit Obsidian completely (Cmd+Q) before this step**, otherwise the output says `graph_colors: pending` and the mastery colors are not written. If that happens, quit Obsidian and run `/calibrate:init` again. See [Browse the graph in Obsidian](#browse-the-graph-in-obsidian).
3. Optional: pre-fill the graph from your own work, see [Bootstrap](#bootstrap-the-graph-from-your-own-work). Skipping this is fine, the graph also grows from your feedback alone.

## Daily use, step by step

1. **Ask a technical or conceptual question** as usual. Claude follows the protocol above. If it did not, say "use calibrate".
2. **Read the answer.** Terms marked with `°` are ones you said you understand. Parenthetical glosses are for terms you did not understand or that are new. The footer lists the new concepts.
3. **Tell it what you did not get.**

   ```
   /calibrate:unclear RQ-VAE, softmax
   ```

   Several terms can be separated with commas. Each is saved as `unknown`, then explained briefly.
4. **Tell it what you now understand.**

   ```
   /calibrate:learned softmax
   ```

   The concept moves to `seen`. It does not become `verified` yet.
5. **Get verified.** Run `/calibrate:quiz` (optionally with a number, default 3). Claude asks one short question per concept that is due, judges your answer, and records pass or fail. Pass gives `verified`, fail gives `unknown`. A concept is due when it is `seen` and was last met on an earlier day, or when its `verified` status is older than 90 days.
6. **Track progress.** `/calibrate:kg-stats` shows concepts per state and how many you flagged as unclear per day. That daily number is the readability metric, it should go down over time. Imports and bootstrapping are not counted in it.

## Bootstrap the graph from your own work

Starting empty works, but you can seed the graph from things you have actually used. Ask Claude something like "build a bootstrap list from my project's requirements and README". A good routine is:

1. **Collect candidates with evidence.** Libraries in `requirements.txt`, methods in your code, metrics in your evaluation scripts, terms in documents you wrote.
2. **Mark only strong evidence as `seen`.** Code you ran counts, text you merely read or that was written with help does not.
3. **Ask yourself about the rest.** Claude can ask you to pick, per concept, `seen` or `unknown`. Unselected concepts become `unknown`, which is the safe direction: a gloss you did not need costs a clause, a missing gloss costs confusion.
4. **Import** a JSON file with `kg.py import`:

   ```json
   [
     {
       "name": "Contrastive learning",
       "aliases": ["SimCLR-style learning"],
       "status": "seen",
       "gloss": "Self-supervised learning that pulls positive pairs together and pushes negatives apart.",
       "related": ["Embedding"],
       "source": "my_project/contrastive_utils.py"
     }
   ]
   ```

   Existing concepts are kept (use `--overwrite` to replace them). `verified` in the file is downgraded to `seen` unless you pass `--allow-verified`.

## Browse the graph in Obsidian

1. Install Obsidian, choose "Open folder as vault", and pick `~/personal-kg`.
2. Open the graph view (ribbon icon, or Cmd+G). Notes are concepts, links are the `related` field.
3. Mastery colors: red `unknown`, amber `seen`, green `verified`, gray `queued`. Every concept file carries a `mastery-<status>` tag, and `/calibrate:init` adds one color group per tag (`tag:#mastery-unknown`, and so on) to `.obsidian/graph.json`. It also turns off tag nodes in the graph, otherwise four tag hubs would sit in the middle of it.
4. **Quit Obsidian (Cmd+Q) before running `/calibrate:init` for the first time.** Obsidian keeps its settings in memory and overwrites edits made while it runs, so the script skips `graph.json` and reports `pending` when Obsidian is open. After the first setup, reopen Obsidian. From then on the tags follow your mastery states and the colors update by themselves.
5. Groups that already exist, including ones you recolored, are never changed.

Links are written as `[[slug|Name]]`, so they resolve by file name. A concept that is referenced but not created yet shows up as an empty ghost node until you mark it.

## Audit and the optional Stop hook

`kg.py audit` checks a text against the graph. At the **first mention**, a concept needs an inline gloss: a parenthetical of at least 4 characters (`X (...)` or `X（...）`), or `, i.e.` / `，即` / `，也就是`. A citation like `(Zhang et al., 2026)` does not count. Fenced code blocks, URLs and the "New concepts" footer line are ignored.

- **Failures** (exit code 1): concepts marked `unknown`, and terms passed with `--terms` that are not in the graph, mentioned without a gloss.
- **Warnings**: acronyms and CamelCase words that are not in the graph and not ignored. Multi-word terms are only caught via `--terms`. Silence a term with `kg.py ignore TERM`. Common words such as LLM, GPU, API, JSON are ignored by default.

On demand, run `/calibrate:audit` to audit Claude's previous answer.

**Automatic audit (Stop hook).** Off by default, switched by the file `~/personal-kg/.audit_on`:

| Command | Effect |
|---|---|
| `/calibrate:audit-hook on` | after each answer, show findings without interrupting (`warn`) |
| `/calibrate:audit-hook on block` | on failures, ask Claude to add the missing glosses before finishing (blocks at most once per answer) |
| `/calibrate:audit-hook off` | disable |
| `/calibrate:audit-hook status` | show the current mode |

Start with `warn` for a few days to see how noisy the warnings are before trying `block`.

## Command reference

**Slash commands**

| Command | What it does |
|---|---|
| `/calibrate:init` | Create the data folder and set up Obsidian mastery colors |
| `/calibrate:unclear X[, Y]` | Mark concepts as `unknown` and explain them |
| `/calibrate:learned X[, Y]` | Mark concepts as `seen` |
| `/calibrate:quiz [n]` | Quick check on due concepts, records pass or fail |
| `/calibrate:kg-stats` | Concepts per state, unclear flags per day |
| `/calibrate:audit [terms]` | Audit the previous answer |
| `/calibrate:audit-hook on [block] / off / status` | Control the automatic audit |

**Script** `skills/calibrate/scripts/kg.py` (called by the skill and commands, you can also run it yourself, for example `python3 skills/calibrate/scripts/kg.py stats` from a clone):

| Subcommand | Purpose |
|---|---|
| `init` | Create the data folder, set up Obsidian colors |
| `lookup TERM... [--max-new N] [--no-touch]` | Action per term, deferring new terms beyond N (default 3) |
| `mark TERM STATUS [--gloss ...] [--alias ...] [--related ...] [--source ...]` | Create or update a concept |
| `import FILE [--overwrite] [--allow-verified]` | Bulk load from JSON |
| `verify TERM pass\|fail` | Record a quiz result |
| `list [--status S]` | List concepts |
| `due [--limit N]` | Concepts due for a check |
| `stats` | Counts and unclear-per-day |
| `audit [--file F] [--terms ...]` | Gloss audit, reads stdin if no file |
| `ignore TERM...` | Never warn about these terms |
| `hook on [--mode warn\|block] / off / status` | Control the Stop hook |
| `rebuild` | Rewrite all concept files in the current format |

If you installed from a marketplace, the script lives in the plugin cache: `find ~/.claude/plugins/cache -name kg.py`.

## Data and configuration

Your data lives outside the plugin, so updating or uninstalling the plugin never touches it.

```
~/personal-kg/
├── concepts/
│   └── self-attention.md     one markdown file per concept
├── events.jsonl              append-only log used by stats
├── ignore.txt                optional, terms the audit never warns about
├── .audit_on                 optional, present only while the hook is on
└── .obsidian/                created by Obsidian, graph.json gets the color groups
```

A concept file:

```markdown
---
name: "Self-attention"
aliases: ["self attention"]
status: "verified"
tags: ["mastery-verified"]
gloss: "Each token weighs all tokens of the same sequence."
related: ["Transformer"]
source: "my_project/model.py"
first_seen: "2026-10-15"
last_seen: "2026-10-15"
last_verified: "2026-10-15"
---

# Self-attention

Each token weighs all tokens of the same sequence.

## Related
- [[transformer|Transformer]]

## Notes
Anything you write here is preserved.
```

You can edit files by hand. Keep the frontmatter valid, and put free text under `## Notes`.

| Environment variable | Default | Meaning |
|---|---|---|
| `PERSONAL_KG_DIR` | `~/personal-kg` | Where the data lives |
| `PKG_DECAY_DAYS` | `90` | How long `verified` lasts before it counts as `seen` again |

Concept matching is exact on names and aliases, plus a conservative fuzzy match (similarity 0.92 or higher, terms of 5 or more characters). Add aliases to improve matching.

## Update, uninstall, troubleshooting

**Update.**

```bash
claude plugin marketplace update calibrate
claude plugin update calibrate@calibrate
```

Then restart Claude Code.

**Uninstall.**

```bash
claude plugin uninstall calibrate@calibrate
claude plugin marketplace remove calibrate
```

Your data in `~/personal-kg` stays. Delete the folder yourself if you want it gone.

**Troubleshooting.**

| Symptom | Likely cause and fix |
|---|---|
| Slash commands do not appear | Restart Claude Code after installing. Check `claude plugin list`. |
| The skill is not used on a technical question | The skill is model-triggered. Say "use calibrate", or name the plugin in your question. |
| `graph_colors: pending` | Obsidian is running. Quit it with Cmd+Q and run `/calibrate:init` again. |
| `graph_colors: unreadable` | `.obsidian/graph.json` is not valid JSON. Fix or delete it, then run `/calibrate:init`. |
| No colors in the graph view | Reopen Obsidian after `/calibrate:init` reported `ok`. If still empty, open the graph settings and check that the groups `tag:#mastery-...` exist. |
| The audit hook does nothing | Check `/calibrate:audit-hook status`. The hook only reports findings, and only after a restart following install or update. |
| Too many audit warnings | Add the terms with `kg.py ignore TERM`, or mark them with `/calibrate:learned`. |

## Limits

- **Presentation, not truth.** Calibrate changes how an answer is written for your mastery state. It does not verify facts, caveats or citations.
- **Term extraction is the model's job.** Specialized terms are listed by Claude, so some are missed. A missed term behaves like a normal, unannotated answer. The audit only finds acronyms and CamelCase on its own, multi-word terms need `--terms`.
- **Triggering is not guaranteed.** The skill is selected by the model. Use the audit hook to catch misses.
- **Self-report is unreliable.** `/calibrate:learned` only gives `seen`. Verification needs a check.
- **Concept matching is simple.** Exact names and aliases plus a conservative fuzzy match. There is no embedding-based linking yet.
- **Tested setup.** macOS, Claude Code, Python 3.11, Obsidian 1.8.10. The Stop hook was tested with simulated hook input and a synthetic transcript, so its behavior inside a live session may differ on other versions. The Obsidian check uses `pgrep`, so on Windows the script cannot tell whether Obsidian is running and you must quit it yourself.
- **Early version.** No MCP server, no embedding retrieval, no session-start hook for domain-level priors.

## License

[MIT](LICENSE)
