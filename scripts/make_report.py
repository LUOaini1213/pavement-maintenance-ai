"""Rebuild README.md and docs/brief.md from results/*.json and the templates in docs/.

    python scripts/make_report.py          # writes both files; exits with an error if a number has no support
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from pavement_ai import report  # noqa: E402
from pavement_ai.report_tables import TABLES  # noqa: E402

OUTPUTS = {"README.md": "docs/README.template.md", "docs/brief.md": "docs/brief.template.md"}


def build() -> dict:
    results = report.load_results()
    out = {}
    for target, template in OUTPUTS.items():
        text = (REPO / template).read_text(encoding="utf-8")
        stray = report.template_digits(text)
        if stray:
            raise SystemExit(f"{template} carries its own numbers: {stray}")
        rendered = report.render(text, results, TABLES)
        missing = report.unsupported_numbers(rendered, results)
        if missing:
            raise SystemExit(f"{target}: numbers without support in results/: {missing}")
        out[target] = rendered
    return out


if __name__ == "__main__":
    for target, text in build().items():
        (REPO / target).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {target} ({len(text.splitlines())} lines)")
