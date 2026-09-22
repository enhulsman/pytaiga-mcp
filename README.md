<p align="center">
<picture>
  <img src="https://taiga.io/media/images/favicon.width-44.png">
</picture>
</p>

# Taiga MCP Bridge


[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/talhaorak/pytaiga-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/talhaorak/pytaiga-mcp/actions/workflows/ci.yml)

## Overview

The Taiga MCP Bridge is a powerful integration layer that connects [Taiga](https://taiga.io/) project management platform with the Model Context Protocol (MCP), enabling AI tools and workflows to interact seamlessly with Taiga's resources.

This bridge provides a comprehensive set of tools and resources for AI agents to:
- Create and manage projects, epics, user stories, tasks, and issues in Taiga
- Track sprints and milestones
- Assign and update work items
- Query detailed information about project artifacts
- Manage project members and permissions

By using the MCP standard, this bridge allows AI systems to maintain contextual awareness about project state and perform complex project management tasks programmatically.

## Features

### Comprehensive Resource Support

The bridge supports the following Taiga resources with complete CRUD operations:

- **Projects**: Create, update, and manage project settings and metadata
- **Epics**: Manage large features that span multiple sprints
- **User Stories**: Handle detailed requirements and acceptance criteria
- **Tasks**: Track smaller units of work within user stories
- **Issues**: Manage bugs, questions, and enhancement requests
- **Sprints (Milestones)**: Plan and track work in time-boxed intervals

### Security & Configuration

- **Secure Credentials**: Environment variable authentication with credential protection - passwords never appear in logs or error messages
- **Auto-Authentication**: Configure `TAIGA_USERNAME` and `TAIGA_PASSWORD` environment variables for seamless startup without manual login
- **Input Validation**: Allowlist-based parameter validation prevents unexpected data from reaching the Taiga API

### Response Filtering

All tools support a `verbosity` parameter to control response size, reducing AI context usage:

| Level | Description | Use Case |
|-------|-------------|----------|
| `minimal` | Core fields only (id, ref, subject, status, project) | Listing many items |
| `standard` | Common fields including version for updates (default) | Normal operations |
| `full` | Complete API response | Debugging, full details |

Example:
```python
# Get minimal response for efficient context usage
stories = client.call_tool("list_user_stories", {
    "project_id": 123,
    "verbosity": "minimal"
})
# Returns: [{"id": 1, "ref": 42, "subject": "...", "status": 1, "project": 123}, ...]
```

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for fast, reliable Python package management.

### Prerequisites

- Python 3.10 or higher
- uv package manager

### Basic Installation

```bash
# Clone the repository
git clone https://github.com/your-org/pyTaigaMCP.git
cd pyTaigaMCP

# Install dependencies
./install.sh
```

### Development Installation

For development (includes testing and code quality tools):

```bash
./install.sh --dev
```

### Manual Installation

If you prefer to install manually:

```bash
# Production dependencies only
uv pip install -e .

# With development dependencies
uv pip install -e ".[dev]"
```

## Configuration

The bridge can be configured through environment variables or a `.env` file:

| Environment Variable | Description | Default |
| --- | --- | --- |
| `TAIGA_API_URL` | Base URL for the Taiga API | http://localhost:9000 |
| `TAIGA_USERNAME` | Taiga username for auto-authentication | (none) |
| `TAIGA_PASSWORD` | Taiga password for auto-authentication | (none) |
| `TAIGA_TRANSPORT` | Transport mode (stdio or sse) | stdio |
| `LOG_LEVEL` | Logging level | INFO |

Create a `.env` file in the project root to set these values:

```
TAIGA_API_URL=https://api.taiga.io/api/v1/
TAIGA_USERNAME=your_username
TAIGA_PASSWORD=your_password
TAIGA_TRANSPORT=stdio
LOG_LEVEL=INFO
```

**Security Note**: Credentials are protected and will never appear in logs, error messages, or stack traces. When `TAIGA_USERNAME` and `TAIGA_PASSWORD` are configured, the server auto-authenticates on startup - no manual login required.

## Usage

### With stdio mode

Paste the following json in your Claude App's or Cursor's mcp settings section.

**Recommended**: Set credentials via environment variables in your shell profile rather than in config files to avoid exposing them in plaintext.

```json
{
    "mcpServers": {
        "taigaApi": {
            "command": "uv",
            "args": [
                "--directory",
                "<path to local pyTaigaMCP folder>",
                "run",
                "src/server.py"
            ],
            "env": {
                "TAIGA_TRANSPORT": "<stdio|sse>",                
                "TAIGA_API_URL": "<Taiga API Url (ex: http://localhost:9000)",
                "TAIGA_USERNAME": "<taiga username>",
                "TAIGA_PASSWORD": "<taiga password>"
            }
        }
}
```

### Running the Bridge

Start the MCP server with:

```bash
# Default stdio transport
./run.sh

# For SSE transport
./run.sh --sse
```

Or manually:

```bash
# For stdio transport (default)
uv run python src/server.py

# For SSE transport
uv run python src/server.py --sse
```

### Transport Modes

The server supports two transport modes:

1. **stdio (Standard Input/Output)** - Default mode for terminal-based clients such as Claude Code or Codex running the server as a subprocess
2. **streamable-http** - Remote HTTP transport for claude.ai connectors and other remote MCP clients, protected by OAuth 2.1 (see below)

You can set the transport mode in several ways:
- Using the `--streamable-http` flag with server.py (default is stdio)
- Setting the `TAIGA_TRANSPORT` environment variable
- Adding `TAIGA_TRANSPORT=streamable-http` to your `.env` file

### Authentication Flow

#### Auto-Authentication (Recommended)

If `TAIGA_USERNAME` and `TAIGA_PASSWORD` environment variables are set, the server automatically authenticates on startup. You can omit `session_id` from tool calls to use the default session:

```python
# No login needed - uses auto-authenticated default session
projects = client.call_tool("list_projects", {})
stories = client.call_tool("list_user_stories", {"project_id": 123})
new_story = client.call_tool("create_user_story", {
    "project_id": 123,
    "subject": "New feature request"
})
```

#### OAuth Mode (streamable-http): Per-User Taiga Identity

In streamable-http mode with `OAUTH_ISSUER_URL` and `OAUTH_AUDIENCE` set, every MCP request must carry a bearer token issued by the configured OAuth provider (Auth0 in the reference deployment). The server publishes `/.well-known/oauth-protected-resource`, so MCP clients that support OAuth discover the provider on their own.

**Who acts in Taiga.** Each OAuth identity acts in Taiga as the Taiga account it has linked. Tool calls resolve their client through `resolve_client()` in `src/session.py`: the OAuth subject is looked up in the encrypted credential store and the stored Taiga token is used. Changes and comments are attributed to that Taiga user.

**Unlinked identities are refused.** An OAuth identity without a linked Taiga account gets an error carrying the link URL from every Taiga tool, including read-only ones. There is no fallback to a shared account, so nobody sees more than their own Taiga permissions allow. The `taiga_link_status` tool reports the same URL. In OAuth mode the `session_id` parameter is rejected, so the startup session built from `TAIGA_USERNAME`/`TAIGA_PASSWORD` cannot be selected by hand; those variables are only needed for stdio mode.

**Linking.** Visiting `<public URL>/link-account` runs the browser flow: log in at the OAuth provider, then enter Taiga credentials once in a form served by this server. The server logs in to Taiga with them, authorizes the Taiga external Application named in `TAIGA_APPLICATION_ID`, and stores only the resulting application token, encrypted with `TAIGA_CREDENTIAL_ENCRYPTION_KEY`. Application tokens do not expire and identify the user, so no re-linking is needed. `taiga_unlink_account` revokes the token in Taiga and forgets it; a Taiga 401 on a stored token also removes the link automatically. Create the Application once in Taiga's Django admin (External apps) with `next_url` `<public URL>/link-account/done`, and put its id in the environment.

**A shared agent identity** is still possible: link the OAuth identity that agents use to a dedicated Taiga service account through the same form.

OAuth-mode environment variables:

| Environment Variable | Description | Default |
| --- | --- | --- |
| `OAUTH_ISSUER_URL` | OAuth issuer, e.g. `https://<tenant>.eu.auth0.com/` | (none) |
| `OAUTH_AUDIENCE` | API identifier, also the server's public URL | (none) |
| `OAUTH_REQUIRED_SCOPES` | Comma-separated scopes a token must carry | (none) |
| `JWKS_CACHE_TTL` | Seconds to cache the provider's signing keys | 600 |
| `TAIGA_APPLICATION_ID` | Id of the Taiga external Application used to mint application tokens | (none) |
| `TAIGA_CREDENTIAL_ENCRYPTION_KEY` | Fernet key for the credential store | (none) |
| `TAIGA_CREDENTIAL_STORE_PATH` | SQLite file holding the encrypted tokens | `~/.taiga-mcp/credentials.db` |
| `OAUTH_LINK_CLIENT_ID` | Provider application used by the browser linking flow | (none) |
| `OAUTH_LINK_CLIENT_SECRET` | Its client secret | (none) |
| `LINK_SESSION_TTL` | Lifetime in seconds of the linking flow's session cookie | 600 |

#### OAuth Provider and claude.ai Connector Setup

The reference deployment uses Auth0 (managed, free tier, no operations burden). Keycloak was considered and rejected as too heavy for a homelab (Java, about 512 MB RAM); the MCP SDK's built-in authorization server was rejected as less battle-tested. Provider-side setup:

1. Create an API (resource server) whose identifier is the server's public URL, with scopes `taiga:read` and `taiga:write`.
2. Create a Regular Web Application for claude.ai with callback `https://claude.ai/api/mcp/auth_callback`.
3. Create a second Regular Web Application for the browser linking flow with callback `<public URL>/link-account/callback`; its client id and secret go into `OAUTH_LINK_CLIENT_ID` and `OAUTH_LINK_CLIENT_SECRET`.
4. Add the users who may use the server; keep sign-ups disabled on the connection.

In claude.ai: Organization Settings, Connectors, Add custom connector. URL `<public URL>/mcp`, and under advanced settings the client id and secret of the claude.ai application. Team members then enable the connector per conversation.

References: [Claude custom connectors](https://support.claude.com/en/articles/11175166), [building custom connectors](https://support.claude.com/en/articles/11503834), [MCP authorization spec](https://modelcontextprotocol.io/specification/draft/basic/authorization), [Auth0 for MCP servers](https://auth0.com/ai/docs/mcp/get-started/authorization-for-your-mcp-server).

#### Manual Session Management

For scenarios requiring multiple sessions or explicit control, use the session-based model:

1. **Login**: Authenticate using the `login` tool:
   ```python
   session = client.call_tool("login", {
       "username": "your_taiga_username",
       "password": "your_taiga_password",
       "host": "https://api.taiga.io" # Optional
   })
   # Save the session_id from the response
   session_id = session["session_id"]
   ```

2. **Using Tools and Resources**: Include the `session_id` in every API call:
   ```python
   # For resources, include session_id in the URI
   projects = client.get_resource(f"taiga://projects?session_id={session_id}")
   
   # For project-specific resources
   epics = client.get_resource(f"taiga://projects/123/epics?session_id={session_id}")
   
   # For tools, include session_id as a parameter
   new_project = client.call_tool("create_project", {
       "session_id": session_id,
       "name": "New Project",
       "description": "Description"
   })
   ```

3. **Check Session Status**: You can check if your session is still valid:
   ```python
   status = client.call_tool("session_status", {"session_id": session_id})
   # Returns information about session validity and remaining time
   ```

4. **Logout**: When finished, you can logout to terminate the session:
   ```python
   client.call_tool("logout", {"session_id": session_id})
   ```

### Example: Complete Project Creation Workflow

Here's a complete example of creating a project with epics and user stories:

```python
from mcp.client import Client

# Initialize MCP client
client = Client()

# Authenticate and get session ID
auth_result = client.call_tool("login", {
    "username": "admin",
    "password": "password123",
    "host": "https://taiga.mycompany.com"
})
session_id = auth_result["session_id"]

# Create a new project
project = client.call_tool("create_project", {
    "session_id": session_id,
    "name": "My New Project",
    "description": "A test project created via MCP"
})
project_id = project["id"]

# Create an epic
epic = client.call_tool("create_epic", {
    "session_id": session_id,
    "project_id": project_id,
    "subject": "User Authentication",
    "description": "Implement user authentication features"
})
epic_id = epic["id"]

# Create a user story in the epic
story = client.call_tool("create_user_story", {
    "session_id": session_id,
    "project_id": project_id,
    "subject": "User Login",
    "description": "As a user, I want to log in with my credentials",
    "epic_id": epic_id
})

# Logout when done
client.call_tool("logout", {"session_id": session_id})
```

## Development

### Project Structure

```
pyTaigaMCP/
├── src/
│   ├── server.py          # MCP server implementation with tools
│   ├── taiga_client.py    # Taiga API client wrapper
│   └── config.py          # Configuration settings with Pydantic
├── tests/
│   ├── test_server.py     # Unit tests
│   └── test_integration.py # Integration tests
├── pyproject.toml         # Project configuration and dependencies
├── install.sh             # Installation script
├── run.sh                 # Server execution script
└── README.md              # Project documentation
```

### Testing

Run tests with pytest:

```bash
# Run all tests
pytest

# Run with coverage reporting
pytest --cov=src
```

### Debugging and Inspection

Use the included inspector tool for debugging:

```bash
# Default stdio transport
./inspect.sh

# For SSE transport
./inspect.sh --sse

# For development mode
./inspect.sh --dev
```

## Error Handling

All API operations return standardized error responses in the following format:

```json
{
  "status": "error",
  "error_type": "ExceptionClassName",
  "message": "Detailed error message"
}
```

## Planned Features

The following features are planned for future releases:

- Session expiration and automatic cleanup
- Rate limiting for API calls
- Retry mechanism with exponential backoff
- Connection pooling

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Install development dependencies (`./install.sh --dev`)
4. Make your changes
5. Run tests (`pytest`)
6. Commit your changes (`git commit -m 'Add some amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Taiga](https://www.taiga.io/) for their excellent project management platform
- [Model Context Protocol (MCP)](https://github.com/mcp-foundation/specification) for the standardized AI communication framework
- All contributors who have helped shape this project
