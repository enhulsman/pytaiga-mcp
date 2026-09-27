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

## Status 2026-09-22

Implemented on branch `feat/per-user-identity` (tests first, 102 unit tests pass):

- `src/session.py`: `resolve_client(session_id)` is the single entry point for tools. stdio unchanged; OAuth mode resolves the caller's subject through the bridge, refuses unlinked subjects with `NotLinkedError` (carries the link URL), rejects an explicit `session_id`, and turns a Taiga 401 into auto-unlink plus the link URL (403 untouched).
- Linking mints a Taiga application token (`src/auth/application_token.py`) for Application `c733a0f2-b7c3-4b48-ba61-1f740547f6f9` ("Taiga MCP", created 2026-09-22 on the VPS). The credential store keeps the token and its Taiga-side id; unlink revokes it in Taiga (best effort) and forgets it locally.
- All core tool modules call `resolve_client`; the seven `update_*` tools share `execute_taiga_operation`.

Deploy: add `TAIGA_APPLICATION_ID` to the env on rp5, pull, restart `taiga-mcp`, then Ezra links his subject to `ezra-agent` at https://taiga-mcp.hulsman.dev/link-account (every tool refuses until then). Bas, Peter and Emiel link their own accounts the same way once they have Auth0 logins.

## Deployed 2026-09-26

Commit `65cf9e8` runs on rp5 (`taiga-mcp.service`, active). Verified through the claude.ai connector: a stale Bearer-format link was auto-removed on Taiga 401, the unlinked state returned the link URL, Ezra re-linked to `ezra-agent` via `/link-account` (application token minted), and `list_projects` then returned exactly `ezra-agent`'s two projects.

Deploy lesson: on rp5 the fork is the git remote named `fork` and upstream talhaorak is `origin`; production had been running branch `feature/extended-tools`. A plain `git pull` on master fetched upstream v2.0.1 (stdio-only) and the service exited at once (502). rp5's master now tracks `fork/master`, fetched over HTTPS because rp5's GitHub key is passphrase-protected and cannot be used non-interactively.

Open: Auth0 logins for Bas, Peter and Emiel; confirm sign-ups disabled in Auth0; optionally rename the remotes on rp5 to match WSL.

## Follow-ups (2026-09-27)

- Auth0 logins for Bas, Peter and Emiel were created on 2026-09-27; each still has to link once at `/link-account`.
- `search` and `get_{user_story,task,issue,epic}_by_ref` shipped in `37c8137` with opt-in live checks (`TAIGA_LIVE=1`, `tests/test_live_search.py`).
- pyTaigaClient bug, deliberately not fixed here: the `Tasks` resource (`list`, `get_by_ref`) passes `query_params=` to `TaigaClient.get`, which only accepts `params=`, so every call raises `TypeError` before a request is sent. The story/issue/epic helpers work but disagree on the slug parameter name (`project_slug` vs `project__slug`). Our tools call the raw endpoints instead. Fixing it means a pull request against talhaorak/pyTaigaClient (dormant since 2026-03) or a fork; Ezra declined both on 2026-09-27. Keep the raw-endpoint pattern until that changes.
