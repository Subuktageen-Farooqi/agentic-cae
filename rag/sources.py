from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from schemas import SourceReference


@dataclass(frozen=True)
class SourceDocument:
    reference: SourceReference
    text: str


def load_source(path: Path, root: Path) -> SourceDocument:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n") or "\n---\n" not in raw[4:]:
        raise ValueError(f"Source {path} must start with JSON metadata between --- lines")
    metadata_text, text = raw[4:].split("\n---\n", 1)
    metadata = json.loads(metadata_text)
    reference = SourceReference(
        **metadata, reference=path.relative_to(root).as_posix(), chunk_id="document",
    )
    if not text.strip():
        raise ValueError(f"Source {path} has no content")
    return SourceDocument(reference=reference, text=text.strip())


def load_collection(root: Path) -> list[SourceDocument]:
    source_dir = root / "sources"
    paths = sorted(source_dir.glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"No knowledge sources found in {source_dir}")
    documents = [load_source(path, root) for path in paths]
    ids = [item.reference.source_id for item in documents]
    if len(ids) != len(set(ids)):
        raise ValueError("Knowledge source IDs must be unique")
    return documents
