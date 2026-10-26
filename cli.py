"""M1 command-line access to dependency probes and durable foundation records."""

import argparse
import json

from config import Config, diagnostics_json
from storage import Store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", help="Override local SQLite/artifact root")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Read-only, secret-free presence diagnostics")
    commands.add_parser("projects", help="List persisted projects; never launches a job")
    jobs = commands.add_parser("jobs", help="Inspect durable job records and owner IDs")
    jobs.add_argument("project_id")
    recover = commands.add_parser("recover", help="Mark an inactive owner's jobs interrupted; never rerun")
    recover.add_argument("--owner", required=True)
    recover.add_argument("--owner-stopped", action="store_true", required=True,
                         help="Assert you checked the old worker is no longer running")
    demo = commands.add_parser("demo-cantilever", help="Run real deterministic CadQuery and FreeCAD integration")
    demo.add_argument("--freecad-cmd", help="Override FreeCADCmd executable")
    knowledge = commands.add_parser("knowledge-update", help="Rebuild the persistent local hybrid index")
    knowledge.add_argument("--root", default="data/knowledge")
    query = commands.add_parser("knowledge-query", help="Query the local knowledge index with provenance")
    query.add_argument("query")
    query.add_argument("--root", default="data/knowledge")
    args = parser.parse_args()
    config = Config.from_env()
    if args.command == "doctor":
        print(diagnostics_json(config))
        return
    if args.command == "knowledge-update":
        from pathlib import Path
        from rag.ingest import build_index
        index = build_index(Path(args.root))
        print(json.dumps({key: index[key] for key in ("schema_version", "embedding", "lexical", "source_hash", "source_count", "chunk_count")}, indent=2))
        return
    if args.command == "knowledge-query":
        from pathlib import Path
        from rag.retriever import LocalHybridRetriever
        index_path = Path(args.root) / "index.json"
        hits = LocalHybridRetriever(index_path).search(args.query)
        print(json.dumps([{"score": hit.score, "text": hit.text,
                           "source": hit.reference.model_dump(mode="json")} for hit in hits], indent=2))
        return
    data_dir = args.data_dir or config.data_dir
    if args.command == "demo-cantilever":
        from examples.deterministic_demo import run
        print(json.dumps(run(data_dir, args.freecad_cmd), indent=2))
        return
    store = Store(data_dir)
    if args.command == "projects":
        print(json.dumps(store.projects(), indent=2))
    elif args.command == "jobs":
        print(json.dumps([job.model_dump(mode="json") for job in store.jobs(args.project_id)], indent=2))
    elif args.command == "recover":
        print(json.dumps({"interrupted_job_ids": store.recover_interrupted(args.owner),
                          "next": "Inspect artifacts and logs; use a new explicit job key for any retry"}, indent=2))


if __name__ == "__main__":
    main()
