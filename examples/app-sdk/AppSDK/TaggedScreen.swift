// SPDX-License-Identifier: Apache-2.0
import RocketwrightKit
import SwiftUI

/// The same views, named for Rocketwright with `.rocketwright(...)`: a Debug build on a simulator reads the names, and
/// anything else ignores them.
struct TaggedScreen: View {
    @State private var notifications = false
    @State private var taps = 0

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    HStack(spacing: 28) {
                        Button {
                            taps += 1
                        } label: {
                            Image(systemName: "gearshape")
                        }
                        .rocketwright("Settings")
                        Button {
                        } label: {
                            Image(systemName: "trash")
                        }
                        .rocketwright(kind: .button, name: "Delete list", identifier: "delete-list")
                    }
                    .font(.title2)
                    VStack(spacing: 6) {
                        Image(systemName: "sun.max").font(.largeTitle)
                        Text("Daily mix")
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.mint.opacity(0.25), in: RoundedRectangle(cornerRadius: 12))
                    .onTapGesture { taps += 1 }
                    .rocketwright(kind: .button, name: "Play daily mix")
                    Toggle("", isOn: $notifications).labelsHidden()
                        .rocketwright(kind: .switch, name: "Notifications")
                }
                .padding()
            }
            .navigationTitle("Tagged")
        }
    }
}
