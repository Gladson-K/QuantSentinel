import datetime
import json
import os
import sqlite3


class SyncState:
    def __init__(self, path=None):
        self.path = path or os.environ.get("DG_V3_DB", "decisions_v3.db")
        self._migrate()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _migrate(self):
        connection = self._connect()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sync_state(source TEXT PRIMARY KEY, cursor INTEGER, last_sync TEXT);
            CREATE TABLE IF NOT EXISTS dead_letters(
                id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, item_id TEXT, reason TEXT, ts TEXT);
            CREATE TABLE IF NOT EXISTS documents(
                doc_id TEXT PRIMARY KEY, source TEXT, author TEXT, ts TEXT, url TEXT,
                thread_id TEXT, acl_json TEXT, reactions_json TEXT, text TEXT);
            CREATE TABLE IF NOT EXISTS evidence(
                id INTEGER PRIMARY KEY AUTOINCREMENT, decision_id TEXT, url TEXT,
                source TEXT, thread_id TEXT, span TEXT);
            CREATE TABLE IF NOT EXISTS merges(
                id TEXT PRIMARY KEY, canonical TEXT, duplicate TEXT, reason TEXT, ts TEXT, undone INTEGER DEFAULT 0);
            """
        )
        connection.commit()
        connection.close()

    def get_cursor(self, source):
        connection = self._connect()
        row = connection.execute("SELECT cursor FROM sync_state WHERE source=?", (source,)).fetchone()
        connection.close()
        return int(row[0]) if row else 0

    def set_cursor(self, source, cursor):
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        connection = self._connect()
        connection.execute(
            "INSERT OR REPLACE INTO sync_state(source,cursor,last_sync) VALUES(?,?,?)", (source, cursor, ts)
        )
        connection.commit()
        connection.close()

    def mark_dead(self, source, item_id, reason):
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        connection = self._connect()
        connection.execute(
            "INSERT INTO dead_letters(source,item_id,reason,ts) VALUES(?,?,?,?)", (source, str(item_id), str(reason), ts)
        )
        connection.commit()
        connection.close()

    def list_dead(self):
        connection = self._connect()
        rows = connection.execute("SELECT source,item_id,reason,ts FROM dead_letters ORDER BY id").fetchall()
        connection.close()
        return [tuple(row) for row in rows]

    def save_document(self, document):
        connection = self._connect()
        connection.execute(
            "INSERT OR IGNORE INTO documents VALUES(?,?,?,?,?,?,?,?,?)",
            (
                document.item_id, document.source, document.author, document.ts, document.url,
                document.thread_id, json.dumps(sorted(document.acl)),
                json.dumps(list(document.reactions)), document.text,
            ),
        )
        connection.commit()
        connection.close()

    def list_documents(self):
        from connectors import Document

        connection = self._connect()
        rows = connection.execute("SELECT * FROM documents ORDER BY ts,doc_id").fetchall()
        connection.close()
        return [
            Document(
                text=row["text"], author=row["author"], ts=row["ts"], url=row["url"],
                thread_id=row["thread_id"], source=row["source"], acl=tuple(json.loads(row["acl_json"])),
                reactions=tuple(json.loads(row["reactions_json"])), item_id=row["doc_id"],
            )
            for row in rows
        ]

    def add_evidence(self, decision_id, url, source, thread_id, span=""):
        connection = self._connect()
        connection.execute(
            "INSERT INTO evidence(decision_id,url,source,thread_id,span) VALUES(?,?,?,?,?)",
            (decision_id, url, source, thread_id, span),
        )
        connection.commit()
        connection.close()

    def evidence_for(self, decision_id):
        connection = self._connect()
        rows = connection.execute(
            "SELECT url,source,thread_id,span FROM evidence WHERE decision_id=? ORDER BY id", (decision_id,)
        ).fetchall()
        connection.close()
        return [dict(url=row[0], source=row[1], thread_id=row[2], span=row[3]) for row in rows]

    def record_merge(self, merge_id, canonical, duplicate, reason):
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


def sync_once(connector, state, handler=None, backfill=False):
    cursor = 0 if backfill else state.get_cursor(connector.name)
    items, next_cursor = connector.list_changes(cursor)
    processed = []
    for item in items:
        try:
            raw = connector.fetch(item)
            document = connector.to_document(raw)
            if handler:
                handler(document)
            processed.append(document)
        except Exception as exc:
            state.mark_dead(connector.name, item.get("id", "?"), exc)
    state.set_cursor(connector.name, next_cursor)
    return processed
