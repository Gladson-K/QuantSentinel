import datetime
import hashlib
import json
import os
import sqlite3

from schemas import Decision, Conflict

SCHEMA_VERSION = "2"


class Store:
    def __init__(self, path=None):
        self.path = path or os.environ.get("DG_V2_DB", "decisions_v2.db")
        self._migrate()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _migrate(self):
        connection = self._connect()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS decisions_v2(
                id TEXT PRIMARY KEY, source TEXT, date TEXT, title TEXT, statement TEXT,
                owner TEXT, scope TEXT, rationale TEXT, alternatives_json TEXT, status TEXT,
                evidence_span TEXT, confidence REAL, negated INTEGER, embedding_id TEXT);
            CREATE TABLE IF NOT EXISTS entities(id TEXT PRIMARY KEY, canonical TEXT, aliases_json TEXT);
            CREATE TABLE IF NOT EXISTS labels(
                id INTEGER PRIMARY KEY AUTOINCREMENT, decision_id TEXT, verdict TEXT,
                reviewer TEXT, ts TEXT);
            CREATE TABLE IF NOT EXISTS conflicts(
                id TEXT PRIMARY KEY, a TEXT, b TEXT, kind TEXT, score REAL,
                explanation TEXT, state TEXT);
            CREATE TABLE IF NOT EXISTS merges(
                id TEXT PRIMARY KEY, canonical TEXT, duplicate TEXT, reason TEXT,
                ts TEXT, undone INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS vector_blobs(
                id TEXT PRIMARY KEY, dim INTEGER, payload BLOB, scale REAL, centroid INTEGER);
            """
        )
        connection.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)", (SCHEMA_VERSION,))
        connection.commit()
        connection.close()

    def version(self):
        connection = self._connect()
        value = connection.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        connection.close()
        return value

    def upsert_decision(self, decision):
        connection = self._connect()
        connection.execute("INSERT OR REPLACE INTO decisions_v2 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", decision.to_row())
        connection.commit()
        connection.close()
        return decision.id

    def list_decisions(self):
        connection = self._connect()
        rows = connection.execute("SELECT * FROM decisions_v2 ORDER BY date,id").fetchall()
        connection.close()
        return [Decision.from_row(row) for row in rows]

    def get_decision(self, decision_id):
        connection = self._connect()
        row = connection.execute("SELECT * FROM decisions_v2 WHERE id=?", (decision_id,)).fetchone()
        connection.close()
        return Decision.from_row(row) if row else None

    def update_statement(self, decision_id, statement, evidence_span=None):
        connection = self._connect()
        connection.execute(
            "UPDATE decisions_v2 SET statement=?, evidence_span=? WHERE id=?",
            (statement, evidence_span or statement, decision_id),
        )
        connection.commit()
        connection.close()

    def add_label(self, decision_id, verdict, reviewer="local"):
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        connection = self._connect()
        connection.execute(
            "INSERT INTO labels(decision_id,verdict,reviewer,ts) VALUES(?,?,?,?)",
            (decision_id, verdict, reviewer, ts),
        )
        connection.commit()
        connection.close()

    def labels_for(self, decision_id):
        connection = self._connect()
        rows = connection.execute(
            "SELECT decision_id,verdict,reviewer,ts FROM labels WHERE decision_id=? ORDER BY id", (decision_id,)
        ).fetchall()
        connection.close()
        return [(row[0], row[1], row[2], row[3]) for row in rows]

    def add_conflict(self, conflict):
        connection = self._connect()
        connection.execute(
            "INSERT OR REPLACE INTO conflicts VALUES(?,?,?,?,?,?,?)",
            (conflict.id, conflict.a, conflict.b, conflict.kind, conflict.score, conflict.explanation, conflict.state),
        )
        connection.commit()
        connection.close()
        return conflict.id

    def list_conflicts(self, state=None):
        connection = self._connect()
        if state:
            rows = connection.execute("SELECT * FROM conflicts WHERE state=? ORDER BY id", (state,)).fetchall()
        else:
            rows = connection.execute("SELECT * FROM conflicts ORDER BY id").fetchall()
        connection.close()
        return [Conflict(row[0], row[1], row[2], row[3], row[4], row[5], row[6]) for row in rows]

    def set_conflict_state(self, conflict_id, state):
        connection = self._connect()
        connection.execute("UPDATE conflicts SET state=? WHERE id=?", (state, conflict_id))
        connection.commit()
        connection.close()

    def add_entity(self, canonical, aliases):
        entity_id = hashlib.sha1(canonical.encode()).hexdigest()[:12]
        connection = self._connect()
        connection.execute(
            "INSERT OR REPLACE INTO entities VALUES(?,?,?)", (entity_id, canonical, json.dumps(sorted(aliases)))
        )
        connection.commit()
        connection.close()
        return entity_id

    def resolve_entity(self, term):
        connection = self._connect()
        rows = connection.execute("SELECT id,canonical,aliases_json FROM entities").fetchall()
        connection.close()
        for row in rows:
            aliases = json.loads(row[2])
            if term.lower() == row[1].lower() or any(term.lower() == a.lower() for a in aliases):
                return row[1]
        return term

    def upsert_vector(self, vector_id, dim, payload, scale, centroid):
        connection = self._connect()
        connection.execute(
            "INSERT OR REPLACE INTO vector_blobs VALUES(?,?,?,?,?)", (vector_id, dim, payload, scale, centroid)
        )
        connection.commit()
        connection.close()

    def list_vectors(self):
        connection = self._connect()
        rows = connection.execute("SELECT id,dim,payload,scale,centroid FROM vector_blobs ORDER BY id").fetchall()
        connection.close()
        return [(row[0], row[1], row[2], row[3], row[4]) for row in rows]

    def add_merge(self, merge_id, canonical, duplicate, reason):
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        connection = self._connect()
        connection.execute(
            "INSERT OR REPLACE INTO merges VALUES(?,?,?,?,?,0)", (merge_id, canonical, duplicate, reason, ts)
        )
        connection.commit()
        connection.close()

    def undo_merge(self, merge_id):
        connection = self._connect()
        connection.execute("UPDATE merges SET undone=1 WHERE id=?", (merge_id,))
        connection.commit()
        connection.close()

    def list_merges(self):
        connection = self._connect()
        rows = connection.execute("SELECT id,canonical,duplicate,reason,ts,undone FROM merges ORDER BY ts").fetchall()
        connection.close()
        return [(row[0], row[1], row[2], row[3], row[4], bool(row[5])) for row in rows]
