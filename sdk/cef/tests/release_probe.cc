// SPDX-License-Identifier: Apache-2.0
// Built with PHONESIMULATOR_CEF_BRIDGE=1 and =0 by `make sdk-cef-release-check`: the second must hold no bridge at all.
#include "phonesimulator_cef/bridge_js.h"
#include "phonesimulator_cef/core.h"

#include <cstdio>

int main(int argc, char**) {
#if defined(PHONESIMULATOR_CEF_BRIDGE) && PHONESIMULATOR_CEF_BRIDGE
  phonesimulator_cef::Server server;
  std::string error;
  // Never started: the probe only keeps the bridge's code and strings in the binary.
  if (argc > 99) server.Start({}, nullptr, &error);
  std::puts(phonesimulator_cef::kBridgeScript + argc - 1);
  std::puts(phonesimulator_cef::ListingFolder("").c_str());
  phonesimulator_cef::Request request;
  phonesimulator_cef::Refusal refusal;
  phonesimulator_cef::Admit("POST /v1/input HTTP/1.1", "", 1, "s", {}, &request, &refusal);
  std::puts("GET /v1/hierarchy");
#else
  (void)argc;
  std::puts("no bridge");
#endif
  return 0;
}
