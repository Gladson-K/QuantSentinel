import hashlib
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@dataclass
class Document:
    text: str
    author: str
    ts: str
    url: str
    thread_id: str
    source: str
    acl: tuple = ()
    reactions: tuple = ()
    item_id: str = ""
    groups: list = field(default_factory=list)

    def __post_init__(self):
        if not self.item_id:
            self.item_id = hashlib.sha1((self.source + "|" + self.url + "|" + self.text).encode()).hexdigest()[:12]


class Transport(ABC):
    @abstractmethod
    def list_changes(self, cursor):
        raise NotImplementedError

    @abstractmethod
    def fetch(self, item):
        raise NotImplementedError


class JsonFixtureTransport(Transport):
    def __init__(self, path=None, items=None):
        if items is None:
            path = path or "github.json"
            if not os.path.isabs(path) and not os.path.exists(path):
                path = os.path.join(FIXTURE_DIR, path)
            with open(path, encoding="utf-8") as handle:
                items = json.load(handle)["items"]
        self.items = sorted(items, key=lambda item: item["seq"])

    def list_changes(self, cursor):
        changed = [item for item in self.items if item["seq"] > cursor]
        next_cursor = max((item["seq"] for item in changed), default=cursor)
        return changed, next_cursor

    def fetch(self, item):
        return dict(item)


class Connector(ABC):
    def __init__(self, name, transport, base_url, default_acl=()):
        self.name = name
        self.transport = transport
        self.base_url = base_url
        self.default_acl = tuple(default_acl)

    def authorize(self, token=None):
        return True

    def list_changes(self, cursor):
        return self.transport.list_changes(cursor)

    def fetch(self, item):
        return self.transport.fetch(item)

    @abstractmethod
    def to_document(self, raw):
        raise NotImplementedError


class RecordedConnector(Connector):
    def to_document(self, raw):
        return Document(
            text=raw["text"],
            author=raw.get("author", "unknown"),
            ts=raw.get("ts", "1970-01-01"),
            url=self.base_url + raw.get("url", ""),
            thread_id=raw.get("thread_id", raw.get("id", "single")),
            source=self.name,
            acl=tuple(raw.get("acl", self.default_acl)),
            reactions=tuple(raw.get("reactions", [])),
            item_id=str(raw.get("id", "")),
        )


class InMemoryConnector(RecordedConnector):
    pass


def github_connector(items=None):
    transport = JsonFixtureTransport(items=items) if items is not None else JsonFixtureTransport("github.json")
    return RecordedConnector("github", transport, "https://github.example/", ("engineering",))


def slack_connector(items=None):
    transport = JsonFixtureTransport(items=items) if items is not None else JsonFixtureTransport("slack.json")
    return RecordedConnector("slack", transport, "https://slack.example/", ("engineering",))
