# LawHub – notes for Claude Code

Django 6 project. Laws are versioned in git, tagged per provision, and users
follow tags; their own AI can connect over MCP. See README.md for the model.

## Commands
- Tests: `python manage.py test` (Django test runner, not pytest)
- Import beta data: `python manage.py import_nalegalu --seed pl_driving --nalegalu <path to nalegalu checkout>`
- Run site + MCP: `uvicorn config.asgi:application --reload` (`runserver` serves the site but not `/mcp`)

## Layout
- `laws/domain/units.py`: framework-free `Unit` tree; every source parses into it. Keep Django out of it.
- `laws/sources/`: one module per source (`nalegalu.py` now, Sejm ELI API next).
- `laws/services.py`: import pipeline (git commit, DB rows, rule tags, change report).
- `tags/rules/pl_driving.yaml`: tag tree, regex rules and questionnaire; questions are YAML, not code.
- `connect/`: MCP server (`mcp_server.py`, MCP Python SDK v2: `MCPServer`, not `FastMCP`) and OAuth glue
  for MCP clients (RFC 8414 metadata, RFC 7591 registration) on top of django-oauth-toolkit.
- `config/asgi.py` routes `/mcp` and `/.well-known/oauth-protected-resource*` to the MCP app, the rest to Django.

## Conventions
- Provision addresses (`art_81/par_6`) must stay stable across versions; tags and subscriptions hang off them.
- UI text is Polish; code, comments and commits are English.
- MCP tools call the ORM through `sync_to_async`; tests call the sync `_impl` functions directly
  (sync_to_async's second connection can't see a TestCase transaction on SQLite).
