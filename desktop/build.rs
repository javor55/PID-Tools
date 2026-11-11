// Tauri vyžaduje, aby zdroj `bundle.resources` existoval i pro `cargo check` / `cargo test`. Sidecar se sestavuje
// zvlášť (python tools/build_sidecar.py -> ../dist/pidtools-api); chybí-li, vznikne prázdná složka a build upozorní.
fn main() {
    let dir = std::path::Path::new("../dist/pidtools-api");
    if !dir.exists() {
        std::fs::create_dir_all(dir).expect("cannot create ../dist/pidtools-api");
        println!("cargo:warning=sidecar missing (run: python tools/build_sidecar.py); bundling an empty folder");
    }
    println!("cargo:rerun-if-changed=../dist/pidtools-api");
    tauri_build::build();
}
