"""FastAPI backend for the NixOS router dashboard."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR.parent))
from generate_snat_config import load_config, render, render_toml


BOOT_TIME = time.time() - time.monotonic()
STATIC_DIR = Path(os.environ.get("NIX_ROUTER_WEBUI_STATIC", Path(__file__).with_name("static")))
PROJECT_DIR = MODULE_DIR.parent
SNAT_CONFIG = Path(os.environ.get("NIX_ROUTER_SNAT_CONFIG", PROJECT_DIR / "general_config.toml"))
SNAT_OUTPUT = Path(os.environ.get("NIX_ROUTER_SNAT_OUTPUT", PROJECT_DIR / "snat-config.nix"))
SNAT_LOCK = threading.Lock()

app = FastAPI(
    title="NixOS Router Web UI",
    version="0.2.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


class PortForward(BaseModel):
    protocol: str = "tcp"
    external_port: int
    target_host: str
    target_port: int


class SnatSettings(BaseModel):
    external_interface: str
    masquerade: bool = True
    ports: list[PortForward]


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


def run_json(command: list[str]) -> Any:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError):
        return []


def interface_status() -> list[dict[str, Any]]:
    links = run_json(["ip", "-json", "link", "show"])
    addresses = run_json(["ip", "-json", "address", "show"])
    addresses_by_index = {
        item.get("ifindex"): [
            {
                "family": address.get("family"),
                "address": address.get("local"),
                "prefixLength": address.get("prefixlen"),
                "scope": address.get("scope"),
            }
            for address in item.get("addr_info", [])
        ]
        for item in addresses
    }

    return [
        {
            "name": link.get("ifname"),
            "state": link.get("operstate", "UNKNOWN"),
            "mac": link.get("address"),
            "mtu": link.get("mtu"),
            "addresses": addresses_by_index.get(link.get("ifindex"), []),
        }
        for link in links
    ]


def bgp_routes(peer_address: str, direction: str) -> list[dict[str, Any]]:
    data = run_json(
        [
            "vtysh",
            "-c",
            f"show bgp ipv4 unicast neighbors {peer_address} {direction} json",
        ]
    )
    if not isinstance(data, dict):
        return []

    route_map: Any = {}
    for key in ("routes", "receivedRoutes", "advertisedRoutes"):
        if isinstance(data.get(key), dict):
            route_map = data[key]
            break

    routes = []
    for prefix, paths in route_map.items():
        for path in paths if isinstance(paths, list) else [paths]:
            if not isinstance(path, dict):
                continue
            nexthops = path.get("nexthops", [])
            next_hop_values = [
                nexthop.get("ip") or nexthop.get("hostname")
                for nexthop in nexthops
                if isinstance(nexthop, dict)
            ]
            if not next_hop_values and path.get("nextHop"):
                next_hop_values = [path["nextHop"]]
            bestpath = path.get("bestpath", False)
            if isinstance(bestpath, dict):
                bestpath = bestpath.get("overall", False)
            aspath = path.get("path")
            if aspath is None and isinstance(path.get("aspath"), dict):
                aspath = path["aspath"].get("string")

            routes.append(
                {
                    "prefix": prefix,
                    "asPath": aspath,
                    "nextHops": next_hop_values,
                    "metric": path.get("metric"),
                    "localPreference": path.get("locPrf", path.get("localPref")),
                    "weight": path.get("weight"),
                    "origin": path.get("origin"),
                    "valid": path.get("valid"),
                    "bestPath": bool(bestpath),
                }
            )
    return routes


def bgp_status() -> dict[str, Any]:
    data = run_json(["vtysh", "-c", "show bgp ipv4 unicast summary json"])
    family = data.get("ipv4Unicast", data) if isinstance(data, dict) else {}
    peers = family.get("peers", {}) if isinstance(family, dict) else {}

    if not isinstance(peers, dict):
        peers = {}

    return {
        "available": bool(family),
        "routerId": family.get("routerId"),
        "localAs": family.get("as"),
        "vrfName": family.get("vrfName"),
        "tableVersion": family.get("tableVersion"),
        "routeCount": family.get("ribCount"),
        "peerCount": family.get("peerCount"),
        "failedPeers": family.get("failedPeers"),
        "peers": [
            {
                "address": address,
                "softwareVersion": peer.get("softwareVersion"),
                "remoteAs": peer.get("remoteAs"),
                "localAs": peer.get("localAs"),
                "state": peer.get("state", "Unknown"),
                "peerState": peer.get("peerState"),
                "uptime": peer.get("peerUptime"),
                "messagesReceived": peer.get("msgRcvd"),
                "messagesSent": peer.get("msgSent"),
                "inputQueue": peer.get("inq"),
                "outputQueue": peer.get("outq"),
                "prefixesReceived": peer.get("pfxRcd"),
                "prefixesSent": peer.get("pfxSnt"),
                "connectionsEstablished": peer.get("connectionsEstablished"),
                "connectionsDropped": peer.get("connectionsDropped"),
                "receivedRoutes": bgp_routes(address, "routes"),
                "advertisedRoutes": bgp_routes(address, "advertised-routes"),
            }
            for address, peer in peers.items()
            if isinstance(peer, dict)
        ],
    }


def snat_payload() -> dict[str, Any]:
    interface, masquerade, ports = load_config(SNAT_CONFIG)
    return {
        "external_interface": interface,
        "masquerade": masquerade,
        "ports": ports,
    }


@app.get("/api/ports", tags=["configuration"])
def get_ports() -> dict[str, Any]:
    try:
        return snat_payload()
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.put("/api/ports", tags=["configuration"])
def put_ports(settings: SnatSettings) -> dict[str, Any]:
    raw_ports = [port.model_dump() for port in settings.ports]
    temporary_config = SNAT_CONFIG.with_suffix(SNAT_CONFIG.suffix + ".tmp")
    temporary_output = SNAT_OUTPUT.with_suffix(SNAT_OUTPUT.suffix + ".tmp")

    with SNAT_LOCK:
        try:
            temporary_config.write_text(
                render_toml(
                    settings.external_interface,
                    settings.masquerade,
                    raw_ports,
                ),
                encoding="utf-8",
            )
            interface, masquerade, ports = load_config(temporary_config)
            temporary_output.write_text(
                render(interface, masquerade, ports),
                encoding="utf-8",
            )
            os.replace(temporary_config, SNAT_CONFIG)
            os.replace(temporary_output, SNAT_OUTPUT)
        except (OSError, ValueError) as error:
            temporary_config.unlink(missing_ok=True)
            temporary_output.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "status": "saved",
        "rebuildRequired": True,
        "ports": ports,
    }


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status", tags=["system"])
def status() -> JSONResponse:
    try:
        load = list(os.getloadavg())
    except OSError:
        load = []

    return JSONResponse(
        {
            "hostname": socket.gethostname(),
            "timestamp": int(time.time()),
            "uptimeSeconds": max(0, int(time.time() - BOOT_TIME)),
            "loadAverage": load,
            "interfaces": interface_status(),
            "bgp": bgp_status(),
        }
    )


# Keep this mount last so that /api routes take precedence.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
