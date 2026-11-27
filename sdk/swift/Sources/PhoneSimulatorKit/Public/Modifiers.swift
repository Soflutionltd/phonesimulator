// SPDX-License-Identifier: Apache-2.0
import SwiftUI

extension View {
    /// Names this view for PhoneSimulator, as a person would call it: an icon button's "Delete", a card's "Weekly promo".
    public func phonesimulator(_ name: String) -> some View {
        phonesimulator(kind: nil, name: name)
    }

    /// Says what this view is for PhoneSimulator: its kind, its name and an identifier to find it by. Anything left nil is
    /// worked out as for any other view. Outside a Debug build on the iOS Simulator this changes nothing.
    public func phonesimulator(
        kind: PhoneSimulator.Kind? = nil, name: String? = nil, identifier: String? = nil
    ) -> some View {
        #if DEBUG && (targetEnvironment(simulator) || os(macOS))
            return background(TagAnchor(tag: Tag(kind: kind, name: name, identifier: identifier)))
        #else
            return self
        #endif
    }
}
