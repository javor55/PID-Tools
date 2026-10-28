//! Otevření projektu poklepem na soubor `.pidproj` (M23): cesta z argumentů příkazové řádky → soubor se přes
//! `PUT /pending-open` předá sidecaru a rozhraní si ho vyzvedne a otevře do svého pracovního prostoru. Okno tak
//! nepotřebuje žádné Tauri IPC.
use std::path::{Path, PathBuf};

use crate::http;

/// Přípony souborů projektu (výchozí `.pidproj`, starší `.json`); malá a velká písmena se nerozlišují.
pub const EXTS: [&str; 2] = ["pidproj", "json"];
/// Stejný limit jako `MAX_PROJECT` v API.
pub const MAX_BYTES: u64 = 300 * 1024 * 1024;

pub fn is_project(p: &Path) -> bool {
    p.extension().and_then(|e| e.to_str()).is_some_and(|e| EXTS.iter().any(|x| e.eq_ignore_ascii_case(x)))
}

/// Cesta k projektu z argumentů (první je program): první argument, který nezačíná `-` a má příponu projektu.
pub fn project_arg(args: &[String]) -> Option<PathBuf> {
    args.iter().skip(1).filter(|a| !a.starts_with('-')).map(PathBuf::from).find(|p| is_project(p))
}

/// Předá soubor sidecaru (`PUT /pending-open`, 204).
pub fn deliver(port: u16, token: &str, path: &Path) -> Result<(), String> {
    let meta = std::fs::metadata(path).map_err(|e| format!("{}: {e}", path.display()))?;
    if meta.len() > MAX_BYTES {
        return Err(format!("{}: file too large", path.display()));
    }
    let raw = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let r = http::request_body(port, "PUT", "/pending-open", Some(token), &raw)?;
    if r.status == 204 { Ok(()) } else { Err(format!("PUT /pending-open -> {}", r.status)) }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(v: &[&str]) -> Vec<String> {
        v.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn finds_the_project_path() {
        let want = Some(PathBuf::from(r"C:\Data\K2 projekt.pidproj"));
        assert_eq!(project_arg(&args(&["pidtools-desktop.exe", r"C:\Data\K2 projekt.pidproj"])), want);
        assert_eq!(project_arg(&args(&["app", "--flag", r"C:\Data\K2 projekt.pidproj"])), want);
        assert_eq!(project_arg(&args(&["app", "/tmp/a.PIDPROJ"])), Some(PathBuf::from("/tmp/a.PIDPROJ")));
        assert_eq!(project_arg(&args(&["app", "starsi.json"])), Some(PathBuf::from("starsi.json")));
    }

    #[test]
    fn ignores_other_arguments() {
        assert_eq!(project_arg(&args(&["a.pidproj"])), None, "the first item is the program, not a file");
        assert_eq!(project_arg(&args(&["app"])), None);
        assert_eq!(project_arg(&args(&["app", "data.csv", "--smoke", "-x.pidproj", "pidproj"])), None);
        assert_eq!(project_arg(&args(&[])), None);
    }

    #[test]
    fn delivers_a_file_to_a_local_server() {
        use std::io::{Read, Write};
        let dir = std::env::temp_dir().join(format!("pidtools-open-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let f = dir.join("a.pidproj");
        std::fs::write(&f, b"{\"version\":2}").unwrap();
        let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = l.local_addr().unwrap().port();
        let h = std::thread::spawn(move || {
            let (mut c, _) = l.accept().unwrap();
            let mut req = String::new();
            let mut buf = [0u8; 1024];
            while !req.ends_with('}') {
                let n = c.read(&mut buf).unwrap();
                req.push_str(&String::from_utf8_lossy(&buf[..n]));
            }
            c.write_all(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n").unwrap();
            req
        });
        deliver(port, "tok", &f).unwrap();
        let req = h.join().unwrap();
        assert!(req.starts_with("PUT /pending-open HTTP/1.1") && req.contains("X-PID-Token: tok"));
        assert!(req.ends_with("{\"version\":2}"));
        assert!(deliver(port, "tok", &dir.join("missing.pidproj")).is_err());
        std::fs::remove_dir_all(&dir).ok();
    }
}
