import hashlib
import math
import struct

import decisiongraph as dg


class HashingEmbedder:
    def __init__(self, dim=64):
        self.dim = dim

    def embed(self, text):
        vector = [0.0] * self.dim
        for token in dg.tokens(text):
            digest = hashlib.sha1(token.encode("utf-8")).digest()
            number = int.from_bytes(digest[:4], "big")
            position = number % self.dim
            sign = 1.0 if (number >> 8) & 1 else -1.0
            vector[position] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector


def quantize_int8(vector):
    maximum = max((abs(value) for value in vector), default=0.0)
    scale = maximum / 127.0 if maximum else 1.0
    quantized = [int(max(-127, min(127, round(value / scale)))) for value in vector]
    return quantized, scale


def dequantize_int8(quantized, scale):
    return [value * scale for value in quantized]


def pack_int8(quantized):
    return struct.pack(f"{len(quantized)}b", *quantized)


def unpack_int8(payload):
    return list(struct.unpack(f"{len(payload)}b", payload))


def pack_floats(values):
    return struct.pack(f"{len(values)}f", *values)


def unpack_floats(payload):
    return list(struct.unpack(f"{len(payload) // 4}f", payload))


def cosine(left, right):
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


class IVFIndex:
    def __init__(self, embedder, nlist=4, probes=2):
        self.embedder = embedder
        self.dim = embedder.dim
        self.nlist = nlist
        self.probes = probes
        self.centroids = []
        self.entries = []

    def build(self, items):
        if not items:
            return
        ordered = sorted(items, key=lambda item: item[0])
        self.centroids = [list(vector) for _, vector in ordered[: min(self.nlist, len(ordered))]]
        for _ in range(5):
            groups = [[] for _ in self.centroids]
            for _, vector in items:
                groups[self._nearest(vector)].append(vector)
            for index, group in enumerate(groups):
                if group:
                    self.centroids[index] = [sum(values) / len(group) for values in zip(*group)]
        self.entries = []
        for identifier, vector in items:
            quantized, scale = quantize_int8(vector)
            self.entries.append((identifier, quantized, scale, self._nearest(vector)))

    def _nearest(self, vector):
        return min(range(len(self.centroids)), key=lambda index: -cosine(vector, self.centroids[index]))

    def query(self, vector, k=3):
        if not self.centroids:
            return []
        probes = sorted(range(len(self.centroids)), key=lambda index: -cosine(vector, self.centroids[index]))
        probes = set(probes[: min(self.probes, len(probes))])
        scored = [
            (identifier, cosine(vector, dequantize_int8(quantized, scale)))
            for identifier, quantized, scale, centroid in self.entries
            if centroid in probes
        ]
        return sorted(scored, key=lambda item: -item[1])[:k]

    def to_rows(self):
        flattened = [value for centroid in self.centroids for value in centroid]
        rows = [("__centroids__", self.dim, pack_floats(flattened), 1.0, -1)]
        for identifier, quantized, scale, centroid in self.entries:
            rows.append((identifier, len(quantized), pack_int8(quantized), scale, centroid))
        return rows

    @classmethod
    def from_rows(cls, rows, embedder, nlist=4, probes=2):
        index = cls(embedder, nlist, probes)
        for identifier, _, payload, scale, centroid in rows:
            if identifier == "__centroids__":
                values = unpack_floats(payload)
                index.centroids = [
                    values[position:position + index.dim] for position in range(0, len(values), index.dim)
                ]
            else:
                index.entries.append((identifier, unpack_int8(payload), scale, centroid))
        return index
