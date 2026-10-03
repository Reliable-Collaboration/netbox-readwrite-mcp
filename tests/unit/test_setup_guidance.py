import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest

from netbox_readwrite_mcp.guidance import INSTRUCTIONS, guidance
from netbox_readwrite_mcp.setup import client_entry, configure, default_config

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_guidance_is_packaged_and_matches_documentation():
    assert (ROOT / "docs/agent-guide.md").read_bytes() == (
        ROOT / "src/netbox_readwrite_mcp/agent-guide.md"
    ).read_bytes()
    assert "get_guidance" in INSTRUCTIONS
    assert "related_objects" in guidance("native-imports-and-bulk-forms")["instructions"]
    with pytest.raises(ValueError, match="Unknown guidance"):
        guidance("../../token")


def test_configure_private_and_never_replaces_lineage(tmp_path):
    path = tmp_path / "private/config.json"
    configure(path, "https://netbox.example.org", "inventory", "secret-token")
    before = path.read_bytes()
    config = json.loads(before)
    assert config["instance_id"]
    assert config["token_file"] == "token"
    assert "secret-token" not in before.decode()
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert (path.parent / "token").stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        configure(path, "https://other.example.org", "other", "different")
    assert path.read_bytes() == before
    assert (path.parent / "token").read_text() == "secret-token\n"


def test_configure_refuses_existing_token_and_public_directory(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    (private / "token").write_text("existing")
    with pytest.raises(FileExistsError):
        configure(private / "config.json", "https://netbox.example.org", "inventory", "new")
    assert not (private / "config.json").exists()
    assert (private / "token").read_text() == "existing"
    private.chmod(0o755)
    with pytest.raises(ValueError, match="private"):
        configure(private / "config.json", "https://netbox.example.org", "inventory", "new")


def test_zipapp_client_config_uses_python_and_archive(monkeypatch, tmp_path):
    archive = tmp_path / "netbox-readwrite-mcp.pyz"
    monkeypatch.setattr(sys, "argv", [str(archive), "configure"])
    result = client_entry(tmp_path / "config.json", "opencode")["mcp"]["netbox"]
    assert result["command"][:2] == [sys.executable, str(archive)]
    assert result["command"][2] == "--config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_config() == tmp_path / "netbox-readwrite-mcp/config.json"


def test_enable_preserves_native_configuration_and_is_idempotent(tmp_path):
    setup = module("companion_setup", ROOT / "companion/netbox_agent_api_setup.py")
    path = tmp_path / "configuration.py"
    original = b'PLUGINS = ["another_plugin"]\nSECRET_KEY = "retained"\n'
    path.write_bytes(original)
    assert setup.enable(path)
    context = {}
    exec(path.read_text(), context)
    assert context["PLUGINS"] == ["another_plugin", "netbox_agent_api"]
    assert context["SECRET_KEY"] == "retained"
    assert path.with_name("configuration.py.before-agent-api").read_bytes() == original
    assert not setup.enable(path)
    link = tmp_path / "link.py"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="symbolic"):
        setup.enable(link)


def test_container_overlay_preserves_settings_and_ldap_location(monkeypatch):
    base = types.ModuleType("test_netbox_configuration")
    base.__file__ = "/etc/netbox/config/configuration.py"
    base.PLUGINS = ["existing"]
    base.DATABASES = {"default": {"HOST": "postgres"}}
    monkeypatch.setitem(sys.modules, base.__name__, base)
    monkeypatch.setenv("NETBOX_AGENT_BASE_CONFIGURATION", base.__name__)
    overlay = module("netbox_agent_api_configuration", ROOT / "companion/netbox_agent_api_configuration.py")
    assert overlay.PLUGINS == ["existing", "netbox_agent_api"]
    assert base.PLUGINS == ["existing"]
    assert overlay.DATABASES == base.DATABASES
    assert overlay.__file__ == base.__file__


def test_setup_cli_keeps_token_out_of_output_and_reprints_identity(tmp_path, capsys):
    from netbox_readwrite_mcp.setup import main

    path = tmp_path / "private/config.json"
    token = tmp_path / "input-token"
    token.write_text("private-test-token")
    args = ["--config", str(path)]
    main(
        [
            "configure",
            *args,
            "--netbox-url",
            "https://netbox.example.org",
            "--actor",
            "inventory",
            "--token-file",
            str(token),
            "--client",
            "opencode",
        ]
    )
    captured = capsys.readouterr()
    assert "private-test-token" not in captured.out + captured.err
    assert json.loads(captured.out)["mcp"]["netbox"]["type"] == "local"
    initial = path.read_bytes()
    main(["client-config", *args])
    assert "mcpServers" in json.loads(capsys.readouterr().out)
    assert path.read_bytes() == initial
    with pytest.raises(SystemExit):
        main(["configure", *args])
    assert "already exists" in capsys.readouterr().err
    assert path.read_bytes() == initial


def test_doctor_reads_only_and_errors_omit_private_response(tmp_path, monkeypatch, capsys):
    from netbox_readwrite_mcp import api
    from netbox_readwrite_mcp.setup import doctor, main

    path = tmp_path / "private/config.json"
    configure(path, "https://netbox.example.org", "inventory", "test-token")
    requests = []

    class Reader:
        def __init__(self, url, token):
            pass

        def get(self, path):
            requests.append(path)
            return {"body": {"netbox-version": "4.7.2"}}

    monkeypatch.setattr(api, "NetBox", Reader)
    assert doctor(path)["companion"] == "available"
    assert requests == ["status/", "plugins/agent-support/", "core/object-changes/?limit=1&fields=id"]
    main(["doctor", "--config", str(path)])
    assert json.loads(capsys.readouterr().out)["history"] == "readable"

    def refused(self, path):
        raise OSError("private-response-with-secret")

    monkeypatch.setattr(Reader, "get", refused)
    with pytest.raises(SystemExit):
        main(["doctor", "--config", str(path)])
    assert "private-response-with-secret" not in capsys.readouterr().err


def test_companion_enable_can_retry_after_backup_was_written(tmp_path, monkeypatch):
    setup = module("companion_setup_retry", ROOT / "companion/netbox_agent_api_setup.py")
    path = tmp_path / "configuration.py"
    original = b"PLUGINS = []\n"
    path.write_bytes(original)
    with monkeypatch.context() as patch:

        def fail(**kwargs):
            raise OSError("synthetic temporary-file failure")

        patch.setattr(setup.tempfile, "mkstemp", fail)
        with pytest.raises(OSError):
            setup.enable(path)
    backup = path.with_name(path.name + ".before-agent-api")
    assert path.read_bytes() == backup.read_bytes() == original
    assert setup.enable(path)
    assert backup.read_bytes() == original


@pytest.mark.parametrize("stage", ["write", "close"])
def test_companion_partial_backup_is_removed_without_touching_config(tmp_path, monkeypatch, stage):
    setup = module("companion_setup_partial", ROOT / "companion/netbox_agent_api_setup.py")
    path = tmp_path / "configuration.py"
    original = b"PLUGINS = []\n"
    path.write_bytes(original)
    backup = path.with_name(path.name + ".before-agent-api")
    opening = Path.open

    class BrokenBackup:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def write(self, value):
            if stage == "write":
                raise OSError("synthetic backup failure")
            return self.stream.write(value)

        def __exit__(self, *args):
            result = self.stream.__exit__(*args)
            if stage == "close":
                raise OSError("synthetic backup close failure")
            return result

    def open_file(selected, *args, **kwargs):
        stream = opening(selected, *args, **kwargs)
        return BrokenBackup(stream) if selected == backup else stream

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", open_file)
        with pytest.raises(OSError):
            setup.enable(path)
    assert path.read_bytes() == original and not backup.exists()
    assert setup.enable(path)


def test_companion_never_overwrites_a_conflicting_or_linked_backup(tmp_path):
    setup = module("companion_setup_conflict", ROOT / "companion/netbox_agent_api_setup.py")
    path = tmp_path / "configuration.py"
    path.write_text("PLUGINS = []\n")
    backup = path.with_name(path.name + ".before-agent-api")
    backup.write_text("different original")
    with pytest.raises(ValueError, match="backup differs"):
        setup.enable(path)
    assert backup.read_text() == "different original"
    backup.unlink()
    backup.symlink_to(path)
    with pytest.raises(ValueError, match="backup differs"):
        setup.enable(path)
    assert backup.is_symlink()
