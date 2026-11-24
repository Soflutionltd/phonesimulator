// SPDX-License-Identifier: Apache-2.0
// Built with SIMTRAIL_CEF_BRIDGE=1 and =0 by `make sdk-cef-release-check`: the second must hold no bridge at all.
#include "simtrail_cef/bridge_js.h"
#include "simtrail_cef/core.h"

#include <cstdio>

int main(int argc, char**) {
#if defined(SIMTRAIL_CEF_BRIDGE) && SIMTRAIL_CEF_BRIDGE
  simtrail_cef::Server server;
  std::string error;
  // Never started: the probe only keeps the bridge's code and strings in the binary.
  if (argc > 99) server.Start({}, nullptr, &error);
  std::puts(simtrail_cef::kBridgeScript + argc - 1);
  std::puts(simtrail_cef::ListingFolder("").c_str());
  simtrail_cef::Request request;
  simtrail_cef::Refusal refusal;
  simtrail_cef::Admit("POST /v1/input HTTP/1.1", "", 1, "s", {}, &request, &refusal);
  std::puts("GET /v1/hierarchy");
#else
  (void)argc;
  std::puts("no bridge");
#endif
  return 0;
}
