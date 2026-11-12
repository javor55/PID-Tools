"""
Doménový model projektu (plán v2, E3): `Project` → `Source[]` · `LoopSpec[]` · `TimeGrid`, registr zdrojů dat,
společná časová mřížka, návrh smyček z názvů tagů a migrace souboru projektu. Bez UI, bez API a bez stavu výpočtů.
"""
from .migrate import migrate_project  # noqa: F401
from .model import (FORMAT, VERSION, DataRef, LoopSpec, Project, Roles, Source, SourceRef,  # noqa: F401
                    TimeGrid)
from .journal import Snapshot  # noqa: F401
