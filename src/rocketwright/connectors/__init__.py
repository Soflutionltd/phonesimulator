# SPDX-License-Identifier: Apache-2.0
"""How Rocketwright reaches a device: connectors (`base`), chosen by what they can do here (`registry`).

Built in: `native` -- Rocketwright's own helper -- and `idb` -- idb_companion -- each for the whole screen, touches,
keys and the accessibility tree; `simctl`, which needs only Xcode and can show the screen but not touch it; and
`mcpbridge`, which reads the screen through Xcode 27. Others are installed as packages that register in the
``rocketwright.connectors`` entry-point group (`docs/contributing/connector-guide.md`).
"""
