# Playwright MCP Server

This workspace hosts the Playwright MCP server for browser automation and E2E testing assistance.

## Install

Node modules are already vendored for local development. If you need to (re)install:

```bash
cd tools/mcp
npm install
```

## Run

From repo root:

```bash
cd tools/mcp
npm run mcp:playwright -- --help
# Start with defaults
npm run mcp:playwright
```

Common flags:
- `--browser <chrome|firefox|webkit|msedge>`
- `--device "iPhone 15"`
- `--headless`
- `--output-dir ./out --save-session --save-trace --save-video=800x600`

## Environment

These can help with CI and reproducibility:
- `PLAYWRIGHT_BROWSERS_PATH=0` use local temp cache for browsers
- `PWDEBUG=0` disable headed debug unless needed

## Codex MCP config (example)

Add a server in Codex settings:
- name: `playwright`
- command: `npm`
- args: `["run", "mcp:playwright", "--silent"]`
- env (optional):
  - `PLAYWRIGHT_BROWSERS_PATH=0`
  - `PWDEBUG=0`

## Notes
- Keep E2E tests in `frontend/tests/e2e/` as source of truth.
- This MCP server is for interactive automation and debugging; it does not replace Playwright CI runs.
