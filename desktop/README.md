# PID Tools desktop window (Tauri 2, M23)

A thin native window around the existing parts: the Python API as a standalone **sidecar** (`pidtools-api`, M22) and
the React UI, which the sidecar serves itself at `/`. Rust only starts and stops the sidecar, shows the window and
guards a single instance.

```
pidtools-desktop.exe ──spawn──> sidecar/pidtools-api-<triple>.exe --port 0 --token <random> --parent-pid <own pid>
        │                              │  stdout: PIDTOOLS_READY {"port":…, "token":"…", "version":"…"}
        │<─────────────────────────────┘
        └─ main window: ui/index.html (splash)  ──navigate──>  http://127.0.0.1:<port>/#token=<token>
```

## Decisions

- **Directory `desktop/`** (not `src-tauri/`): the repo is Python + a `frontend/` app, `desktop/` says what it is, and the
  Tauri CLI finds `desktop/tauri.conf.json` by itself. There is no JS in it (no `package.json`; the CLI is run with `npx`).
- **UI loaded from the sidecar**, not bundled: the window navigates to `http://127.0.0.1:<port>/#token=…`. The API
  and UI share one origin (no CORS, no CSP juggling, no `window.__PID__`), and the UI that is tested in the browser is
  exactly the UI in the window. `frontend/src/api/client.ts` reads the token from the fragment and removes it from the
  address. The window has **no Tauri capabilities** (empty permission list), so the page from `127.0.0.1` has no IPC
  and no access to the system. The bundled `ui/index.html` is only a splash and the error page.
- **The onedir ships as one resource folder, the sidecar is spawned by path** (not `externalBin`): Tauri copies an
  `externalBin` file to the app directory (`/usr/bin` in a Linux package) but resources elsewhere, so `_internal/` could
  not be guaranteed next to the exe. `bundle.resources` maps `../dist/pidtools-api` -> `sidecar/`, so the whole onedir
  (exe + `_internal/`) stays together. The exe is found by name (`pidtools-api[-<triple>][.exe]`) in, in order:
  `$PIDTOOLS_SIDECAR_DIR`, `<app dir>/sidecar` (Windows NSIS), `<app dir>/resources/sidecar`, `../dist/pidtools-api`
  (source tree, `cargo tauri dev`). No shell plugin is needed (`std::process`), and the sidecar's console window is
  suppressed (`CREATE_NO_WINDOW`).
- **Lifecycle**: the sidecar gets `--parent-pid`, so it exits by itself when the app crashes or is killed; a normal exit
  kills it explicitly (`RunEvent::Exit`). Startup timeout is 20 s; on failure (not found, exit before READY, timeout,
  wrong token) the splash page shows the message and the last stderr lines of the sidecar.
- **Dialogs**: no dialog plugin and no JS bridge. The UI uses `<a download>` (blob) and `<input type=file>`. WebView2
  (Windows) handles both natively: a file picker, and a download with its own *Save as* dialog. The web behaviour stays
  unchanged. WebKitGTK (Linux) does not offer a save dialog for blob downloads; Linux is a development platform only.
  If testing on Windows shows a problem, the bridge would be `save_file(name, bytes)` / `open_file()` commands plus
  `@tauri-apps/api` and `window.__TAURI_INTERNALS__` detection in `ProjectTab.tsx` (not done).
- **Single instance** (`tauri-plugin-single-instance`): a second launch focuses (and un-minimizes) the first window.
- **File association: none.** Projects are plain `.json` (`app.project`, shared with the Qt desktop and Streamlit, whose
  dialogs filter `*.json`). Associating `.json` would hijack every JSON file, and a new extension (`.pidproj`) would
  break interchange with the other frontends and make the UI/API change as well, so it is not trivial. Opening a project
  works through the *Load project* button. If a dedicated extension is wanted later, the single-instance callback
  already receives `argv`; the missing part is a frontend event that opens the file via `PUT /workspaces/{id}/project`.
- **Versions**: `tauri =2.12.3`, `tauri-build =2.7.2`, `tauri-plugin-single-instance =2.5.3` (latest releases at least two
  weeks old when written), CLI `@tauri-apps/cli@2.12.2`. `Cargo.lock` is committed; CI uses `--locked`.

## Build and run

Prerequisites: Rust >= 1.77, Node, Python with `requirements-api.txt` and `pyinstaller==6.22.3`. Linux also needs
`libwebkit2gtk-4.1-dev librsvg2-dev libayatana-appindicator3-dev`; Windows needs WebView2 (in Windows 11 and updated 10).

```
(cd frontend && npm ci && npm run build)       # -> pidtools/api/ui
python tools/build_sidecar.py                  # -> dist/pidtools-api/
cd desktop
cargo test                                     # ready line, URL, HTTP client, start/timeout handling
npx @tauri-apps/cli@2.12.2 dev                 # window, sidecar from ../dist/pidtools-api
npx @tauri-apps/cli@2.12.2 build --bundles nsis   # desktop/target/release/bundle/nsis/*-setup.exe (unsigned)
```

`cargo check` works without a built sidecar (`build.rs` creates an empty `dist/pidtools-api`, because Tauri insists on
the resource path existing). `cargo install tauri-cli --version "^2"` also works (`cargo tauri dev|build`).

**Smoke test**: `pidtools-desktop --smoke [--smoke-log file]` starts the sidecar, waits for READY and checks from Rust
`GET /health`, 401 without a token, `GET /` serves the UI, and `POST` / `GET` / `DELETE /workspaces`; exit code 0 means
success. No window opens. With a hand-made sidecar: `PIDTOOLS_SIDECAR_DIR=<dir with pidtools-api> pidtools-desktop --smoke`.

## CI

`.github/workflows/desktop.yml` (windows-latest): frontend, sidecar, `cargo check` + `cargo test`, `tauri build`
(NSIS, **unsigned**, placeholder for M24), silent install into a temp directory, `--smoke` of the *installed* app (so
the real layout `sidecar/_internal` next to the exe is verified), a check that no sidecar process is left, uninstall,
upload of the installer as an artifact.
