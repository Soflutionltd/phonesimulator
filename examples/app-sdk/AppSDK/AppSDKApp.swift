// SPDX-License-Identifier: Apache-2.0
import PhoneSimulatorKit
import SwiftUI

/// A small app with the screens PhoneSimulator reads badly from accessibility alone -- icon-only buttons, a card with a
/// tap gesture, an unlabeled switch, a hand-drawn control -- and PhoneSimulatorKit started, so they read well.
@main
struct AppSDKApp: App {
    init() {
        PhoneSimulator.register(describer: RatingControlDescriber())
        // SwiftUI's debug data is opt-in and read on iOS 26 only; launch with PHONESIMULATOR_SWIFTUI_DEBUG_DATA=1 to try it.
        let debugData = ProcessInfo.processInfo.environment["PHONESIMULATOR_SWIFTUI_DEBUG_DATA"] == "1"
        PhoneSimulator.start(PhoneSimulator.Options(swiftUIDebugData: debugData))
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
