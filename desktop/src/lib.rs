//! PID Tools – okno desktopu (M23). Spustí sidecar `pidtools-api` (M22), počká na řádek READY a okno přepne na
//! rozhraní, které sidecar sám obsluhuje (`http://127.0.0.1:<port>/#token=…`). Okno nemá žádné Tauri IPC (prázdná
//! capability), takže stránka z 127.0.0.1 nedostane přístup k systému.
pub mod http;
pub mod openfile;
pub mod sidecar;

use std::io::Write;
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::{Manager, RunEvent, Url, WebviewWindow};

use sidecar::Sidecar;

struct State {
    sidecar: Mutex<Option<Sidecar>>,
    /// Projekt k otevření (z argumentů při startu nebo z druhého spuštění), než ho převezme sidecar.
    pending: Mutex<Option<PathBuf>>,
}

/// Předá čekající soubor projektu sidecaru (`PUT /pending-open`); bez sidecaru zůstane čekat do jeho startu.
fn deliver_pending(app: &tauri::AppHandle) {
    let st = app.state::<State>();
    let Some((port, token)) = st.sidecar.lock().ok().and_then(|s| s.as_ref().map(|s| (s.ready.port, s.ready.token.clone())))
    else {
        return;
    };
    let Some(path) = st.pending.lock().ok().and_then(|mut p| p.take()) else { return };
    if let Err(e) = openfile::deliver(port, &token, &path) {
        eprintln!("cannot open {}: {e}", path.display());
    }
}

/// Druhé spuštění s cestou k projektu: soubor se předá a stránka dostane událost (`pidtools:pending-open`),
/// po které si ho vyzvedne. `eval` nepotřebuje Tauri IPC ani oprávnění.
fn open_in_running_app(app: &tauri::AppHandle, path: PathBuf) {
    *app.state::<State>().pending.lock().expect("state") = Some(path);
    let app = app.clone();
    std::thread::spawn(move || {
        deliver_pending(&app);
        if let Some(w) = app.get_webview_window("main") {
            let _ = w.eval("window.dispatchEvent(new Event('pidtools:pending-open'))");
        }
    });
}

/// Chybu ukáže úvodní stránka okna (ui/index.html).
fn show_error(win: &WebviewWindow, msg: &str, detail: &str) {
    let js = |s: &str| serde_json::to_string(s).unwrap_or_else(|_| "\"\"".into());
    let _ = win.eval(format!("window.__pidFail({}, {})", js(msg), js(detail)));
}

fn boot(win: WebviewWindow) {
    let started = sidecar::locate().and_then(|exe| sidecar::start(&exe, sidecar::START_TIMEOUT));
    match started {
        Ok(sc) => {
            let url = Url::parse(&sidecar::ui_url(&sc.ready)).expect("valid url");
            win.app_handle().state::<State>().sidecar.lock().expect("state").replace(sc);
            deliver_pending(win.app_handle()); // projekt z argumentů prvního spuštění – dřív, než se rozhraní načte
            if let Err(e) = win.navigate(url) {
                show_error(&win, "Cannot open the user interface.", &e.to_string());
            }
        }
        Err(e) => show_error(&win, "The PID Tools backend did not start.", &e),
    }
}

fn focus(app: &tauri::AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

pub fn run() {
    let app = tauri::Builder::default()
        // druhé spuštění předvolí okno první instance; s cestou k projektu (.pidproj) ho v ní i otevře
        .plugin(tauri_plugin_single_instance::init(|app, argv, _cwd| {
            if let Some(p) = openfile::project_arg(&argv) {
                open_in_running_app(app, p);
            }
            focus(app);
        }))
        .manage(State {
            sidecar: Mutex::new(None),
            pending: Mutex::new(openfile::project_arg(&std::env::args().collect::<Vec<_>>())),
        })
        .setup(|app| {
            let win = app.get_webview_window("main").expect("main window");
            std::thread::spawn(move || boot(win));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("cannot build the Tauri app");
    app.run(|app, event| {
        if let RunEvent::Exit = event {
            if let Some(mut sc) = app.state::<State>().sidecar.lock().ok().and_then(|mut s| s.take()) {
                sc.kill(); // pro pád aplikace hlídá sidecar --parent-pid
            }
        }
    });
}

// ---- --smoke: sidecar + cesta přes API z Rustu, bez okna

struct Log(Option<std::fs::File>);

impl Log {
    fn line(&mut self, s: &str) {
        eprintln!("{s}");
        if let Some(f) = self.0.as_mut() {
            let _ = writeln!(f, "{s}");
            let _ = f.flush();
        }
    }
}

fn expect(cond: bool, what: &str) -> Result<(), String> {
    if cond { Ok(()) } else { Err(format!("check failed: {what}")) }
}

/// `--smoke --open soubor.pidproj`: soubor se předá jako při poklepu a z `/pending-open` se musí vrátit beze změny
/// (jednou; podruhé je místo prázdné).
fn smoke_open(sc: &Sidecar, file: &str, log: &mut Log) -> Result<(), String> {
    let (port, tok) = (sc.ready.port, Some(sc.ready.token.as_str()));
    openfile::deliver(port, &sc.ready.token, std::path::Path::new(file))?;
    let got = http::request(port, "GET", "/pending-open", tok)?;
    let want = std::fs::read_to_string(file).map_err(|e| format!("{file}: {e}"))?;
    expect(got.status == 200 && got.body == want, "GET /pending-open returns the delivered project")?;
    expect(http::request(port, "GET", "/pending-open", tok)?.status == 204, "pending project is taken once")?;
    log.line(&format!("open: {file} delivered ({} bytes) and taken", want.len()));
    Ok(())
}

fn smoke_steps(sc: &Sidecar, open: Option<&str>, log: &mut Log) -> Result<(), String> {
    let (port, tok) = (sc.ready.port, Some(sc.ready.token.as_str()));
    let h = http::request(port, "GET", "/health", None)?;
    expect(h.status == 200 && h.body.contains("\"ok\""), "GET /health")?;
    log.line(&format!("health: {}", h.body.trim()));
    expect(http::request(port, "GET", "/workspaces/x", None)?.status == 401, "no token -> 401")?;
    let ui = http::request(port, "GET", "/", None)?;
    expect(ui.status == 200 && ui.body.to_lowercase().contains("<html"), "GET / serves the UI")?;
    let ws = http::request(port, "POST", "/workspaces", tok)?;
    expect(ws.status == 200 || ws.status == 201, "POST /workspaces")?;
    let id = serde_json::from_str::<serde_json::Value>(&ws.body)
        .ok()
        .and_then(|v| v["id"].as_str().map(String::from))
        .ok_or("workspace id missing")?;
    let path = format!("/workspaces/{id}");
    expect(http::request(port, "GET", &path, tok)?.status == 200, "GET /workspaces/{id}")?;
    expect(http::request(port, "DELETE", &path, tok)?.status == 204, "DELETE /workspaces/{id}")?;
    log.line(&format!("workspace {id}: created, read, deleted"));
    open.map_or(Ok(()), |f| smoke_open(sc, f, log))
}

/// `pidtools-desktop --smoke [--smoke-log soubor] [--open projekt.pidproj]`: vrací kód ukončení (0 = v pořádku). Na Windows je aplikace
/// GUI program bez konzole, proto se průběh zapisuje i do souboru.
pub fn smoke(log_path: Option<&str>, open: Option<&str>) -> i32 {
    let mut log = Log(log_path.and_then(|p| std::fs::File::create(p).ok()));
    let t0 = std::time::Instant::now();
    let result = sidecar::locate().and_then(|exe| {
        log.line(&format!("sidecar: {}", exe.display()));
        sidecar::start(&exe, sidecar::START_TIMEOUT)
    });
    let code = match result {
        Ok(mut sc) => {
            log.line(&format!("smoke: ready in {:.2} s (sidecar {})", t0.elapsed().as_secs_f32(), sc.ready.version));
            let r = smoke_steps(&sc, open, &mut log);
            sc.kill();
            match r {
                Ok(()) => {
                    log.line("smoke: ok");
                    0
                }
                Err(e) => {
                    log.line(&format!("smoke: FAILED {e}"));
                    1
                }
            }
        }
        Err(e) => {
            log.line(&format!("smoke: FAILED {e}"));
            1
        }
    };
    code
}
