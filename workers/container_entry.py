"""Trusted entry point inside the required generated-CAD container."""
import json
from pathlib import Path
from workers.cad_worker import run_trusted_build


def main():
    root = Path("/job")
    job = json.loads((root / "input.json").read_text(encoding="utf-8"))
    manifest = run_trusted_build(project_id=job["project_id"], job_id=job["job_id"],
        model_source=root / "input.py", params=job["parameters"],
        output_dir=root / "output", project_root=root, execution_kind="generated_container")
    (root / "completion.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
