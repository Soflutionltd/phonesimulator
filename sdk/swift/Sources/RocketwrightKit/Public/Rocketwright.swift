// SPDX-License-Identifier: Apache-2.0
import Foundation

/// Rocketwright's debug SDK: while it runs, Rocketwright reads this app's own view hierarchy.
///
/// Call `Rocketwright.start()` once, early -- in your `App`'s `init` or `application(_:didFinishLaunchingWithOptions:)`.
/// In a Debug build on the iOS Simulator or native macOS the app answers Rocketwright on authenticated `127.0.0.1`.
/// Release builds and unsupported platforms compile out the SDK's workings. Previews and extensions never start
/// the server. Catalyst and Designed for iPad apps use Rocketwright's per-process Accessibility adapter.
public enum Rocketwright {
    /// The version of Rocketwright this SDK came with.
    public static let sdkVersion = "3.12.0"

    /// Posted on the main thread when a native macOS Debug app starts answering Rocketwright -- `userInfo["wanted"]` is
    /// `true` -- and when it stops (`false`). An app that embeds a web engine which builds its accessibility tree only
    /// when asked -- CEF, a Chromium host -- turns it on here, so Rocketwright reads the page as well as the app:
    ///
    ///     NotificationCenter.default.addObserver(forName: Rocketwright.accessibilityWanted, object: nil, queue: .main) {
    ///         if $0.userInfo?["wanted"] as? Bool == true { browser.enableAccessibility() }
    ///     }
    public static let accessibilityWanted = Notification.Name("RocketwrightAccessibilityWanted")

    /// Starts answering Rocketwright. Calling it again while it runs changes nothing; call `stop()` first to use other
    /// options.
    @MainActor
    public static func start(_ options: Options = Options()) {
        #if DEBUG && targetEnvironment(simulator)
            Runtime.shared.start(options)
        #elseif DEBUG && os(macOS)
            MacRuntime.shared.start(options)
        #endif
    }

    /// Stops answering Rocketwright and takes back what told Rocketwright where to ask.
    @MainActor
    public static func stop() {
        #if DEBUG && targetEnvironment(simulator)
            Runtime.shared.stop()
        #elseif DEBUG && os(macOS)
            MacRuntime.shared.stop()
        #endif
    }

    /// Whether the app is answering Rocketwright now.
    @MainActor
    public static var isRunning: Bool {
        #if DEBUG && targetEnvironment(simulator)
            return Runtime.shared.isRunning
        #elseif DEBUG && os(macOS)
            return MacRuntime.shared.isRunning
        #else
            return false
        #endif
    }
}
