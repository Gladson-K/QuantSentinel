#!/usr/bin/env python3
"""DecisionGraph V1: local-first decision capture, search and conflict detection.

Stdlib only. Usage: python decisiongraph.py ingest ./notes | list | search "q" | conflicts | report
"""
import argparse
import datetime
import hashlib
import math
import os
import re
import sqlite3
from collections import Counter

DB = os.environ.get("DG_DB", "decisions.db")
STRONG = [
    r"\b(we|team|i)\s+(have\s+)?(decided|agreed|resolved)\b",
    r"^\s*[-*]?\s*decision\s*:",
    r"\bgoing with\b",
    r"\bwe('re| are) going to\b",
    r"\blet'?s (use|go|adopt|drop|stop|switch|migrate)\b",
]
WEAK = [
    r"\bwe (will|won'?t|will not|shall)\b",
    r"\b(no longer|from now on|effective immediately)\b",
]
NEG = re.compile(r"\b(not|n't|never|no longer|stop|drop|deprecate|remove|avoid|without|won't)\b", re.IGNORECASE)
OPT = re.compile(r"\b(use|adopt|go with|going with|switch to|migrate to|choose|using)\s+([A-Za-z0-9_.\-]+)", re.IGNORECASE)
STOP = {
    "the", "a", "an", "to", "of", "and", "or", "in", "on", "for", "we", "is", "are", "be", "will",
    "with", "that", "this", "it", "as", "at", "by", "from", "our", "us", "let", "lets", "decided",
    "agreed", "decision", "going", "use", "using", "not", "no",
}


def set_db(path):
    global DB
    DB = path
    return DB


def get_db():
    return DB


def stem(word):
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def tokens(text):
    return [stem(w) for w in re.findall(r"[a-z0-9_.\-]+", text.lower()) if w not in STOP and len(w) > 1]


def conn():
    connection = sqlite3.connect(get_db())
    connection.executescript(
        """CREATE TABLE IF NOT EXISTS docs(path TEXT PRIMARY KEY, date TEXT, sha TEXT);
        CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY, path TEXT, date TEXT, text TEXT,
          confidence REAL, negated INTEGER);"""
    )
    return connection


def doc_date(path):
    match = re.search(r"\d{4}-\d{2}-\d{2}", os.path.basename(path))
    return match.group(0) if match else datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()


def extract(text):
    found = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        sentence = sentence.strip(" -*\t")
        if len(sentence) < 12:
            continue
        if any(re.search(pattern, sentence, re.IGNORECASE) for pattern in STRONG):
            found.append((sentence, 0.9))
        elif any(re.search(pattern, sentence, re.IGNORECASE) for pattern in WEAK):
            found.append((sentence, 0.5))
    return found


def ingest(root):
    connection = sqlite3.connect(get_db())
    connection.executescript(
        """CREATE TABLE IF NOT EXISTS docs(path TEXT PRIMARY KEY, date TEXT, sha TEXT);
        CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY, path TEXT, date TEXT, text TEXT,
          confidence REAL, negated INTEGER);"""
    )
    added = 0
    if os.path.isfile(root):
        paths = [root]
    else:
        paths = [
            os.path.join(directory, name)
            for directory, _, files in os.walk(root)
            for name in files
            if name.endswith((".md", ".txt"))
        ]
    for path in sorted(paths):
        with open(path, encoding="utf-8", errors="ignore") as handle:
            body = handle.read()
        sha = hashlib.sha1(body.encode()).hexdigest()
        row = connection.execute("SELECT sha FROM docs WHERE path=?", (path,)).fetchone()
        if row and row[0] == sha:
            continue
        connection.execute("DELETE FROM decisions WHERE path=?", (path,))
        date = doc_date(path)
        connection.execute("REPLACE INTO docs VALUES(?,?,?)", (path, date, sha))
        for sentence, confidence in extract(body):
            decision_id = hashlib.sha1((path + sentence).encode()).hexdigest()[:10]
            connection.execute(
                "REPLACE INTO decisions VALUES(?,?,?,?,?,?)",
                (decision_id, path, date, sentence, confidence, int(bool(NEG.search(sentence)))),
            )
            added += 1
    connection.commit()
    connection.close()
    print(f"ingested {len(paths)} files, {added} decisions")
    return added


def load():
    connection = conn()
    rows = connection.execute(
        "SELECT id,path,date,text,confidence,negated FROM decisions ORDER BY date,id"
    ).fetchall()
    connection.close()
    return rows


def tfidf(rows):
    documents = [Counter(tokens(row[3])) for row in rows]
    totals = Counter(word for document in documents for word in document)
    count = max(len(documents), 1)
    return [
        {word: (1 + math.log(freq)) * math.log(1 + count / totals[word]) for word, freq in document.items()}
        for document in documents
    ]


def cos(left, right):
    numerator = sum(value * right.get(word, 0) for word, value in left.items())
    denominator = math.sqrt(sum(value * value for value in left.values())) * math.sqrt(
        sum(value * value for value in right.values())
    )
    return numerator / denominator if denominator else 0.0


def conflicts():
    rows = load()
    vectors = tfidf(rows)
    found = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            older, newer = rows[i], rows[j]
            if older[1] == newer[1] and older[3] == newer[3]:
                continue
            similarity = cos(vectors[i], vectors[j])
            kind = None
            older_option, newer_option = OPT.search(older[3]), OPT.search(newer[3])
            if older_option and newer_option and older_option.group(2).lower() != newer_option.group(2).lower():
                shared = (set(tokens(older[3])) & set(tokens(newer[3]))) - {
                    older_option.group(2).lower(),
                    newer_option.group(2).lower(),
                }
                if len(shared) >= 1 and similarity >= 0.15:
                    kind = "option_swap"
            if not kind and similarity >= 0.3 and older[5] != newer[5]:
                kind = "polarity_flip"
            older_numbers = set(re.findall(r"\d+(?:\.\d+)?", older[3]))
            newer_numbers = set(re.findall(r"\d+(?:\.\d+)?", newer[3]))
            if not kind and similarity >= 0.5 and older_numbers and newer_numbers and older_numbers != newer_numbers:
                kind = "number_change"
            if kind:
                relation = "supersedes?" if newer[2] > older[2] else "same-day conflict"
                found.append(
                    {
                        "kind": kind,
                        "sim": round(similarity, 2),
                        "relation": relation,
                        "older": older,
                        "newer": newer,
                    }
                )
    return found


def cmd_list(_):
    for row in load():
        print(f"{row[0]} {row[2]} [{row[4]:.1f}] {row[3]}")


def cmd_search(args):
    rows = load()
    query = Counter(tokens(args.query))
    scored = sorted(
        ((sum(1 for word in query if word in tokens(row[3])), row) for row in rows),
        key=lambda item: -item[0],
    )
    for score, row in scored[: args.k]:
        if score:
            print(f"{row[0]} {row[2]} {row[3]}  ({os.path.basename(row[1])})")


def cmd_conflicts(_):
    for finding in conflicts():
        print(
            f"[{finding['kind']} sim={finding['sim']} {finding['relation']}]\n"
            f"  OLD {finding['older'][2]}: {finding['older'][3]}\n"
            f"  NEW {finding['newer'][2]}: {finding['newer'][3]}"
        )


def cmd_report(args):
    rows, findings = load(), conflicts()
    lines = ["# Decision Report", f"- Decisions: {len(rows)}", f"- Possible conflicts: {len(findings)}", "", "## Conflicts"]
    for finding in findings:
        lines.append(
            f"- **{finding['kind']}** ({finding['relation']}): "
            f"\"{finding['older'][3]}\" vs \"{finding['newer'][3]}\""
        )
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    print("wrote", args.out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="DecisionGraph V1 CLI")
    subcommands = parser.add_subparsers(dest="cmd", required=True)
    ingest_parser = subcommands.add_parser("ingest")
    ingest_parser.add_argument("path")
    subcommands.add_parser("list")
    subcommands.add_parser("conflicts")
    search_parser = subcommands.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("-k", type=int, default=5)
    report_parser = subcommands.add_parser("report")
    report_parser.add_argument("--out", default="report.md")
    args = parser.parse_args(argv)
    handlers = {
        "ingest": lambda: ingest(args.path),
        "list": lambda: cmd_list(args),
        "search": lambda: cmd_search(args),
        "conflicts": lambda: cmd_conflicts(args),
        "report": lambda: cmd_report(args),
    }
    handlers[args.cmd]()


if __name__ == "__main__":
    main()
