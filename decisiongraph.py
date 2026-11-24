#!/usr/bin/env python3
"""DecisionGraph V1: local-first decision capture, search and conflict detection.
Stdlib only. Usage: python decisiongraph.py ingest ./notes | list | search "q" | conflicts | report
"""
import argparse, datetime, hashlib, json, math, os, re, sqlite3, sys
from collections import Counter

DB = os.environ.get("DG_DB", "decisions.db")
STRONG = [r"\b(we|team|i)\s+(have\s+)?(decided|agreed|resolved)\b", r"^\s*[-*]?\s*decision\s*:",
          r"\bgoing with\b", r"\bwe('re| are) going to\b", r"\blet'?s (use|go|adopt|drop|stop|switch|migrate)\b"]
WEAK = [r"\bwe (will|won'?t|will not|shall)\b", r"\b(no longer|from now on|effective immediately)\b"]
NEG = re.compile(r"\b(not|n't|never|no longer|stop|drop|deprecate|remove|avoid|without|won't)\b", re.I)
OPT = re.compile(r"\b(use|adopt|go with|going with|switch to|migrate to|choose|using)\s+([A-Za-z0-9_.\-]+)", re.I)
STOP = set("the a an to of and or in on for we is are be will with that this it as at by from our us let lets "
           "decided agreed decision going use using not no".split())

def stem(w):
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4: return w[: -len(suf)]
    return w

def tokens(t): return [stem(w) for w in re.findall(r"[a-z0-9_.\-]+", t.lower()) if w not in STOP and len(w) > 1]

def conn():
    c = sqlite3.connect(DB)
    c.executescript("""CREATE TABLE IF NOT EXISTS docs(path TEXT PRIMARY KEY, date TEXT, sha TEXT);
    CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY, path TEXT, date TEXT, text TEXT,
      confidence REAL, negated INTEGER);""")
    return c

def doc_date(path):
    m = re.search(r"\d{4}-\d{2}-\d{2}", os.path.basename(path))
    return m.group(0) if m else datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()

def extract(text):
    out = []
    for s in re.split(r"(?<=[.!?])\s+|\n+", text):
        s = s.strip(" -*\t")
        if len(s) < 12: continue
        if any(re.search(p, s, re.I) for p in STRONG): out.append((s, 0.9))
        elif any(re.search(p, s, re.I) for p in WEAK): out.append((s, 0.5))
    return out

def ingest(root):
    c, n = conn(), 0
    paths = [root] if os.path.isfile(root) else [os.path.join(d, f) for d, _, fs in os.walk(root)
             for f in fs if f.endswith((".md", ".txt"))]
    for p in sorted(paths):
        with open(p, encoding="utf-8", errors="ignore") as fh: body = fh.read()
        sha = hashlib.sha1(body.encode()).hexdigest()
        row = c.execute("SELECT sha FROM docs WHERE path=?", (p,)).fetchone()
        if row and row[0] == sha: continue          # incremental: unchanged file
        c.execute("DELETE FROM decisions WHERE path=?", (p,))
        d = doc_date(p)
        c.execute("REPLACE INTO docs VALUES(?,?,?)", (p, d, sha))
        for s, conf in extract(body):
            did = hashlib.sha1((p + s).encode()).hexdigest()[:10]
            c.execute("REPLACE INTO decisions VALUES(?,?,?,?,?,?)", (did, p, d, s, conf, int(bool(NEG.search(s)))))
            n += 1
    c.commit(); print(f"ingested {len(paths)} files, {n} decisions")

def load():
    return conn().execute("SELECT id,path,date,text,confidence,negated FROM decisions ORDER BY date,id").fetchall()

def tfidf(rows):
    docs = [Counter(tokens(r[3])) for r in rows]
    df = Counter(w for d in docs for w in d)
    N = max(len(docs), 1)
    vecs = [{w: (1 + math.log(c)) * math.log(1 + N / df[w]) for w, c in d.items()} for d in docs]
    return vecs

def cos(a, b):
    num = sum(v * b.get(w, 0) for w, v in a.items())
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0

def conflicts():
    rows = load(); vecs = tfidf(rows); found = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            if a[1] == b[1] and a[3] == b[3]: continue
            sim = cos(vecs[i], vecs[j]); kind = None
            oa, ob = OPT.search(a[3]), OPT.search(b[3])
            if oa and ob and oa.group(2).lower() != ob.group(2).lower():
                shared = (set(tokens(a[3])) & set(tokens(b[3]))) - {oa.group(2).lower(), ob.group(2).lower()}
                if len(shared) >= 1 and sim >= 0.15: kind = "option_swap"
            if not kind and sim >= 0.3 and a[5] != b[5]: kind = "polarity_flip"
            na, nb = set(re.findall(r"\d+(?:\.\d+)?", a[3])), set(re.findall(r"\d+(?:\.\d+)?", b[3]))
            if not kind and sim >= 0.5 and na and nb and na != nb: kind = "number_change"
            if kind:
                rel = "supersedes?" if b[2] > a[2] else "same-day conflict"
                found.append(dict(kind=kind, sim=round(sim, 2), relation=rel, older=a, newer=b))
    return found

def cmd_list(_): [print(f"{r[0]} {r[2]} [{r[4]:.1f}] {r[3]}") for r in load()]

def cmd_search(a):
    rows = load(); q = Counter(tokens(a.query))
    scored = sorted(((sum(1 for w in q if w in tokens(r[3])), r) for r in rows), key=lambda x: -x[0])
    for s, r in scored[:a.k]:
        if s: print(f"{r[0]} {r[2]} {r[3]}  ({os.path.basename(r[1])})")

def cmd_conflicts(_):
    for f in conflicts():
        print(f"[{f['kind']} sim={f['sim']} {f['relation']}]\n  OLD {f['older'][2]}: {f['older'][3]}\n  NEW {f['newer'][2]}: {f['newer'][3]}")

def cmd_report(a):
    rows, cf = load(), conflicts()
    lines = ["# Decision Report", f"- Decisions: {len(rows)}", f"- Possible conflicts: {len(cf)}", "", "## Conflicts"]
    for f in cf: lines.append(f"- **{f['kind']}** ({f['relation']}): \"{f['older'][3]}\" vs \"{f['newer'][3]}\"")
    open(a.out, "w").write("\n".join(lines)); print("wrote", a.out)

if __name__ == "__main__":
    p = argparse.ArgumentParser(); s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("ingest").add_argument("path")
    s.add_parser("list"); s.add_parser("conflicts")
    q = s.add_parser("search"); q.add_argument("query"); q.add_argument("-k", type=int, default=5)
    r = s.add_parser("report"); r.add_argument("--out", default="report.md")
    a = p.parse_args()
    {"ingest": lambda: ingest(a.path), "list": lambda: cmd_list(a), "search": lambda: cmd_search(a),
     "conflicts": lambda: cmd_conflicts(a), "report": lambda: cmd_report(a)}[a.cmd]()
