"""
Stav jedné smyčky desktopu – pracovní prostor bez UI je v aplikační vrstvě (pidtools.app.workspace); okna jen
čtou a mění jeho stav a volají jeho metody.
"""
from ..app.workspace import DEFAULTS, Workspace

LoopState = Workspace

__all__ = ["DEFAULTS", "LoopState"]
