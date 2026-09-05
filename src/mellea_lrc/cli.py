"""Command-line entrypoint for the validation pipeline.

Two commands. ``validate`` runs the per-citation route end to end, and
``identify`` runs the identity stage, once per root of the citation tree::

    mellea-lrc validate "See Brown v. Board of Education, 347 U.S. 483, 495 (1954)."
    mellea-lrc validate --from-file filing.pdf
    mellea-lrc identify --from-artifact data/runs/extraction-v2.0/documents/001.json -o out.json

The source is read as text unless ``--from-file`` says it names a document or
``--from-artifact`` says it is an extracted-document JSON artifact, which is how
extraction's output reaches this stage from another process. The serialized
result is written as JSON, to ``--output`` when given and to stdout otherwise.
CourtListener and model credentials are read from the environment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mellea_lrc.extraction import ExtractedDocument, extract_citations, extract_from_plain_text
from mellea_lrc.preprocessing import preprocess
from mellea_lrc.serialization import (
    deserialize_extracted_document,
    serialize_identified_document,
    serialize_validated_document,
)
from mellea_lrc.validation import validate_document
from mellea_lrc.validation.identity import identify_document


def _parse(source: str, *, from_file: bool, from_artifact: bool = False) -> ExtractedDocument:
    """Parse the citations out of a document on disk, or out of the text itself.

    ``from_artifact`` loads an extracted-document JSON artifact instead, which
    is how extraction's output reaches this stage across a process boundary.
    """
    if from_artifact:
        return deserialize_extracted_document(json.loads(Path(source).read_text(encoding="utf-8")))
    if from_file:
        return extract_citations(preprocess(Path(source)))
    return extract_from_plain_text(source)


def _identify(args: argparse.Namespace) -> int:
    """Establish which case each authority in the source names."""
    document = _parse(args.source, from_file=args.from_file, from_artifact=args.from_artifact)
    roots = sum(1 for item in document.citations if item.authority_id == item.citation_id)
    print(f"{len(document.citations)} citations, {roots} roots; identifying", file=sys.stderr)
    identified = asyncio.run(identify_document(document))
    _write(json.dumps(serialize_identified_document(identified), indent=2, ensure_ascii=False), args.output)
    return 0


def _write(text: str, output: Path | None) -> None:
    if output is None:
        sys.stdout.write(text + "\n")
    else:
        output.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {output}", file=sys.stderr)


def _validate(args: argparse.Namespace) -> int:
    """Parse the source, then check every citation it contains."""
    document = _parse(args.source, from_file=args.from_file)
    print(f"Parsed {len(document.full_citations)} citations; validating", file=sys.stderr)
    validated = asyncio.run(validate_document(document))

    _write(json.dumps(serialize_validated_document(validated), indent=2, ensure_ascii=False), args.output)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the validation pipeline."""
    parser = argparse.ArgumentParser(prog="mellea-lrc", description=__doc__.splitlines()[0])
    subcommands = parser.add_subparsers(dest="command", required=True)

    validate = subcommands.add_parser(
        "validate",
        help="Parse the citations in a source, then check them against CourtListener.",
        description="Parse the citations in a source, then check them against CourtListener.",
    )
    validate.add_argument("source", help="The text to check, or a document path with --from-file.")
    origin = validate.add_mutually_exclusive_group()
    origin.add_argument(
        "--from-text",
        dest="from_file",
        action="store_false",
        default=False,
        help="Read the source as text itself. This is the default.",
    )
    origin.add_argument(
        "--from-file",
        dest="from_file",
        action="store_true",
        help="Read the source as a path to a document (PDF, DOCX, or .txt).",
    )
    validate.add_argument("-o", "--output", type=Path, help="Write JSON here instead of stdout.")
    validate.set_defaults(handler=_validate)

    identify = subcommands.add_parser(
        "identify",
        help="Establish which case each authority in a source names.",
        description=(
            "Run the identity stage: one lookup per root of the citation tree, the rule guard, "
            "and a model judgement only where a rule disagrees."
        ),
    )
    identify.add_argument(
        "source",
        help="The text to check, a document path with --from-file, or an artifact with --from-artifact.",
    )
    identify_origin = identify.add_mutually_exclusive_group()
    identify_origin.add_argument(
        "--from-file", dest="from_file", action="store_true", help="Read the source as a document path."
    )
    identify_origin.add_argument(
        "--from-artifact",
        dest="from_artifact",
        action="store_true",
        help="Read the source as an extracted-document JSON artifact, as scripts/extract_bench.py writes.",
    )
    identify.add_argument("-o", "--output", type=Path, help="Write JSON here instead of stdout.")
    identify.set_defaults(handler=_identify, from_file=False, from_artifact=False)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
