# Jinja Universal

Jinja2 template support for Zed editor with syntax highlighting for 380+ languages.

All file extensions support `.jinja`, `.jinja2`, and `.j2` variants (e.g., `config.yaml.jinja`, `config.yaml.jinja2`, `config.yaml.j2`).

## Installation

1. Open Zed
2. Go to Extensions
3. Search for "Jinja Universal"
4. Install

**Or** for development:
1. Copy the `jinja-universal` folder to `~/.config/zed/extensions/`
2. Or use "Install Dev Extension" from Zed's command palette

## How It Works

This extension uses a [forked Jinja2 grammar](https://github.com/Else00/tree-sitter-jinja2-universal) as the "core" parser and injects the appropriate language grammar based on the file extension.

For example, when you open `config.yaml.jinja`:
1. The file is parsed with the Jinja2 grammar
2. The YAML grammar is injected into the content sections
3. You get syntax highlighting for both Jinja2 syntax (`{% %}`, `{{ }}`) and YAML content

> **Note**: For the host language to be highlighted, Zed must support it (either built-in or via an extension). If not, you'll still see Jinja syntax highlighted, but the host content appears as plain text.

## Syntax Highlighting

This extension maps Jinja2 syntax to [Zed syntax captures](https://zed.dev/docs/extensions/languages):

| Jinja Element | Capture | Examples |
|---------------|---------|----------|
| Block delimiters | `@preproc` | `{%`, `%}` |
| Expression delimiters | `@preproc` | `{{`, `}}` |
| Comment delimiters | `@comment` | `{#`, `#}` |
| Comment content | `@comment` | `{# comment text #}` |
| Keywords | `@preproc` | `for`, `in`, `if`, `elif`, `else`, `endif`, `endfor`, `block`, `endblock`, `extends`, `include`, `set`, `macro`, `endmacro`, `call`, `endcall`, `filter`, `raw`, `endraw`, `import`, `from`, `as`, `with` |
| Variables | `@variable` | `item`, `items`, `user` |
| Function calls | `@function` | `range()`, `join()`, `default()` |
| Block/macro names | `@function` | name in `{% block content %}` |
| Strings | `@string` | `"hello"`, `'world'` |
| Template paths | `@string.special` | path in `{% extends "base.html" %}` |
| Numbers | `@number` | `42`, `3.14` |
| Booleans | `@boolean` | `True`, `False` |
| Operators | `@operator` | `==`, `!=`, `<`, `>`, `<=`, `>=` |
| Keyword arguments | `@property` | `name` in `{{ func(name=value) }}` |
| Brackets | `@punctuation.bracket` | `(`, `)`, `[`, `]`, `{`, `}` |
| Delimiters | `@punctuation.delimiter` | `,`, `:`, `=` |

### Customizing Colors

To customize Jinja colors in your Zed theme, override the relevant captures:

```json
{
  "syntax": {
    "preproc": {
      "color": "#ff69b4"
    }
  }
}
```

**Note**: Changing a capture affects all uses of that capture in your theme, not just Jinja.

## Development

Requires: `just`, `uv`, `git`, Python 3.13+

### Philosophy

**Zed is the source of truth.** This extension automatically syncs with Zed's supported languages - we don't manually maintain a list of 400+ languages.

The workflow is:
```
Zed repos (GitHub)
    ↓ sync
languages.toml (our config)
    ↓ generate  
languages/{lang}_jinja/ (generated folders)
```

When Zed adds support for a new language (either built-in or via extension), we run `just sync` and it appears in our config. When we run `just generate`, it creates the Jinja variant automatically.

### Why Source Types?

Not all languages are equal in Zed:

| Source | What it means | Works in Zed? |
|--------|---------------|---------------|
| `native` | Built into Zed core | ✅ Always |
| `extension` | Requires installing a Zed extension | ✅ If extension installed |
| `extra` | No Zed support exists | ❌ Host content = plain text |

The `sync` script detects this automatically:
- Scans `zed-industries/zed` repo → finds native languages
- Scans `zed-industries/extensions` repo → finds extension languages
- Anything else in our config → marked as `extra`

### Choosing Which Languages to Include

You can generate different subsets of languages:

```bash
just generate          # native + extension (default)
just generate-native   # native only
just generate-all      # everything including extra
```

**The published extension uses `native + extension` (386 languages)** because:
- These are the languages that actually work in Zed
- Including `extra` would clutter Zed's language selector with non-functional options
- When you open a `.yaml.jinja` file, YAML highlighting works because Zed supports YAML

The `extra` languages (21) are kept in the config for:
- Future-proofing: when Zed adds support, `just sync` updates them automatically
- Experimentation: `just generate-all` if you want to test them

### Main Workflow

**Keeping up with Zed:**
```bash
just sync       # Fetch latest from Zed, update source fields
just sync-add   # Also add any NEW languages Zed now supports
just generate   # Regenerate folders from updated config
```

Or all at once:
```bash
just build      # sync + sort + generate
```

**Checking what Zed supports:**
```bash
just zed-native   # List built-in languages (~22)
just zed-ext      # List extension languages (~364)
just diff         # Compare our config vs Zed's data
just count        # Stats by source type
```

### Adding a Language Manually

Only needed for languages Zed doesn't support yet (rare):

```bash
# 1. Add to languages.toml
[mylang]
name = "My Language"
zed_language = "mylang"
extensions = ["ml"]
source = "extra"

# 2. Regenerate (use --all to include extra)
just generate-all
```

When Zed eventually adds support, `just sync` will automatically change the source from `extra` to `native` or `extension`.

### Architecture

```
languages/jinja2/           # BASE - actual highlighting rules
    ├── highlights.scm      # Jinja syntax highlighting
    ├── brackets.scm
    └── indents.scm

languages/{lang}_jinja/     # GENERATED - don't edit!
    ├── config.toml         # File extensions
    ├── injections.scm      # Injects host language
    └── *.scm               # Copied from jinja2/
```

**To change highlighting**: Edit `languages/jinja2/highlights.scm`, then `just generate`.

### Scripts

Two separate scripts (intentionally):

| Script | Speed | Purpose |
|--------|-------|---------|
| `sync_zed_languages.py` | Slow (network) | Fetch from Zed repos |
| `generate.py` | Fast (local) | Generate folders from config |

This way you can `just generate` quickly without re-syncing every time.

Both scripts are **fail-fast**: they validate everything (directories, files, config structure) before making any changes. If Zed's repo structure changes, they fail with clear errors instead of silently breaking.

---

## Supported Languages

<details>
<summary>Click to expand the full list of 353 supported languages</summary>

<!-- GENERATED_MODE_START -->

**Generated selection:** `native + extension (default)`

Literal scope: all native and extension languages (extra excluded).

<!-- GENERATED_MODE_END -->

In the table below, `.*` means the extension supports `.jinja`, `.jinja2`, and `.j2` variants.

For example, `.yaml.*` means: `.yaml.jinja`, `.yaml.jinja2`, `.yaml.j2`

> **Note**: Pure Jinja files (`.jinja`, `.jinja2`, `.j2`) and `.html.*` files default to HTML injection.

<!-- LANGUAGES_TABLE_START -->

| Language | File Extensions |
|----------|-----------------|
| Jinja2 | `.html.*`, `.j2`, `.jinja`, `.jinja2` |
| ActionScript-Jinja | `.as.*` |
| Ada-Jinja | `.adb.*`, `.ads.*` |
| Agda-Jinja | `.agda.*` |
| Aiken-Jinja | `.ak.*` |
| Alex-Jinja | `.x.*` |
| Amber-Jinja | `.ab.*` |
| Angular-Jinja | `.component.html.*`, `.ng.html.*` |
| Animation.txt-Jinja | `.animation.txt.*` |
| Apache Avro (IDL)-Jinja | `.avdl.*` |
| ArkTS Language-Jinja | `.ets.*` |
| AsciiDoc-Jinja | `.ad.*`, `.adoc.*`, `.asc.*`, `.asciidoc.*` |
| ASN.1-Jinja | `.mib.*` |
| ass-Jinja | `.ass.*`, `.ssa.*` |
| Assembly-Jinja | `.S.*`, `.asm.*`, `.s.*` |
| Astro-Jinja | `.astro.*` |
| AutoHotkey-Jinja | `.ahk.*` |
| AWK-Jinja | `.awk.*` |
| Baml-Jinja | `.baml.*` |
| bazelrc-Jinja | `.bazelrc.*` |
| Beancount-Jinja | `.bean.*`, `.beancount.*` |
| Bend-Jinja | `.bend.*` |
| BibTeX-Jinja | `.bib.*`, `.biblatex.*`, `.bibtex.*` |
| Bicep Parameters-Jinja | `.bicepparam.*` |
| Bicep-Jinja | `.bicep.*` |
| Bison-Jinja | `.y.*`, `.yy.*` |
| bitbake-Jinja | `.bb.*`, `.bbappend.*`, `.bbclass.*`, `.conf.*`, `.inc.*` |
| Blade-Jinja | `.blade.php.*` |
| Blueprint-Jinja | `.blp.*` |
| Bluespec SystemVerilog-Jinja | `.bsv.*` |
| Bqn-Jinja | `.bqn.*` |
| Brainfuck-Jinja | `.bf.*` |
| Bsl-Jinja | `.bsl.*` |
| C#-Jinja | `.cs.*`, `.csx.*` |
| C++-Jinja | `.C.*`, `.H.*`, `.c++.*`, `.cc.*`, `.cpp.*`, `.cu.*`, `.cuh.*`, `.cxx.*`, `.h.*`, `.h++.*`, `.hh.*`, `.hpp.*`, `.hxx.*`, `.inl.*`, `.ino.*`, `.ipp.*`, `.ixx.*` |
| C-Jinja | `.c.*` |
| C3-Jinja | `.c3.*`, `.c3i.*` |
| Cabal-Jinja | `.cabal.*` |
| Caddyfile-Jinja | `.Caddyfile.*`, `.caddyfile.*` |
| Cadence-Jinja | `.cdc.*` |
| Cairo-Jinja | `.cairo.*` |
| Candid-Jinja | `.did.*` |
| Cap'n Proto-Jinja | `.capnp.*` |
| Cedar-Jinja | `.cedar.*` |
| CFEngine-Jinja | `.cf.*`, `.cf.sub.*`, `.cf3.*`, `.cfengine.*`, `.cfengine3.*` |
| CFML (Markup)-Jinja | `.cfm.*`, `.cfml.*` |
| CFML (Script)-Jinja | `.cfs.*` |
| Cherri-Jinja | `.cherri.*` |
| Circom-Jinja | `.circom.*` |
| Clarity-Jinja | `.clar.*` |
| Clojure-Jinja | `.bb.*`, `.clj.*`, `.cljc.*`, `.cljd.*`, `.cljs.*`, `.edn.*` |
| CMake-Jinja | `.cmake.*` |
| COBOL-Jinja | `.cbl.*`, `.cob.*` |
| CODEOWNERS-Jinja | `.CODEOWNERS.*`, `.CODEOWNERS.txt.*` |
| CoffeeScript-Jinja | `.coffee.*` |
| Coi-Jinja | `.coi.*`, `.d.coi.*` |
| CONL-Jinja | `.conl.*` |
| Cooklang-Jinja | `.cook.*` |
| Cpp2-Jinja | `.cpp2.*`, `.h2.*` |
| CQL-Jinja | `.cql.*` |
| Crystal-Jinja | `.cr.*` |
| Csound-Jinja | `.csd.*`, `.orc.*`, `.sco.*`, `.udo.*` |
| CSS-Jinja | `.css.*`, `.pcss.*`, `.postcss.*` |
| CSV-Jinja | `.csv.*` |
| CUE-Jinja | `.cue.*` |
| Curry-Jinja | `.curry.*` |
| Cylc-Jinja | `.cylc.*` |
| Cypher-Jinja | `.cql.*`, `.cyp.*`, `.cypher.*` |
| Cython-Jinja | `.pxd.*`, `.pxi.*`, `.pyx.*` |
| D-Jinja | `.d.*`, `.dd.*`, `.di.*` |
| D2-Jinja | `.d2.*` |
| Dafny-Jinja | `.dfy.*` |
| Dart-Jinja | `.dart.*` |
| DBML-Jinja | `.dbml.*` |
| Demo Tape-Jinja | `.tape.*` |
| Desktop Entry-Jinja | `.desktop.*`, `.directory.*` |
| devicetree-Jinja | `.dts.*`, `.dtsi.*`, `.dtso.*`, `.its.*` |
| Diff-Jinja | `.diff.*`, `.patch.*` |
| Django-Jinja | `.dj.html.*`, `.dj.md.*`, `.dj.txt.*` |
| Dockerfile-Jinja | `.Containerfile.*`, `.Dockerfile.*`, `.dockerfile.*` |
| DOT-Jinja | `.DOT.*`, `.dot.*`, `.gv.*` |
| DuckyScript-Jinja | `.txt.*` |
| Dune-Jinja | `.dune.*`, `.dune-project.*`, `.dune-workspace.*` |
| Earthfile-Jinja | `.Earthfile.*` |
| ECR-Jinja | `.ecr.*` |
| Edge-Jinja | `.edge.*` |
| Editorconfig-Jinja | `.editorconfig.*` |
| Elisp-Jinja | `.el.*` |
| Elixir-Jinja | `.ex.*`, `.exs.*` |
| Elm-Jinja | `.elm.*` |
| Env-Jinja | `.env.*`, `.envrc.*` |
| Erlang-Jinja | `.erl.*`, `.hrl.*`, `.xrl.*`, `.yrl.*` |
| Exograph-Jinja | `.exo.*` |
| F#-Jinja | `.fs.*`, `.fsi.*`, `.fsscript.*`, `.fsx.*` |
| Ferret Lockfile-Jinja | `.ferret.lock.*` |
| Ferret Manifest-Jinja | `.fer.ret.*` |
| Ferret-Jinja | `.fer.*` |
| Fift-Jinja | `.fif.*` |
| Fish-Jinja | `.fish.*` |
| FlatBuffers-Jinja | `.fbs.*` |
| Fortran-Jinja | `.F.*`, `.F03.*`, `.F08.*`, `.F90.*`, `.F95.*`, `.f.*`, `.f03.*`, `.f08.*`, `.f90.*`, `.f95.*` |
| Fountain-Jinja | `.fountain.*`, `.spmd.*` |
| Freemarker-Jinja | `.ftl.*` |
| Func-Jinja | `.fc.*` |
| G-code-Jinja | `.001.*`, `.S.*`, `.anc.*`, `.apt.*`, `.aptcl.*`, `.bfb.*`, `.cls.*`, `.cnc.*`, `.din.*`, `.dnc.*`, `.ecs.*`, `.eia.*`, `.fan.*`, `.fgc.*`, `.fnc.*`, `.g.*`, `.g00.*`, `.gc.*`, `.gcd.*`, `.gco.*`, `.gcode.*`, `.gp.*`, `.hnc.*`, `.knc.*`, `.lib.*`, `.m.*`, `.min.*`, `.mmg.*`, `.mpf.*`, `.mpt.*`, `.nc.*`, `.ncd.*`, `.ncf.*`, `.ncg.*`, `.nci.*`, `.ncp.*`, `.ngc.*`, `.out.*`, `.pim.*`, `.pit.*`, `.plt.*`, `.ply.*`, `.prg.*`, `.pu1.*`, `.rol.*`, `.sbp.*`, `.spf.*`, `.ssb.*`, `.sub.*`, `.tap.*`, `.tcn.*`, `.xpi.*` |
| GDScript-Jinja | `.gd.*` |
| GDShader-Jinja | `.gdshader.*`, `.gdshaderinc.*` |
| Gemini-Jinja | `.gemini.*`, `.gmi.*` |
| Gherkin-Jinja | `.feature.*`, `.gherkin.*` |
| Ghostty-Jinja | `.ghostty.*` |
| Git Attributes-Jinja | `.gitattributes.*` |
| Git Commit-Jinja | `.COMMIT_EDITMSG.*`, `.EDIT_DESCRIPTION.*`, `.MERGE_MSG.*`, `.NOTES_EDITMSG.*`, `.TAG_EDITMSG.*` |
| Git Ignore-Jinja | `.containerignore.*`, `.cursorignore.*`, `.dockerignore.*`, `.eslintignore.*`, `.fdignore.*`, `.git-blame-ignore-revs.*`, `.gitignore.*`, `.ignore.*`, `.npmignore.*`, `.prettierignore.*`, `.rgignore.*`, `.vscodeignore.*` |
| Gleam-Jinja | `.gleam.*` |
| Glimmer (JavaScript)-Jinja | `.gjs.*` |
| Glimmer (TypeScript)-Jinja | `.gts.*` |
| Go Mod-Jinja | `.mod.*` |
| Go Sum-Jinja | `.go.sum.*` |
| Go Text Template-Jinja | `.go.txt.*`, `.gotmpl.*`, `.gtpl.*`, `.txt.gotmpl.*`, `.txt.gotpl.*` |
| Go Work-Jinja | `.work.*` |
| Go-Jinja | `.go.*` |
| Godot Resource-Jinja | `.gdextension.*`, `.godot.*`, `.import.*`, `.tres.*`, `.tscn.*` |
| GPR-Jinja | `.gpr.*` |
| GraphQL-Jinja | `.gql.*`, `.graphql.*`, `.graphqls.*` |
| Gren-Jinja | `.gren.*` |
| GreyCat-Jinja | `.gcl.*` |
| GritQL Snippet-Jinja | `.gritqlsnippet.*` |
| GritQL-Jinja | `.grit.*` |
| Groovy-Jinja | `.JenkinsFile.*`, `.Jenkinsfile.*`, `.gradle.*`, `.groovy.*` |
| GROQ-Jinja | `.groq.*` |
| Haml-Jinja | `.haml.*`, `.html.haml.*` |
| Handlebars-Jinja | `.handlebars.*`, `.hbs.*` |
| Hare-Jinja | `.ha.*` |
| Haskell-Jinja | `.hs.*` |
| Haxe-Jinja | `.hx.*` |
| HEEX-Jinja | `.heex.*` |
| Helm-Jinja | `.helmignore.*` |
| HLSL-Jinja | `.hlsl.*` |
| HOCON-Jinja | `.conf.*`, `.hocon.*` |
| HQL-Jinja | `.hx.*` |
| http-Jinja | `.http.*` |
| Huff-Jinja | `.huff.*` |
| Hurl-Jinja | `.hurl.*` |
| HXML-Jinja | `.hxml.*` |
| Hyprlang-Jinja | `.conf.*`, `.hl.*` |
| Inform 6-Jinja | `.h.*`, `.inf.*` |
| INI-Jinja | `.cfg.*`, `.conf.*`, `.ini.*` |
| Ink-Jinja | `.ink.*` |
| ion-Jinja | `.ion.*` |
| ion_schema-Jinja | `.isl.*` |
| ISLE-Jinja | `.isle.*` |
| Jai-Jinja | `.jai.*` |
| Janet-Jinja | `.janet.*` |
| Java-Jinja | `.java.*` |
| JavaScript-Jinja | `.cjs.*`, `.js.*`, `.jsx.*`, `.mjs.*` |
| Jdl-Jinja | `.jdl.*` |
| Jinja2-Jinja | `.j2.*`, `.jinja.*`, `.jinja2.*` |
| jq-Jinja | `.jq.*` |
| JSON Lines-Jinja | `.jsonl.*`, `.ndjson.*` |
| JSON-Jinja | `.geojson.*`, `.json.*` |
| JSON5-Jinja | `.json5.*` |
| JSONC-Jinja | `.jsonc.*` |
| Jsonnet-Jinja | `.jsonnet.*`, `.libsonnet.*` |
| JSP-Jinja | `.jsp.*`, `.jspf.*`, `.tag.*` |
| Julia-Jinja | `.jl.*` |
| Just-Jinja | `JUSTFILE.*`, `Justfile.*`, `just.*`, `justfile.*` |
| KCL-Jinja | `.k.*` |
| Kconfig-Jinja | `.Kconfig.*` |
| KDL-Jinja | `.kdl.*` |
| Kotlin-Jinja | `.kt.*`, `.kts.*` |
| Koto-Jinja | `.koto.*` |
| LaTeX-Jinja | `.cls.*`, `.dtx.*`, `.ins.*`, `.latex.*`, `.sty.*`, `.tex.*` |
| Latte-Jinja | `.latte.*` |
| Lean-Jinja | `.lean.*` |
| Ledger-Jinja | `.journal.*`, `.ldg.*`, `.ldgr.*`, `.ledger.*` |
| Less-Jinja | `.less.*` |
| LilyPond-Jinja | `.ily.*`, `.ly.*` |
| Linker Script-Jinja | `.ld.*` |
| Liquid-Jinja | `.liquid.*` |
| LLVM IR-Jinja | `.ll.*` |
| LOG-Jinja | `.log.*` |
| Logstash Config-Jinja | `.conf.*` |
| Lox-Jinja | `.lox.*` |
| Lua-Jinja | `.lua.*` |
| Luau-Jinja | `.luau.*` |
| Mach-Jinja | `.mach.*` |
| Makefile-Jinja | `.GNUmakefile.*`, `.Makefile.*`, `.makefile.*`, `.mk.*` |
| Markdown-Jinja | `.MD.*`, `.markdown.*`, `.md.*`, `.mdwn.*` |
| MATLAB-Jinja | `.m.*` |
| mcfunction-Jinja | `.mcfunction.*` |
| MDX-Jinja | `.mdx.*` |
| Menhir-Jinja | `.mly.*` |
| Mermaid-Jinja | `.mermaid.*`, `.mmd.*` |
| microScript-Jinja | `.ms.*` |
| MoonBit-Jinja | `.mbt.*` |
| Motoko-Jinja | `.mo.*` |
| Move-Jinja | `.move.*` |
| Mustache-Jinja | `.mustache.*` |
| Navi Stream-Jinja | `.nvs.*` |
| Navi-Jinja | `.navi.*`, `.nv.*` |
| NetLinx-Jinja | `.axb.*`, `.axi.*`, `.axs.*`, `.lib.*` |
| Nginx-Jinja | `.nginx.conf.*` |
| Nickel-Jinja | `.ncl.*` |
| Nim Format String-Jinja | `.nim_format_string.*` |
| Nim-Jinja | `.nim.*`, `.nims.*` |
| Nix-Jinja | `.nix.*` |
| Noir-Jinja | `.nr.*` |
| Numscript-Jinja | `.num.*`, `.numscript.*` |
| Nunjucks-Jinja | `.njk.*` |
| Nushell-Jinja | `.nu.*` |
| Oat-Jinja | `.oat.*` |
| OCaml Interface-Jinja | `.mli.*` |
| OCaml-Jinja | `.ml.*` |
| OCamllex-Jinja | `.mll.*` |
| Odin-Jinja | `.odin.*` |
| OMNeT++ MSG-Jinja | `.msg.*` |
| OMNeT++ NED-Jinja | `.ned.*` |
| OpenFGA-Jinja | `.fga.*` |
| OpenSCAD-Jinja | `.scad.*` |
| Org-Jinja | `.org.*` |
| P4 Language-Jinja | `.p4.*` |
| Pact-Jinja | `.pact.*`, `.repl.*` |
| Pascal-Jinja | `.dpr.*`, `.inc.*`, `.lpr.*`, `.p.*`, `.pas.*`, `.pp.*` |
| Pdxinfo-Jinja | `.pdxinfo.*` |
| Perl-Jinja | `.pl.*`, `.pm.*`, `.t.*` |
| Perm-Jinja | `.perm.*` |
| Pest-Jinja | `.pest.*` |
| PHP-Jinja | `.php.*`, `.phtml.*` |
| pica200-Jinja | `.pica.*` |
| Pkl-Jinja | `.pcf.*`, `.pkl.*` |
| PlantUML-Jinja | `.iuml.*`, `.plantuml.*`, `.pu.*`, `.puml.*`, `.wsd.*` |
| Polar-Jinja | `.polar.*` |
| Pony-Jinja | `.pony.*` |
| PowerShell-Jinja | `.ps1.*`, `.psm1.*` |
| Prisma-Jinja | `.prisma.*` |
| Prolog-Jinja | `.P.*`, `.pl.*`, `.pro.*` |
| Properties-Jinja | `.properties.*` |
| Pug-Jinja | `.pug.*` |
| Puppet-Jinja | `.epp.*`, `.pp.*` |
| PureScript-Jinja | `.purs.*` |
| Python requirements-Jinja | `.requirements.txt.*` |
| Python-Jinja | `.mpy.*`, `.py.*`, `.pyi.*` |
| QuakeC-Jinja | `.qc.*` |
| R-Jinja | `.R.*`, `.r.*` |
| Racket-Jinja | `.rkt.*` |
| RBS-Jinja | `.rbs.*` |
| RCL-Jinja | `.rcl.*` |
| Reason-Jinja | `.re.*` |
| Red-Jinja | `.red.*`, `.reds.*` |
| REDscript-Jinja | `.reds.*` |
| Regedit-Jinja | `.reg.*` |
| rego-Jinja | `.rego.*`, `.rq.*` |
| ReScript-Jinja | `.res.*`, `.resi.*` |
| reStructuredText-Jinja | `.rst.*` |
| Rhai-Jinja | `.rhai.*` |
| Risor-Jinja | `.risor.*` |
| Robot-Jinja | `.robot.*` |
| Roc-Jinja | `.roc.*` |
| RON-Jinja | `.ron.*` |
| Roto-Jinja | `.roto.*` |
| RPM Spec-Jinja | `.spec.*` |
| RsHtml-Jinja | `.rs.html.*` |
| Ruby-Jinja | `.rb.*` |
| Rust-Jinja | `.rs.*` |
| SageMath-Jinja | `.sage.*` |
| SASS-Jinja | `.sass.*` |
| Scala-Jinja | `.mill.*`, `.sbt.*`, `.sc.*`, `.scala.*` |
| Scheme-Jinja | `.scm.*`, `.ss.*` |
| SCSS-Jinja | `.scss.*` |
| Shell-Jinja | `.bash.*`, `.bashrc.*`, `.profile.*`, `.sh.*`, `.zsh.*`, `.zshrc.*` |
| Sieve-Jinja | `.sieve.*`, `.sieveinterface.*` |
| Simula-Jinja | `.sim.*` |
| Slang-Jinja | `.slang.*` |
| Slim-Jinja | `.html.slim.*`, `.slim.*` |
| Smithy-Jinja | `.smithy.*` |
| Snakemake-Jinja | `.Snakefile.*`, `.smk.*`, `.snakefile.*` |
| Solidity-Jinja | `.sol.*` |
| Soma-Jinja | `.soma.*` |
| Sourcepawn-Jinja | `.sp.*` |
| SpiceDB-Jinja | `.zed.*` |
| Spicy-Jinja | `.evt.*`, `.hlt.*`, `.spicy.*` |
| spthy-Jinja | `.spthy.*` |
| SQL-Jinja | `.sql.*` |
| Squirrel-Jinja | `.nut.*` |
| SSH Config-Jinja | `.config.*`, `.ssh_config.*` |
| Stan-Jinja | `.stan.*` |
| Standard ML-Jinja | `.fun.*`, `.sig.*`, `.sml.*` |
| Starlark-Jinja | `.BUILD.*`, `.bazelrc.*`, `.bzl.*`, `.star.*` |
| Statamic Antlers-Jinja | `.antlers.html.*` |
| Strace-Jinja | `.strace.*` |
| Structured Text-Jinja | `.st.*`, `.stx.*` |
| SuperHTML-Jinja | `.shtml.*` |
| Svelte-Jinja | `.svelte.*` |
| Sway-Jinja | `.sw.*` |
| Swift-Jinja | `.swift.*`, `.swiftinterface.*` |
| SystemRDL-Jinja | `.rdl.*` |
| Tact-Jinja | `.tact.*` |
| Tcl-Jinja | `.tcl.*`, `.tm.*` |
| Templ-Jinja | `.templ.*` |
| Tera-Jinja | `.tera.*` |
| Terraform-Jinja | `.hcl.*`, `.tf.*` |
| Textproto-Jinja | `.pbtxt.*`, `.textpb.*`, `.textproto.*`, `.txtpb.*` |
| Thrift-Jinja | `.thrift.*` |
| TL-B-Jinja | `.tlb.*` |
| tmux-Jinja | `.tmux.*`, `.tmux.conf.*` |
| Tolk-Jinja | `.tolk.*` |
| TOML-Jinja | `.toml.*` |
| TOON-Jinja | `.toon.*` |
| TQL-Jinja | `.tql.*` |
| Tree-sitter Query-Jinja | `.scm.*` |
| TSV-Jinja | `.tsv.*` |
| TSX-Jinja | `.tsx.*` |
| Turtle-Jinja | `.ttl.*`, `.turtle.*` |
| Twig-Jinja | `.html.twig.*`, `.twig.*`, `.twig.html.*` |
| Txtar-Jinja | `.txtar.*` |
| TypeScript-Jinja | `.cts.*`, `.mts.*`, `.ts.*` |
| Typespec-Jinja | `.tsp.*`, `.typespec.*` |
| Typst-Jinja | `.typ.*`, `.typst.*` |
| ucode-Jinja | `.uc.*` |
| Uiua-Jinja | `.ua.*` |
| Umka-Jinja | `.um.*` |
| Ungrammar-Jinja | `.ungram.*` |
| Unison-Jinja | `.u.*` |
| V-Jinja | `.v.*`, `.vsh.*`, `.vv.*` |
| Vala-Jinja | `.vala.*`, `.vapi.*` |
| vCard-Jinja | `.vcf.*` |
| Vento-Jinja | `.vento.*`, `.vto.*` |
| Verilog-Jinja | `.sv.*`, `.svh.*`, `.v.*`, `.vh.*` |
| VHDL-Jinja | `.vhd.*`, `.vhdl.*` |
| VHS-Jinja | `.tape.*` |
| ViewTree ($mol)-Jinja | `.view.tree.*` |
| VRL-Jinja | `.vrl.*` |
| Vue-Jinja | `.vue.*` |
| WDL-Jinja | `.wdl.*` |
| WebAssembly-Jinja | `.wast.*`, `.wat.*` |
| WebIDL-Jinja | `.webidl.*` |
| WeiXin Markup Language-Jinja | `.wxml.*` |
| WGSL-Jinja | `.wgsl.*` |
| whkd-Jinja | `.whkdrc.*` |
| Wikitext-Jinja | `.mediawiki.*`, `.wikimedia.*`, `.wikitext.*` |
| WIT-Jinja | `.wit.*` |
| WoW TOC-Jinja | `.toc.*` |
| Wren-Jinja | `.wren.*` |
| XML-Jinja | `.xml.*` |
| Xonsh-Jinja | `.xonshrc.*`, `.xsh.*` |
| YAML-Jinja | `.yaml.*`, `.yml.*` |
| YANG-Jinja | `.yang.*` |
| Yara-Jinja | `.yar.*`, `.yara.*` |
| Yarn Spinner-Jinja | `.yarn.*` |
| Yul-Jinja | `.yul.*` |
| Zig-Jinja | `.zig.*`, `.zon.*` |
| ziggy-Jinja | `.zgy.*`, `.ziggy.*` |
| ziggy-schema-Jinja | `.zgy-schema.*`, `.ziggy-schema.*` |
| ZoKrates-Jinja | `.zok.*` |

<!-- LANGUAGES_TABLE_END -->

</details>

---

## Credits

- Tree-sitter grammar forked from [jinja2-support](https://github.com/ArcherHume/jinja2-support) by Archer Hume
- Modified grammar: [tree-sitter-jinja2-universal](https://github.com/Else00/tree-sitter-jinja2-universal)

## License

MIT
