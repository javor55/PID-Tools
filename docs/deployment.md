# Deployment and operation

> **Team web with sign-in:** see [Team web](#team-web-new-ui-container) – a container with Cloudflare Access,
> per-user workspaces, limits and logs. The old Streamlit web app was removed from `main` (milestone M28) and lives on
> in the branch **`streamlit`**.

PID Tools runs as a web app (FastAPI API + React UI, `python -m pidtools.api` or the container `Dockerfile.web`) or as
a desktop application (a window for engineering stations). Both use the same computations and project files.

| Option | For whom | Data |
|---|---|---|
| **Public Streamlit instance** (old app, branch `streamlit`) | quick trial, demo and non-sensitive data | leave for a third-party server |
| **Locally on a PC** | an individual engineer | stay on the own PC |
| **Offline PC / engineering station** (portable package via USB, desktop application) | PCs without internet, PCS 7 engineering stations | stay on the PC |
| **Internal server / local web** (`python -m pidtools.api`) | a team / company | stay in the company network |
| **Team web (new UI)** – one container, sign-in via Cloudflare Access | a team / company | stay on your server |
| **Public mode** – the same container without sign-in, nothing stored on the server | public demo / trial | processed in memory for the session only |

---

## Public instance (old Streamlit app)

<https://pidtools.streamlit.app/> – deployed from the branch **`streamlit`** (the current Streamlit app, frozen
since 11 Nov 2026) and updated automatically on every push to it. `main` is the development branch of the new UI
(API, React, desktop) – fixes of the Streamlit app go to `streamlit`, which cannot open project v3 with data. Nothing to install. Access can be restricted to invited users in the app settings on Streamlit Community
Cloud (subject to the terms of the service). Before uploading plant data there, check that your company rules allow
it.

## Locally on a PC

Install [Python 3.11](https://www.python.org/downloads/), then:
```bash
python -m venv .venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-api.txt
npm --prefix frontend ci && npm --prefix frontend run build   # writes pidtools/api/ui
python -m pidtools.api                                     # prints the URL with a token; --port, --host
```
In a company network with a proxy, configure the proxy for pip (`pip config set global.proxy http://proxy:port`)
or have the libraries installed by your IT.

## Offline PC (USB)

For a PC without internet there is a **Windows (x64)** download. It contains everything it needs (Python,
libraries, the application); no internet and no admin rights are needed. Download them on a PC with internet from
the repository's GitHub **Releases** or from the latest run of the *Offline package (Windows)* workflow (*Actions*
tab › run › *Artifacts*; an artifact is a ZIP that contains the package files).

**Desktop application** (window, no browser, no network port) – a classic Windows application with its icon:

- `PID-Tools-<version>-setup.exe` – installer for the current user (no admin rights): installs to
  `%LOCALAPPDATA%\Programs\PID Tools`, adds PID Tools to the Start menu (optionally to the desktop) and to
  *Settings › Apps* for uninstalling. Start **PID Tools** from the Start menu.
- `PID-Tools-<version>-desktop-win64-portable.zip` – the same without installing: unzip (e.g. to a USB stick or
  `C:\Tools`) and run **`PID Tools.exe`**. A data file or a project can be dropped on the exe to open it.

Windows 10 or 11 (x64). To remove the portable versions delete the folder; to update replace it (or run a newer
installer). Project files are interchangeable between the desktop and the web app.

**Building the packages yourself** (Windows PC with internet and Python 3.11):
```bash
pip install -r requirements.txt -r requirements-desktop.txt pyinstaller
python tools/build_desktop.py   # -> dist/PID Tools/PID Tools.exe, portable ZIP, installer (needs Inno Setup 6)
```
The workflow `.github/workflows/offline-package.yml` does the same on GitHub: it builds the desktop on Windows, tests it
(the exe runs a self-test with `--smoke`) and publishes it as an artifact; for a version tag (`v*`) it attaches it
to a release. The Tauri desktop with the bundled API (`desktop/`) is built by `desktop.yml` / `sidecar.yml`.

## Internal server

Without sign-in the API is meant for one user (token on the command line). To share it within a team use the
[Team web](#team-web-new-ui-container) below (container `Dockerfile.web`, sign-in via Cloudflare Access) or put it behind a
reverse proxy with authentication (e.g. company SSO) and HTTPS.

**Requirements (indicative):** one session takes on the order of hundreds of MB of memory (more for large exports);
optimization and gain scheduling briefly load one CPU core. 2 cores and 2–4 GB RAM should be enough for a small
team.

## Team web (new UI, container)

The new web (FastAPI API + the built React UI) runs as **one container** and, has
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
  Python 3.11 slim with `requirements.txt` + `requirements-api.txt` only (no Qt). Base images are pinned by tag **and digest**. It runs as the non-root user
  `pidtools` (uid 10001) and listens on `$PORT` (default 8080) with proxy headers enabled. The old Streamlit image
  (`Dockerfile`) was removed with the Streamlit app (branch `streamlit`).
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
| `PIDTOOLS_MAX_WORKSPACES_USER` | 5 | workspaces per user; a new one frees the user's least recently used workspace |
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

**Public instance on Oracle Cloud Free Tier (ARM64):** the folder [`deploy/`](../deploy/README.md) holds a Czech
step-by-step guide, `compose.yml` (app + Cloudflare Tunnel, update timer `install-update-timer.sh`, hardened: read-only root, no published ports)
and `.env.example` (all variables, incl. the public-mode limits listed in this document). Pushing to the branch
`deploy` runs the workflow *Web image* (multi-arch build, smoke test, Trivy scan) and publishes
`ghcr.io/javor55/pid-tools:deploy`; a systemd timer on the VM picks it up within 5 minutes. The `Audit` workflow runs
`pip-audit` and `npm audit` on PRs and weekly.
## Public mode (no sign-in)

`PIDTOOLS_AUTH=public` runs the same container for **anyone on the internet without a login** - meant for a demo / trial
instance behind a Cloudflare Tunnel on a small VM. It reuses the team-mode machinery (every workspace and job belongs to
a *session* instead of a user), but because nobody is vetted the server keeps **nothing on disk** and is limited
per session, per client IP and globally.

```bash
docker run -d --name pid-tools-public --restart unless-stopped -p 127.0.0.1:8080:8080 \
  -e PIDTOOLS_AUTH=public -e PIDTOOLS_TRUST_CF_IP=1 --read-only --tmpfs /tmp pid-tools-web
```

**Sessions.** The first call of the UI (`GET /api/v1/config`) makes the server issue a random 256-bit session id in the
cookie `pidtools_sid` (`HttpOnly; Secure; SameSite=Strict`, `Max-Age` = idle time). The id is the "user": another
session's workspace or job id returns **404**. A session expires after `PIDTOOLS_SESSION_TTL` seconds without a request
and its workspaces, jobs and in-memory settings are freed. A cookie value the server does not know (forged, expired) is
replaced. Writes with an `Origin` header that differs from `Host` get **403** (CSRF defence in addition to
`SameSite=Strict`). Without HTTPS the browser drops `Secure` cookies - for a local test over plain http set
`PIDTOOLS_COOKIE_SECURE=0`.

| Variable | Public default | Meaning |
|---|---|---|
| `PIDTOOLS_AUTH` | - | `public` enables the mode |
| `PIDTOOLS_COOKIE_SECURE` | `1` | `Secure` flag of the session cookie (and `Strict-Transport-Security`); `0` only for local http |
| `PIDTOOLS_SESSION_TTL` | 7200 | idle expiry of a session in seconds |
| `PIDTOOLS_MAX_SESSIONS` | 200 | sessions in total; when full, new visitors get **503** `pub_busy` (existing sessions keep working) |
| `PIDTOOLS_MAX_UPLOAD_MB` | 20 | largest request body (data file, project, settings); bigger gives **413** from `Content-Length`; a body without `Content-Length` (chunked) gives 411 |
| `PIDTOOLS_MAX_WORKSPACES_USER` | 3 | workspaces per session (a new one frees the least recently used one) |
| `PIDTOOLS_MAX_WORKSPACES` | 100 | workspaces in total |
| `PIDTOOLS_MAX_JOBS_USER` | 2 | queued + running jobs per session; more gives **429** |
| `PIDTOOLS_MAX_JOBS` | number of CPUs | jobs running at once (processes) |
| `PIDTOOLS_MAX_QUEUE` | 4 | jobs waiting beyond the running ones, server-wide; when running + waiting is full: **503** `pub_busy` with `Retry-After` |
| `PIDTOOLS_RATE_LIMIT` | 300 | API requests per minute and client IP (token bucket, burst = 1/6 of it; `/health` is exempt); over: **429** |
| `PIDTOOLS_RATE_UPLOAD` | 10 | uploads of 256 kB or more and job submissions per minute and client IP (burst = half) |
| `PIDTOOLS_TRUST_CF_IP` | off | `1` takes the client IP from `CF-Connecting-IP` (only behind Cloudflare Tunnel; otherwise the socket peer is used) |
| `PIDTOOLS_WORKSPACE_TTL` | 3600 | idle expiry of a workspace in seconds |

New sessions are also limited to 10 per minute (burst 5) per IP, so one client cannot fill the session table.
**Behind the tunnel set `PIDTOOLS_TRUST_CF_IP=1`** - otherwise all visitors share the IP of `cloudflared` and one rate
bucket - and make sure the container port is reachable **only** from the tunnel (`-p 127.0.0.1:...` or a private Docker
network), because with the flag on anyone who can reach the port could forge the header. In public mode
`X-Forwarded-For` is not trusted (the server starts uvicorn without proxy headers unless you set
`PIDTOOLS_FORWARDED_ALLOW_IPS` yourself).

**What is disabled or kept in memory**

| Feature | In public mode |
|---|---|
| App settings (`/app-settings`) | in memory of the session, bounded by the validation; lost with the session (export / import still work); connections are never stored |
| Report logo upload | **403** `logo_disabled`; the UI hides it |
| Recovery copy (autosave), recent projects | off (`/autosave` gives **403**, `/recent` is empty); the UI does not autosave - users save the project as a file |
| User controller library (create, import, edit, delete) | read-only (**403**); presets work; a loop can still carry its own controller inside the project |
| OPC UA (browse, find, history) and historian addresses | **403** `opc_disabled`; the UI hides the buttons |
| Journal attachments | **403** `attachments_disabled` (journal snapshots and notes work) |
| `/docs`, `/redoc`, `/openapi.json` | off |
| Disk | nothing is written under the config, data or controller directories (a test asserts it); run the container with a read-only root filesystem and a `tmpfs` for `/tmp` |

**Privacy.** The UI shows a notice on the Start screen and in the help (`?`): data is processed only on the server for
the session and discarded when it ends or after the idle time; save the project to a file. Access logs contain only a
short hash of the session id (`user=s-1a2b3c4d`), never the id itself, the query string or uploaded data. Responses of
the API carry `Cache-Control: no-store`.

## Security hardening (all modes)

- Every response carries `Content-Security-Policy` (`default-src 'self'; script-src 'self'; style-src 'self'
  'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none';
  form-action 'self'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`,
  `Cross-Origin-Opener-Policy: same-origin` and a minimal `Permissions-Policy`. The report preview lives in a sandboxed
  frame served from `/report-host.html` with its own CSP (the report carries Plotly scripts) and no network access.
  A reverse proxy must not strip or override these headers.
- The report logo accepts **png / jpg only** (SVG can carry scripts). An old SVG logo is still readable but served as an
  attachment with `Content-Security-Policy: sandbox`.
- Input limits: CSV / Excel are limited to 2 000 000 rows and 500 columns; an `.xlsx` (a zip) is rejected before parsing
  when its unpacked size exceeds 128 MB or it holds more than 2 000 files (zip bomb); project and settings files have
  size caps and absurdly nested JSON is a 400; the controller equation language has limits on source length (20 000
  characters), statements, parameters, tree nodes and depth.
- Errors never contain stack traces; file paths are removed from job errors in public mode.

## Data and privacy

- Uploaded data are processed only in the server memory for the duration of the session (and in the computation
  cache); the application writes nothing to disk and calls no external services.
- The web app does not store work in progress – the user saves it as a project (`.pidproj` file, JSON content).
- The project (`.pidproj`, JSON content) and the protocol (HTML) are downloaded to the user's computer. A protocol with charts
  "from the internet" loads the chart library from a CDN when opened; the default (embedded) works offline.

## Updates

- The public Streamlit instance (branch `streamlit`) updates itself.
- **Locally:** download the new version (or `git pull`) and reinstall the requirements and rebuild the UI.
- **Docker:** rebuild the image and restart the container.

Projects saved by an older version can be loaded in a newer one. The app version is shown in *Help › About* and in
the protocol footer; changes are listed in the [CHANGELOG](../CHANGELOG.md).

## Development and tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```
The tests cover the computation core, data loading, the API, the React UI (Playwright), the desktop and the agreement of
the in-browser live simulation with the Python computation (requires Node.js; skipped without it).
