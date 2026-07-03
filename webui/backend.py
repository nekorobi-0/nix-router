"""FastAPI backend for the NixOS router dashboard."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


BOOT_TIME = time.time() - time.monotonic()
STATIC_DIR = Path(os.environ.get("NIX_ROUTER_WEBUI_STATIC", Path(__file__).with_name("static")))

app = FastAPI(
    title="NixOS Router Web UI",
    version="0.2.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def run_json(command: list[str]) -> Any:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
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
        }
    )


# Keep this mount last so that /api routes take precedence.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
