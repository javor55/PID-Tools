"""python -m pidtools.desktop [data.csv | projekt.pidproj | projekt.json]"""
import sys

from . import launch

sys.exit(launch())
