from fastapi.testclient import TestClient

from backend import PortForward, SnatSettings, app, bgp_status, get_ports, put_ports


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_status() -> None:
    response = client.get("/api/status")
    body = response.json()

    assert response.status_code == 200
    assert isinstance(body["hostname"], str)
    assert isinstance(body["uptimeSeconds"], int)
    assert isinstance(body["interfaces"], list)
    assert isinstance(body["bgp"]["available"], bool)


def test_frontend() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Nix Router" in response.text
    assert 'href="#/bgp"' in response.text
    assert 'id="refresh"' not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_bgp_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.run_json",
        lambda command: {
            "routerId": "192.168.100.1",
            "as": 65000,
            "peers": {
                "192.168.100.2": {
                "remoteAs": 65100,
                "localAs": 65000,
                "state": "Established",
                "peerUptime": "01:02:03",
                "pfxRcd": 12,
                "pfxSnt": 8,
                "msgRcvd": 20,
                "msgSent": 21,
                },
            },
        }
        if command[-1] == "show bgp ipv4 unicast summary json"
        else {
            "routes": {
                "203.0.113.0/24": [
                    {
                        "path": "65100 65200",
                        "nexthops": [{"ip": "192.168.100.2"}],
                        "locPrf": 100,
                        "bestpath": {"overall": True},
                        "valid": True,
                    }
                ]
            }
        },
    )

    result = bgp_status()

    assert result["available"] is True
    assert result["routerId"] == "192.168.100.1"
    assert result["peers"][0]["state"] == "Established"
    assert result["peers"][0]["prefixesReceived"] == 12
    assert result["peers"][0]["prefixesSent"] == 8
    assert result["peers"][0]["messagesSent"] == 21
    assert result["peers"][0]["receivedRoutes"][0]["prefix"] == "203.0.113.0/24"
    assert result["peers"][0]["receivedRoutes"][0]["asPath"] == "65100 65200"


def test_port_configuration(tmp_path, monkeypatch) -> None:
    config = tmp_path / "general_config.toml"
    output = tmp_path / "snat-config.nix"
    config.write_text(
        '[snat]\nexternal_interface = "wan0"\nmasquerade = true\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("backend.SNAT_CONFIG", config)
    monkeypatch.setattr("backend.SNAT_OUTPUT", output)

    result = put_ports(
        SnatSettings(
            external_interface="wan0",
            masquerade=True,
            ports=[
                PortForward(
                    protocol="tcp",
                    external_port=8080,
                    target_host="192.168.1.10",
                    target_port=80,
                )
            ],
        )
    )

    assert result["rebuildRequired"] is True
    assert get_ports()["ports"][0]["external_port"] == 8080
    assert "tcp dport 8080 dnat to 192.168.1.10:80" in output.read_text()
