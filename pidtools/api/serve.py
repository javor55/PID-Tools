"""
Spuštění webu pro tým / v kontejneru: python -m pidtools.api.serve (nastavení z proměnných PIDTOOLS_*, port z PORT;
návod docs/deployment.md). Jeden proces: pracovní prostory a úlohy jsou v paměti.
"""
import os
import sys


def main():
    import uvicorn

    from .deploy import app_from_env
    app = app_from_env()
    # Veřejný režim: X-Forwarded-For se nepřijímá (šlo by jím obejít limit po IP); IP klienta dává CF-Connecting-IP
    # (PIDTOOLS_TRUST_CF_IP=1), jinak protistrana spojení. Výchozí „*“ platí jen pro týmový režim za důvěryhodným proxy.
    public = os.environ.get("PIDTOOLS_AUTH", "").strip().lower() == "public"
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8080")),   # noqa: S104
                proxy_headers=not public or bool(os.environ.get("PIDTOOLS_FORWARDED_ALLOW_IPS")),
                forwarded_allow_ips=os.environ.get("PIDTOOLS_FORWARDED_ALLOW_IPS", "*"),
                log_level="warning", access_log=False, server_header=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
