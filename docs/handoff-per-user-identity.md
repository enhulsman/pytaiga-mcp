# Handoff: per-user Taiga identity in OAuth mode

Continuation prompt for a fresh Claude Code session in this repo. Written 2026-09-14.

## Context

- Repo: enhulsman/pytaiga-mcp is its own project now. Remote `origin` = the fork, `upstream` = talhaorak/pytaiga-mcp (dormant since 2026-03-17, single-file server, no OAuth; borrow ideas from it by re-implementing, never by merging). Work on a new branch off `master`.
- Production: `taiga-mcp.service` on rp5 runs `src/server.py --streamable-http` with Auth0 (issuer https://anamata.eu.auth0.com/, audience https://taiga-mcp.hulsman.dev/, scopes taiga:read/taiga:write, dynamic client registration enabled). Public URL https://taiga-mcp.hulsman.dev/mcp. Deploy = `git pull` + `sudo systemctl restart taiga-mcp` on rp5; Ezra does that step.
- Since 2026-09-14 the server logs in to Taiga as the service account `ezra-agent` ("Ezra's Agent"). That is intentional for Ezra's own agents and stays the identity for unlinked use if we choose so.

## Current behaviour (verified by reading the code)

Every core tool calls `get_session_id()` in `src/session.py` and resolves the `"default"` session built at startup from `TAIGA_USERNAME`/`TAIGA_PASSWORD`. OAuth therefore only gates access; it never chooses the Taiga account. README section "OAuth Mode (streamable-http): Single Service Account" documents this.

The per-user machinery exists but is dead for tool calls:
- `src/auth/link_routes.py`: browser flow `/link-account` -> Auth0 -> HTML form with Taiga credentials -> stores a Taiga token.
- `src/auth/credential_store.py`: encrypted sqlite, one Taiga token per OAuth `sub`.
- `src/auth/session_bridge.py`: `OAuthSessionBridge.get_client(oauth_sub)`, TTL cache, auto-unlink on Taiga 401.
- `src/tools/oauth_tools.py`: `taiga_link_status`, `taiga_unlink_account`.
- No caller of `bridge.get_client` exists outside `src/auth/`.
- Tools are registered in `src/tools/__init__.py`; each module follows `get_session_id -> get_authenticated_client -> execute_taiga_operation`. Seven `delete_*` tools are among them.

## Goal

In OAuth mode, each OAuth identity acts in Taiga as its own linked Taiga user, so Bas and Peter can use the server as themselves while Ezra's agents keep acting as `ezra-agent`.

Decide with Ezra, before code, the fallback for an unlinked identity: (a) act as the service account, or (b) refuse and return the link URL. Ezra's lean: (b) for write tools, (a) for read tools. Argue it first, then agree.

## Constraints

- Tests first. Existing: `tests/test_session_bridge.py`, `tests/test_server.py` (61 unit tests pass via `uv run --extra dev python -m pytest tests/test_server.py tests/test_session_bridge.py tests/test_credential_store.py tests/test_token_verifier.py`). Add coverage for: client resolution per OAuth sub, the unlinked fallback per tool class, stdio mode unchanged.
- No openspec in this repo: outline the approach and get confirmation before writing code.
- Keep the change in the resolution layer: one helper the tools call instead of `get_session_id` + `get_authenticated_client`, so the tool modules change mechanically. Keep the existing auto-unlink on 401.
- Never read `.env` files; env key names are listed in the README.
- Afterwards: update the README section and its "Planned Features" bullet, then the homelab docs via `/docs-update` (devices/pi5.md, taiga-mcp row currently says "per-user linking exists in the code but is not wired in"; devices/vps.md has the `ezra-agent` paragraph).
- Commits through the git-commit-handler agent, no AI attribution, no push unless asked.

## Open questions to raise before building

- Does Auth0 need anything for Bas and Peter (users in the tenant, restrictions on DCR-created clients)?
- Is the link form's Taiga password entry acceptable, or should linking use Taiga application tokens instead?
- Should the `ezra-agent` identity stay the default for Ezra's own OAuth identity, or should Ezra link as himself and keep a separate OAuth identity for agents?

## Decisions taken 2026-09-14 (later session)

- Unlinked fallback: refuse every tool call in OAuth mode and return the link URL. No read/write split. Ezra agreed after hearing the case for the hybrid.
- Ezra's own OAuth subject links to the `ezra-agent` Taiga credentials, so everything under his Auth0 login (agents and Claude.ai) acts as `ezra-agent`. A second Auth0 user for agents remains possible later without code changes.
- Keep the password link form for now. Taiga application tokens are attractive (no expiry, revocable in Taiga, no password through our server) and should be evaluated against the Taiga external-apps API before building the refresh machinery below.
- Close the bypass: in OAuth mode the helper must reject an explicit `session_id`, since `"default"` would otherwise select the service account.
- Measured on rp5 against the production Taiga: `auth_token` expires after 24 h, `refresh` after 192 h (8 days). Consequences:
  - The credential store must keep the refresh token and expiry, and the bridge must refresh before expiry and on 401 before unlinking. `pytaigaclient` has `auth.refresh_token()` but does not auto-refresh.
  - The startup service-account session in `src/server.py` also holds a 24 h token and nothing refreshes it. Production is expected to start returning 401 about a day after each restart. Not yet observed (deployed 2026-09-14). Fix alongside, or first as a hotfix.
- Auth0 MCP server (`npx @auth0/auth0-mcp-server init --client claude-code --read-only`) will be installed by Ezra. It exposes applications, APIs, actions, logs and forms only: no users, connections or tenant settings. Use it to check the link application's callback; use the Auth0 dashboard or `auth0` CLI for Bas and Peter's accounts and the DCR setting.
- Next action waits for Ezra to return with the Auth0 MCP installed.
