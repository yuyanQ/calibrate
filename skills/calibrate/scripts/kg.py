#!/usr/bin/env python3
"""Personal concept graph for the Calibrate plugin (standard library only).

Data lives outside the plugin, in $PERSONAL_KG_DIR (default ~/personal-kg):
    concepts/<slug>.md   one markdown file per concept (frontmatter + Obsidian [[links]])
    events.jsonl         append-only log used by `stats`

Mastery states: queued -> unknown -> seen -> verified
    queued    deferred by the per-answer cap, not yet shown to the user
    unknown   the user did not understand it (or it was just introduced)
    seen      the user says they understand it (self-report, not verified)
    verified  passed a quick check; decays back to `seen` after $PKG_DECAY_DAYS (default 90)

Commands: init | lookup | mark | import | verify | list | due | stats | audit | ignore | hook | rebuild
"""
import argparse
import datetime as dt
import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

STATUSES = ("queued", "unknown", "seen", "verified")
FUZZY_CUTOFF = 0.92
FUZZY_MIN_LEN = 5

DATA_DIR = Path(os.environ.get("PERSONAL_KG_DIR", "~/personal-kg")).expanduser()
CONCEPTS_DIR = DATA_DIR / "concepts"
EVENTS_FILE = DATA_DIR / "events.jsonl"
DECAY_DAYS = int(os.environ.get("PKG_DECAY_DAYS", "90"))


def today():
    return dt.date.today().isoformat()


def normalize(text):
    text = re.sub(r"[\s_\-]+", " ", text.strip().lower())
    return re.sub(r"[^\w ]", "", text).strip()


def slugify(name):
    slug = re.sub(r"[^\w]+", "-", name.strip().lower()).strip("-")
    return slug or "concept"


def parse_value(raw):
    raw = raw.strip()
    if raw[:1] in ('"', "["):
        try:
            return json.loads(raw)
        except ValueError:
            pass
    return raw


def read_concept(path):
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                if ": " in line or line.endswith(":"):
                    key, _, value = line.partition(":")
                    meta[key.strip()] = parse_value(value)
            body = text[end + 4:].lstrip("\n")
    notes = ""
    marker = "## Notes"
    if marker in body:
        notes = body.split(marker, 1)[1].strip("\n")
    meta.setdefault("aliases", [])
    meta.setdefault("related", [])
    meta.setdefault("status", "unknown")
    meta["_slug"] = path.stem
    meta["_notes"] = notes
    return meta


def write_concept(meta):
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    meta["tags"] = [f"mastery-{meta['status']}"]
    fields = ("name", "aliases", "status", "tags", "gloss", "related", "source",
              "first_seen", "last_seen", "last_verified")
    lines = ["---"]
    for key in fields:
        value = meta.get(key, "")
        if isinstance(value, (list, str)) and (isinstance(value, list) or value):
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            lines.append(f"{key}:")
    lines.append("---")
    body = [f"# {meta['name']}", ""]
    if meta.get("gloss"):
        body += [meta["gloss"], ""]
    if meta.get("related"):
        # Obsidian resolves links by file name, so link to the slug and show the name
        known = load_all()
        index = build_index(known)
        links = []
        for rel in meta["related"]:
            slug, _ = find(rel, known, index)
            links.append(f"- [[{slug or slugify(rel)}|{rel}]]")
        body += ["## Related"] + links + [""]
    body += ["## Notes", meta.get("_notes", "")]
    text = "\n".join(lines) + "\n\n" + "\n".join(body).rstrip("\n") + "\n"
    (CONCEPTS_DIR / f"{meta['_slug']}.md").write_text(text, encoding="utf-8")


GRAPH_COLORS = {"unknown": 0xE5484D, "seen": 0xF5A524, "verified": 0x30A46C, "queued": 0x8B8D98}


def obsidian_running():
    try:
        return subprocess.run(["pgrep", "-x", "Obsidian"], capture_output=True).returncode == 0
    except OSError:
        return False


def ensure_graph_style():
    """Add mastery color groups to the vault's Obsidian graph view.

    Groups match the `mastery-<status>` tag written into each concept's frontmatter.
    Existing groups, including ones the user recolored, are left untouched. While
    Obsidian is running the file is not touched, because Obsidian keeps its settings
    in memory and overwrites edits made behind its back. Returns a status string.
    """
    path = DATA_DIR / ".obsidian" / "graph.json"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        return "unreadable"  # never clobber a settings file we cannot parse
    groups = cfg.get("colorGroups") or []
    have = {g.get("query") for g in groups}
    added = [{"query": f"tag:#mastery-{s}", "color": {"a": 1, "rgb": rgb}}
             for s, rgb in GRAPH_COLORS.items() if f"tag:#mastery-{s}" not in have]
    if not added:
        return "ok"
    if obsidian_running():
        return "pending: quit Obsidian, then run `kg.py init`"
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg["colorGroups"] = groups + added
    cfg["showTags"] = False  # tag nodes would hang four hubs in the middle of the graph
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return "ok"


def load_all():
    if not CONCEPTS_DIR.is_dir():
        return {}
    concepts = {}
    for path in sorted(CONCEPTS_DIR.glob("*.md")):
        meta = read_concept(path)
        meta.setdefault("name", path.stem)
        concepts[path.stem] = meta
    return concepts


def build_index(concepts):
    index = {}
    for slug, meta in concepts.items():
        for label in [meta["name"]] + list(meta["aliases"]):
            index.setdefault(normalize(label), slug)
    return index


def find(term, concepts, index):
    key = normalize(term)
    if key in index:
        return index[key], "exact"
    if len(key) >= FUZZY_MIN_LEN:
        close = difflib.get_close_matches(key, list(index), n=1, cutoff=FUZZY_CUTOFF)
        if close:
            return index[close[0]], "fuzzy"
    return None, None


def log_event(event, **fields):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "event": event}
    record.update(fields)
    with EVENTS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def days_since(date_str):
    try:
        return (dt.date.today() - dt.date.fromisoformat(date_str)).days
    except (TypeError, ValueError):
        return None


def effective(meta):
    """Return (effective_status, stale, quiz_due) for a stored concept."""
    status = meta["status"]
    stale = False
    if status == "verified":
        age = days_since(meta.get("last_verified"))
        if age is None or age > DECAY_DAYS:
            status, stale = "seen", True
    quiz_due = stale
    if status == "seen" and not stale:
        age = days_since(meta.get("last_seen"))
        quiz_due = age is not None and age >= 1
    return status, stale, quiz_due


def cmd_init(_args):
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"data_dir": str(DATA_DIR), "concepts": len(load_all()),
                      "graph_colors": ensure_graph_style()}))


def cmd_lookup(args):
    concepts = load_all()
    index = build_index(concepts)
    results, new_budget = [], args.max_new
    for term in args.terms:
        slug, how = find(term, concepts, index)
        if slug is not None and concepts[slug]["status"] != "queued":
            meta = concepts[slug]
            status, stale, quiz_due = effective(meta)
            action = {"verified": "plain", "seen": "light", "unknown": "gloss"}[status]
            results.append({
                "term": term, "concept": meta["name"], "match": how,
                "status": status, "stale": stale, "quiz_due": quiz_due,
                "action": action, "gloss": meta.get("gloss", ""),
                "related": meta["related"],
            })
            if not args.no_touch:
                meta["last_seen"] = today()
                write_concept(meta)
            continue
        # not in the graph (or only queued): introduce within the cap, else defer
        if new_budget > 0:
            new_budget -= 1
            results.append({"term": term, "concept": None, "status": "new",
                            "action": "introduce", "gloss": "", "related": []})
        else:
            results.append({"term": term, "concept": None, "status": "new",
                            "action": "defer", "gloss": "", "related": []})
            if slug is None and not args.no_touch:
                register(term, "queued")
    print(json.dumps(results, ensure_ascii=False, indent=2))


def register(term, status, gloss="", aliases=(), related=(), source="", log=True):
    concepts = load_all()
    index = build_index(concepts)
    slug, _ = find(term, concepts, index)
    created = slug is None
    if created:
        slug = slugify(term)
        base, n = slug, 2
        while slug in concepts:
            slug, n = f"{base}-{n}", n + 1
        meta = {"name": term.strip(), "aliases": [], "related": [], "_slug": slug,
                "_notes": "", "first_seen": today()}
    else:
        meta = concepts[slug]
    meta["status"] = status
    meta["last_seen"] = today()
    if status == "verified":
        meta["last_verified"] = today()
    if gloss:
        meta["gloss"] = gloss
    if source:
        meta["source"] = source
    for label in aliases:
        if normalize(label) != normalize(meta["name"]) and label not in meta["aliases"]:
            meta["aliases"].append(label)
    for rel in related:
        if rel not in meta["related"]:
            meta["related"].append(rel)
    write_concept(meta)
    ensure_graph_style()
    if log:
        log_event("mark", term=meta["name"], status=status, created=created)
    return meta, created


def cmd_mark(args):
    meta, created = register(args.term, args.status, args.gloss or "",
                             args.alias or (), args.related or (), args.source or "")
    print(json.dumps({"concept": meta["name"], "status": meta["status"],
                      "created": created, "file": f"concepts/{meta['_slug']}.md"},
                     ensure_ascii=False))


def cmd_import(args):
    """Bulk-load concepts from a JSON list; existing concepts are kept unless --overwrite."""
    items = json.loads(Path(args.file).read_text(encoding="utf-8"))
    concepts = load_all()
    index = build_index(concepts)
    added, skipped = [], []
    for item in items:
        status = item.get("status", "seen")
        if status == "verified" and not args.allow_verified:
            status = "seen"
        slug, _ = find(item["name"], concepts, index)
        if slug is not None and not args.overwrite:
            skipped.append(item["name"])
            continue
        register(item["name"], status, item.get("gloss", ""), item.get("aliases", ()),
                 item.get("related", ()), item.get("source", ""), log=False)
        concepts = load_all()
        index = build_index(concepts)
        added.append(item["name"])
    log_event("import", file=Path(args.file).name, added=len(added), skipped=len(skipped))
    print(json.dumps({"added": len(added), "skipped_existing": skipped}, ensure_ascii=False))


def cmd_verify(args):
    status = "verified" if args.result == "pass" else "unknown"
    meta, created = register(args.term, status)
    log_event("verify", term=meta["name"], result=args.result)
    print(json.dumps({"concept": meta["name"], "status": meta["status"]},
                     ensure_ascii=False))


def cmd_list(args):
    rows = []
    for meta in load_all().values():
        if args.status and meta["status"] != args.status:
            continue
        rows.append({"name": meta["name"], "status": meta["status"],
                     "last_seen": meta.get("last_seen", ""),
                     "gloss": meta.get("gloss", "")})
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_due(args):
    rows = []
    for meta in load_all().values():
        status, stale, quiz_due = effective(meta)
        if quiz_due and meta["status"] != "queued":
            rows.append({"name": meta["name"], "status": status, "stale": stale,
                         "gloss": meta.get("gloss", "")})
    print(json.dumps(rows[: args.limit], ensure_ascii=False, indent=2))


def cmd_stats(_args):
    counts = {s: 0 for s in STATUSES}
    for meta in load_all().values():
        counts[meta["status"]] = counts.get(meta["status"], 0) + 1
    per_day = {}
    if EVENTS_FILE.is_file():
        for line in EVENTS_FILE.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("event") == "mark" and rec.get("status") == "unknown":
                day = rec["ts"][:10]
                per_day[day] = per_day.get(day, 0) + 1
    print(json.dumps({"concepts_by_status": counts,
                      "unknown_marked_per_day": dict(sorted(per_day.items())[-14:])},
                     ensure_ascii=False, indent=2))


DEFAULT_IGNORE = {
    "AI", "ML", "LLM", "LLMS", "GPU", "CPU", "API", "URL", "JSON", "CSV", "SQL", "HTTP",
    "HTTPS", "PDF", "HTML", "CSS", "XML", "YAML", "ID", "IDS", "OK", "TODO", "NLP", "GPT",
    "UI", "CLI", "OS", "RAM", "PR", "CI", "FAQ", "UTC", "ASCII", "UTF",
}
ACRONYM_RE = re.compile(
    r"(?<![A-Za-z0-9_\-])(?:[A-Z][A-Z0-9]*(?:-[A-Za-z0-9]+)+|[A-Z]{2,}[A-Za-z0-9]*)(?![A-Za-z0-9_])")
CAMEL_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+(?![A-Za-z0-9_])")
FENCE_RE = re.compile(r"```.*?```", re.S)
URL_RE = re.compile(r"https?://\S+|\]\([^)]*\)")
FOOTER_RE = re.compile(r"^.*(?:New concepts|新概念).*$", re.M | re.I)
SKIP_AFTER = "*_`°\"'”’」』 \t"
GLOSS_LEADS = ("，即", ", i.e.", ",i.e.", "，也就是", "，指", "，是指")


def clean_text(text):
    """Blank out regions the audit must ignore, keeping offsets stable."""
    for regex in (FENCE_RE, URL_RE, FOOTER_RE):
        text = regex.sub(lambda m: " " * len(m.group()), text)
    return text


def label_pattern(label):
    if re.search(r"[^\x00-\x7f]", label):
        return re.compile(re.escape(label), re.I)
    parts = [re.escape(p) for p in re.split(r"[\s\-_]+", label.strip()) if p]
    body = r"[\s\-_]*".join(parts)
    return re.compile(rf"(?<![A-Za-z0-9]){body}s?(?![A-Za-z0-9])", re.I)


def has_gloss(text, end):
    """True if the mention ending at `end` is followed by an inline explanation."""
    rest = text[end:end + 260].lstrip(SKIP_AFTER)
    if rest[:1] in ("(", "（"):
        closes = [i for i in (rest.find(c) for c in (")", "）")) if i > 0]
        inner = rest[1:min(closes) if closes else len(rest)].strip()
        return len(inner) >= 4 and not re.search(r"et al\.?|\b(?:19|20)\d{2}\b", inner)
    return rest.startswith(GLOSS_LEADS)


def run_audit(text, terms=()):
    """Check that unknown / unregistered concepts get an inline gloss at first mention.

    failures: concepts the graph marks unknown, or terms passed via `terms` that are
              not in the graph, mentioned without a gloss.
    warnings: heuristic candidates (acronyms, CamelCase) not in the graph and not
              ignored, mentioned without a gloss. Multi-word terms are only caught
              when passed via `terms`.
    """
    concepts = load_all()
    index = build_index(concepts)
    ignore = set(DEFAULT_IGNORE)
    ignore_file = DATA_DIR / "ignore.txt"
    if ignore_file.is_file():
        ignore |= {ln.strip().upper() for ln in
                   ignore_file.read_text(encoding="utf-8").splitlines() if ln.strip()}
    clean = clean_text(text)

    targets = []  # (labels, display, kind, severity)
    for meta in concepts.values():
        if meta["status"] == "unknown":
            targets.append(([meta["name"]] + list(meta["aliases"]), meta["name"],
                            "unknown", "failure"))
    claimed = set()
    for term in terms:
        if find(term, concepts, index)[0] is None:
            targets.append(([term], term, "new", "failure"))
            claimed.add(normalize(term))
    for match in list(ACRONYM_RE.finditer(clean)) + list(CAMEL_RE.finditer(clean)):
        term = match.group()
        key = normalize(term)
        if term.upper() in ignore or key in claimed:
            continue
        stem = term[:-1] if term.endswith("s") and len(term) > 3 else term
        if find(term, concepts, index)[0] or find(stem, concepts, index)[0]:
            continue
        claimed.add(key)
        targets.append(([term], term, "candidate", "warning"))

    failures, warnings = [], []
    for labels, display, kind, severity in targets:
        best = None
        for label in labels:
            m = label_pattern(label).search(clean)
            if m and (best is None or m.start() < best.start()):
                best = m
        if best is None or has_gloss(clean, best.end()):
            continue
        context = clean[max(0, best.start() - 20):best.end() + 30].replace("\n", " ").strip()
        item = {"term": display, "kind": kind, "context": context}
        (failures if severity == "failure" else warnings).append(item)
    return {"ok": not failures, "failures": failures, "warnings": warnings}


def cmd_audit(args):
    text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    result = run_audit(text, args.terms or ())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)


def cmd_ignore(args):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (DATA_DIR / "ignore.txt").open("a", encoding="utf-8") as fh:
        for term in args.terms:
            fh.write(term + "\n")
    print(json.dumps({"ignored": args.terms}, ensure_ascii=False))


def cmd_hook(args):
    flag = DATA_DIR / ".audit_on"
    if args.action == "on":
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        flag.write_text(args.mode + "\n", encoding="utf-8")
    elif args.action == "off" and flag.is_file():
        flag.unlink()
    mode = flag.read_text(encoding="utf-8").strip() if flag.is_file() else None
    print(json.dumps({"audit_hook": "on" if mode else "off", "mode": mode}))


def cmd_rebuild(_args):
    concepts = load_all()
    for meta in concepts.values():
        write_concept(meta)
    print(json.dumps({"rewritten": len(concepts), "graph_colors": ensure_graph_style()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    p = sub.add_parser("lookup")
    p.add_argument("terms", nargs="+")
    p.add_argument("--max-new", type=int, default=3)
    p.add_argument("--no-touch", action="store_true")
    p.set_defaults(func=cmd_lookup)

    p = sub.add_parser("mark")
    p.add_argument("term")
    p.add_argument("status", choices=STATUSES)
    p.add_argument("--gloss")
    p.add_argument("--alias", action="append")
    p.add_argument("--related", action="append")
    p.add_argument("--source")
    p.set_defaults(func=cmd_mark)

    p = sub.add_parser("import")
    p.add_argument("file")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--allow-verified", action="store_true")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("verify")
    p.add_argument("term")
    p.add_argument("result", choices=("pass", "fail"))
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("list")
    p.add_argument("--status", choices=STATUSES)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("due")
    p.add_argument("--limit", type=int, default=3)
    p.set_defaults(func=cmd_due)

    sub.add_parser("stats").set_defaults(func=cmd_stats)
    sub.add_parser("rebuild").set_defaults(func=cmd_rebuild)

    p = sub.add_parser("audit")
    p.add_argument("--file", help="answer text file (default: stdin)")
    p.add_argument("--terms", nargs="*", help="specialized terms the answer uses, incl. multi-word ones")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("ignore")
    p.add_argument("terms", nargs="+")
    p.set_defaults(func=cmd_ignore)

    p = sub.add_parser("hook")
    p.add_argument("action", choices=("on", "off", "status"))
    p.add_argument("--mode", choices=("warn", "block"), default="warn")
    p.set_defaults(func=cmd_hook)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
