#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Regenerate the vendored idb_companion client in src/rocketwright/connectors/idb/proto/.
#
# The proto is idb's own (MIT), from the release the Homebrew companion was built from:
#   curl -fsSL -o src/rocketwright/connectors/idb/proto/idb.proto \
#     https://raw.githubusercontent.com/facebook/idb/v<version>/proto/idb.proto
# Then run this from the repository root. grpcio-tools is a development dependency used only here; Rocketwright talks
# to the companion through grpclib.
set -eu
cd "$(dirname "$0")/.."
uv run python -m grpc_tools.protoc -I src \
  --python_out=src --grpclib_python_out=src \
  src/rocketwright/connectors/idb/proto/idb.proto
echo "regenerated src/rocketwright/connectors/idb/proto/idb_pb2.py and idb_grpc.py"
