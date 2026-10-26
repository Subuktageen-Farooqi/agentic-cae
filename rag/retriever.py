from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path

from rag.ingest import tokenize
from schemas import SourceReference


@dataclass(frozen=True)
class RetrievalHit:
    score: float
    semantic_score: float
    lexical_score: float
    text: str
    reference: SourceReference


class LocalHybridRetriever:
    def __init__(self, index_path: Path):
        data = json.loads(index_path.read_text(encoding="utf-8"))
        if data.get("schema_version") != "1.0" or not data.get("chunks"):
            raise ValueError("Knowledge index is missing or unsupported")
        self.data = data

    def search(self, query: str, limit: int = 4, minimum_score: float = 0.08) -> list[RetrievalHit]:
        terms = tokenize(query)
        if not terms:
            return []
        counts = Counter(terms)
        idf = self.data["idf"]
        weighted = {term: count * idf.get(term, 0.0) for term, count in counts.items() if term in idf}
        norm = math.sqrt(sum(value * value for value in weighted.values())) or 1.0
        query_vector = {term: value / norm for term, value in weighted.items()}
        lengths = [chunk["length"] for chunk in self.data["chunks"]]
        average_length = sum(lengths) / len(lengths)
        raw: list[tuple[float, float, dict]] = []
        max_bm25 = 0.0
        for chunk in self.data["chunks"]:
            semantic = sum(value * chunk["vector"].get(term, 0.0) for term, value in query_vector.items())
            lexical = 0.0
            for term in counts:
                frequency = chunk["term_counts"].get(term, 0)
                if frequency:
                    lexical += idf.get(term, 0.0) * (frequency * 2.2) / (
                        frequency + 1.2 * (0.25 + 0.75 * chunk["length"] / average_length))
            max_bm25 = max(max_bm25, lexical)
            raw.append((semantic, lexical, chunk))
        hits = []
        for semantic, lexical, chunk in raw:
            normalized_lexical = lexical / max_bm25 if max_bm25 else 0.0
            score = 0.65 * semantic + 0.35 * normalized_lexical
            if score >= minimum_score:
                hits.append(RetrievalHit(score, semantic, normalized_lexical, chunk["text"],
                                         SourceReference.model_validate(chunk["reference"])))
        return sorted(hits, key=lambda item: (-item.score, item.reference.chunk_id))[:limit]
