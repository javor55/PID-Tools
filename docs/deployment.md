# Deployment and operation

PID Tools runs as a web app ([Streamlit](https://streamlit.io/): a Python server, users work in the browser) or as a
desktop application (a window, no browser and no network port – suitable for engineering stations). Both use the
same computations and the same project files.

| Option | For whom | Data |
|---|---|---|
| **Public instance** (Streamlit Community Cloud) | quick trial, demo and non-sensitive data | leave for a third-party server |
| **Locally on a PC** | an individual engineer | stay on the own PC |
| **Offline PC / engineering station** (portable package via USB, desktop application or web app) | PCs without internet, PCS 7 engineering stations | stay on the PC |
| **Internal server** | a team / company | stay in the company network |

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

For a PC without internet there is a **portable package for Windows (x64)**: a folder with its own Python, all
libraries and the application. Nothing is installed, no admin rights are needed.

1. On a PC with internet download `PID-Tools-<version>-win64-offline.zip` (about 300 MB) from the repository's
   GitHub **Releases** or from the latest run of the *Offline package (Windows)* workflow (*Actions* tab ›
   run › *Artifacts*; the artifact is a ZIP that contains the package ZIP).
2. Copy it to the offline PC (USB stick) and unzip it, e.g. to `C:\Tools\PID-Tools` (avoid very long paths).
3. **Desktop application:** double-click **`PID-Tools-desktop.bat`** – a window opens (no browser, no network port,
   nothing running in the background). A data file or a project can be dropped on the `.bat` file to open it.
4. **Web app** (the same functions in the browser): double-click **`PID-Tools.bat`**. A console window starts the
   app and the browser opens <http://localhost:8501>. Close the console window to stop the app.

The package needs Windows 10 or 11 (x64).

To uninstall, delete the folder. To update, replace the folder with a newer package (projects saved in JSON stay
compatible).

**Building the package yourself** (Windows PC with internet and Python 3.11):
```bash
python tools/build_offline.py        # -> dist/PID-Tools-<version>-win64-offline.zip
python tools/build_offline.py --no-desktop   # web app only, without Qt (smaller)
```
The workflow `.github/workflows/offline-package.yml` does the same on GitHub: it builds the package on Windows,
tests it with its own embedded Python (core, the whole web app and the desktop windows on demo data, server start)
and publishes it as an
artifact; for a version tag (`v*`) it attaches it to a release.

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

## Configuration

`.streamlit/config.toml`:

| Option | Setting | Why |
|---|---|---|
| `browser.gatherUsageStats` | `false` | no Streamlit telemetry |
| `client.toolbarMode` | `viewer` | users do not see developer options |
| `server.maxUploadSize` | `200` (MB) | size of an uploaded export |
| `[theme.light]`, `[theme.dark]` | colours | light and dark theme (switched by the user in the ⋮ menu) |

## Data and privacy

- Uploaded data are processed only in the server memory for the duration of the session (and in the computation
  cache); the application writes nothing to disk and calls no external services.
- Work in progress is autosaved **in the user's browser** (IndexedDB) – not on the server. The user can switch it
  off or clear it in the Project & report tab.
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
