from fastapi.testclient import TestClient

from backend import app, bgp_status


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
    assert 'id="refresh"' not in response.text


def test_bgp_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.run_json",
        lambda command: {
            "ipv4Unicast": {
                "routerId": "192.168.100.1",
                "as": 65000,
                "peers": {
                    "192.168.100.2": {
                        "remoteAs": 65100,
                        "state": "Established",
                        "peerUptime": "01:02:03",
                        "pfxRcd": 12,
                    }
                },
            }
        },
    )

    result = bgp_status()

    assert result["available"] is True
    assert result["routerId"] == "192.168.100.1"
    assert result["peers"][0]["state"] == "Established"
    assert result["peers"][0]["prefixesReceived"] == 12
