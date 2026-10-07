"""Test evaluated NixOS tables with a real IPv4-over-IPv6 tunnel.

unshare -Urn python3 tests/nixos_firewall_integration.py /path/to/tables.json
Use a NixOS configuration evaluated with the documentation's example addresses.
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from firewall_integration import cleanup, inside, peer, probe, run, server


def main():
    if os.geteuid() != 0 or os.readlink("/proc/self/ns/net") == os.readlink("/proc/1/ns/net"):
        raise SystemExit("Use unshare -Urn; never run this on the host network")
    tables = json.loads(Path(sys.argv[1]).read_text())
    if "tables" in tables:
        tables = tables["tables"]
    run("ip", "link", "set", "lo", "up")
    run("sysctl", "-qw", "net.ipv4.ip_forward=1", "net.ipv6.conf.all.forwarding=1")
    wan = peer("enp1s0", "198.51.100", "2001:db8:1")
    lan = peer("enp2s0", "10.0.1", "2001:db8:3")
    # Map only the documentation's Xpass outer addresses to the test WAN subnet.
    policy = "\n".join(
        f"table {table['family']} {name} {{\n{table['content']}\n}}"
        for name, table in tables.items() if table.get("enable", True)
    ).replace("2001:db8::1", "2001:db8:1::1").replace("2001:db8::2", "2001:db8:1::2")
    if 'ip6 saddr 2001:db8:1::2 ip6 daddr 2001:db8:1::1' not in policy:
        raise SystemExit("Evaluate with example Xpass addresses for this isolated test")
    run("nft", "-f", "-", input=policy)
    run("ip", "link", "add", "ip6tnl1", "type", "ip6tnl", "mode", "ipip6", "local", "2001:db8:1::1",
        "remote", "2001:db8:1::2", "encaplimit", "none")
    run("ip", "addr", "add", "192.0.2.1/24", "dev", "ip6tnl1")
    run("ip", "link", "set", "ip6tnl1", "up")
    inside(wan, "ip", "link", "add", "xpass-peer", "type", "ip6tnl", "mode", "ipip6", "local", "2001:db8:1::2",
           "remote", "2001:db8:1::1", "encaplimit", "none")
    inside(wan, "ip", "addr", "add", "192.0.2.2/24", "dev", "xpass-peer")
    inside(wan, "ip", "link", "set", "xpass-peer", "up")
    inside(lan, "ip", "addr", "add", "192.168.0.101/32", "dev", "peer0")
    run("ip", "route", "add", "192.168.0.0/24", "via", "10.0.1.2")
    host = SimpleNamespace(pid=os.getpid())
    for port in [22, 8080, 9100]:
        server(host, port=port)
        server(host, ipv6=True, port=port)
        probe(wan, "198.51.100.1", port, allowed=False)
        probe(wan, "2001:db8:1::1", port, allowed=False)
        probe(wan, "192.0.2.1", port, allowed=False)
        probe(lan, "10.0.1.1", port)
        probe(lan, "2001:db8:3::1", port)
    server(lan, port=8352)
    server(lan)
    server(lan, ipv6=True)
    probe(wan, "192.0.2.1", 80)  # Public HTTP forward through real Xpass encapsulation.
    probe(wan, "10.0.1.2", allowed=False)
    probe(wan, "2001:db8:3::2", allowed=False)
    print("Evaluated NixOS firewall and real IPIP6 tunnel passed (18 network probes).")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
