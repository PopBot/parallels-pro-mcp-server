import asyncio
import unittest

from parallels_mcp.server import mcp


class ServerRegistrationTests(unittest.TestCase):
    def test_registers_the_current_tool_surface(self) -> None:
        result = asyncio.run(mcp.list_tools())
        self.assertEqual(
            {tool.name for tool in result},
            {
                "vm_list",
                "vm_status",
                "vm_start",
                "vm_stop",
                "vm_suspend",
                "vm_wait_ready",
                "vm_exec",
                "vm_screenshot",
                "vm_send_keys",
                "snapshot_list",
                "snapshot_create",
                "snapshot_revert",
                "snapshot_delete",
            },
        )
