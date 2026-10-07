# Security checks

Run the credential, DDNS and existing Web UI tests:

```bash
uv run --project webui pytest tests/test_xpass_credentials.py webui/tests
```

Run the forwarding tests in disposable user and network namespaces:

```bash
unshare -Urn python3 tests/firewall_integration.py
```

This checks IPv4 and IPv6 unsolicited inbound connections, TCP/UDP port forwarding,
outbound connections and replies, container initiated traffic, unexpected Docker
DNAT to the same backend, and a firewall reload. It uses the real rule template
and port configuration generator. It does not change the host network.

`nixos_firewall_integration.py` additionally tests the evaluated NixOS INPUT and
FORWARD tables together, including real kernel IPIP6 encapsulation. Prepare a
temporary copy of the repository **excluding** the real `xpass-env.nix`, all
credentials, `.git` and virtual environments. Add the README's example network
addresses to the copy's `xpass-env.nix` (only its three network fields). Keep the
checked-in `snat-config.nix` and `flake.lock` for this test. In that copy, evaluate:

```bash
nix eval --impure --json \
  path:.#nixosConfigurations.router.config.networking.nftables.tables \
  > /tmp/nix-router-test-tables.json
```

Then, in the original checkout:

```bash
unshare -Urn python3 tests/nixos_firewall_integration.py /tmp/nix-router-test-tables.json
```

The tests model WAN, LAN and tunnel peers; they cannot verify the ISP connection,
deployed container configuration, live BGP routes or hardware behavior. Check
those on the router after applying from a LAN management connection or console.
