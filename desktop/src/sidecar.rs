//! Sidecar `pidtools-api` (M22): nalezení programu, spuštění, čekání na řádek READY, ukončení.
use serde::Deserialize;
use std::collections::VecDeque;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{self, RecvTimeoutError};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

pub const READY: &str = "PIDTOOLS_READY";
pub const HOST: &str = "127.0.0.1";
/// Jak dlouho čekáme na řádek READY (zabalený program startuje ~1 s, antivirus při prvním spuštění déle).
pub const START_TIMEOUT: Duration = Duration::from_secs(20);

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Ready {
    pub port: u16,
    pub token: String,
    pub version: String,
}

/// Řádek `PIDTOOLS_READY {json}` → Ready; jiný řádek (nebo rozbitý JSON) → None.
pub fn parse_ready(line: &str) -> Option<Ready> {
    let rest = line.trim().strip_prefix(READY)?.strip_prefix(' ')?;
    serde_json::from_str(rest).ok()
}

/// Adresa rozhraní, které obsluhuje sidecar; token v části za `#` se nikdy neposílá serveru ani do logů.
pub fn ui_url(r: &Ready) -> String {
    format!("http://{HOST}:{}/#token={}", r.port, r.token)
}

/// Náhodný token (24 bajtů, hex – bez znaků, které by adresa musela kódovat).
pub fn new_token() -> String {
    let mut b = [0u8; 24];
    getrandom::fill(&mut b).expect("OS random generator unavailable");
    b.iter().map(|x| format!("{x:02x}")).collect()
}

/// Spustitelný soubor onedir ve složce: `pidtools-api[-<trojice>][.exe]`.
pub fn find_exe(dir: &Path) -> Option<PathBuf> {
    let mut found: Vec<PathBuf> = std::fs::read_dir(dir)
        .ok()?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.is_file())
        .filter(|p| {
            let n = p.file_name().and_then(|n| n.to_str()).unwrap_or("");
            let stem = n.strip_suffix(".exe").unwrap_or(n);
            stem == "pidtools-api" || stem.starts_with("pidtools-api-")
        })
        .collect();
    found.sort();
    found.into_iter().next()
}

/// Složky, kde hledat onedir (v pořadí): proměnná PIDTOOLS_SIDECAR_DIR, vedle aplikace (`sidecar/`; Windows NSIS),
/// `resources/sidecar` (Linux balíčky), zdrojový strom (`cargo tauri dev`: ../dist/pidtools-api).
pub fn candidate_dirs(env_dir: Option<&str>, exe_dir: &Path) -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> = Vec::new();
    if let Some(d) = env_dir.filter(|d| !d.is_empty()) {
        v.push(PathBuf::from(d));
    }
    v.push(exe_dir.join("sidecar"));
    v.push(exe_dir.join("resources").join("sidecar"));
    if let Some(parent) = exe_dir.parent() {
        v.push(parent.join("lib").join("PID Tools").join("sidecar"));
    }
    v.push(Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("dist").join("pidtools-api"));
    v
}

pub fn locate() -> Result<PathBuf, String> {
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(Path::to_path_buf))
        .unwrap_or_default();
    let dirs = candidate_dirs(std::env::var("PIDTOOLS_SIDECAR_DIR").ok().as_deref(), &exe_dir);
    dirs.iter().find_map(|d| find_exe(d)).ok_or_else(|| {
        let tried: Vec<String> = dirs.iter().map(|d| d.display().to_string()).collect();
        format!("Sidecar pidtools-api not found. Looked in:\n{}", tried.join("\n"))
    })
}

pub struct Sidecar {
    child: Child,
    pub ready: Ready,
}

impl Sidecar {
    pub fn kill(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for Sidecar {
    fn drop(&mut self) {
        self.kill();
    }
}

#[cfg(windows)]
fn no_console(cmd: &mut Command) {
    use std::os::windows::process::CommandExt;
    cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: sidecar je konzolový program, okno konzole se nesmí ukázat
}
#[cfg(not(windows))]
fn no_console(_: &mut Command) {}

fn tail(lines: &Arc<Mutex<VecDeque<String>>>) -> String {
    lines.lock().map(|l| l.iter().cloned().collect::<Vec<_>>().join("\n")).unwrap_or_default()
}

/// Čte proud po řádcích (i s neplatným UTF-8) až do konce; každý řádek předá `f`. Čtení nesmí skončit dřív,
/// jinak by se roura zaplnila a sidecar by se zablokoval.
fn pump<R: std::io::Read + Send + 'static>(r: R, mut f: impl FnMut(String) + Send + 'static) {
    std::thread::spawn(move || {
        let mut rd = BufReader::new(r);
        let mut buf = Vec::new();
        while rd.read_until(b'\n', &mut buf).map(|n| n > 0).unwrap_or(false) {
            f(String::from_utf8_lossy(&buf).trim_end().to_string());
            buf.clear();
        }
    });
}

/// Spustí sidecar na volném portu s náhodným tokenem a počká na řádek READY.
pub fn start(exe: &Path, timeout: Duration) -> Result<Sidecar, String> {
    let token = new_token();
    let mut cmd = Command::new(exe);
    cmd.args(["--port", "0", "--token", &token, "--parent-pid", &std::process::id().to_string()])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(d) = exe.parent() {
        cmd.current_dir(d);
    }
    no_console(&mut cmd);
    let mut child = cmd.spawn().map_err(|e| format!("Cannot start {}: {e}", exe.display()))?;
    let (tx, rx) = mpsc::channel::<String>();
    pump(child.stdout.take().expect("piped stdout"), move |l| {
        let _ = tx.send(l);
    });
    let err_tail = Arc::new(Mutex::new(VecDeque::new()));
    let sink = Arc::clone(&err_tail);
    pump(child.stderr.take().expect("piped stderr"), move |l| {
        if let Ok(mut q) = sink.lock() {
            q.push_back(l);
            if q.len() > 30 {
                q.pop_front();
            }
        }
    });
    let t0 = Instant::now();
    let fail = |child: &mut Child, why: String| {
        let _ = child.kill();
        let code = child.wait().ok().and_then(|s| s.code());
        let code = code.map(|c| format!(" (exit code {c})")).unwrap_or_default();
        Err(format!("{why}{code}\n{}", tail(&err_tail)))
    };
    loop {
        let left = timeout.saturating_sub(t0.elapsed());
        match rx.recv_timeout(left) {
            Ok(line) => {
                if let Some(r) = parse_ready(&line) {
                    if r.token != token {
                        return fail(&mut child, "Sidecar reported a different token.".into());
                    }
                    return Ok(Sidecar { child, ready: r });
                }
            }
            Err(RecvTimeoutError::Timeout) => {
                return fail(&mut child, format!("Sidecar did not become ready within {} s.", timeout.as_secs()))
            }
            Err(RecvTimeoutError::Disconnected) => {
                return fail(&mut child, "Sidecar exited before it was ready.".into());
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_ready_line() {
        let r = parse_ready(r#"PIDTOOLS_READY {"port": 51234, "token": "abc", "version": "3.3.0b1"}"#).unwrap();
        assert_eq!(r, Ready { port: 51234, token: "abc".into(), version: "3.3.0b1".into() });
        assert_eq!(parse_ready("PIDTOOLS_READY {\"port\":1,\"token\":\"t\",\"version\":\"v\"}\r\n").unwrap().port, 1);
    }

    #[test]
    fn rejects_other_lines() {
        assert!(parse_ready("INFO: Started server").is_none());
        assert!(parse_ready("PIDTOOLS_READY").is_none());
        assert!(parse_ready("PIDTOOLS_READY not json").is_none());
        assert!(parse_ready(r#"PIDTOOLS_READY {"port": 70000, "token": "a", "version": "v"}"#).is_none());
        assert!(parse_ready(r#"PIDTOOLS_READYX {"port": 1, "token": "a", "version": "v"}"#).is_none());
    }

    #[test]
    fn builds_ui_url() {
        let r = Ready { port: 8123, token: "tok".into(), version: "1".into() };
        assert_eq!(ui_url(&r), "http://127.0.0.1:8123/#token=tok");
    }

    #[test]
    fn tokens_are_random_hex() {
        let (a, b) = (new_token(), new_token());
        assert_eq!(a.len(), 48);
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(a, b);
    }

    #[test]
    fn finds_exe_by_convention() {
        let d = std::env::temp_dir().join(format!("pidtools-find-{}", std::process::id()));
        std::fs::create_dir_all(d.join("_internal")).unwrap();
        assert!(find_exe(&d).is_none());
        std::fs::write(d.join("readme.txt"), "x").unwrap();
        std::fs::write(d.join("pidtools-api-x86_64-pc-windows-msvc.exe"), "x").unwrap();
        let p = find_exe(&d).unwrap();
        assert!(p.ends_with("pidtools-api-x86_64-pc-windows-msvc.exe"));
        std::fs::remove_dir_all(&d).unwrap();
    }

    #[test]
    fn candidate_order() {
        let v = candidate_dirs(Some("/x"), Path::new("/app"));
        assert_eq!(v[0], PathBuf::from("/x"));
        assert_eq!(v[1], PathBuf::from("/app/sidecar"));
        assert_eq!(candidate_dirs(None, Path::new("/app"))[0], PathBuf::from("/app/sidecar"));
    }

    #[cfg(unix)]
    #[test]
    fn start_reports_early_exit_and_timeout() {
        use std::os::unix::fs::PermissionsExt;
        let d = std::env::temp_dir().join(format!("pidtools-fake-{}", std::process::id()));
        std::fs::create_dir_all(&d).unwrap();
        let mk = |name: &str, body: &str| {
            let p = d.join(name);
            std::fs::write(&p, format!("#!/bin/sh\n{body}\n")).unwrap();
            std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o755)).unwrap();
            p
        };
        let bad = mk("bad", "echo boom >&2; exit 3");
        let e = start(&bad, Duration::from_secs(5)).err().unwrap();
        assert!(e.contains("exited before") && e.contains("boom") && e.contains("exit code 3"), "{e}");
        let slow = mk("slow", "sleep 30");
        let e = start(&slow, Duration::from_millis(300)).err().unwrap();
        assert!(e.contains("did not become ready"), "{e}");
        // se špatným tokenem
        let wrong = mk("wrong", r#"echo 'PIDTOOLS_READY {"port":1,"token":"nope","version":"v"}'; sleep 30"#);
        assert!(start(&wrong, Duration::from_secs(5)).err().unwrap().contains("different token"));
        std::fs::remove_dir_all(&d).unwrap();
    }
}
