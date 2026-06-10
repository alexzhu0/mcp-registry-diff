import json
import tempfile
from pathlib import Path
import unittest
from io import StringIO
from contextlib import redirect_stdout

from mcp_registry_diff.cli import (
    _first_field,
    compare_registries,
    format_markdown,
    normalize_registry,
    run,
    should_fail,
)


class RegistryDiffTests(unittest.TestCase):
    def _write_json(self, directory: Path, filename: str, content) -> str:
        path = directory / filename
        path.write_text(json.dumps(content), encoding="utf-8")
        return str(path)

    def _assert_json_output(self, text: str):
        payload = json.loads(text)
        self.assertIn("added", payload)
        self.assertIn("removed", payload)
        self.assertIn("changed", payload)

    def test_first_field_prefers_left_to_right(self):
        record = {"name": "server-name", "id": "server-id"}
        self.assertEqual(_first_field(record, ("id", "name")), "server-id")

    def test_normalize_list_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            old_path = self._write_json(tmp, "old.json", [{"id": "s1", "name": "Old Server"}])
            old = normalize_registry(old_path)
        self.assertIn("s1", old)
        self.assertEqual(old["s1"]["name"], "Old Server")

    def test_normalize_servers_key_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            old_path = self._write_json(tmp, "old.json", {"servers": [{"id": "s1", "name": "Old Server"}]})
            old = normalize_registry(old_path)
        self.assertIn("s1", old)
        self.assertEqual(old["s1"]["name"], "Old Server")

    def test_normalize_keyed_object_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            old_path = self._write_json(tmp, "old.json", {"key-one": {"name": "Key One", "image": "python:3.12"}})
            old = normalize_registry(old_path)
        self.assertIn("key-one", old)
        self.assertEqual(old["key-one"]["image"], "python:3.12")

    def test_detects_added_and_removed_servers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            old_path = self._write_json(tmp, "old.json", [{"id": "s1", "name": "Server 1", "auth": "none"}])
            new_path = self._write_json(tmp, "new.json", [{"id": "s2", "name": "Server 2", "auth": "token"}])
            diff = compare_registries(old_path, new_path)
        self.assertEqual(diff["summary"]["added"], 1)
        self.assertEqual(diff["summary"]["removed"], 1)
        self.assertEqual(diff["added"][0]["id"], "s2")
        self.assertEqual(diff["removed"][0]["id"], "s1")

    def test_detects_tracked_field_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            old_path = self._write_json(
                tmp,
                "old.json",
                [
                    {
                        "id": "s1",
                        "image": "python:3.10",
                        "tag": "v1",
                        "command": ["python", "-m", "serve"],
                        "env": {"MODE": "dev"},
                        "auth": "none",
                        "scope": ["read"],
                        "network": ["egress"],
                        "filesystem": ["tmp"],
                    }
                ],
            )
            new_path = self._write_json(
                tmp,
                "new.json",
                [
                    {
                        "id": "s1",
                        "image": "python:3.11",
                        "tag": "v2",
                        "command": ["python", "-m", "serve", "--reload"],
                        "env": ["MODE=prod", "TOKEN=abc"],
                        "auth": "token",
                        "scope": ["read", "write"],
                        "network": ["egress", "intra"],
                        "filesystem": ["tmp", "home"],
                    }
                ],
            )
            diff = compare_registries(old_path, new_path)
        changed = diff["changed"][0]["changed_fields"]
        changed_fields = {item["field"] for item in changed}
        self.assertEqual(diff["summary"]["changed"], 1)
        self.assertSetEqual(
            changed_fields,
            {"image", "tag", "command", "env", "auth", "scope", "network", "filesystem"},
        )

    def test_markdown_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            old_path = self._write_json(tmp, "old.json", [{"id": "s1", "name": "A", "auth": "none"}])
            new_path = self._write_json(tmp, "new.json", [{"id": "s1", "name": "A", "auth": "token"}])
            output = run(old_path, new_path, "markdown")
        self.assertIn("# MCP Registry Diff", output)
        self.assertIn("Comparing", output)
        self.assertIn("## Changed", output)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            old_path = self._write_json(tmp, "old.json", [{"id": "s1", "name": "A", "network": ["egress"]}])
            new_path = self._write_json(tmp, "new.json", [{"id": "s1", "name": "A", "network": ["egress", "intra"]}])
            output = run(old_path, new_path, "json")
        self._assert_json_output(output)
        self.assertIn("s1", output)

    def test_fail_on_any_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            old_path = self._write_json(tmp, "old.json", [{"id": "s1", "name": "A", "auth": "none"}])
            new_path = self._write_json(tmp, "new.json", [{"id": "s1", "name": "A", "auth": "token"}])
            diff = compare_registries(old_path, new_path)
        self.assertTrue(should_fail(diff, "any-change"))

    def test_fail_on_risk_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            old_path = self._write_json(tmp, "old.json", [{"id": "s1", "name": "A", "scope": ["read"]}])
            new_path = self._write_json(tmp, "new.json", [{"id": "s1", "name": "A", "scope": ["read", "write"]}])
            diff = compare_registries(old_path, new_path)
        self.assertTrue(should_fail(diff, "risk-change"))

    def test_fail_on_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            old_path = self._write_json(tmp, "old.json", [{"id": "s1", "name": "A"}])
            new_path = self._write_json(tmp, "new.json", [{"id": "s1", "name": "A", "scope": ["read"]}])
            diff = compare_registries(old_path, new_path)
        self.assertFalse(should_fail(diff, "none"))

    def test_main_writes_output_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            old_path = self._write_json(tmp, "old.json", [{"id": "s1", "name": "A"}])
            new_path = self._write_json(tmp, "new.json", [{"id": "s1", "name": "A", "auth": "token"}])
            output_path = tmp / "out.md"
            stdout = StringIO()
            with redirect_stdout(stdout):
                from mcp_registry_diff.cli import main

                code = main([old_path, new_path, "--format", "markdown", "--fail-on", "any-change", "--output", str(output_path)])
            self.assertEqual(code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("Changed", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
