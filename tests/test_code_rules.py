"""Pravidla kódu, která jinak odhalí až CI (jiná verze knihovny než lokálně)."""
import pathlib
import re

API = pathlib.Path(__file__).resolve().parents[1] / "pidtools" / "api"


def test_pydantic_field_defaults_are_keyword():
    """`Field(1.6, ge=…)` mypy s pydanticem 2.14 nebere jako výchozí hodnotu („Missing named argument“) – jen
    `Field(default=…)`. Lokálně (starší pydantic) to projde, proto pravidlo hlídá tento test."""
    bad = []
    for f in sorted(API.glob("*.py")):
        for no, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bField\((?!default|\.\.\.|[a-z_]+\s*=|\))", line):
                bad.append(f"{f.name}:{no}: {line.strip()}")
    assert not bad, "\n".join(bad)
