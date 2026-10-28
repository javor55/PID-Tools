# Deployment and operation

> **Team web with sign-in (new UI):** see [Team web](#team-web-new-ui-container) – a container with
> Cloudflare Access, per-user workspaces, limits and logs. The other sections describe the current Streamlit web
> app and the desktop application.

PID Tools runs as a web app ([Streamlit](https://streamlit.io/): a Python server, users work in the browser) or as a
desktop application (a window, no browser and no network port – suitable for engineering stations). Both use the
same computations and the same project files.

| Option | For whom | Data |
|---|---|---|
| **Public instance** (Streamlit Community Cloud) | quick trial, demo and non-sensitive data | leave for a third-party server |
| **Locally on a PC** | an individual engineer | stay on the own PC |
| **Offline PC / engineering station** (portable package via USB, desktop application or web app) | PCs without internet, PCS 7 engineering stations | stay on the PC |
| **Internal server** | a team / company | stay in the company network |
| **Team web (new UI)** – one container, sign-in via Cloudflare Access | a team / company | stay on your server |

---

## Public instance

<https://pidtools.streamlit.app/> – updated automatically from the repository branch it is deployed from (usually
`main`). Nothing to install. Access can be restricted to invited users in the app settings on Streamlit Community
Cloud (subject to the terms of the service). Before uploading plant data there, check that your company rules allow
it.

## Locally on a PC

**Windows**
1. Install [Python 3.11](https://www.python.org/downloads/) (tick *Add Python to PATH*).
2. Download the repository (*Code › Download ZIP*) and unzip it.
3. Run `start.bat` – on the first start it installs the libraries (requires access to PyPI), then opens the app at
   <http://localhost:8501>.

In a company network with a proxy, configure the proxy for pip (`pip config set global.proxy http://proxy:port`)
or have the libraries installed by your IT.

**Linux / macOS**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Offline PC (USB)

For a PC without internet there are two **Windows (x64)** downloads. Both contain everything they need (Python,
libraries, the application); no internet and no admin rights are needed. Download them on a PC with internet from
the repository's GitHub **Releases** or from the latest run of the *Offline package (Windows)* workflow (*Actions*
tab › run › *Artifacts*; an artifact is a ZIP that contains the package files).

**Desktop application** (window, no browser, no network port) – a classic Windows application with its icon:

- `PID-Tools-<version>-setup.exe` – installer for the current user (no admin rights): installs to
  `%LOCALAPPDATA%\Programs\PID Tools`, adds PID Tools to the Start menu (optionally to the desktop) and to
  *Settings › Apps* for uninstalling. Start **PID Tools** from the Start menu.
- `PID-Tools-<version>-desktop-win64-portable.zip` – the same without installing: unzip (e.g. to a USB stick or
  `C:\Tools`) and run **`PID Tools.exe`**. A data file or a project can be dropped on the exe to open it.

**Web app offline** (the same functions in the browser on this PC):

- `PID-Tools-<version>-web-win64-offline.zip` – unzip, e.g. to `C:\Tools\PID-Tools-web` (avoid very long paths),
  and double-click **`PID-Tools.bat`**. A console window starts the app and the browser opens
  <http://localhost:8501>. Close the console window to stop the app. The OPC UA data source is included.

Windows 10 or 11 (x64). To remove the portable versions delete the folder; to update replace it (or run a newer
installer). Projects saved in JSON stay compatible and are interchangeable between the desktop and the web app.

**Building the packages yourself** (Windows PC with internet and Python 3.11):
```bash
pip install -r requirements.txt -r requirements-desktop.txt pyinstaller
python tools/build_desktop.py   # -> dist/PID Tools/PID Tools.exe, portable ZIP, installer (needs Inno Setup 6)
python tools/build_offline.py   # -> dist/PID-Tools-<version>-web-win64-offline.zip
```
The workflow `.github/workflows/offline-package.yml` does the same on GitHub: it builds both on Windows, tests them
(the desktop exe runs a self-test with `--smoke`; the web package runs the core and the whole app with its own
embedded Python and starts the server) and publishes them as artifacts; for a version tag (`v*`) it attaches them
to a release.

## Internal server

The application has **no built-in login** – to share it within a team, run it in the company network, optionally
behind a reverse proxy with authentication (e.g. company SSO) and HTTPS.

**Directly with Python** (e.g. as a systemd service):
```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
```

**Docker** (`Dockerfile` is in the repository):
```bash
docker build -t pid-tools .
docker run -d --name pid-tools -p 8501:8501 --restart unless-stopped pid-tools
```
Health check: `http://server:8501/_stcore/health` returns `ok`.

**Requirements (indicative):** one session takes on the order of hundreds of MB of memory (more for large exports);
optimization and gain scheduling briefly load one CPU core. 2 cores and 2–4 GB RAM should be enough for a small
team.

## Team web (new UI, container)

The new web (FastAPI API + the built React UI) runs as **one container** and, unlike the Streamlit app above, has
user sign-in: every workspace and job belongs to the user who created it. The desktop and local use of the API
(`python -m pidtools.api`, token) is unchanged – everything below is opt-in through environment variables.

```
browser ──► Cloudflare Access (login, policy) ──► tunnel / proxy ──► container :8080
                                adds the signed header Cf-Access-Jwt-Assertion
```

### Run the container

```bash
docker build -f Dockerfile.web -t pid-tools-web .
docker run -d --name pid-tools-web --restart unless-stopped -p 127.0.0.1:8080:8080 \
  -e PIDTOOLS_AUTH=cloudflare -e PIDTOOLS_CF_TEAM=yourteam -e PIDTOOLS_CF_AUD=<audience tag> \
  pid-tools-web
```

- The image is multi-stage: Node 24 builds the UI (`npx -y npm@11.21.0 ci && npm run build`), the runtime stage is
  Python 3.11 slim with `requirements.txt` + `requirements-api.txt` only (no Qt; the Streamlit line of
  `requirements.txt` is filtered out). Base images are pinned by tag **and digest**. It runs as the non-root user
  `pidtools` (uid 10001) and listens on `$PORT` (default 8080) with proxy headers enabled. The old Streamlit image
  is still `Dockerfile`; `Dockerfile.web` replaces it when the old web app is removed.
- Health check: `GET /health` (no sign-in) returns `{"status":"ok","version":…}`; the image has a `HEALTHCHECK`.
- **One process only** (workspaces and jobs are in memory): do not run several replicas behind a load balancer and
  do not use several uvicorn workers. A restart drops the workspaces – users save their work as a project file.
- Sizing: a job is a separate process (identification, optimization) that loads one CPU core; 2–4 cores and 4 GB
  RAM suit a small team with `PIDTOOLS_MAX_JOBS=2`.
- Without the container: `pip install -r requirements-api.txt`, build the UI (`cd frontend && npx -y npm@11.21.0 ci
  && npm run build`, it writes `pidtools/api/ui`) and run `python -m pidtools.api.serve` with the same variables.

### Cloudflare Access setup

1. **Zero Trust dashboard → Settings (General)**: note the **team domain** `yourteam.cloudflareaccess.com`;
   `PIDTOOLS_CF_TEAM` is `yourteam` (the full host name also works).
2. Publish the container under a hostname behind Cloudflare, e.g. with **Cloudflare Tunnel** (`cloudflared`
   next to the container, public hostname `pid.example.com` → service `http://pid-tools-web:8080`).
3. **Access → Applications → Add an application → Self-hosted**: application domain `pid.example.com`, session
   duration as you wish (when the session expires, Cloudflare shows its login page; reload the page afterwards).
4. Add an **Allow policy** (e.g. *Emails ending in* `@example.com`, or an Access group / your identity provider).
   A request that does not match a policy never reaches the container.
5. Open the application's settings (Overview / Basic information) and copy the **Application Audience (AUD) Tag** →
   `PIDTOOLS_CF_AUD`.
6. Start the container with the three variables above. The app verifies every API request itself: the
   `Cf-Access-Jwt-Assertion` header must be a JWT signed (RS256) with a key from
   `https://yourteam.cloudflareaccess.com/cdn-cgi/access/certs`, with issuer `https://yourteam.cloudflareaccess.com`,
   your AUD tag and a valid expiry. Missing or invalid → **401**; the signing keys cannot be downloaded and none is
   cached → **503**. Keys are cached in memory (1 hour; an unknown key id triggers a refetch at most once a minute,
   also when Cloudflare is unreachable), so the container needs outbound HTTPS to
   `yourteam.cloudflareaccess.com`. The user name is the `email` claim (a service token has none: its
   `common_name`).

Only `/health` and the static UI files (code and fonts, no data) are served without the header; everything that
touches data requires it. The UI itself needs no changes: the browser sends Cloudflare's cookie, Cloudflare adds the
header.

### Other proxy (OIDC) – header mode

For oauth2-proxy, Authelia, an nginx `auth_request` etc. the app can trust a user header set by the proxy:

```bash
-e PIDTOOLS_AUTH=header -e PIDTOOLS_TRUST_USER_HEADER=1 -e PIDTOOLS_USER_HEADER=X-Auth-Request-Email
```

**Risk:** the header is not signed. Anyone who can reach the container directly (not through the proxy), or a proxy
that passes through a header sent by the client, can act as any user. Use this mode only when (1) the container is
reachable solely from the proxy (private network, no published port) and (2) the proxy **overwrites** the header on
every request. That is why the mode refuses to start without the explicit `PIDTOOLS_TRUST_USER_HEADER=1`. A value
that is not a plain e-mail / user name (`A–Z a–z 0–9 . _ @ + -`) is rejected with 401; names are compared in lower
case. Prefer the Cloudflare mode when you can.

### Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `PIDTOOLS_AUTH` | `token` | `cloudflare`, `header` (team mode) or `token` (one shared token – the desktop behaviour) |
| `PIDTOOLS_CF_TEAM` | – | Cloudflare team (`yourteam` or `yourteam.cloudflareaccess.com`); required for `cloudflare` |
| `PIDTOOLS_CF_AUD` | – | Application Audience tag; required for `cloudflare` |
| `PIDTOOLS_USER_HEADER` | `X-Forwarded-Email` | header with the user name (`header` mode) |
| `PIDTOOLS_TRUST_USER_HEADER` | off | `1` confirms you understood the risk above (required for `header`) |
| `PIDTOOLS_TOKEN` | – | token for `PIDTOOLS_AUTH=token` (required there) |
| `PIDTOOLS_MAX_WORKSPACES_USER` | 5 | workspaces per user; the next one gets **429** until one is deleted or expires |
| `PIDTOOLS_MAX_WORKSPACES` | 20 | workspaces in total; when full, the longest idle one (of any user) is dropped – set it to at least *users × per-user limit* |
| `PIDTOOLS_MAX_JOBS_USER` | 2 | queued + running jobs per user; more → **429** |
| `PIDTOOLS_MAX_JOBS` | 2 | jobs running at the same time (processes); the rest wait in the queue |
| `PIDTOOLS_MAX_UPLOAD_MB` | 100 | largest uploaded file; bigger → **413** (from `Content-Length`, before the body is read; a proxy in front may have its own lower limit) |
| `PIDTOOLS_WORKSPACE_TTL` | 3600 | idle expiry of a workspace in seconds (every request to it renews it) |
| `PIDTOOLS_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `PIDTOOLS_CORS` | – | comma-separated origins for CORS (not needed: the UI is served by the same container) |
| `PIDTOOLS_FORWARDED_ALLOW_IPS` | `*` | proxies whose `X-Forwarded-*` headers uvicorn trusts (scheme / client address only; sign-in does not use them) |
| `PORT`, `HOST` | 8080, 0.0.0.0 | listening port and address |

The limits apply in all modes; the per-user ones only with a user (`cloudflare`, `header`).

### Users and isolation

A workspace (its data, model and settings) belongs to the user who created it. Another user's workspace id returns
**404**, exactly as if it did not exist (for reading, deleting, data, identification, report…). The same holds for
jobs (`/jobs/{id}`, `/cancel`, `/result`, `/events`). Isolation does not depend on the ids being secret. There is
no administrator role that could see other users' data through the API.

### Logs

Standard Python `logging` to stderr (`docker logs`), one `key=value` line each, level from `PIDTOOLS_LOG_LEVEL`:

```
2026-10-28 07:16:08,051 INFO pidtools.access user=bob@acme.com method=GET path=/workspaces/QIasl… status=404 ms=2.2
2026-10-28 07:16:08,076 INFO pidtools.jobs job submit id=j1 user=alice@acme.com fn=run
2026-10-28 07:16:08,341 INFO pidtools.jobs job start id=j1 user=alice@acme.com fn=run
2026-10-28 07:16:20,383 INFO pidtools.jobs job end id=j1 user=alice@acme.com state=done seconds=12.28
```

- `pidtools.access`: one line per request (`user=-` when the sign-in failed); the query string is not logged;
  `/health` only at `DEBUG`. Job end states: `done`, `error` (with `error=…`), `cancelled`, `timeout`.
- Uploaded data and results are never logged.

### Network

- Publish the port only to the tunnel / proxy (`-p 127.0.0.1:8080:8080`, or no `-p` and a shared Docker network with
  `cloudflared`). In Cloudflare mode a request that bypasses Cloudflare still needs a valid JWT and cannot forge a
  user, but keep the origin closed anyway (defence in depth; mandatory in `header` mode).
- HTTPS ends at Cloudflare / the proxy; the container speaks plain HTTP.
- Server-sent events (`/jobs/{id}/events`) must not be buffered by the proxy (Cloudflare does not).

### Updating

Pull the new version of the repository, rebuild (`docker build -f Dockerfile.web -t pid-tools-web .`), remove the
old container and start the new one with the same options (an `--env-file` keeps them in one place). Workspaces
live in memory and are lost on restart: announce a short window; users save their project (*Project → Save*) and
open it again. Projects saved by an older version open in a newer one. Limits are changed by restarting with other
values.

---

## Configuration (Streamlit app)

`.streamlit/config.toml`:

| Option | Setting | Why |
|---|---|---|
| `browser.gatherUsageStats` | `false` | no Streamlit telemetry |
| `client.toolbarMode` | `viewer` | users do not see developer options |
| `server.maxUploadSize` | `100` (MB) | size of an uploaded export |
| `[theme.light]`, `[theme.dark]` | colours | light and dark theme (switched by the user in the ⋮ menu) |

## Data and privacy

- Uploaded data are processed only in the server memory for the duration of the session (and in the computation
  cache); the application writes nothing to disk and calls no external services.
- The web app does not store work in progress – the user saves it as a project (JSON file).
- The project (JSON) and the protocol (HTML) are downloaded to the user's computer. A protocol with charts
  "from the internet" loads the chart library from a CDN when opened; the default (embedded) works offline.

## Updates

- The **public instance** updates itself.
- **Locally:** download the new version (or `git pull`) and start again; `start.bat` installs missing libraries.
- **Docker:** rebuild the image and restart the container.

Projects saved by an older version can be loaded in a newer one. The app version is shown in *Help › About* and in
the protocol footer; changes are listed in the [CHANGELOG](../CHANGELOG.md).

## Development and tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```
The tests cover the computation core, data loading, the whole application (Streamlit AppTest) and the agreement of
the in-browser live simulation with the Python computation (requires Node.js; skipped without it).
