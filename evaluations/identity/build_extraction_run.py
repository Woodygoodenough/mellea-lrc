"""Write the extraction run the identity stage reads, from a bench's text.

The extraction side keeps its own evaluation; what this stage needs is the
serialized `ExtractedDocument` per filing, with spans, citation objects, root
and co-location ids, and a manifest naming what produced it. Extraction is
deterministic, so this is a minute of work and no allowance is spent.

    uv run python -m evaluations.identity.build_extraction_run data/extraction-v2.1
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from mellea_lrc.extraction import extract_citations
from mellea_lrc.extraction.reading.relaxation import Relaxation
from mellea_lrc.preprocessing import preprocess
from mellea_lrc.serialization import (
    deserialize_extracted_document,
    serialize_extracted_document,
)


def _commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def run(bench: Path, out: Path, *, relaxation: Relaxation) -> int:
    paths = sorted((bench / "documents_txt").glob("*.txt"))
    if not paths:
        print(f"no documents in {bench}")
        return 1
    (out / "documents").mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    kinds: Counter[str] = Counter()
    for path in paths:
        # eyecite writes to stdout on some inputs; the artifact is the output.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            document = extract_citations(preprocess(path), relaxation=relaxation)
        payload = serialize_extracted_document(document)
        # An artifact nobody can load is not an artifact, so it is read back here.
        if deserialize_extracted_document(json.loads(json.dumps(payload))) != document:
            print(f"round-trip failed for {path.name}")
            return 1
        (out / "documents" / f"{path.stem}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        by_kind = Counter(item.citation.kind.value for item in document.citations)
        kinds.update(by_kind)
        entries.append(
            {
                "document": path.name,
                "artifact": f"documents/{path.stem}.json",
                "text_sha256_16": hashlib.sha256(document.text.encode("utf-8")).hexdigest()[:16],
                "text_length": len(document.text),
                "citations": len(document.citations),
                "by_kind": dict(sorted(by_kind.items())),
            }
        )
    manifest = {
        "artifact_type": "extraction_run",
        "source": str(bench),
        "relaxation": relaxation.value,
        "produced_by": "evaluations/identity/build_extraction_run.py",
        "commit": _commit(),
        "written": datetime.now(UTC).isoformat(timespec="seconds"),
        "documents": len(entries),
        "citations": sum(int(entry["citations"]) for entry in entries),
        "by_kind": dict(sorted(kinds.items())),
        "entries": entries,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{len(entries)} documents, {manifest['citations']} citations -> {out}")
    for kind, count in kinds.most_common():
        print(f"  {kind:22} {count:4}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bench", type=Path, help="a bench directory holding documents_txt/")
    parser.add_argument(
        "--out", type=Path, default=None, help="where to write; default data/runs/<bench name>"
    )
    parser.add_argument(
        "--relaxation", choices=[level.value for level in Relaxation], default=Relaxation.FULL.value
    )
    args = parser.parse_args()
    out = args.out or Path("data/runs") / args.bench.name
    return run(args.bench, out, relaxation=Relaxation(args.relaxation))


if __name__ == "__main__":
    raise SystemExit(main())
