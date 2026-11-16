"""Render README.md and the bilingual brief from results/*.json, and check their numbers against the results.

Template syntax:  {{file:dotted.path|spec}}  where `file` is the stem of a JSON file in results/, and spec is
    a Python format spec for the number as stored      e.g.  .3f   ,d   d
    pctN       value x 100 with N decimals (no % sign added)
    s          a string leaf, inserted as is
{{table:name}} inserts a table built by a function registered in TABLES (see report_tables.py).

Templates carry no digits of their own: every number in the rendered text comes from a results file. The checker
(`unsupported_numbers`) re-derives that independently from the rendered text, so a hand-edited number is caught.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "results"
PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+):([^|}]+?)\s*(?:\|\s*([^}]+?)\s*)?\}\}")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
THOUSANDS = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")


def load_results(folder: Path = RESULTS) -> dict:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))}


def lookup(results: dict, file: str, path: str):
    node = results[file]
    for part in path.split("."):
        if isinstance(node, list):
            node = node[int(part)]
        else:
            node = node[part]
    return node


def fmt(value, spec: str) -> str:
    if spec == "s":
        if not isinstance(value, str):
            raise TypeError(f"'s' needs a string, got {value!r}")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"number expected, got {value!r}")
    if spec.startswith("pct"):
        return format(value * 100.0, f".{int(spec[3:] or 0)}f")
    if spec.endswith("d"):
        if float(value) != int(value):
            raise ValueError(f"{value!r} is not a whole number")
        return format(int(value), spec)
    return format(value, spec)


def render(template: str, results: dict, tables: dict | None = None) -> str:
    def sub(m: re.Match) -> str:
        file, path, spec = m.group(1), m.group(2).strip(), (m.group(3) or "s")
        if file == "table":
            return (tables or {})[path](results)
        return fmt(lookup(results, file, path), spec)

    out = PLACEHOLDER.sub(sub, template)
    if "{{" in out or "}}" in out:
        raise ValueError("unresolved placeholder in template")
    return out


def template_digits(template: str) -> list[str]:
    """Digits a template carries outside its placeholders (there must be none)."""
    return re.findall(r"\d+", PLACEHOLDER.sub("", template))


def leaves(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from leaves(v)
    elif isinstance(node, list):
        for v in node:
            yield from leaves(v)
    else:
        yield node


def _supported(token: str, numbers: list[float], string_tokens: set[str]) -> bool:
    if token in string_tokens:
        return True
    plain = token.replace(",", "") if THOUSANDS.match(token) else token
    if plain.count(".") > 1 or "," in plain:
        return False                                   # an identifier such as 7.4.7: only verbatim support counts
    decimals = len(plain.split(".")[1]) if "." in plain else 0
    for v in numbers:
        for scaled in (abs(v), abs(v) * 100.0):
            if decimals == 0:
                if abs(scaled - round(scaled)) < 1e-9 and format(round(scaled), "d") == plain:
                    return True
            elif format(scaled, f".{decimals}f") == plain:
                return True
    return False


def unsupported_numbers(text: str, results: dict) -> list[str]:
    """Numbers in `text` that no value in the results supports.

    A number is supported when it equals a numeric leaf (or 100 x it, for percentages) rounded to the number of
    decimals shown, or when it appears verbatim inside a string leaf (standard numbers, dates, URLs). A number
    shown without decimals needs a whole-number value behind it.
    """
    numbers, string_tokens = [], set()
    for leaf in leaves(results):
        if isinstance(leaf, bool) or leaf is None:
            continue
        if isinstance(leaf, (int, float)):
            numbers.append(float(leaf))
        elif isinstance(leaf, str):
            string_tokens.update(NUMBER.findall(leaf))
    missing = []
    for token in NUMBER.findall(text):
        if not _supported(token, numbers, string_tokens):
            missing.append(token)
    return missing
