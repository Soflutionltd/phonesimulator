// SPDX-License-Identifier: Apache-2.0
fn main() {
    println!("{}", rocketwright_web::script());
    let _server = rocketwright_web::Server::start(
        rocketwright_web::Options {
            bundle_id: "dev.rocketwright.Probe".into(),
            name: "Probe".into(),
            home: std::env::temp_dir(),
            windows: vec![1],
        },
        |_| Err("no registered webview".into()),
    );
}
