from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

import generate
from common import ConfigDict, LanguageConfig, Source


@pytest.fixture
def generate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    repo = tmp_path / "repo"
    languages_dir = repo / "languages"
    jinja2_dir = languages_dir / "jinja2"
    templates_dir = repo / "templates"
    readme_path = repo / "README.md"
    extension_toml_path = repo / "extension.toml"

    jinja2_dir.mkdir(parents=True)
    templates_dir.mkdir(parents=True)
    _ = readme_path.write_text("""<summary>Click to expand the full list of 0 supported languages</summary>
<!-- GENERATED_MODE_START -->
OLD MODE
<!-- GENERATED_MODE_END -->
<!-- LANGUAGES_TABLE_START -->
OLD
<!-- LANGUAGES_TABLE_END -->
""")
    _ = extension_toml_path.write_text(
        'description = "Jinja2 template support for 0 languages (Python, YAML, TOML, Markdown, HTML, JS, SQL, and more)"\n'
    )

    _ = (templates_dir / "config.toml.template").write_text('name = "$name"\npath_suffixes = [$suffixes]\n')
    _ = (templates_dir / "injections.scm.template").write_text("(language) @injection.language # $zed_language\n")
    for name in ["highlights.scm", "brackets.scm", "indents.scm"]:
        _ = (jinja2_dir / name).write_text(name)

    monkeypatch.setattr(generate, "LANGUAGES_DIR", languages_dir)
    monkeypatch.setattr(generate, "JINJA2_DIR", jinja2_dir)
    monkeypatch.setattr(generate, "TEMPLATES_DIR", templates_dir)
    monkeypatch.setattr(generate, "README_PATH", readme_path)
    monkeypatch.setattr(generate, "EXTENSION_TOML_PATH", extension_toml_path)
    monkeypatch.setattr(generate, "config_template", None)
    monkeypatch.setattr(generate, "injections_template", None)

    return {
        "repo": repo,
        "languages_dir": languages_dir,
        "jinja2_dir": jinja2_dir,
        "templates_dir": templates_dir,
        "readme_path": readme_path,
        "extension_toml_path": extension_toml_path,
    }


def test_load_templates_and_render(generate_env: dict[str, Path]) -> None:
    cfg = generate.load_template("config.toml")
    assert "$name" in cfg.template

    generate.init_templates()
    config_toml = generate.generate_config_toml("Lang", ["b", "a"])
    assert 'name = "Lang"' in config_toml
    assert '"a.j2"' in config_toml

    injections = generate.generate_injections_scm("yaml")
    assert "yaml" in injections


def test_generate_helpers_and_folder_ops(generate_env: dict[str, Path]) -> None:
    assert generate.generate_path_suffixes(["yml"]) == ["yml.jinja", "yml.jinja2", "yml.j2"]
    assert generate.format_extensions_for_readme(["b", "a"]) == "`.a.*`, `.b.*`"
    assert generate.get_detection_tokens({"name": "X", "zed_language": "x", "suffixes": ["py"], "filenames": ["Justfile"]}) == [
        "py",
        "Justfile",
    ]
    assert generate.get_detection_tokens({"name": "X", "zed_language": "x", "suffixes": ["py"]}) == ["py"]
    assert generate.get_detection_tokens({"name": "X", "zed_language": "x", "filenames": ["Justfile"]}) == ["Justfile"]
    assert generate.format_detection_for_readme(
        {"name": "X", "zed_language": "x", "suffixes": ["py"], "filenames": ["Justfile"]}
    ) == ("`.py.*`, `Justfile.*`")
    assert generate.format_detection_for_readme({"name": "X", "zed_language": "x", "suffixes": ["py"]}) == "`.py.*`"
    assert generate.format_detection_for_readme({"name": "X", "zed_language": "x", "filenames": ["Justfile"]}) == ("`Justfile.*`")
    assert generate.has_detection_tokens({"name": "X", "zed_language": "x", "extensions": ["x"]})
    assert not generate.has_detection_tokens({"name": "X", "zed_language": "x", "extensions": []})

    target = generate_env["languages_dir"] / "x_jinja"
    target.mkdir(parents=True)
    generate.copy_template_files(target)
    assert (target / "highlights.scm").exists()

    (generate_env["jinja2_dir"] / "indents.scm").unlink()
    target_missing = generate_env["languages_dir"] / "y_jinja"
    target_missing.mkdir(parents=True)
    generate.copy_template_files(target_missing)
    assert not (target_missing / "indents.scm").exists()

    generate.init_templates()
    info: LanguageConfig = {"name": "X", "zed_language": "x", "extensions": ["x"]}
    generate.generate_language_folder("x", info)
    assert (target / "config.toml").exists()
    assert (target / "injections.scm").exists()

    assert generate.delete_language_folder("x") is True
    assert generate.delete_language_folder("x") is False


def test_get_existing_language_folders_and_source_logic(
    monkeypatch: pytest.MonkeyPatch,
    generate_env: dict[str, Path],
) -> None:
    assert generate.get_existing_language_folders() == set()

    (generate_env["languages_dir"] / "aa_jinja").mkdir(parents=True)
    (generate_env["languages_dir"] / "bb").mkdir(parents=True)
    assert generate.get_existing_language_folders() == {"aa"}

    info: LanguageConfig = {"name": "N", "zed_language": "n", "extensions": ["n"]}
    assert generate.normalize_source(info) == "extra"
    info["source"] = Source.NATIVE
    assert generate.normalize_source(info) == "native"
    info["source"] = Source.EXTENSION.value
    assert generate.normalize_source(info) == "extension"

    args = generate.GenerateArgs()
    args.all = True
    assert generate.should_include(info, args)
    empty_detection: LanguageConfig = {"name": "E", "zed_language": "e", "extensions": [], "source": Source.NATIVE.value}
    assert not generate.should_include(empty_detection, args)
    args.all = False
    args.native = True
    assert not generate.should_include(info, args)
    info["source"] = Source.NATIVE.value
    assert generate.should_include(info, args)
    args.native = False
    args.ext = True
    info["source"] = Source.EXTENSION.value
    assert generate.should_include(info, args)
    args.ext = False
    assert generate.should_include(info, args)
    info["source"] = "extra"
    assert not generate.should_include(info, args)

    args.native = True
    args.ext = True
    assert not generate.should_include(info, args)

    monkeypatch.setattr(generate, "LANGUAGES_DIR", generate_env["repo"] / "missing-langs")
    assert generate.get_existing_language_folders() == set()


def test_generate_languages_and_readme_updates(
    monkeypatch: pytest.MonkeyPatch,
    generate_env: dict[str, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    (generate_env["languages_dir"] / "old_jinja").mkdir(parents=True)
    (generate_env["languages_dir"] / "a_jinja").mkdir(parents=True)
    config: ConfigDict = {
        "a": {"name": "A", "zed_language": "a", "extensions": ["a"], "source": "native"},
        "b": {"name": "B", "zed_language": "b", "extensions": ["b"], "source": "extra"},
    }
    args = generate.GenerateArgs()

    generate.init_templates()
    generated, skipped, deleted = generate.generate_languages(config, args)
    assert (generated, skipped, deleted) == (1, 1, 1)

    table = generate.generate_readme_table(config, args)
    assert "A-Jinja" in table
    assert "B-Jinja" not in table

    table_detection = generate.generate_readme_table(
        {"j": {"name": "Just", "zed_language": "just", "suffixes": ["just"], "filenames": ["Justfile"], "source": "native"}},
        args,
    )
    assert "`.just.*`" in table_detection
    assert "`Justfile.*`" in table_detection

    assert (
        generate.update_readme(table, 1, "native + extension (default)", "all native and extension languages (extra excluded).")
        is True
    )
    readme = generate_env["readme_path"].read_text()
    assert "full list of 1 supported languages" in readme
    assert "A-Jinja" in readme
    assert "**Generated selection:** `native + extension (default)`" in readme
    assert "Literal scope: all native and extension languages (extra excluded)." in readme

    source_categories = generate.infer_selected_source_categories(config, args)
    assert source_categories == ["native"]

    mixed_config: ConfigDict = {
        "n": {"name": "N", "zed_language": "n", "extensions": ["n"], "source": "native"},
        "e": {"name": "E", "zed_language": "e", "extensions": ["e"], "source": "extension"},
        "x": {"name": "X", "zed_language": "x", "extensions": ["x"], "source": "extra"},
    }
    all_args = generate.GenerateArgs()
    all_args.all = True
    assert generate.infer_selected_source_categories(mixed_config, all_args) == ["native", "extension", "extra"]

    assert generate.format_human_list([]) == ""
    assert generate.format_human_list(["native"]) == "native"
    assert generate.format_human_list(["native", "extension"]) == "native and extension"
    assert generate.format_human_list(["native", "extension", "extra"]) == "native, extension, and extra"

    assert generate.update_extension_manifest(1, source_categories) is True
    manifest = generate_env["extension_toml_path"].read_text()
    assert "support for 1 languages" in manifest
    assert "across Zed's native category" in manifest

    assert generate.update_extension_manifest(1, ["none"]) is True
    manifest = generate_env["extension_toml_path"].read_text()
    assert "across Zed's configured" in manifest

    generate.print_stats(config)
    out = capsys.readouterr().out
    assert "Native: 1" in out
    assert "Extra: 1" in out

    config["c"] = {"name": "C", "zed_language": "c", "extensions": ["c"], "enabled": True}
    generate.print_stats(config)
    out = capsys.readouterr().out
    assert "Native: 2" in out

    args = generate.GenerateArgs()
    generate.print_filter_info(args)
    assert "native + extension (default)" in capsys.readouterr().out
    args.native = True
    generate.print_filter_info(args)
    assert "native only" in capsys.readouterr().out
    args.ext = True
    generate.print_filter_info(args)
    assert "native + extension" in capsys.readouterr().out
    args = generate.GenerateArgs()
    args.all = True
    generate.print_filter_info(args)
    assert "all (native + extension + extra)" in capsys.readouterr().out

    args = generate.GenerateArgs()
    assert generate.get_filter_label(args) == "native + extension (default)"
    assert generate.get_filter_scope(args) == "all native and extension languages (extra excluded)."
    args.all = True
    assert generate.get_filter_scope(args) == "all native, extension, and extra languages."
    args.all = False
    args.native = True
    args.ext = True
    assert generate.get_filter_scope(args) == "all native and extension languages."
    args.ext = False
    assert generate.get_filter_scope(args) == "only native languages."
    args.native = False
    args.ext = True
    assert generate.get_filter_label(args) == "extension only"
    assert generate.get_filter_scope(args) == "only extension languages."
    assert generate.infer_selected_source_categories({}, args) == ["none"]

    bad_readme = generate_env["repo"] / "bad.md"
    bad_readme.write_text("no markers")
    monkeypatch.setattr(generate, "README_PATH", bad_readme)
    with pytest.raises(SystemExit):
        generate.update_readme("x", 1, "native + extension", "all native and extension languages.")

    with pytest.raises(SystemExit):
        generate.replace_marked_block("x <!-- B --> y <!-- A -->", "<!-- A -->", "<!-- B -->", "new")

    bad_manifest = generate_env["repo"] / "bad_extension.toml"
    bad_manifest.write_text('name = "Jinja Universal"\n')
    monkeypatch.setattr(generate, "EXTENSION_TOML_PATH", bad_manifest)
    with pytest.raises(SystemExit):
        generate.update_extension_manifest(1, ["native"])


def test_sort_parse_and_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {}

    monkeypatch.setattr(
        generate, "load_and_validate_config", lambda: {"x": {"name": "X", "zed_language": "x", "extensions": ["x"]}}
    )
    monkeypatch.setattr(generate, "save_config", lambda cfg: called.setdefault("saved", cfg))
    generate.sort_config()
    assert "saved" in called

    monkeypatch.setattr(sys, "argv", ["generate.py", "--native"])
    args = generate.parse_arguments()
    assert args.native is True

    monkeypatch.setattr(generate, "parse_arguments", lambda: generate.GenerateArgs())
    monkeypatch.setattr(generate, "validate_generate_environment", lambda: called.setdefault("validated", True))
    monkeypatch.setattr(
        generate, "load_and_validate_config", lambda: {"x": {"name": "X", "zed_language": "x", "extensions": ["x"]}}
    )
    monkeypatch.setattr(generate, "init_templates", lambda: called.setdefault("init", True))
    monkeypatch.setattr(generate, "print_stats", lambda _cfg: called.setdefault("stats", True))
    monkeypatch.setattr(generate, "print_filter_info", lambda _args: called.setdefault("filters", True))
    monkeypatch.setattr(generate, "generate_languages", lambda _cfg, _args: (2, 1, 1))
    monkeypatch.setattr(generate, "generate_readme_table", lambda _cfg, _args: "TABLE")
    monkeypatch.setattr(generate, "update_readme", lambda _table, _count, _label, _scope: True)
    monkeypatch.setattr(generate, "update_extension_manifest", lambda _count, _categories: True)
    assert generate.main() == 0

    monkeypatch.setattr(generate, "parse_arguments", lambda: generate.GenerateArgs())
    monkeypatch.setattr(generate, "generate_languages", lambda _cfg, _args: (1, 0, 0))
    assert generate.main() == 0

    sort_args = generate.GenerateArgs()
    sort_args.sort = True
    monkeypatch.setattr(generate, "parse_arguments", lambda: sort_args)
    monkeypatch.setattr(generate, "sort_config", lambda: called.setdefault("sorted", True))
    assert generate.main() == 0
    assert called["sorted"] is True


def test_generate_module_main_guard_help(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["generate.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        _ = runpy.run_module("generate", run_name="__main__")
    assert exc.value.code == 0
