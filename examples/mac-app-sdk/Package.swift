// swift-tools-version:6.0
// SPDX-License-Identifier: Apache-2.0
import PackageDescription

let package = Package(
    name: "MacAppSDK",
    platforms: [.macOS(.v14)],
    dependencies: [.package(name: "Rocketwright", path: "../..")],
    targets: [
        .executableTarget(
            name: "MacAppSDK", dependencies: [.product(name: "RocketwrightKit", package: "Rocketwright")], path: "Sources")
    ]
)
