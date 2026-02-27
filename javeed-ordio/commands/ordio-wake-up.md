---
description: Wake up the MCP server (handles Render free-tier cold start)
allowed-tools: []
argument-hint:
---

# Wake Up MCP Server

The javeed-ordio MCP server runs on Render free tier and spins down after 15 minutes of inactivity. The first call after idle takes ~30 seconds while the container starts.

## Instructions

1. Tell the user: "Waking up the MCP server -- this can take up to 30 seconds on first use."
2. Call `list_profiles()` as a lightweight ping.
3. If the call succeeds, tell the user: "Server is ready." and suggest a next command (e.g. `/ordio-weekly` or `/ordio-plan`).
4. If the call fails or times out, tell the user: "The server is still starting. Please wait a moment and try again."
