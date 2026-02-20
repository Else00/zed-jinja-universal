from __future__ import annotations

import json
import runpy
import sys
import urllib.request
from pathlib import Path
from types import TracebackType
from typing import cast

import pytest

import sync_zed_languages as sync
from common import ConfigDict, Source


def li(
    lang_id: str,
    zed_language: str | None = None,
    source: Source = Source.EXTENSION,
    extensions: list[str] | None = None,
    syntax_signature: str = "",
) -> sync.LanguageInfo:
    return sync.LanguageInfo(
        id=lang_id,
        name=lang_id.title(),
        zed_language=zed_language or lang_id,
        extensions=extensions or [],
        source=source,
        syntax_signature=syntax_signature,
    )


@pytest.fixture
def sync_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    cache_dir = tmp_path / ".zed-cache"
    zed_main = cache_dir / "zed"
    zed_ext = cache_dir / "extensions"
    monkeypatch.setattr(sync, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(sync, "ZED_MAIN_REPO_PATH", zed_main)
    monkeypatch.setattr(sync, "ZED_EXT_REPO_PATH", zed_ext)
    return {"cache_dir": cache_dir, "zed_main": zed_main, "zed_ext": zed_ext}


def test_run_cmd() -> None:
    code, out, err = sync.run_cmd([sys.executable, "-c", "print('ok')"])
    assert code == 0
    assert out.strip() == "ok"
    assert err == ""


def test_ensure_repo_existing_and_clone_branches(
    monkeypatch: pytest.MonkeyPatch,
    sync_paths: dict[str, Path],
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    monkeypatch.setattr(sync, "run_cmd", lambda _cmd, cwd=None: (0, "", ""))
    assert sync.ensure_repo("url", repo, "repo")

    calls: list[list[str]] = []

    def fake_run_cmd(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
        calls.append(cmd)
        if cmd[1] == "pull":
            return (1, "", "nope")
        if cmd[1] == "clone":
            return (0, "", "")
        return (0, "", "")

    monkeypatch.setattr(sync, "run_cmd", fake_run_cmd)
    assert sync.ensure_repo("url", repo, "repo")
    assert any(cmd[1] == "clone" for cmd in calls)

    missing_repo = tmp_path / "missing"
    monkeypatch.setattr(sync, "run_cmd", lambda _cmd, cwd=None: (1, "", "clone error"))
    assert not sync.ensure_repo("url", missing_repo, "repo")


def test_ensure_zed_repos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync, "ensure_repo", lambda *_args, **_kwargs: True)
    commands: list[list[str]] = []

    def record_run_cmd(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
        _ = cwd
        commands.append(cmd)
        return (0, "", "")

    monkeypatch.setattr(sync, "run_cmd", record_run_cmd)
    assert sync.ensure_zed_main_repo()
    assert commands[0][1] == "sparse-checkout"
    assert commands[1][1] == "checkout"

    monkeypatch.setattr(sync, "ensure_repo", lambda *_args, **_kwargs: False)
    assert not sync.ensure_zed_main_repo()

    monkeypatch.setattr(sync, "ensure_repo", lambda *_args, **_kwargs: True)
    assert sync.ensure_extensions_repo()


def test_fetch_text_and_url_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool:
            _ = (exc_type, exc, tb)
            return False

        def read(self) -> bytes:
            return b"hello"

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    assert sync.fetch_text("https://example.com") == "hello"

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("bad")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert sync.fetch_text("https://example.com") is None

    raw = sync.github_url_to_raw("https://github.com/org/repo.git", "main", "a/b")
    assert raw == "https://raw.githubusercontent.com/org/repo/main/a/b"
    raw_no_git = sync.github_url_to_raw("https://github.com/org/repo", "main", "a/b")
    assert raw_no_git == "https://raw.githubusercontent.com/org/repo/main/a/b"


def test_parse_toml_value_and_extract_extensions() -> None:
    content = 'name = "X"\npath_suffixes = [".py", "*.jinja", "x/y", "txt"]\nnum = 3\n'
    assert sync.parse_toml_value(content, "missing") is None
    assert sync.parse_toml_value(content, "name") == "X"
    assert sync.parse_toml_value(content, "path_suffixes") == [".py", "*.jinja", "x/y", "txt"]
    assert sync.parse_toml_value(content, "num") == "3"
    assert sync.parse_toml_value_regex_fallback(content, "missing") is None
    assert sync.parse_toml_value_regex_fallback(content, "name") == "X"
    assert sync.parse_toml_value_regex_fallback(content, "path_suffixes") == [".py", "*.jinja", "x/y", "txt"]
    assert sync.parse_toml_value_regex_fallback('x = [["a"], ["b"]]', "x") == ["a", "b"]
    assert sync.parse_toml_value_regex_fallback(content, "num") == "3"
    nested = 'x = [["a"], ["b"]]\n'
    assert sync.parse_toml_value(nested, "x") == ["a", "b"]
    malformed = 'x = ["a"\n'
    assert sync.parse_toml_value(malformed, "x") == []

    multiline = """
name = "Docker Compose"
path_suffixes = [
  "docker-compose.yml",
  "compose.yaml",
]
"""
    assert sync.parse_toml_value(multiline, "path_suffixes") == ["docker-compose.yml", "compose.yaml"]
    assert sync.get_grammar_extensions(multiline) == ["docker-compose.yml", "compose.yaml"]

    assert sync.flatten_string_list(["a", ["b", ["c"]], 1]) == ["a", "b", "c"]

    exts = sync.extract_extensions([".py", "*.jinja", "*abc", "a/b", "", "txt", ".py"])
    assert exts == ["py", "jinja", "abc", "txt"]


def test_get_native_languages(monkeypatch: pytest.MonkeyPatch, sync_paths: dict[str, Path]) -> None:
    monkeypatch.setattr(sync, "ensure_zed_main_repo", lambda: False)
    with pytest.raises(SystemExit):
        sync.get_native_languages()

    monkeypatch.setattr(sync, "ensure_zed_main_repo", lambda: True)
    langs_dir = sync_paths["zed_main"] / "crates" / "languages" / "src"
    with pytest.raises(SystemExit):
        sync.get_native_languages()

    langs_dir.mkdir(parents=True)
    _ = (langs_dir / "not-a-dir.txt").write_text("x")
    good = langs_dir / "python"
    good.mkdir()
    _ = (good / "config.toml").write_text('name = "Python"\npath_suffixes = [".py"]\n')
    noconfig = langs_dir / "noconfig"
    noconfig.mkdir()
    broken = langs_dir / "broken"
    broken.mkdir()
    _ = (broken / "config.toml").write_text('name = "Broken"\n')

    original = sync.parse_toml_value

    def patched_parse(content: str, key: str):
        if "Broken" in content:
            raise ValueError("bad")
        return original(content, key)

    monkeypatch.setattr(sync, "parse_toml_value", patched_parse)
    langs = sync.get_native_languages()
    assert len(langs) == 1
    assert langs[0].id == "python"

    for child in langs_dir.iterdir():
        if child.is_dir():
            for sub in child.iterdir():
                sub.unlink()
            child.rmdir()
    with pytest.raises(SystemExit):
        sync.get_native_languages()


def test_parse_gitmodules(monkeypatch: pytest.MonkeyPatch, sync_paths: dict[str, Path]) -> None:
    with pytest.raises(SystemExit):
        sync.parse_gitmodules()

    sync_paths["zed_ext"].mkdir(parents=True)
    gitmodules = sync_paths["zed_ext"] / ".gitmodules"
    _ = gitmodules.write_text('[submodule "extensions/a"]\npath = extensions/a\n')
    with pytest.raises(SystemExit):
        sync.parse_gitmodules()

    _ = gitmodules.write_text("""[submodule "extensions/"]
path = invalid
[submodule "extensions/a"]
path = extensions/a
url = https://github.com/o/a.git
[submodule "extensions/b"]
path = extensions/b
url = https://github.com/o/b.git
""")
    parsed = sync.parse_gitmodules()
    assert parsed["a"].endswith("a.git")
    assert parsed["b"].endswith("b.git")


def test_extension_parsing_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sync, "fetch_text", lambda url: "ok" if "/main/" in url else None)
    assert sync.fetch_extension_toml("https://github.com/o/r.git") == ("ok", "main")

    monkeypatch.setattr(sync, "fetch_text", lambda url: "ok" if "/master/" in url else None)
    assert sync.fetch_extension_toml("https://github.com/o/r.git") == ("ok", "master")

    monkeypatch.setattr(sync, "fetch_text", lambda _url: None)
    assert sync.fetch_extension_toml("https://github.com/o/r.git") is None

    grammars = sync.extract_grammars("[grammars.python]\n[grammars.typescript]\n")
    assert grammars == ["python", "typescript"]
    assert "languages/a/config.toml" in sync.get_config_paths_for_grammar("a")
    assert "languages/BQN/config.toml" in sync.get_config_paths_for_grammar("bqn")

    def fetch_for_helpers(url: str) -> str | None:
        if "/languages/a/" in url:
            return 'name = "L"\npath_suffixes = [".l"]\n'
        return None

    monkeypatch.setattr(sync, "fetch_text", fetch_for_helpers)
    cfg = sync.fetch_grammar_config("https://github.com/o/r.git", "main", "a")
    assert cfg is not None
    none_cfg = sync.fetch_grammar_config("https://github.com/o/r.git", "main", "missing")
    assert none_cfg is None

    assert sync.get_display_name("foo_bar", None) == "Foo Bar"
    assert sync.get_display_name("foo", 'name = "X"') == "X"
    assert sync.get_display_name("foo", 'name = ["X"]') == "Foo"


def test_fetch_grammar_config_finds_uppercase_language_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fetch_uppercase(url: str) -> str | None:
        if "/languages/BQN/config.toml" in url:
            return 'name = "BQN"\npath_suffixes = ["bqn"]\n'
        return None

    monkeypatch.setattr(sync, "fetch_text", fetch_uppercase)
    cfg = sync.fetch_grammar_config("https://github.com/o/r.git", "main", "bqn")
    assert cfg is not None
    assert sync.get_grammar_extensions(cfg) == ["bqn"]
    assert sync.get_grammar_extensions(None) == []
    assert sync.get_grammar_extensions('path_suffixes = [".x"]') == ["x"]
    assert sync.get_grammar_extensions("path_suffixes = 2") == []
    assert sync.make_repository_signature("https://github.com/O/R.git/", "dial") == "https://github.com/o/r#dial"
    assert sync.make_repository_signature("https://github.com/O/R.git/") == "https://github.com/o/r"
    assert sync.derive_extension_grammar_signature({"repository": "https://github.com/o/r", "path": "dial"}) == (
        "https://github.com/o/r#dial"
    )
    assert sync.derive_extension_grammar_signature({"repository": "https://github.com/o/r"}) == "https://github.com/o/r"
    assert sync.derive_extension_grammar_signature({"path": "dialect"}) == ""
    assert sync.derive_extension_grammar_signature("bad") == ""

    cargo = tmp_path / "Cargo.toml"
    _ = cargo.write_text(
        """
[workspace]
[workspace.dependencies]
tree-sitter-yaml = { git = "https://github.com/zed-industries/tree-sitter-yaml", rev = "x" }
tree-sitter-typescript = { git = "https://github.com/zed-industries/tree-sitter-typescript", path = "dialects/tsx" }
other = "1.0"
"""
    )
    monkeypatch.setattr(sync, "ensure_zed_main_repo", lambda: True)
    monkeypatch.setattr(sync, "ZED_MAIN_CARGO_PATH", cargo)
    signatures = sync.parse_native_tree_sitter_git_signatures()
    assert signatures == {
        "https://github.com/zed-industries/tree-sitter-typescript#dialects/tsx",
        "https://github.com/zed-industries/tree-sitter-yaml",
    }
    assert sync.extract_native_tree_sitter_git_signatures(
        {"tree-sitter-yaml": {"git": "https://github.com/zed-industries/tree-sitter-yaml"}}
    ) == {"https://github.com/zed-industries/tree-sitter-yaml"}

    with pytest.raises(SystemExit):
        sync.extract_native_tree_sitter_git_signatures({"tree-sitter-yaml": {"rev": "x"}})

    monkeypatch.setattr(sync, "ensure_zed_main_repo", lambda: False)
    with pytest.raises(SystemExit):
        sync.parse_native_tree_sitter_git_signatures()

    missing_cargo = tmp_path / "missing.toml"
    monkeypatch.setattr(sync, "ensure_zed_main_repo", lambda: True)
    monkeypatch.setattr(sync, "ZED_MAIN_CARGO_PATH", missing_cargo)
    with pytest.raises(SystemExit):
        sync.load_zed_workspace_dependencies()

    invalid_workspace = tmp_path / "invalid_workspace.toml"
    _ = invalid_workspace.write_text("[root]\n")
    monkeypatch.setattr(sync, "ZED_MAIN_CARGO_PATH", invalid_workspace)
    with pytest.raises(SystemExit):
        sync.load_zed_workspace_dependencies()

    invalid_dependencies = tmp_path / "invalid_dependencies.toml"
    _ = invalid_dependencies.write_text("[workspace]\nname = 'x'\n")
    monkeypatch.setattr(sync, "ZED_MAIN_CARGO_PATH", invalid_dependencies)
    with pytest.raises(SystemExit):
        sync.load_zed_workspace_dependencies()

    monkeypatch.setattr(sync, "fetch_grammar_config", lambda *_args, **_kwargs: 'name = "A"\npath_suffixes = [".a"]\n')
    built = sync.build_extension_language_info("a-lang", "url", "main", syntax_signature="sig")
    assert built.id == "a_lang"
    assert built.name == "A"
    assert built.extensions == ["a"]
    assert built.syntax_signature == "sig"


def test_extension_capability_helpers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert sync.normalize_repo_url("https://github.com/O/R.git/") == "https://github.com/o/r"
    assert sync.parse_extension_table_keys({}, "grammars") == []
    assert sync.parse_extension_table_keys({"grammars": {"b": {}, "a": {}, 1: {}}}, "grammars") == ["a", "b"]
    assert sync.parse_extension_table_keys("x", "grammars") == []

    repos = sync.parse_extension_grammar_repositories(
        {
            "grammars": {
                "a": {"repository": "https://github.com/O/R.git"},
                "b": {"repository": "https://github.com/o/r"},
                "c": {"repository": 2},
            }
        }
    )
    assert repos == ["https://github.com/o/r"]
    assert sync.parse_extension_grammar_repositories("x") == []
    assert sync.parse_extension_grammar_repositories({"grammars": "x"}) == []
    assert sync.parse_extension_grammar_repositories(
        {"grammars": {"x": "no", "y": {"repository": "https://github.com/o/y"}}}
    ) == ["https://github.com/o/y"]
    assert sync.dedupe_strings(["a", "b", "a"]) == ["a", "b"]
    assert sync.split_path_suffixes([".py", "*.jinja", "Justfile", "docker-compose.yml", ".JUSTFILE.*", "x/y", ""]) == (
        [".py", "*.jinja"],
        ["Justfile", "docker-compose.yml"],
        [".JUSTFILE.*", "x/y"],
    )

    monkeypatch.setattr(sync, "fetch_grammar_config", lambda *_args, **_kwargs: 'path_suffixes = [".py", "Justfile", "*.j2"]')
    targets = sync.get_grammar_detection_targets("url", "main", "python")
    assert targets == ([".py", "Justfile", "*.j2"], [".py", "*.j2"], ["Justfile"], [])
    monkeypatch.setattr(sync, "fetch_grammar_config", lambda *_args, **_kwargs: None)
    assert sync.get_grammar_detection_targets("url", "main", "python") == ([], [], [], [])
    monkeypatch.setattr(sync, "fetch_grammar_config", lambda *_args, **_kwargs: 'name = "X"')
    assert sync.get_grammar_detection_targets("url", "main", "python") == ([], [], [], [])

    monkeypatch.setattr(sync, "fetch_extension_toml", lambda _repo: None)
    none_cap = sync.parse_extension_capability("x", "https://github.com/o/x.git")
    assert none_cap.has_extension_toml is False
    assert none_cap.grammar_names == []
    assert none_cap.full_filenames == []

    monkeypatch.setattr(sync, "fetch_grammar_config", lambda *_args, **_kwargs: 'path_suffixes = [".py", "Dockerfile"]')
    monkeypatch.setattr(sync, "fetch_extension_toml", lambda _repo: ("[grammars.python]\nbad = [", "main"))
    bad_cap = sync.parse_extension_capability("x", "https://github.com/o/x.git")
    assert bad_cap.has_extension_toml is True
    assert bad_cap.grammar_names == ["python"]
    assert bad_cap.language_servers == []
    assert bad_cap.suffixes == [".py"]
    assert bad_cap.full_filenames == ["Dockerfile"]

    valid_toml = """
[grammars.a]
repository = "https://github.com/O/A.git"

[grammars.b]
repository = "https://github.com/o/a"

[language_servers.zls]
"""
    monkeypatch.setattr(
        sync,
        "fetch_grammar_config",
        lambda _repo, _branch, grammar: (
            'path_suffixes = [".a", "Afile"]' if grammar == "a" else 'path_suffixes = [".b", "docker-compose.yml", ".JUSTFILE.*"]'
        ),
    )
    monkeypatch.setattr(sync, "fetch_extension_toml", lambda _repo: (valid_toml, "main"))
    good_cap = sync.parse_extension_capability("ext-a", "https://github.com/o/ext-a.git")
    assert good_cap.grammar_names == ["a", "b"]
    assert good_cap.grammar_repositories == ["https://github.com/o/a"]
    assert good_cap.language_servers == ["zls"]
    assert good_cap.path_suffixes == [".a", "Afile", ".b", "docker-compose.yml", ".JUSTFILE.*"]
    assert good_cap.suffixes == [".a", ".b"]
    assert good_cap.full_filenames == ["Afile", "docker-compose.yml"]
    assert good_cap.other_patterns == [".JUSTFILE.*"]

    as_dict = sync.capability_to_json_dict(good_cap)
    assert as_dict["category"] == "grammar+lsp"
    assert as_dict["full_filenames"] == ["Afile", "docker-compose.yml"]

    monkeypatch.setattr(sync, "ensure_extensions_repo", lambda: True)
    monkeypatch.setattr(sync, "parse_gitmodules", lambda: {"b": "url2", "a": "url1", "c": "url3", "d": "url4"})
    monkeypatch.setattr(
        sync,
        "parse_extension_capability",
        lambda name, _url: sync.ExtensionCapability(
            extension_id=name,
            repo_url="repo",
            has_extension_toml=name != "d",
            grammar_names=["g"] if name in {"a", "c"} else [],
            grammar_repositories=["https://github.com/zed-industries/tree-sitter-go"] if name in {"a", "c"} else [],
            language_servers=["lsp"] if name == "b" else [],
        ),
    )
    caps = sync.collect_extension_capabilities()
    assert [cap.extension_id for cap in caps] == ["a", "b", "c", "d"]

    sync.print_extension_capability_report(caps)
    out = capsys.readouterr().out
    assert "EXTENSION CAPABILITY REPORT" in out
    assert "LSP-only: 1" in out
    assert "Shared grammar repositories (first 20):" in out
    assert "Missing extension.toml (first 20): d" in out

    sync.print_extension_capability_report(
        [
            sync.ExtensionCapability(
                extension_id="solo",
                repo_url="repo",
                has_extension_toml=True,
                grammar_names=["g"],
                grammar_repositories=["https://github.com/org/one"],
                language_servers=[],
            )
        ]
    )
    out = capsys.readouterr().out
    assert "Shared grammar repositories: 0" in out
    assert "LSP-only: 0" in out

    tmp_json = tmp_path / "capabilities.json"
    sync.write_extension_capability_json(caps, tmp_json)
    payload = cast(list[dict[str, object]], json.loads(tmp_json.read_text()))
    assert payload[0]["extension_id"] == "a"
    assert "full_filenames" in payload[0]

    monkeypatch.setattr(sync, "ensure_extensions_repo", lambda: False)
    with pytest.raises(SystemExit):
        sync.collect_extension_capabilities()

    monkeypatch.setattr(sync, "ensure_extensions_repo", lambda: True)
    monkeypatch.setattr(sync, "parse_gitmodules", lambda: {"a": "url1"})

    def always_raise(_name: str, _url: str) -> sync.ExtensionCapability:
        raise RuntimeError("x")

    monkeypatch.setattr(sync, "parse_extension_capability", always_raise)
    with pytest.raises(SystemExit):
        sync.collect_extension_capabilities()

    monkeypatch.setattr(sync, "parse_gitmodules", lambda: {})
    with pytest.raises(SystemExit):
        sync.collect_extension_capabilities()

    many = {f"x{i}": "url" for i in range(100)}
    monkeypatch.setattr(sync, "parse_gitmodules", lambda: many)
    monkeypatch.setattr(
        sync,
        "parse_extension_capability",
        lambda name, _url: sync.ExtensionCapability(
            extension_id=name,
            repo_url="repo",
            has_extension_toml=True,
            grammar_names=[],
            grammar_repositories=[],
            language_servers=[],
        ),
    )
    _ = sync.collect_extension_capabilities()
    assert "Checked 100/100..." in capsys.readouterr().out


def test_get_extension_language_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync, "fetch_extension_toml", lambda _repo: None)
    assert sync.get_extension_language_info("x", "url") is None

    monkeypatch.setattr(sync, "fetch_extension_toml", lambda _repo: ("bad =", "main"))
    monkeypatch.setattr(sync, "extract_grammars", lambda _content: [])
    assert sync.get_extension_language_info("x", "url") is None

    monkeypatch.setattr(sync, "fetch_extension_toml", lambda _repo: ('name = "X"', "main"))
    monkeypatch.setattr(sync, "extract_grammars", lambda _content: ["a"])
    monkeypatch.setattr(
        sync,
        "build_extension_language_info",
        lambda grammar, _repo, _branch, syntax_signature="": li(grammar, syntax_signature=syntax_signature),
    )
    langs = sync.get_extension_language_info("x", "url")
    assert langs is not None
    assert langs[0].syntax_signature == ""

    monkeypatch.setattr(sync, "extract_grammars", lambda _content: ["a", "b"])
    monkeypatch.setattr(
        sync,
        "build_extension_language_info",
        lambda grammar, _repo, _branch, syntax_signature="": li(grammar, syntax_signature=syntax_signature),
    )
    langs = sync.get_extension_language_info("x", "url")
    assert langs is not None
    assert [lang.id for lang in langs] == ["a", "b"]
    assert langs[0].syntax_signature == ""

    ext_toml = """
[grammars.docker-compose]
repository = "https://github.com/zed-industries/tree-sitter-yaml"
"""
    monkeypatch.setattr(sync, "fetch_extension_toml", lambda _repo: (ext_toml, "main"))
    langs = sync.get_extension_language_info("x", "url")
    assert langs is not None
    assert langs[0].syntax_signature == "https://github.com/zed-industries/tree-sitter-yaml"


def test_get_extension_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync, "ensure_extensions_repo", lambda: False)
    with pytest.raises(SystemExit):
        sync.get_extension_languages()

    monkeypatch.setattr(sync, "ensure_extensions_repo", lambda: True)
    monkeypatch.setattr(sync, "parse_gitmodules", lambda: {"a": "urlA", "b": "urlB"})
    monkeypatch.setattr(sync, "get_extension_language_info", lambda name, _url: [li(name)])
    langs = sync.get_extension_languages()
    assert sorted(lang.id for lang in langs) == ["a", "b"]

    many = {f"x{i}": f"url{i}" for i in range(100)}
    monkeypatch.setattr(sync, "parse_gitmodules", lambda: many)
    monkeypatch.setattr(sync, "get_extension_language_info", lambda name, _url: [li(name)])
    langs = sync.get_extension_languages()
    assert len(langs) == 100

    monkeypatch.setattr(sync, "parse_gitmodules", lambda: {"a": "urlA", "b": "urlB"})

    def raise_for_all(_name: str, _url: str):
        raise RuntimeError("fetch")

    monkeypatch.setattr(sync, "get_extension_language_info", raise_for_all)
    with pytest.raises(SystemExit):
        sync.get_extension_languages()

    monkeypatch.setattr(sync, "parse_gitmodules", lambda: {"a": "urlA"})
    monkeypatch.setattr(sync, "get_extension_language_info", lambda _name, _url: None)
    with pytest.raises(SystemExit):
        sync.get_extension_languages()


def test_filter_extensions_reusing_native_syntax() -> None:
    native_signatures = {"https://github.com/zed-industries/tree-sitter-yaml"}
    ext = [
        li("docker_compose", syntax_signature="https://github.com/zed-industries/tree-sitter-yaml"),
        li("helm", syntax_signature="https://github.com/ngalaiko/tree-sitter-go-template#dialects/helm"),
    ]
    kept, skipped = sync.filter_extensions_reusing_native_syntax(native_signatures, ext)
    assert [lang.id for lang in kept] == ["helm"]
    assert [lang.id for lang in skipped] == ["docker_compose"]


def test_print_and_compare_helpers(capsys: pytest.CaptureFixture[str]) -> None:
    sync.print_languages([li("x", extensions=["a", "b", "c", "d"])], "Title")
    assert "Title" in capsys.readouterr().out

    native = [li("python", source=Source.NATIVE)]
    ext = [li("python", source=Source.EXTENSION), li("go", source=Source.EXTENSION)]
    zed_map = sync.map_zed_languages(native, ext)
    assert zed_map["python"].source == Source.NATIVE
    assert zed_map["go"].source == Source.EXTENSION

    config: ConfigDict = {
        "python": {"name": "Python", "zed_language": "python", "extensions": ["py"]},
        "ruby": {"name": "Ruby", "zed_language": "ruby", "extensions": ["rb"]},
    }
    by_zed = sync.map_config_languages(config)
    assert by_zed["ruby"][0] == "ruby"

    sync.print_comparison_header()
    only_ours = sync.print_only_in_ours({"ruby"}, {"python"}, by_zed)
    assert only_ours == {"ruby"}
    only_zed = sync.print_only_in_zed({"python"}, {"ruby"}, {"python": li("python", extensions=["py"])})
    assert only_zed == {"python"}
    no_diff = sync.compare_extension_sets({"name": "N", "zed_language": "n", "extensions": ["a"]}, li("n", extensions=["a"]))
    assert no_diff == []
    diffs = sync.compare_extension_sets({"name": "N", "zed_language": "n", "extensions": ["a"]}, li("n", extensions=["b"]))
    assert len(diffs) == 2
    zed_for_diff = {"python": li("python", extensions=["py", "pyw"])}
    collected = sync.collect_extension_differences({"python"}, zed_for_diff, by_zed)
    assert collected
    only_ours = sync.compare_extension_sets(
        {"name": "N", "zed_language": "n", "extensions": ["a", "b"]},
        li("n", extensions=["a"]),
    )
    assert len(only_ours) == 1
    only_zed = sync.compare_extension_sets(
        {"name": "N", "zed_language": "n", "extensions": ["a"]},
        li("n", extensions=["a", "b"]),
    )
    assert len(only_zed) == 1

    sync.print_extension_differences(collected)
    sync.print_extension_differences([("x", ["d"])] * 21)
    sync.print_no_diff_message(set(), set(), [])
    sync.print_comparison_footer(config, {"python": li("python")}, {"python"})
    out = capsys.readouterr().out
    assert "COMPARISON" in out
    assert "Summary:" in out


def test_compare_with_zed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    config: ConfigDict = {
        "python": {"name": "Python", "zed_language": "python", "extensions": ["py"]},
        "ruby": {"name": "Ruby", "zed_language": "ruby", "extensions": ["rb"]},
    }
    monkeypatch.setattr(sync, "load_config", lambda: config)
    sync.compare_with_zed([li("python", source=Source.NATIVE, extensions=["py"])], [li("go", extensions=["go"])])
    out = capsys.readouterr().out
    assert "In our config but NOT in Zed" in out
    assert "In Zed but NOT in our config" in out

    monkeypatch.setattr(
        sync, "load_config", lambda: {"python": {"name": "Python", "zed_language": "python", "extensions": ["py"]}}
    )
    sync.compare_with_zed([li("python", source=Source.NATIVE, extensions=["py"])], [])
    assert "[OK] No differences found!" in capsys.readouterr().out


def test_argument_and_main_helpers(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["sync_zed_languages.py", "--list", "--native"])
    args = sync.parse_arguments()
    assert args.list is True
    assert sync.get_fetch_flags(args) == (True, False)
    monkeypatch.setattr(sys, "argv", ["sync_zed_languages.py", "--classify"])
    args = sync.parse_arguments()
    assert args.classify is True
    monkeypatch.setattr(sys, "argv", ["sync_zed_languages.py", "--classify-json", "/tmp/out.json"])
    args = sync.parse_arguments()
    assert args.classify_json == "/tmp/out.json"

    args = sync.SyncArgs()
    assert sync.get_fetch_flags(args) == (True, True)
    args.native = True
    args.ext = True
    assert sync.get_fetch_flags(args) == (True, True)

    monkeypatch.setattr(sync, "get_native_languages", lambda: [li("python", source=Source.NATIVE)])
    monkeypatch.setattr(sync, "get_extension_languages", lambda: [li("go")])
    native, ext = sync.fetch_zed_languages(True, True)
    assert len(native) == 1 and len(ext) == 1
    assert sync.fetch_zed_languages(False, False) == ([], [])

    list_args = sync.SyncArgs()
    list_args.list = True
    list_args.native = True
    assert sync.handle_list_mode(list_args, native, ext) is True
    out = capsys.readouterr().out
    assert "Zed Native Languages" in out

    list_args.native = False
    list_args.ext = True
    assert sync.handle_list_mode(list_args, native, ext) is True
    out = capsys.readouterr().out
    assert "Zed Extension Languages" in out

    list_args.ext = False
    assert sync.handle_list_mode(list_args, native, ext) is True
    out = capsys.readouterr().out
    assert "Total:" in out

    list_args.list = False
    assert sync.handle_list_mode(list_args, native, ext) is False

    config: ConfigDict = {"x": {"name": "X", "zed_language": "x", "extensions": ["x"]}}
    updated = sync.update_sources(config, {"x"}, set())
    assert updated == 1
    config["e"] = {"name": "E", "zed_language": "e", "extensions": ["e"]}
    config["n"] = {"name": "N", "zed_language": "n", "extensions": ["n"]}
    updated = sync.update_sources(config, {"x"}, {"e"})
    assert updated == 2
    updated = sync.update_sources(config, {"x"}, set())
    assert updated == 1

    backfill_cfg: ConfigDict = {
        "a": {"name": "A", "zed_language": "a", "extensions": []},
        "b": {"name": "B", "zed_language": "b", "filenames": ["Bfile"]},
        "c": {"name": "C", "zed_language": "c"},
    }
    backfilled = sync.backfill_missing_detection_tokens(
        backfill_cfg,
        {
            "a": li("a", extensions=["aa"]),
            "b": li("b", extensions=["bb"]),
            "c": li("c", extensions=[]),
        },
    )
    assert backfilled == 1
    assert backfill_cfg["a"].get("extensions") == ["aa"]
    assert backfill_cfg["b"].get("filenames") == ["Bfile"]
    assert "extensions" not in backfill_cfg["c"]

    add_args = sync.SyncArgs()
    add_args.add = True
    added = sync.add_missing_languages(config, [li("y", source=Source.NATIVE)], add_args)
    assert added == 1
    added = sync.add_missing_languages(config, [li("y", source=Source.NATIVE)], add_args)
    assert added == 0

    add_args.native = True
    add_args.ext = False
    added = sync.add_missing_languages(config, [li("z", source=Source.EXTENSION)], add_args)
    assert added == 0

    add_args.native = False
    add_args.ext = True
    added = sync.add_missing_languages(config, [li("w", source=Source.NATIVE)], add_args)
    assert added == 0

    counted = sync.count_sources(config)
    assert counted["native"] >= 1

    sync.print_sync_results(1, 4, 2, {"native": 1, "extension": 2, "extra": 3}, include_added=True)
    sync.print_sync_results(1, 4, 2, {"native": 1, "extension": 2, "extra": 3}, include_added=False)
    out = capsys.readouterr().out
    assert "Updated: 1 source fields" in out
    assert "Backfilled detections: 4" in out

    main_args = sync.SyncArgs()
    main_args.classify = True
    monkeypatch.setattr(sync, "parse_arguments", lambda: main_args)
    monkeypatch.setattr(sync, "validate_sync_environment", lambda: None)
    called_classify: dict[str, bool] = {}
    monkeypatch.setattr(sync, "collect_extension_capabilities", lambda: [])
    monkeypatch.setattr(sync, "print_extension_capability_report", lambda _caps: called_classify.setdefault("classify", True))
    assert sync.main() == 0
    assert called_classify["classify"] is True

    main_args = sync.SyncArgs()
    main_args.classify_json = "/tmp/cap.json"
    monkeypatch.setattr(sync, "parse_arguments", lambda: main_args)
    monkeypatch.setattr(sync, "validate_sync_environment", lambda: None)
    monkeypatch.setattr(sync, "collect_extension_capabilities", lambda: [])
    monkeypatch.setattr(sync, "print_extension_capability_report", lambda _caps: None)
    wrote: dict[str, str] = {}
    monkeypatch.setattr(sync, "write_extension_capability_json", lambda _caps, p: wrote.setdefault("path", str(p)))
    assert sync.main() == 0
    assert wrote["path"] == "/tmp/cap.json"

    main_args = sync.SyncArgs()
    main_args.list = True
    monkeypatch.setattr(sync, "parse_arguments", lambda: main_args)
    monkeypatch.setattr(sync, "validate_sync_environment", lambda: None)
    monkeypatch.setattr(sync, "fetch_zed_languages", lambda _n, _e: ([li("python", source=Source.NATIVE)], []))
    assert sync.main() == 0

    main_args = sync.SyncArgs()
    main_args.diff = True
    monkeypatch.setattr(sync, "parse_arguments", lambda: main_args)
    monkeypatch.setattr(sync, "handle_list_mode", lambda *_args, **_kwargs: False)
    called_diff: dict[str, bool] = {}
    monkeypatch.setattr(sync, "compare_with_zed", lambda *_args, **_kwargs: called_diff.setdefault("diff", True))
    assert sync.main() == 0
    assert called_diff["diff"] is True

    main_args = sync.SyncArgs()
    monkeypatch.setattr(sync, "parse_arguments", lambda: main_args)
    monkeypatch.setattr(sync, "handle_list_mode", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(sync, "fetch_zed_languages", lambda _n, _e: ([li("python", source=Source.NATIVE)], [li("go")]))
    monkeypatch.setattr(
        sync, "load_config", lambda: {"python": {"name": "Python", "zed_language": "python", "extensions": ["py"]}}
    )
    monkeypatch.setattr(sync, "save_config", lambda _cfg: None)
    assert sync.main() == 0

    main_args = sync.SyncArgs()
    monkeypatch.setattr(sync, "parse_arguments", lambda: main_args)
    monkeypatch.setattr(sync, "handle_list_mode", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(sync, "fetch_zed_languages", lambda _n, _e: ([], [li("go")]))
    monkeypatch.setattr(sync, "load_config", lambda: {"go": {"name": "Go", "zed_language": "go", "extensions": ["go"]}})
    monkeypatch.setattr(sync, "save_config", lambda _cfg: None)
    assert sync.main() == 0

    main_args = sync.SyncArgs()
    monkeypatch.setattr(sync, "parse_arguments", lambda: main_args)
    monkeypatch.setattr(sync, "handle_list_mode", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        sync,
        "fetch_zed_languages",
        lambda _n, _e: (
            [li("yaml", source=Source.NATIVE)],
            [
                li(
                    "docker_compose",
                    zed_language="docker-compose",
                    syntax_signature="https://github.com/zed-industries/tree-sitter-yaml",
                )
            ],
        ),
    )
    monkeypatch.setattr(
        sync, "parse_native_tree_sitter_git_signatures", lambda: {"https://github.com/zed-industries/tree-sitter-yaml"}
    )
    cfg_filtered: ConfigDict = {
        "docker_compose": {"name": "Docker Compose", "zed_language": "docker-compose", "extensions": [], "source": "extension"}
    }
    monkeypatch.setattr(sync, "load_config", lambda: cfg_filtered)
    monkeypatch.setattr(sync, "save_config", lambda _cfg: None)
    assert sync.main() == 0
    assert cfg_filtered["docker_compose"].get("source") == "extra"


def test_sync_module_main_guard_help(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["sync_zed_languages.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        _ = runpy.run_module("sync_zed_languages", run_name="__main__")
    assert exc.value.code == 0
