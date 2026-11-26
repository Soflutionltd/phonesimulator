// SPDX-License-Identifier: Apache-2.0
import RocketwrightKit
import SwiftUI

/// A small app with the screens Rocketwright reads badly from accessibility alone -- icon-only buttons, a card with a
/// tap gesture, an unlabeled switch, a hand-drawn control -- and RocketwrightKit started, so they read well.
@main
struct AppSDKApp: App {
    init() {
        Rocketwright.register(describer: RatingControlDescriber())
        // SwiftUI's debug data is opt-in and read on iOS 26 only; launch with ROCKETWRIGHT_SWIFTUI_DEBUG_DATA=1 to try it.
        let debugData = ProcessInfo.processInfo.environment["ROCKETWRIGHT_SWIFTUI_DEBUG_DATA"] == "1"
        Rocketwright.start(Rocketwright.Options(swiftUIDebugData: debugData))
    }

    var body: some Scene {
        WindowGroup {
            TabView {
                SwiftUIScreen()
                    .tabItem { Label("SwiftUI", systemImage: "swift") }
                TaggedScreen()
                    .tabItem { Label("Tagged", systemImage: "tag") }
                UIKitScreen()
                    .ignoresSafeArea()
                    .tabItem { Label("UIKit", systemImage: "square.stack.3d.up") }
            }
        }
    }
}
