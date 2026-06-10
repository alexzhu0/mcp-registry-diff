# mcp-registry-diff

Compare two MCP registry JSON exports and get a clear diff of risky behavior changes.

## Why

MCP server registries and approved-server lists change like dependencies, but teams often review them as raw JSON. This tool turns registry drift into a focused report so operators can spot new servers, removed servers, and risky access changes before rollout.

`mcp-registry-diff` normalizes common registry shapes and reports additions, removals, and field changes for:

- `image`
- `tag`
- `command`
- `env`
- `auth`
- `scope`
- `network`
- `filesystem`

## Quickstart

```bash
# Compare example registries shipped in this repo
PYTHONPATH=src python3 -m mcp_registry_diff examples/registry-old.json examples/registry-new.json --format markdown --fail-on none
```

No network is required.

## Install

```bash
git clone <repo-url>
cd mcp-registry-diff
PYTHONPATH=src python3 -m unittest discover -s tests
```

## Usage

```bash
PYTHONPATH=src python3 -m mcp_registry_diff <old_registry.json> <new_registry.json> [--format markdown|json] [--output path] [--fail-on risk-change|any-change|none]
```

## Examples

```bash
PYTHONPATH=src python3 -m mcp_registry_diff examples/registry-old.json examples/registry-new.json --format markdown --fail-on none
PYTHONPATH=src python3 -m mcp_registry_diff examples/registry-old.json examples/registry-new.json --format json --fail-on none
PYTHONPATH=src python3 -m mcp_registry_diff examples/registry-old.json examples/registry-new.json --output registry-diff.md --fail-on none
```

### Output modes

- `markdown` (default): Markdown report with summary tables.
- `json`: Machine-readable diff payload.

### Fail modes

- `risk-change` (default CI-safe): fail when risky fields change.
- `any-change`: fail on any add/remove/change.
- `none`: never fail.

Risk fields are `auth`, `scope`, `network`, and `filesystem`.

## API

The stable interface is the CLI:

```bash
PYTHONPATH=src python3 -m mcp_registry_diff OLD.json NEW.json --format markdown
PYTHONPATH=src python3 -m mcp_registry_diff OLD.json NEW.json --format json --output diff.json
PYTHONPATH=src python3 -m mcp_registry_diff OLD.json NEW.json --fail-on risk-change
```

## Supported registry shapes

The CLI accepts three common forms:

- JSON list: `[ {...}, {...} ]`
- JSON object with server list: `{ "servers": [ ... ] }`, `{ "items": [ ... ] }`, `{ "repositories": [ ... ] }`, `{ "mcpServers": [ ... ] }`
- JSON object keyed by server id/name: `{ "server-id": {...}, "server-id-2": {...} }`

## FAQ

- Does this need network access? No. It compares local JSON snapshots.
- Does it replace registry governance? No. It gives a deterministic review artifact for humans and CI.
- Why does the quickstart use `--fail-on none`? The sample intentionally includes risky changes so the report is visible without making the demo fail.

## Contributing

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Open issues with a minimal old/new registry pair and the expected diff. Keep new normalization rules deterministic and covered by tests.

## License

MIT
