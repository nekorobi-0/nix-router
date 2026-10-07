import json
import base64
import ssl
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import prepare_xpass_credentials as migration
import xpass_ddns as ddns


SETTINGS = {
    "xpassIPv6Prefix": "2001:db8::1/64",
    "xpassTunnelRemote": "2001:db8::2",
    "xpassIPv4Fixed": "192.0.2.1/32",
    "xpassDDNSUser": "user",
    "xpassDDNSPassword": 'secret&+="\\日本語',
    "xpassDdnsDomain": "ddns.example.net",
    "xpassFQDN": "router.example.net",
    "xpassDDNSId": "account",
}


def nix_settings(settings):
    return "{\n" + "".join(f"{key} = {json.dumps(value)};\n" for key, value in settings.items()) + "}\n"


def test_migration_removes_secrets_and_is_repeatable(tmp_path):
    source = tmp_path / "xpass-env.nix"
    # Nix permits literal unicode; JSON's unicode escape is not a Nix escape.
    original = nix_settings(SETTINGS).replace(r"\u65e5\u672c\u8a9e", "日本語")
    source.write_text(original)
    directory = tmp_path / "protected"
    migration.prepare(source, directory)
    assert migration.parse_settings(source.read_text()) == {
        key: SETTINGS[key] for key in migration.NETWORK_FIELDS
    }
    credential = directory / "xpass-ddns.json"
    assert json.loads(credential.read_text())["xpassDDNSPassword"] == SETTINGS["xpassDDNSPassword"]
    assert credential.stat().st_mode & 0o777 == 0o600
    assert directory.stat().st_mode & 0o777 == 0o700
    assert (directory / "xpass-env.original.nix").read_text() == original
    migration.prepare(source, directory)
    assert json.loads(credential.read_text())["xpassDDNSPassword"] == SETTINGS["xpassDDNSPassword"]


@pytest.mark.parametrize("body", [
    '{ xpassIPv6Prefix = builtins.readFile "/tmp/secret"; }',
    '{ xpassIPv6Prefix = "${builtins.readFile /tmp/secret}"; }',
    '{ xpassIPv6Prefix = "x"; xpassIPv6Prefix = "y"; }',
])
def test_migration_rejects_executable_or_ambiguous_source(body):
    with pytest.raises(ValueError):
        migration.parse_settings(body)


def test_partial_legacy_settings_do_not_overwrite_source(tmp_path):
    source = tmp_path / "xpass-env.nix"
    original = nix_settings({key: value for key, value in SETTINGS.items() if key != "xpassDDNSPassword"})
    source.write_text(original)
    with pytest.raises(ValueError):
        migration.prepare(source, tmp_path / "protected")
    assert source.read_text() == original
    assert not (tmp_path / "protected" / "xpass-ddns.json").exists()


def test_legacy_password_alias_preserves_both_passwords():
    settings = dict(SETTINGS, xpassDDNSPass="basic-password")
    parsed = migration.parse_settings(nix_settings(settings))
    assert parsed["xpassDDNSPassword"] == SETTINGS["xpassDDNSPassword"]
    assert "xpassDDNSPass" not in parsed
    assert parsed["xpassBasicPassword"] == "basic-password"
    del settings["xpassDDNSPassword"]
    assert migration.parse_settings(nix_settings(settings))["xpassDDNSPassword"] == "basic-password"


def test_migration_recovers_legacy_basic_password_and_keeps_tls_preference(tmp_path):
    source = tmp_path / "xpass-env.nix"
    source.write_text(nix_settings({key: SETTINGS[key] for key in migration.NETWORK_FIELDS}))
    directory = tmp_path / "protected"
    directory.mkdir()
    (directory / "xpass-env.original.nix").write_text(nix_settings(dict(SETTINGS, xpassDDNSPass="basic-password")))
    credential = directory / "xpass-ddns.json"
    credential.write_text(json.dumps(dict(SETTINGS, xpassDDNSVerifyTLS=False)))
    migration.prepare(source, directory)
    result = json.loads(credential.read_text())
    assert result["xpassBasicPassword"] == "basic-password"
    assert result["xpassDDNSPassword"] == SETTINGS["xpassDDNSPassword"]
    assert result["xpassDDNSVerifyTLS"] is False
    result["xpassBasicPassword"] = "manually-updated-password"
    credential.write_text(json.dumps(result))
    migration.prepare(source, directory)
    assert json.loads(credential.read_text())["xpassBasicPassword"] == "manually-updated-password"


def test_password_is_encoded_and_never_in_url_authority():
    request = ddns.make_request(SETTINGS)
    parsed = urlsplit(request.full_url)
    assert parsed.scheme == "https"
    assert parsed.username is None
    assert parse_qs(parsed.query)["p"] == [SETTINGS["xpassDDNSPassword"]]
    assert parse_qs(parsed.query)["a"] == ["2001:db8::1"]
    assert request.get_header("Authorization").startswith("Basic ")


def test_basic_and_ddns_passwords_are_separate():
    request = ddns.make_request(dict(SETTINGS, xpassBasicPassword="basic-password"))
    authorization = request.get_header("Authorization").removeprefix("Basic ")
    assert base64.b64decode(authorization).decode() == "user:basic-password"
    assert parse_qs(urlsplit(request.full_url).query)["p"] == [SETTINGS["xpassDDNSPassword"]]


@pytest.mark.parametrize("verify_tls", [None, True, False])
def test_tls_verification_and_redirect_policy(monkeypatch, verify_tls):
    captured = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            assert limit == 65536
            return b"<H2>* DDNS API update : Success</H2>"

    class Opener:
        def open(self, request, timeout):
            assert timeout == 30
            return Response()

    def build_opener(*handlers):
        captured["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(ddns, "build_opener", build_opener)
    settings = dict(SETTINGS)
    if verify_tls is not None:
        settings["xpassDDNSVerifyTLS"] = verify_tls
    ddns.update(settings)
    https, redirects = captured["handlers"]
    assert https._context.verify_mode == (ssl.CERT_NONE if verify_tls is False else ssl.CERT_REQUIRED)
    assert https._context.check_hostname is (verify_tls is not False)
    assert redirects.redirect_request(None, None, 302, None, None, "https://other.example") is None


@pytest.mark.parametrize("value", ["false", 0, None])
def test_invalid_tls_setting_never_opens_a_connection(monkeypatch, value):
    monkeypatch.setattr(ddns, "build_opener", lambda *args: pytest.fail("invalid TLS setting opened a connection"))
    with pytest.raises(ValueError):
        ddns.update(dict(SETTINGS, xpassDDNSVerifyTLS=value))


@pytest.mark.parametrize("failure", [
    URLError("https://user:SECRET@example/?p=SECRET"),
    HTTPError("https://example/?p=SECRET", 403, "SECRET", {}, None),
])
def test_failures_do_not_log_password(tmp_path, monkeypatch, capsys, failure):
    (tmp_path / "xpass-ddns.json").write_text(json.dumps(SETTINGS))
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    def fail(settings): raise failure
    monkeypatch.setattr(ddns, "update", fail)
    assert ddns.main() == 1
    logs = capsys.readouterr()
    assert "SECRET" not in logs.err
    assert not logs.out
