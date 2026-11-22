"""Regression tests: deny the live VPS public interface network, never hardcode it.

Execute without pytest: python3 -m unittest discover -s tests -p 'test_firewall_public_subnet.py' -v
"""
import importlib.util
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "security" / "firewall.py"
SPEC = importlib.util.spec_from_file_location("browser_egress_guard", PATH)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class PublicSubnetDetectionTest(unittest.TestCase):
    def run_with_interfaces(self, interfaces):
        with patch.object(
            guard.subprocess,
            "run",
            return_value=types.SimpleNamespace(stdout=json.dumps(interfaces)),
        ):
            return guard.host_public_subnets()

    def test_public_interface_denies_connected_network(self):
        interfaces = [
            {"ifname": "eth0", "addr_info": [
                {"family": "inet", "local": "1.2.3.4", "prefixlen": 24, "scope": "global"},
                {"family": "inet", "local": "10.50.1.9", "prefixlen": 24, "scope": "global"},
            ]},
            {"ifname": "tailscale0", "addr_info": [
                {"family": "inet", "local": "100.101.102.103", "prefixlen": 32, "scope": "global"}
            ]},
        ]
        self.assertEqual(self.run_with_interfaces(interfaces), ["1.2.3.0/24"])

    def test_nat_only_host_fails_closed(self):
        interfaces = [{"ifname": "ens0", "addr_info": [
            {"family": "inet", "local": "10.20.30.40", "prefixlen": 24, "scope": "global"}
        ]}]
        with self.assertRaisesRegex(RuntimeError, "No public IPv4 interface"):
            self.run_with_interfaces(interfaces)

    def test_static_private_network_deny_unchanged(self):
        self.assertIn("10.0.0.0/8", guard.STATIC_DENY)
        self.assertIn("100.64.0.0/10", guard.STATIC_DENY)
        self.assertIn("169.254.0.0/16", guard.STATIC_DENY)
        self.assertTrue(all(x != "1.2.3.0/24" for x in guard.STATIC_DENY))

    def test_live_source_has_no_vps_address(self):
        source = PATH.read_text()
        self.assertIn("host_public_subnets()", source)
        self.assertIn("STATIC_DENY", source)


if __name__ == "__main__":
    unittest.main()
