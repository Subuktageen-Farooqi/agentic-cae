from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

from rag.sources import SourceDocument, load_collection


TOKEN = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)?", re.I)


def tokenize(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN.findall(text)]


def chunk_document(document: SourceDocument, max_words: int = 140) -> list[dict]:
    sections: list[tuple[str, list[str]]] = []
    heading = "Document"
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", document.text):
        block = block.strip()
        if block.startswith("#"):
            if paragraphs:
                sections.append((heading, paragraphs))
                paragraphs = []
            heading = block.lstrip("# ").strip()
        elif block:
            paragraphs.append(block)
    if paragraphs:
        sections.append((heading, paragraphs))
    chunks: list[dict] = []
    for section, values in sections:
        current: list[str] = []
        count = 0
        for paragraph in values:
            words = paragraph.split()
            if current and count + len(words) > max_words:
                chunks.append(_chunk(document, section, "\n\n".join(current), len(chunks) + 1))
                current, count = [], 0
            current.append(paragraph)
            count += len(words)
        if current:
            chunks.append(_chunk(document, section, "\n\n".join(current), len(chunks) + 1))
    return chunks


def _chunk(document: SourceDocument, section: str, text: str, ordinal: int) -> dict:
    digest = hashlib.sha256(f"{document.reference.source_id}\0{section}\0{text}".encode()).hexdigest()[:16]
    reference = document.reference.model_copy(update={"section_or_page": section,
                                                       "chunk_id": f"{document.reference.source_id}:{ordinal}:{digest}"})
    return {"reference": reference.model_dump(mode="json"), "text": text, "tokens": tokenize(text)}


def build_index(knowledge_root: Path, output: Path | None = None) -> dict:
    documents = load_collection(knowledge_root)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    document_frequency: Counter[str] = Counter()
    for chunk in chunks:
        document_frequency.update(set(chunk["tokens"]))
    total = len(chunks)
    idf = {term: math.log((1 + total) / (1 + frequency)) + 1
           for term, frequency in sorted(document_frequency.items())}
    for chunk in chunks:
        counts = Counter(chunk.pop("tokens"))
        norm = math.sqrt(sum((count * idf[term]) ** 2 for term, count in counts.items())) or 1.0
        chunk["vector"] = {term: count * idf[term] / norm for term, count in sorted(counts.items())}
        chunk["term_counts"] = dict(sorted(counts.items()))
        chunk["length"] = sum(counts.values())
    source_hash = hashlib.sha256("".join(document.text for document in documents).encode()).hexdigest()
    index = {"schema_version": "1.0", "embedding": "local_tfidf_v1", "lexical": "bm25_v1",
             "built_at": datetime.now(timezone.utc).isoformat(), "source_hash": source_hash,
             "source_count": len(documents), "chunk_count": len(chunks), "idf": idf, "chunks": chunks}
    destination = output or knowledge_root / "index.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".index-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(index, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return index
