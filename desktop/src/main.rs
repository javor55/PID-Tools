// Na Windows GUI program bez konzole (sidecar si okno konzole nezakládá, viz sidecar::no_console).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.iter().any(|a| a == "--smoke") {
        let log = args.iter().position(|a| a == "--smoke-log").and_then(|i| args.get(i + 1));
        let open = args.iter().position(|a| a == "--open").and_then(|i| args.get(i + 1));
        std::process::exit(pidtools_desktop_lib::smoke(log.map(String::as_str), open.map(String::as_str)));
    }
    pidtools_desktop_lib::run();
}
