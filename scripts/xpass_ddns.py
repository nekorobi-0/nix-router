"""Update Xpass DDNS using a systemd credential and verified HTTPS."""

from __future__ import annotations

import base64
import json
import os
import ssl
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler


DDNS_FIELDS = (
    "xpassDDNSUser", "xpassDDNSPassword", "xpassDdnsDomain",
    "xpassFQDN", "xpassDDNSId", "xpassIPv6Prefix",
)


class NoRedirects(HTTPRedirectHandler):
    # The query includes a password: never forward it to a redirect target.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def make_request(settings: dict[str, str]) -> Request:
    if any(not isinstance(settings.get(key), str) or not settings[key] for key in DDNS_FIELDS):
        raise ValueError("missing DDNS settings")
    domain = settings["xpassDdnsDomain"]
    endpoint = urlsplit(f"https://{domain}")
    if (
        not endpoint.hostname or endpoint.username is not None
        or endpoint.password is not None or endpoint.path
        or endpoint.query or endpoint.fragment
        or any(character.isspace() for character in domain)
    ):
        raise ValueError("invalid DDNS domain")
    query = urlencode({
        "d": settings["xpassFQDN"],
        "p": settings["xpassDDNSPassword"],
        "a": settings["xpassIPv6Prefix"],
        "u": settings["xpassDDNSId"],
    })
    authorization = base64.b64encode(
        f"{settings['xpassDDNSUser']}:{settings['xpassDDNSPassword']}".encode()
    ).decode("ascii")
    return Request(
        f"https://{domain}/cgi-bin/ddns_api.cgi?{query}",
        headers={"Authorization": f"Basic {authorization}"},
    )


def update(settings: dict[str, str]) -> None:
    request = make_request(settings)
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirects())
    with opener.open(request, timeout=30) as response:
        # Do not log a response which might contain credentials.
        response.read(65536)


def main() -> int:
    try:
        credential = Path(os.environ["CREDENTIALS_DIRECTORY"]) / "xpass-ddns.json"
        settings = json.loads(credential.read_text(encoding="utf-8"))
        update(settings)
    except HTTPError as error:
        print(f"Xpass DDNS update failed: HTTP {error.code}", file=sys.stderr)
        return 1
    except Exception:
        # urllib exceptions may include the URL, which contains the API password.
        print("Xpass DDNS update failed; check credentials, network and TLS certificate.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
