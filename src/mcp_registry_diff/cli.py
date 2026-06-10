"""Command-line interface for MCP registry diffing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


TRACKED_FIELDS = ("image", "tag", "command", "env", "auth", "scope", "network", "filesystem")
RISK_FIELDS = ("auth", "scope", "network", "filesystem")
LIST_KEYS = ("servers", "items", "repositories", "mcpServers")
ID_FIELDS = ("id", "slug", "package", "title", "full_name")
NAME_FIELDS = ("name", "title", "id", "slug", "package", "full_name")
SERVER_HINT_FIELDS = set(ID_FIELDS + NAME_FIELDS + TRACKED_FIELDS)
FIELD_ALIASES = {
    "auth": ("auth", "authentication", "authorization"),
    "scope": ("scope", "scopes", "permissions"),
    "network": ("network", "networks", "networkAccess", "network_access"),
    "filesystem": ("filesystem", "files", "filesystemAccess", "filesystem_access"),
    "image": ("image", "docker_image", "container_image"),
}


def _looks_like_server_record(record: Dict[str, Any]) -> bool:
    if SERVER_HINT_FIELDS & set(record):
        return True
    return any(alias in record for aliases in FIELD_ALIASES.values() for alias in aliases)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare MCP registry snapshots.")
    parser.add_argument("old_registry", help="Path to the old registry JSON file.")
    parser.add_argument("new_registry", help="Path to the new registry JSON file.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output", help="Write output to a file. Defaults to stdout.")
    parser.add_argument("--fail-on", choices=["risk-change", "any-change", "none"], default="risk-change")
    return parser


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _first_field(record: Dict[str, Any], keys: Iterable[str], default: Optional[str] = None) -> Any:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
        if not isinstance(value, str):
            return value
    return default


def _listify_servers(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    # Object keyed by id/name, possibly mixed with metadata fields.
    keyed_servers = []
    for server_id, server_data in payload.items():
        if str(server_id).startswith("_") or not isinstance(server_data, dict):
            continue
        if not _looks_like_server_record(server_data):
            continue
        data = dict(server_data)
        data["id"] = data.get("id") or server_id
        keyed_servers.append(data)
    if keyed_servers:
        return keyed_servers

    # Single server object.
    if _looks_like_server_record(payload):
        result = []
        data = dict(payload)
        data["id"] = data.get("id") or data.get("name") or "server-0"
        result.append(data)
        return result

    return []


def _normalize_env(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return sorted([str(item) for item in value])
    return str(value)


def _normalize_text_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return sorted({str(v) for v in value})
    if isinstance(value, tuple):
        return sorted({str(v) for v in value})
    return [str(value)]

def _normalize_command(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return str(value)


def _extract_field(server: Dict[str, Any], field: str) -> Any:
    if field in FIELD_ALIASES:
        value = _first_field(server, FIELD_ALIASES[field])
    else:
        value = server.get(field)
    if value is None:
        return None
    if field == "env":
        return _normalize_env(value)
    if field in ("scope", "network", "filesystem"):
        return _normalize_text_list(value)
    if field == "command":
        return _normalize_command(value)
    return value


def _normalize_server_record(server: Dict[str, Any], fallback_key: str) -> Dict[str, Any]:
    record_id = _first_field(server, ID_FIELDS) or fallback_key
    record_name = _first_field(server, NAME_FIELDS) or record_id
    normalized = {
        "id": str(record_id),
        "name": str(record_name),
    }
    for field in TRACKED_FIELDS:
        normalized[field] = _extract_field(server, field)
    return normalized


def _coerce_for_compare(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _has_risk_fields(server: Dict[str, Any]) -> bool:
    for field in RISK_FIELDS:
        if server.get(field) is not None:
            value = server[field]
            if isinstance(value, str) and value.strip():
                return True
            if isinstance(value, (list, tuple, dict)) and len(value) > 0:
                return True
            if value is not None and not isinstance(value, (str, list, tuple, dict)):
                return True
    return False


def normalize_registry(path: str) -> Dict[str, Dict[str, Any]]:
    payload = _read_json(path)
    servers = _listify_servers(payload)
    normalized = {}
    seen_ids = set()
    for index, server in enumerate(servers):
        fallback = f"server-{index}"
        server_record = _normalize_server_record(server, fallback)
        server_id = server_record["id"]
        while server_id in seen_ids:
            server_id = f"{server_id}-dup{index}"
        normalized[server_id] = server_record
        seen_ids.add(server_id)
    return normalized


def compare_registries(old_registry: str, new_registry: str) -> Dict[str, Any]:
    old_servers = normalize_registry(old_registry)
    new_servers = normalize_registry(new_registry)

    old_keys = set(old_servers)
    new_keys = set(new_servers)
    added_keys = sorted(new_keys - old_keys)
    removed_keys = sorted(old_keys - new_keys)
    common_keys = sorted(old_keys & new_keys)

    added = [{"id": server_id, "after": new_servers[server_id]} for server_id in added_keys]
    removed = [{"id": server_id, "before": old_servers[server_id]} for server_id in removed_keys]

    changed = []
    for server_id in common_keys:
        old_record = old_servers[server_id]
        new_record = new_servers[server_id]
        field_changes = []
        for field in TRACKED_FIELDS:
            old_value = _coerce_for_compare(old_record.get(field))
            new_value = _coerce_for_compare(new_record.get(field))
            if old_value != new_value:
                field_changes.append(
                    {
                        "field": field,
                        "old": old_record.get(field),
                        "new": new_record.get(field),
                    }
                )
        if field_changes:
            changed.append(
                {
                    "id": server_id,
                    "name": new_record["name"],
                    "before": old_record,
                    "after": new_record,
                    "changed_fields": field_changes,
                }
            )
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
    }


def _format_json_payload(old_path: str, new_path: str, diff: Dict[str, Any], fail_on: str) -> str:
    return json.dumps(
        {
            "old_registry": old_path,
            "new_registry": new_path,
            "fail_on": fail_on,
            "summary": diff["summary"],
            "added": diff["added"],
            "removed": diff["removed"],
            "changed": diff["changed"],
        },
        indent=2,
        sort_keys=True,
    )


def _markdown_section(title: str, rows: List[str]) -> List[str]:
    return [f"## {title}"] + (["- none"] if not rows else rows) + [""]


def _markdown_table(changes: Dict[str, Any]) -> List[str]:
    lines = [
        "| id | field | old | new |",
        "| --- | --- | --- | --- |",
    ]
    for change in changes.get("changed_fields", []):
        lines.append(
            "| {id} | {field} | {old} | {new} |".format(
                id=changes["id"],
                field=change["field"],
                old=_pretty_json(change.get("old")),
                new=_pretty_json(change.get("new")),
            )
        )
    if len(lines) == 2:
        lines.append("| - | - | - | - |")
    return lines + [""]


def _pretty_json(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, (dict, list)):
        return f"`{json.dumps(value, sort_keys=True)}`"
    if isinstance(value, str):
        return f"`{value}`"
    return f"`{value}`"


def format_markdown(old_path: str, new_path: str, diff: Dict[str, Any]) -> str:
    lines: List[str] = [
        "# MCP Registry Diff",
        "",
        f"Comparing `{old_path}` -> `{new_path}`",
        "",
        "## Summary",
        f"- Added: {diff['summary']['added']}",
        f"- Removed: {diff['summary']['removed']}",
        f"- Changed: {diff['summary']['changed']}",
        "",
    ]

    added_rows = [f"- `{item['id']}`" for item in diff["added"]] if diff["added"] else []
    removed_rows = [f"- `{item['id']}`" for item in diff["removed"]] if diff["removed"] else []
    lines.extend(_markdown_section("Added", added_rows))
    lines.extend(_markdown_section("Removed", removed_rows))
    lines.append("## Changed")
    if not diff["changed"]:
        lines.append("- none")
        lines.append("")
    else:
        for change in diff["changed"]:
            lines.append(f"### {change['id']}")
            lines.extend(_markdown_table(change))
    return "\n".join(lines)


def _has_risk_change(diff: Dict[str, Any]) -> bool:
    for item in diff["added"] + diff["removed"]:
        if _has_risk_fields(item.get("after", item.get("before", {}))):
            return True
    for change in diff["changed"]:
        for field_change in change.get("changed_fields", []):
            if field_change["field"] in RISK_FIELDS:
                if field_change.get("old") != field_change.get("new"):
                    return True
    return False


def _has_any_change(diff: Dict[str, Any]) -> bool:
    return bool(diff["summary"]["added"] + diff["summary"]["removed"] + diff["summary"]["changed"])


def run(
    old_registry_path: str,
    new_registry_path: str,
    output_format: str = "markdown",
    fail_on: str = "risk-change",
) -> str:
    diff = compare_registries(old_registry_path, new_registry_path)
    if output_format == "json":
        return _format_json_payload(old_registry_path, new_registry_path, diff, fail_on)
    return format_markdown(old_registry_path, new_registry_path, diff)


def should_fail(diff: Dict[str, Any], mode: str) -> bool:
    if mode == "none":
        return False
    if mode == "any-change":
        return _has_any_change(diff)
    if mode == "risk-change":
        return _has_risk_change(diff)
    raise ValueError(f"unknown fail mode: {mode}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        diff = compare_registries(args.old_registry, args.new_registry)
        if args.format == "json":
            output = _format_json_payload(args.old_registry, args.new_registry, diff, args.fail_on)
        else:
            output = format_markdown(args.old_registry, args.new_registry, diff)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
        else:
            print(output)
        return 1 if should_fail(diff, args.fail_on) else 0
    except (FileNotFoundError, json.JSONDecodeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
