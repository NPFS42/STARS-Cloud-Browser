#!/usr/bin/env python3
"""Scoped, idempotent browser egress guard; does not change other Docker networks.

Run with --apply/--remove/--check after Docker creates its DOCKER-USER chain.
All operations use iptables-nft; the chain is limited to one dedicated /28.
"""
import os
import subprocess
import sys
import json
import ipaddress

SUBNET = "172.30.251.0/28"
CHAIN = "STARS_BROWSER_EGRESS"
BIN = "/usr/sbin/iptables"
STATIC_DENY = ["0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4"]

def host_public_subnets():
    """Discover each host public IPv4 interface subnet; never publish host-specific ranges.

    Fail closed if discovery is unavailable. Private and CGNAT addresses are already
    included in STATIC_DENY, and are deliberately not treated as public NICs.
    """
    result = subprocess.run(
        ["/usr/sbin/ip", "-j", "-4", "address", "show"],
        capture_output=True, text=True, check=True, timeout=10
    )
    networks = set()
    for interface in json.loads(result.stdout):
        for entry in interface.get("addr_info", []):
            if entry.get("family") != "inet" or entry.get("scope") != "global":
                continue
            address = ipaddress.ip_address(entry["local"])
            if address.is_global:
                prefix = int(entry["prefixlen"])
                networks.add(str(ipaddress.ip_interface(f"{address}/{prefix}").network))
    if not networks:
        raise RuntimeError(
            "No public IPv4 interface could be discovered. Configure and test "
            "an explicit deny policy for NAT-only hosts before starting the browser."
        )
    return sorted(networks)

def deny_cidrs():
    """Deduplicated static private ranges plus dynamic public host subnets."""
    return list(dict.fromkeys(STATIC_DENY + host_public_subnets()))

REPLY = ("INPUT", "-s", SUBNET, "-d", "172.30.251.1", "-p", "tcp", "--sport", "8811", "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-m", "comment", "--comment", "stars-browser-loopback-reply", "-j", "ACCEPT")

def run(*args, check=True):
    return subprocess.run([BIN, "-w", "3", *args], check=check, capture_output=True, text=True)


def exists(*args):
    return run("-C", *args, check=False).returncode == 0


def build():
    # Only our dedicated bridge's source addresses enter these rules. No global drops.
    if run("-L", CHAIN, "-n", check=False).returncode != 0:
        run("-N", CHAIN)
    # New chain is empty only during first install; refuse to adopt foreign rules.
    chain = run("-S", CHAIN).stdout.strip().splitlines()
    if len(chain) > 1 and not all("stars-browser" in line for line in chain[1:]):
        raise RuntimeError("Existing chain contains unrecognized rules; refusing modification")
    if len(chain) == 1:
        for ip in deny_cidrs():
            run("-A", CHAIN, "-d", ip, "-m", "comment", "--comment", "stars-browser-private-deny", "-j", "REJECT")
        for proto in ("tcp", "udp"):
            if proto == "tcp":
                for port in ("80", "443", "53"):
                    run("-A", CHAIN, "-p", proto, "--dport", port, "-m", "comment", "--comment", "stars-browser-web-only", "-j", "RETURN")
            else:
                run("-A", CHAIN, "-p", proto, "--dport", "53", "-m", "comment", "--comment", "stars-browser-dns-only", "-j", "RETURN")
        run("-A", CHAIN, "-m", "comment", "--comment", "stars-browser-default-deny", "-j", "REJECT")
    if not exists("DOCKER-USER", "-s", SUBNET, "-m", "comment", "--comment", "stars-browser-egress", "-j", CHAIN):
        run("-I", "DOCKER-USER", "1", "-s", SUBNET, "-m", "comment", "--comment", "stars-browser-egress", "-j", CHAIN)
    if not exists("INPUT", "-s", SUBNET, "-m", "comment", "--comment", "stars-browser-host-deny", "-j", "REJECT"):
        run("-I", "INPUT", "1", "-s", SUBNET, "-m", "comment", "--comment", "stars-browser-host-deny", "-j", "REJECT")
    if not exists(*REPLY):
        run("-I", "INPUT", "1", *REPLY[1:])
    check_guard()


def check_guard():
    chain = run("-S", CHAIN).stdout
    required = deny_cidrs()
    expected = len(required) + 5
    rules = [x for x in chain.splitlines() if x.startswith("-A ")]
    if len(rules) != expected:
        raise RuntimeError("Browser chain has wrong rule count")
    # Count alone is insufficient: verify that every required deny rule exists.
    for dest in required:
        if not exists(CHAIN, "-d", dest, "-m", "comment", "--comment",
                      "stars-browser-private-deny", "-j", "REJECT"):
            raise RuntimeError("Required browser destination deny is missing")
    if not exists("DOCKER-USER", "-s", SUBNET, "-m", "comment", "--comment", "stars-browser-egress", "-j", CHAIN):
        raise RuntimeError("DOCKER-USER browser guard missing")
    if not exists("INPUT", "-s", SUBNET, "-m", "comment", "--comment", "stars-browser-host-deny", "-j", "REJECT"):
        raise RuntimeError("Host-input browser guard missing")
    if not exists(*REPLY):
        raise RuntimeError("Host loopback reply exception missing")
    a=run("-S", "INPUT").stdout
    if a.index("stars-browser-loopback-reply")>a.index("stars-browser-host-deny"):
        raise RuntimeError("Host reply allow must precede browser host deny")
    print("STARS_BROWSER_FIREWALL_OK scoped=" + SUBNET)


def remove():
    if exists(*REPLY):
        run("-D", *REPLY)
    if exists("DOCKER-USER", "-s", SUBNET, "-m", "comment", "--comment", "stars-browser-egress", "-j", CHAIN):
        run("-D", "DOCKER-USER", "-s", SUBNET, "-m", "comment", "--comment", "stars-browser-egress", "-j", CHAIN)
    if exists("INPUT", "-s", SUBNET, "-m", "comment", "--comment", "stars-browser-host-deny", "-j", "REJECT"):
        run("-D", "INPUT", "-s", SUBNET, "-m", "comment", "--comment", "stars-browser-host-deny", "-j", "REJECT")
    if run("-L", CHAIN, "-n", check=False).returncode == 0:
        rules = run("-S", CHAIN).stdout.strip().splitlines()
        if any("stars-browser" not in line for line in rules[1:]):
            raise RuntimeError("Refusing to remove chain with foreign rules")
        run("-F", CHAIN)
        run("-X", CHAIN)
    print("STARS_BROWSER_FIREWALL_REMOVED")


if __name__ == "__main__":
    if os.geteuid():
        sys.exit("Root required")
    args = sys.argv[1:]
    if len(args) != 1 or args[0] not in ("--apply", "--check", "--remove"):
        sys.exit("usage: firewall.py --apply|--check|--remove")
    try:
        {"--apply": build, "--check": check_guard, "--remove": remove}[args[0]]()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        sys.exit("STARS_BROWSER_FIREWALL_FAILED: " + str(exc))
