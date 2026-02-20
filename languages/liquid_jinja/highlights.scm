; =============================================================================
; jinja-universal highlights.scm v0.8.0
; Using @preproc for Jinja-specific syntax (delimiters and keywords)
; =============================================================================

; Delimiters - @preproc for distinctive color
(jinja_tag_begin) @preproc
(jinja_tag_end) @preproc
(jinja_expr_begin) @preproc
(jinja_expr_end) @preproc

; Comments - keep as @comment
(jinja_note_begin) @comment
(jinja_note_end) @comment
(jinja_comment_content) @comment

; Keywords - @preproc for distinctive color
(kw_for) @preproc
(kw_if) @preproc
(kw_elif) @preproc
(kw_else) @preproc
(kw_endif) @preproc
(kw_endfor) @preproc
(kw_block) @preproc
(kw_endblock) @preproc
(kw_extends) @preproc
(kw_include) @preproc
(kw_import) @preproc
(kw_from) @preproc
(kw_as) @preproc
(kw_set) @preproc
(kw_macro) @preproc
(kw_endmacro) @preproc
(kw_call) @preproc
(kw_endcall) @preproc
(kw_filter) @preproc
(kw_raw) @preproc
(kw_endraw) @preproc
(kw_with) @preproc

; "in" keyword in for loops
(jinja_for "in" @preproc)

; End statements
(jinja_end_statement) @preproc

; Literals
(bool) @boolean
(integer) @number
(float) @number
(lit_string) @string

; Variables/identifiers
(identifier) @variable

; Function calls
(fn_call
  fn_name: (identifier) @function)

; Properties
(kwarg
  key: (identifier) @property)
(pair
  key: (lit_string) @property)

; Brackets and punctuation
["(" ")" "[" "]" "{" "}"] @punctuation.bracket
["," ":" "="] @punctuation.delimiter

; Operators
(comparison
  operator: _ @operator)

; Named blocks
(jinja_block
  block_name: (identifier) @function)
(jinja_macro
  macro_name: (identifier) @function)
(jinja_filter
  filter_name: (identifier) @function)

; Template references
(jinja_extends
  parent_template: (lit_string) @string.special)
(jinja_include
  template: (lit_string) @string.special)
(jinja_import
  module: (lit_string) @string.special)
(jinja_from
  module: (lit_string) @string.special)
