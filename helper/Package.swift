// swift-tools-version:6.0
// SPDX-License-Identifier: Apache-2.0
//
// PhoneSimulator's native helper: the screen, input and element tree of one booted simulator, served to PhoneSimulator on a unix
// socket -- without idb_companion.
//
// `HelperCore` is everything that can be decided without a simulator: the wire protocol, what a screenshot or a stream
// is cut to, how input maps onto each HID transport, and how an accessibility tree becomes PhoneSimulator's document. It is
// unit-tested to the per-file coverage bar. `HelperPlatform` is the thin layer that reaches Apple's private simulator
// frameworks through the Objective-C runtime; it is exercised against real simulators by PhoneSimulator's live suite.

import PackageDescription

let package = Package(
    name: "PhoneSimulatorHelper",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "phonesimulator-helper", targets: ["phonesimulator-helper"]),
    ],
    targets: [
        .target(name: "HelperCore"),
        .target(name: "ObjCGuard"),
        .target(
            name: "HelperPlatform",
            dependencies: ["HelperCore", "ObjCGuard"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .executableTarget(
            name: "phonesimulator-helper",
            dependencies: ["HelperCore", "HelperPlatform"],
            swiftSettings: [.swiftLanguageMode(.v5)],
            // The Info.plist macOS reads to ask for the Camera, which reading a cabled device's screen needs, embedded
            // in the program itself.
            linkerSettings: [
                .unsafeFlags([
                    "-Xlinker", "-sectcreate", "-Xlinker", "__TEXT", "-Xlinker", "__info_plist",
                    "-Xlinker", "\(Context.packageDirectory)/Support/Info.plist",
                ]),
            ]
        ),
        .testTarget(name: "HelperCoreTests", dependencies: ["HelperCore"]),
    ]
)
