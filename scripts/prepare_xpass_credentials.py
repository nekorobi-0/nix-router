"""Move legacy Xpass secrets out of the flake source before rebuilding."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

from xpass_ddns import DDNS_FIELDS, make_request


NETWORK_FIELDS = ("xpassIPv6Prefix", "xpassTunnelRemote", "xpassIPv4Fixed")
TOKEN = re.compile(r'\s+|#[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"|[A-Za-z_][A-Za-z0-9_]*|[{}=;]', re.S)


def parse_settings(source: str) -> dict[str, str]:
    """Accept only the documented flat Nix attrset; never evaluate Nix code."""
    tokens = []
    position = 0
    while position < len(source):
        match = TOKEN.match(source, position)
        if match is None:
            raise ValueError("xpass-env.nix must be a flat attribute set of string literals")
        token = match.group()
        position = match.end()
        if token.isspace() or token.startswith(("#", "/*")):
            continue
        tokens.append(token)
    if not tokens or tokens[0] != "{" or tokens[-1] != "}":
        raise ValueError("invalid xpass-env.nix attribute set")
    settings = {}
    entries = tokens[1:-1]
    if len(entries) % 4:
        raise ValueError("invalid xpass-env.nix assignments")
    for index in range(0, len(entries), 4):
        key, equal, value, semicolon = entries[index:index + 4]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or equal != "=" or semicolon != ";":
            raise ValueError("invalid xpass-env.nix assignment")
        if not value.startswith('"') or re.search(r"(?<!\\)\$\{", value):
            raise ValueError("Xpass values must be string literals without interpolation")
        if key in settings:
            raise ValueError("duplicate Xpass setting")
        # Nix's documented string escapes overlap with JSON, plus escaped interpolation.
        settings[key] = json.loads(value.replace(r"\${", "${"))
    # Older deployments used DDNSPass for Basic auth and DDNSPassword for the API.
    if "xpassDDNSPass" in settings:
        legacy_password = settings.pop("xpassDDNSPass")
        settings.setdefault("xpassDDNSPassword", legacy_password)
        settings.setdefault("xpassBasicPassword", legacy_password)
    if any(not settings.get(key) for key in NETWORK_FIELDS):
        raise ValueError("missing Xpass network settings")
    if set(settings) - set(NETWORK_FIELDS) - set(DDNS_FIELDS) - {"xpassBasicPassword"}:
        raise ValueError("unknown Xpass settings; migrate these manually")
    return settings


def atomic_write(path: Path, text: str, mode: int) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prepare(source: Path, directory: Path) -> None:
    if source.is_symlink() or directory.is_symlink():
        raise ValueError("Xpass paths must not be symbolic links")
    original = source.read_text(encoding="utf-8")
    settings = parse_settings(original)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    credential = directory / "xpass-ddns.json"
    backup = directory / "xpass-env.original.nix"
    if credential.is_symlink():
        raise ValueError("credential must not be a symbolic link")
    secret_fields = (set(DDNS_FIELDS) - set(NETWORK_FIELDS)) | {"xpassBasicPassword"}
    if secret_fields & settings.keys():
        ddns = {key: settings.get(key) for key in DDNS_FIELDS}
        if "xpassBasicPassword" in settings:
            ddns["xpassBasicPassword"] = settings["xpassBasicPassword"]
        make_request(ddns)
        if not backup.exists():
            atomic_write(backup, original, 0o600)
    else:
        ddns = json.loads(credential.read_text(encoding="utf-8"))
        # Recover a Basic password omitted by the first migration, without replacing
        # a manually configured value or restoring credentials for another account.
        if "xpassBasicPassword" not in ddns and backup.is_file():
            previous = parse_settings(backup.read_text(encoding="utf-8"))
            if (
                "xpassBasicPassword" in previous
                and previous.get("xpassDDNSUser") == ddns.get("xpassDDNSUser")
                and previous.get("xpassDDNSPassword") == ddns.get("xpassDDNSPassword")
            ):
                ddns["xpassBasicPassword"] = previous["xpassBasicPassword"]
        ddns["xpassIPv6Prefix"] = settings["xpassIPv6Prefix"]
        make_request(ddns)
    atomic_write(credential, json.dumps(ddns, ensure_ascii=False) + "\n", 0o600)
    sanitized = "{\n" + "".join(
        f"  {key} = " + json.dumps(settings[key]).replace('${', r'\${') + ";\n"
        for key in NETWORK_FIELDS
    ) + "}\n"
    if original != sanitized:
        atomic_write(source, sanitized, 0o644)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent.parent / "xpass-env.nix")
    parser.add_argument("--directory", type=Path, default=Path("/etc/nix-router"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run as root to prepare the protected DDNS credential")
    try:
        prepare(args.source, args.directory)
    except Exception:
        parser.exit(1, "Cannot prepare Xpass credentials. Check the flat xpass-env.nix format and existing credential; no secret values are logged.\n")
    print("Prepared root-only DDNS credentials and removed secrets from xpass-env.nix.")


if __name__ == "__main__":
    main()
