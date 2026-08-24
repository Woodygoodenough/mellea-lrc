"""Fork the published dataset into a private repo, and push v2 into it.

The Hub has no fork button for datasets, but it does have a server-side copy:
:meth:`HfApi.duplicate_repo` clones a repo including its git history and its
LFS objects without a local download and upload round trip. That is what makes
this a fork rather than a re-upload -- the private copy keeps v1's history, so
v2 lands as a commit on top of the published dataset rather than as an
unrelated repo that happens to contain similar files.

Two things it does deliberately.

**It never touches the published repo.** The source is only ever read. Every
write goes to ``--to``, which must be a repo the running account owns.

**It refuses to push a corpus that does not rebuild.** ``derived/`` holds
offsets into ``documents_txt/``, and a corpus whose spans do not slice out of
its own text is worse than no corpus, because the failure is silent downstream.
The verification that the regeneration runs is re-run here against the files as
they sit on disk, and a failure stops the push.

Usage::

    uv run python -m scripts.corpus.push_to_hub \
      --corpus data/false-citation-bench-v2 \
      --to Woodygoodenough/false-citation-bench-private \
      --from-id gt-csse/false-citation-bench
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from huggingface_hub import HfApi

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from scripts.corpus import build_case_names

# Everything under the corpus root that belongs in the dataset. Anything not
# listed is not uploaded, so a stray cache or scratch file cannot leak into a
# published artifact by sitting in the directory.
UPLOADED = ("annotations", "derived", "documents_pdf", "documents_txt", "README.md", "VERSION.md")


def verify(corpus: Path) -> None:
    """Refuse to push a corpus whose annotations do not address its own text."""
    for name in ("extraction.jsonl", "extraction_locators.jsonl", "case_names.jsonl"):
        if not (corpus / "derived" / name).exists():
            raise SystemExit(f"{corpus}/derived/{name} is missing; run the regeneration first")

    texts: dict[str, str] = {}

    def text_of(document: str) -> str:
        if document not in texts:
            texts[document] = (corpus / "documents_txt" / document).read_text(encoding="utf-8")
        return texts[document]

    wrong = 0
    checked = 0
    for name in ("extraction.jsonl", "extraction_locators.jsonl"):
        for line in (corpus / "derived" / name).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            span = row["span"]
            checked += 1
            if text_of(row["document"])[span["start"] : span["end"]] != row["matched_text"]:
                wrong += 1
    if wrong:
        raise SystemExit(f"{wrong} of {checked} annotation spans do not slice out of their document")

    names = [
        json.loads(line)
        for line in (corpus / "derived" / "case_names.jsonl").read_text().splitlines()
        if line
    ]
    name_checked, name_wrong = build_case_names.verify(names, corpus)
    if name_wrong:
        raise SystemExit(f"{name_wrong} of {name_checked} case names do not slice out of their document")
    print(f"verified {checked} annotation spans and {name_checked} case names against the corpus text")


def push(corpus: Path, to_id: str, from_id: str | None, message: str) -> str:
    """Fork the source repo if needed, then upload the corpus into it."""
    api = HfApi()
    who = api.whoami()
    owner = to_id.split("/")[0]
    if owner != who["name"] and owner not in {org["name"] for org in who.get("orgs", ())}:
        raise SystemExit(f"{who['name']} cannot write to {to_id}")

    try:
        api.repo_info(to_id, repo_type="dataset")
        print(f"{to_id} already exists; uploading into it")
    except Exception:
        if from_id is None:
            api.create_repo(to_id, repo_type="dataset", private=True)
            print(f"created {to_id} (private, no history)")
        else:
            api.duplicate_repo(from_id=from_id, to_id=to_id, repo_type="dataset", private=True)
            print(f"forked {from_id} into {to_id} (private, history preserved)")

    for entry in UPLOADED:
        path = corpus / entry
        if not path.exists():
            continue
        if path.is_dir():
            api.upload_folder(
                repo_id=to_id,
                repo_type="dataset",
                folder_path=str(path),
                path_in_repo=entry,
                commit_message=f"{message}: {entry}",
            )
        else:
            api.upload_file(
                repo_id=to_id,
                repo_type="dataset",
                path_or_fileobj=str(path),
                path_in_repo=entry,
                commit_message=f"{message}: {entry}",
            )
        print(f"  uploaded {entry}")
    return f"https://huggingface.co/datasets/{to_id}"


def main() -> None:
    """Verify the corpus, then fork and upload it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--to", required=True, help="target repo, e.g. user/name")
    parser.add_argument("--from-id", default=None, help="repo to fork; omit to create an empty one")
    parser.add_argument("--message", default="false-citation-bench v2")
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()

    verify(arguments.corpus)
    if arguments.verify_only:
        return
    print(push(arguments.corpus, arguments.to, arguments.from_id, arguments.message))


if __name__ == "__main__":
    main()
