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

## Configuration

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
