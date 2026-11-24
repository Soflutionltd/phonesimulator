// swift-tools-version:6.0
// SPDX-License-Identifier: Apache-2.0
//
// SimtrailKit: Simtrail's optional debug SDK. An app under development links it, calls `Simtrail.start()`, and
// Simtrail reads the app's own UIKit and SwiftUI view hierarchy -- so a screen whose controls have no accessibility
// labels still reads well. It does nothing outside a Debug build on the iOS Simulator. See docs/app-sdk.md.
//
// This manifest is at the top of the repository because SwiftPM needs it there for a package added by URL. Simtrail's
// native helper is a separate package in helper/.

import PackageDescription

let package = Package(
    name: "Simtrail",
    platforms: [.iOS(.v16), .macOS(.v14)],
    products: [
        .library(name: "SimtrailKit", targets: ["SimtrailKit"])
    ],
    targets: [
        .target(name: "SimtrailKit", path: "sdk/swift/Sources/SimtrailKit"),
        .testTarget(
            name: "SimtrailKitTests",
            dependencies: ["SimtrailKit"],
            path: "sdk/swift/Tests/SimtrailKitTests"
        ),
    ]
)
