// SPDX-License-Identifier: Apache-2.0
fn main() {
    println!("{}", phonesimulator_web::script());
    let _server = phonesimulator_web::Server::start(
        phonesimulator_web::Options {
            bundle_id: "dev.phonesimulator.Probe".into(),
            name: "Probe".into(),
            home: std::env::temp_dir(),
            windows: vec![1],
        },
        |_| Err("no registered webview".into()),
    );
}
