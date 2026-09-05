"""Look for margin residue in the regenerated text under looser tests.

The report beside the dataset calls a gutter four or more consecutive ascending
integers, each alone on its own line, and finds none left. That is one
threshold, and an earlier note on another branch reported two documents still
carrying a gutter after the same rule removed the same 4,854 numbers -- so the
disagreement is in the test, not in the rule.

This drops the threshold to pairs, looks for standalone integers of any kind,
and checks the citation the whole problem was found on.

    uv run python -m exploration.margin_rules.residue_probe
"""

from __future__ import annotations

import re
from pathlib import Path

V2 = Path("data/extraction-v2.0/documents_txt")
BODY_MARKER = "--- Plain text ---\n"
_STANDALONE = re.compile(r"(?m)^[ \t]*(\d{1,3})[ \t]*$")


def body(path: Path) -> str:
    _, marker, text = path.read_text(encoding="utf-8").partition(BODY_MARKER)
    return text if marker else path.read_text(encoding="utf-8")


def runs(text: str, minimum: int) -> list[list[int]]:
    values = [int(m.group(1)) for m in _STANDALONE.finditer(text)]
    found, current = [], []
    for value in values:
        if current and value == current[-1] + 1:
            current.append(value)
            continue
        if len(current) >= minimum:
            found.append(current)
        current = [value]
    if len(current) >= minimum:
        found.append(current)
    return found


def main() -> None:
    print(f"{'document':<46}{'standalone':>11}{'runs>=2':>9}{'runs>=3':>9}{'runs>=4':>9}")
    for path in sorted(V2.glob("*.txt")):
        text = body(path)
        standalone = len(_STANDALONE.findall(text))
        print(
            f"{path.stem[:44]:<46}{standalone:>11}"
            f"{len(runs(text, 2)):>9}{len(runs(text, 3)):>9}{len(runs(text, 4)):>9}"
        )

    print("\n--- the motivating citation, document 022 ---")
    for path in sorted(V2.glob("022*.txt")):
        text = body(path)
        for probe in ("214 F.3d 1058", "214 F.3d", "1058"):
            hit = text.find(probe)
            print(f"  {probe!r:<18} {'found at ' + str(hit) if hit >= 0 else 'ABSENT'}")
        start = text.find("214 F.3d")
        if start >= 0:
            print(f"  context: {text[start - 60 : start + 80]!r}")


if __name__ == "__main__":
    main()
