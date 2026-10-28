//! Nejmenší HTTP/1.1 klient pro `--smoke` (jen 127.0.0.1, bez závislostí): jeden požadavek, `Connection: close`.
use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;

pub struct Response {
    pub status: u16,
    pub body: String,
}

pub fn request(port: u16, method: &str, path: &str, token: Option<&str>) -> Result<Response, String> {
    let mut s = TcpStream::connect(("127.0.0.1", port)).map_err(|e| format!("connect: {e}"))?;
    let t = Some(Duration::from_secs(30));
    s.set_read_timeout(t).and_then(|_| s.set_write_timeout(t)).map_err(|e| e.to_string())?;
    let auth = token.map(|t| format!("X-PID-Token: {t}\r\n")).unwrap_or_default();
    let req = format!("{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n{auth}Content-Length: 0\r\nConnection: close\r\n\r\n");
    s.write_all(req.as_bytes()).map_err(|e| format!("write: {e}"))?;
    let mut raw = Vec::new();
    s.read_to_end(&mut raw).map_err(|e| format!("read: {e}"))?;
    parse(&String::from_utf8_lossy(&raw))
}

pub fn parse(raw: &str) -> Result<Response, String> {
    let (head, body) = raw.split_once("\r\n\r\n").ok_or("malformed response")?;
    let status = head
        .lines()
        .next()
        .and_then(|l| l.split_whitespace().nth(1))
        .and_then(|c| c.parse().ok())
        .ok_or("malformed status line")?;
    Ok(Response { status, body: body.to_string() })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_response() {
        let r = parse("HTTP/1.1 200 OK\r\ncontent-length: 2\r\n\r\n{}").unwrap();
        assert_eq!((r.status, r.body.as_str()), (200, "{}"));
        assert!(parse("garbage").is_err());
    }

    #[test]
    fn talks_to_a_local_server() {
        let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = l.local_addr().unwrap().port();
        let h = std::thread::spawn(move || {
            let (mut c, _) = l.accept().unwrap();
            let mut buf = [0u8; 1024];
            let n = c.read(&mut buf).unwrap();
            let req = String::from_utf8_lossy(&buf[..n]).to_string();
            c.write_all(b"HTTP/1.1 201 Created\r\nContent-Length: 2\r\n\r\nok").unwrap();
            req
        });
        let r = request(port, "POST", "/workspaces", Some("tok")).unwrap();
        assert_eq!((r.status, r.body.as_str()), (201, "ok"));
        let req = h.join().unwrap();
        assert!(req.starts_with("POST /workspaces HTTP/1.1") && req.contains("X-PID-Token: tok"));
    }
}
