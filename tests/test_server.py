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
                "vm_copy_to_guest",
                "vm_copy_from_guest",
                "vm_share_folder",
                "vm_unshare_folder",
                "vm_clone",
                "vm_delete",
                "vm_set_headless",
                "vm_set_network_condition",
                "snapshot_list",
                "snapshot_create",
                "snapshot_revert",
                "snapshot_delete",
            },
        )

    def test_confirmation_guards(self) -> None:
        from parallels_mcp.server import snapshot_create, snapshot_delete, snapshot_revert, vm_delete

        with self.assertRaises(ValueError):
            asyncio.run(vm_delete(vm="test-vm", confirm=False))

        with self.assertRaises(ValueError):
            asyncio.run(snapshot_create(vm="test-vm", name="snap1", confirm=False))

        with self.assertRaises(ValueError):
            asyncio.run(snapshot_revert(vm="test-vm", snapshot="snap1", confirm=False))

        with self.assertRaises(ValueError):
            asyncio.run(snapshot_delete(vm="test-vm", snapshot="snap1", confirm=False))

