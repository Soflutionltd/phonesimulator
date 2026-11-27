// swift-tools-version:6.0
// SPDX-License-Identifier: Apache-2.0
//
// PhoneSimulatorKit: PhoneSimulator's optional debug SDK. An app under development links it, calls `PhoneSimulator.start()`, and
// PhoneSimulator reads the app's own UIKit and SwiftUI view hierarchy -- so a screen whose controls have no accessibility
// labels still reads well. It does nothing outside a Debug build on the iOS Simulator. See docs/app-sdk.md.
//
// This manifest is at the top of the repository because SwiftPM needs it there for a package added by URL. PhoneSimulator's
// native helper is a separate package in helper/.

import PackageDescription

let package = Package(
    name: "PhoneSimulator",
    platforms: [.iOS(.v16), .macOS(.v14)],
    products: [
        .library(name: "PhoneSimulatorKit", targets: ["PhoneSimulatorKit"])
    ],
    targets: [
        .target(name: "PhoneSimulatorKit", path: "sdk/swift/Sources/PhoneSimulatorKit"),
        .testTarget(
            name: "PhoneSimulatorKitTests",
            dependencies: ["PhoneSimulatorKit"],
            path: "sdk/swift/Tests/PhoneSimulatorKitTests"
        ),
    ]
)
