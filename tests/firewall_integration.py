"""Run with unshare -Urn python3 tests/firewall_integration.py.

All interfaces, routing and nftables operations stay in disposable namespaces.
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generate_snat_config import render


def run(*args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"{args}: {result.stderr.strip()}")
    return result


def inside(peer, *args):
    return run("nsenter", "-t", str(peer.pid), "-n", *args)


processes = []


def peer(interface, ipv4, ipv6):
    process = subprocess.Popen(["unshare", "-n", "sleep", "120"])
    processes.append(process)
    for _ in range(100):
        if os.readlink(f"/proc/{process.pid}/ns/net") != os.readlink("/proc/self/ns/net"):
            break
        time.sleep(.01)
    run("ip", "link", "add", interface, "type", "veth", "peer", "name", "peer0")
    run("ip", "link", "set", "peer0", "netns", str(process.pid))
    run("ip", "addr", "add", f"{ipv4}.1/24", "dev", interface)
    run("ip", "-6", "addr", "add", f"{ipv6}::1/64", "dev", interface, "nodad")
    run("ip", "link", "set", interface, "up")
    inside(process, "ip", "link", "set", "lo", "up")
    inside(process, "ip", "addr", "add", f"{ipv4}.2/24", "dev", "peer0")
    inside(process, "ip", "-6", "addr", "add", f"{ipv6}::2/64", "dev", "peer0", "nodad")
    inside(process, "ip", "link", "set", "peer0", "up")
    inside(process, "ip", "route", "add", "default", "via", f"{ipv4}.1")
    inside(process, "ip", "-6", "route", "add", "default", "via", f"{ipv6}::1")
    return process


def server(peer, ipv6=False, udp=False, port=18080):
    code = '''
import socket,sys
s=socket.socket(socket.AF_INET6 if sys.argv[1]=='6' else socket.AF_INET, socket.SOCK_DGRAM if sys.argv[2]=='udp' else socket.SOCK_STREAM)
if sys.argv[1]=='6': s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
s.bind(('::' if sys.argv[1]=='6' else '0.0.0.0',int(sys.argv[3])))
if sys.argv[2]=='udp':
 print('ready',flush=True)
 while True:
  data,addr=s.recvfrom(4096); s.sendto(data,addr)
else:
 s.listen(); print('ready',flush=True)
 while True:
  c,a=s.accept(); c.settimeout(2)
  try: c.sendall(c.recv(4096))
  except (OSError,TimeoutError): pass
  finally: c.close()
'''
    process = subprocess.Popen(
        ["nsenter", "-t", str(peer.pid), "-n", sys.executable, "-u", "-c", code,
         "6" if ipv6 else "4", "udp" if udp else "tcp", str(port)],
        stdout=subprocess.PIPE, text=True,
    )
    processes.append(process)
    assert process.stdout.readline().strip() == "ready"


def probe(peer, address, port=18080, udp=False, allowed=True):
    code = '''
import socket,sys
s=socket.socket(socket.AF_INET6 if ':' in sys.argv[1] else socket.AF_INET,socket.SOCK_DGRAM if sys.argv[3]=='udp' else socket.SOCK_STREAM)
s.settimeout(.4)
try:
 s.connect((sys.argv[1],int(sys.argv[2]))); s.send(b'probe'); ok=s.recv(4096)==b'probe'
except OSError: ok=False
print('allowed' if ok else 'blocked')
'''
    result = inside(peer, sys.executable, "-c", code, address, str(port), "udp" if udp else "tcp")
    actual = result.stdout.strip()
    assert actual == ("allowed" if allowed else "blocked"), (address, port, udp, allowed, actual)
    print(f"PASS {'UDP' if udp else 'TCP'} {address}:{port} {actual}")


def main():
    if os.geteuid() != 0 or os.readlink("/proc/self/ns/net") == os.readlink("/proc/1/ns/net"):
        raise SystemExit("Use unshare -Urn; never run this on the host network")
    run("ip", "link", "set", "lo", "up")
    run("sysctl", "-qw", "net.ipv4.ip_forward=1", "net.ipv6.conf.all.forwarding=1")
    wan = peer("enp1s0", "198.51.100", "2001:db8:1")
    tunnel = peer("ip6tnl1", "192.0.2", "2001:db8:2")
    lan = peer("enp2s0", "10.0.1", "2001:db8:3")
    docker = peer("br-test", "172.18.0", "2001:db8:4")
    for process in [wan, tunnel, lan]:
        server(process)
        server(process, ipv6=True)
        server(process, udp=True)
    # Match the actual generated policy, including empty or changed forwarding lists.
    entries = [dict(protocol=p, external_port=8080 if p == "tcp" else 5353,
                    target_host="10.0.1.2", target_port=18080) for p in ["tcp", "udp"]]
    generated = render("ip6tnl1", True, entries)
    contents = re.findall(r"content = ''\n(.*?)    '';", generated, re.S)
    policy = (ROOT / "wan-firewall.nft").read_text().replace("@WAN@", "enp1s0").replace(
        "@LAN_INTERFACES@", '"enp2s0", "enp3s0", "enp1s0d1"')
    rules = "table inet wan-guard {\n" + policy + contents[1] + "}\ntable ip nat {\n" + contents[0] + "}\n"
    run("nft", "-f", "-", input=rules)
    # Emulate Docker accepting forwarding and publishing a port to the same backend.
    run("nft", "-f", "-", input='''
table ip docker_test {
 chain forward { type filter hook forward priority filter; policy accept; accept; }
 chain prerouting { type nat hook prerouting priority dstnat + 1;
  iifname "ip6tnl1" tcp dport 9090 dnat to 10.0.1.2:18080
  iifname "enp1s0" tcp dport 8080 dnat to 10.0.1.2:18080
 }
}
''')
    for external in [wan, tunnel]:
        probe(external, "10.0.1.2", allowed=False)
        probe(external, "2001:db8:3::2", allowed=False)
        probe(external, "10.0.1.2", udp=True, allowed=False)
    probe(tunnel, "192.0.2.1", 8080)
    probe(tunnel, "192.0.2.1", 5353, udp=True)
    probe(tunnel, "192.0.2.1", 9090, allowed=False)
    probe(wan, "198.51.100.1", 8080, allowed=False)
    for external, address, address6 in [
        (wan, "198.51.100.2", "2001:db8:1::2"),
        (tunnel, "192.0.2.2", "2001:db8:2::2"),
    ]:
        probe(lan, address)
        probe(lan, address6)
        probe(lan, address, udp=True)
    probe(docker, "198.51.100.2")
    # A reload must keep unsolicited WAN traffic blocked, including Docker's DNAT.
    run("nft", "delete", "table", "inet", "wan-guard")
    run("nft", "-f", "-", input="table inet wan-guard {\n" + policy + contents[1] + "}\n")
    probe(tunnel, "192.0.2.1", 9090, allowed=False)
    print("Firewall integration passed (18 network probes).")


def cleanup():
    for process in reversed(processes):
        process.terminate()
    for process in processes:
        process.wait(timeout=5)


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
