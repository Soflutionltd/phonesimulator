// swift-tools-version:6.0
// SPDX-License-Identifier: Apache-2.0
//
// RocketwrightKit: Rocketwright's optional debug SDK. An app under development links it, calls `Rocketwright.start()`, and
// Rocketwright reads the app's own UIKit and SwiftUI view hierarchy -- so a screen whose controls have no accessibility
// labels still reads well. It does nothing outside a Debug build on the iOS Simulator. See docs/app-sdk.md.
//
// This manifest is at the top of the repository because SwiftPM needs it there for a package added by URL. Rocketwright's
// native helper is a separate package in helper/.

import PackageDescription

let package = Package(
    name: "Rocketwright",
    platforms: [.iOS(.v16), .macOS(.v14)],
    products: [
        .library(name: "RocketwrightKit", targets: ["RocketwrightKit"])
    ],
    targets: [
        .target(name: "RocketwrightKit", path: "sdk/swift/Sources/RocketwrightKit"),
        .testTarget(
            name: "RocketwrightKitTests",
            dependencies: ["RocketwrightKit"],
            path: "sdk/swift/Tests/RocketwrightKitTests"
        ),
    ]
)
