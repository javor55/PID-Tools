"""
Spuštění API: python -m pidtools.api [--host 127.0.0.1] [--port 8765] [--token …] [--cors URL …]
              python -m pidtools.api --openapi pidtools/api/openapi.json   (jen zapsat popis rozhraní)
Bez --token se vygeneruje náhodný a vypíše na první řádek (desktop ho předá oknu aplikace).
"""
import argparse
import json
import secrets
import sys
from pathlib import Path


def openapi_json():
    from . import create_app
    return json.dumps(create_app().openapi(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m pidtools.api")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--token", default=None)
    ap.add_argument("--cors", nargs="*", default=[])
    ap.add_argument("--openapi", metavar="FILE", help="write the OpenAPI description and exit")
    a = ap.parse_args(argv)
    if a.openapi:
        Path(a.openapi).write_text(openapi_json(), encoding="utf-8")
        return 0
    import uvicorn

    from . import create_app
    token = a.token or secrets.token_urlsafe(24)
    if not a.token:
        print(f"token {token}", flush=True)
    uvicorn.run(create_app(token=token, cors_origins=a.cors), host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
