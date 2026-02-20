from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast

import pytest

import common


@pytest.fixture
def patched_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    repo_root = tmp_path / "repo"
    config_path = repo_root / "languages.toml"
    languages_dir = repo_root / "languages"
    templates_dir = repo_root / "templates"
    jinja2_dir = languages_dir / "jinja2"
    readme_path = repo_root / "README.md"
    extension_toml_path = repo_root / "extension.toml"
    cache_dir = repo_root / ".zed-cache"

    monkeypatch.setattr(common, "REPO_ROOT", repo_root)
    monkeypatch.setattr(common, "CONFIG_PATH", config_path)
    monkeypatch.setattr(common, "LANGUAGES_DIR", languages_dir)
    monkeypatch.setattr(common, "TEMPLATES_DIR", templates_dir)
    monkeypatch.setattr(common, "JINJA2_DIR", jinja2_dir)
    monkeypatch.setattr(common, "README_PATH", readme_path)
    monkeypatch.setattr(common, "EXTENSION_TOML_PATH", extension_toml_path)
    monkeypatch.setattr(common, "CACHE_DIR", cache_dir)

    return {
        "repo_root": repo_root,
        "config_path": config_path,
        "languages_dir": languages_dir,
        "templates_dir": templates_dir,
        "jinja2_dir": jinja2_dir,
        "readme_path": readme_path,
        "extension_toml_path": extension_toml_path,
    }


def test_fail_and_fail_many(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        common.fail("boom")
    assert exc.value.code == 1
    assert "ERROR: boom" in capsys.readouterr().err

    with pytest.raises(SystemExit) as exc:
        common.fail_many(["a", "b"])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "ERROR: a" in err
    assert "ERROR: b" in err


def test_validate_paths_exist_success_and_failure(
    patched_paths: dict[str, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    existing = patched_paths["repo_root"] / "exists.txt"
    existing.parent.mkdir(parents=True, exist_ok=True)
    _ = existing.write_text("ok")
    common.validate_paths_exist(existing)

    with pytest.raises(SystemExit):
        common.validate_paths_exist(
            patched_paths["repo_root"] / "missing_dir",
            patched_paths["repo_root"] / "missing.txt",
            context="ctx",
        )
    err = capsys.readouterr().err
    assert "Validation failed: ctx" in err
    assert "directory not found" in err
    assert "file not found" in err

    with pytest.raises(SystemExit):
        common.validate_paths_exist(patched_paths["repo_root"] / "another-missing")
    assert "Validation failed" not in capsys.readouterr().err


def test_validate_generate_environment_success(patched_paths: dict[str, Path]) -> None:
    patched_paths["templates_dir"].mkdir(parents=True)
    patched_paths["languages_dir"].mkdir(parents=True)
    patched_paths["jinja2_dir"].mkdir(parents=True)
    _ = patched_paths["readme_path"].write_text("# README")
    _ = patched_paths["extension_toml_path"].write_text('description = "Jinja2 template support for 0 languages"')
    _ = patched_paths["config_path"].write_text("")
    for tmpl in common.REQUIRED_TEMPLATES:
        _ = (patched_paths["templates_dir"] / tmpl).write_text("x")

    common.validate_generate_environment()


def test_validate_generate_environment_failure(
    patched_paths: dict[str, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        common.validate_generate_environment()
    err = capsys.readouterr().err
    assert "Templates directory missing" in err
    assert "Languages directory missing" in err
    assert "README.md missing" in err
    assert "extension.toml missing" in err
    assert "Config file missing" in err

    patched_paths["templates_dir"].mkdir(parents=True)
    with pytest.raises(SystemExit):
        common.validate_generate_environment()
    assert "Template file missing" in capsys.readouterr().err


def test_validate_sync_environment(
    monkeypatch: pytest.MonkeyPatch,
    patched_paths: dict[str, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    patched_paths["config_path"].parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
    common.validate_sync_environment()

    monkeypatch.setattr(common, "CONFIG_PATH", patched_paths["repo_root"] / "no-parent" / "languages.toml")
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(SystemExit):
        common.validate_sync_environment()
    err = capsys.readouterr().err
    assert "git command not found in PATH" in err
    assert "Config parent directory missing" in err


def test_validate_config_entry_and_validate_config(capsys: pytest.CaptureFixture[str]) -> None:
    errors = common.validate_config_entry("x", {"name": "N"})
    assert "[x] missing required field: zed_language" in errors
    assert "missing detection fields" in errors[1]

    errors = common.validate_config_entry(
        "x",
        {"name": "N", "zed_language": "x", "extensions": "bad", "source": "bad"},
    )
    assert "[x] 'extensions' must be a list" in errors
    assert any("invalid source" in err for err in errors)

    errors = common.validate_config_entry(
        "x",
        {"name": "N", "zed_language": "x", "suffixes": [1]},
    )
    assert "[x] 'suffixes' must contain only strings" in errors

    with pytest.raises(SystemExit):
        common.validate_config({})
    assert "Config is empty" in capsys.readouterr().err

    with pytest.raises(SystemExit):
        invalid = cast(common.ConfigDict, {"x": {"name": "N", "zed_language": "x"}})
        common.validate_config(invalid)
    assert "missing detection fields" in capsys.readouterr().err

    assert (
        common.validate_config_entry(
            "x",
            {"name": "N", "zed_language": "x", "extensions": [], "source": common.Source.NATIVE.value},
        )
        == []
    )
    assert (
        common.validate_config_entry("y", {"name": "Y", "zed_language": "y", "suffixes": ["py"], "filenames": ["Justfile"]}) == []
    )

    common.validate_config({"x": {"name": "N", "zed_language": "x", "extensions": ["x"]}})


def test_normalize_config_and_load_config(
    monkeypatch: pytest.MonkeyPatch,
    patched_paths: dict[str, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        common.normalize_config([])
    assert "Invalid config format" in capsys.readouterr().err

    with pytest.raises(SystemExit):
        common.normalize_config({1: {"name": "N"}})
    assert "Invalid config key type" in capsys.readouterr().err

    with pytest.raises(SystemExit):
        common.normalize_config({"x": "bad"})
    assert "Invalid config entry for [x]" in capsys.readouterr().err

    valid = common.normalize_config({"x": {"name": "N", "zed_language": "x", "extensions": ["x"]}})
    assert valid["x"]["name"] == "N"

    assert common.load_config() == {}

    patched_paths["config_path"].parent.mkdir(parents=True, exist_ok=True)
    _ = patched_paths["config_path"].write_text('[x]\nname = "N"\nzed_language = "x"\nextensions = ["x"]\n')
    loaded = common.load_config()
    assert loaded["x"]["zed_language"] == "x"

    monkeypatch.setattr(common, "CONFIG_PATH", patched_paths["repo_root"] / "missing" / "languages.toml")
    with pytest.raises(SystemExit):
        common.load_and_validate_config()
    assert "Config file not found" in capsys.readouterr().err

    monkeypatch.setattr(common, "CONFIG_PATH", patched_paths["config_path"])
    loaded = common.load_and_validate_config()
    assert loaded["x"].get("extensions") == ["x"]


def test_save_config_sorts_and_defaults_source(
    patched_paths: dict[str, Path],
) -> None:
    patched_paths["config_path"].parent.mkdir(parents=True, exist_ok=True)
    config: common.ConfigDict = {
        "z": {"name": "Zed", "zed_language": "z", "extensions": ["z"]},
        "a": {"name": "Alpha", "zed_language": "a", "extensions": ["a"], "source": common.Source.NATIVE.value},
    }
    common.save_config(config)

    saved = patched_paths["config_path"].read_text()
    assert saved.index("[a]") < saved.index("[z]")
    assert 'source = "native"' in saved
    assert f'source = "{common.Source.EXTRA.value}"' in saved

    config_new: common.ConfigDict = {
        "n": {"name": "New", "zed_language": "n", "suffixes": ["py"], "filenames": ["Justfile"]},
    }
    common.save_config(config_new)
    saved = patched_paths["config_path"].read_text()
    assert 'suffixes = ["py"]' in saved
    assert 'filenames = ["Justfile"]' in saved

    invalid_detection = cast(common.ConfigDict, {"k": {"name": "Keep", "zed_language": "k", "extensions": "bad"}})
    common.save_config(invalid_detection)
    saved = patched_paths["config_path"].read_text()
    assert "extensions = []" in saved
