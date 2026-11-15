"""MCP config blocks for Claude Code and OpenCode, in the shapes the OpenCode 1 and 2 documentation gives."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import orchestrate  # noqa: E402


class McpConfigTests(unittest.TestCase):
    def test_claude_code_gets_mcp_servers_with_command_and_args(self):
        block = orchestrate.mcp_config("playwright", "claude")["mcpServers"]["playwright"]
        self.assertIn("@playwright/mcp@", " ".join(block["args"]))

    def test_opencode_v1_shape_is_the_default_because_both_versions_read_it(self):
        block = orchestrate.mcp_config("playwright", "opencode")
        self.assertEqual(set(block["mcp"]), {"playwright"})
        self.assertEqual((block["mcp"]["playwright"]["type"], block["mcp"]["playwright"]["enabled"]), ("local", True))

    def test_opencode_v2_groups_servers_and_has_no_enabled_field(self):
        """OpenCode 2 docs: servers go under mcp.servers, and `disabled` replaces `enabled`."""
        block = orchestrate.mcp_config("playwright", "opencode", "v2")
        server = block["mcp"]["servers"]["playwright"]
        self.assertEqual(server["type"], "local")
        self.assertNotIn("enabled", server)
        self.assertNotIn("disabled", server)
        self.assertIsInstance(server["command"], list)

    def test_an_unknown_server_is_refused(self):
        with self.assertRaises(SystemExit):
            orchestrate.mcp_config("no-such-server", "opencode", "v2")


if __name__ == "__main__":
    unittest.main()
