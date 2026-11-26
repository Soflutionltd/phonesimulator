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
