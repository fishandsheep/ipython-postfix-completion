# Extended Reference

This guide contains detailed template, configuration, Tab behavior, development,
and release information. For installation and common usage, see the [README](../README.md).

## Template Reference

Templates take the expression to the left of the dot as `{expr}`. `{indent}` is
the leading indentation of the input line. These are the built-in templates:

| Name | Expansion |
| --- | --- |
| `print` | `print({expr})` |
| `len` | `len({expr})` |
| `not` | `not {expr}` |
| `par` | `({expr})` |
| `var` | `key = {expr}`; selects `key` |
| `await` | `await {expr}` |
| `return` | `return {expr}` |
| `if` | `if {expr}:` with an indented `pass` |
| `while` | `while {expr}:` with an indented blank body |
| `for` | `for item in {expr}:` with an indented `pass` |
| `fori` | `for i, value in enumerate({expr}):` with an indented `pass` |
| `ef` | `if {expr}:`, `elif cond:`, and `else:` branches, each with `pass` |
| `raise` | `raise {expr}` |
| `yield` | `yield {expr}` |
| `str` | `str({expr})` |
| `list` | `list({expr})` |
| `set` | `set({expr})` |
| `dict` | `dict({expr})` |
| `tuple` | `tuple({expr})` |
| `type` | `type({expr})` |
| `range` | `range({expr})` |

Integer literals used with `.for` or `.fori` are wrapped in `range(...)`.
Signed and underscored integer literals are recognized. A variable such as `n`
is left unchanged because completion cannot know its runtime type. Thus
`10.fori` uses `enumerate(range(10))`, while `items.fori` uses
`enumerate(items)`.

When a partial name matches multiple templates, the completion menu lists each
match. In particular, `.f` can show both `for` and `fori`; Tab on the exact
`.if` suffix expands `if`.

## Placeholder and Tab Behavior

For built-in `.var`, `.for`, `.if`, `.fori`, and `.ef` templates, Tab accepts
the selected placeholder and advances to the next one. Shift+Tab selects the
previous placeholder. Typing replaces the selected text. After the final stop,
Tab accepts it and places the cursor after the expansion. Enter accepts the
selected `.var` name; press Enter again to submit the input.

The built-in placeholder behavior is enabled only when the corresponding
template retains its built-in definition. Overriding a built-in template
disables its special selection behavior.

### Smart Tab Jump

Smart Tab jump is enabled by default in terminal IPython. When the cursor is
immediately before a valid Python closing token, Tab moves over it without
changing source text. Repeated presses exit nested constructs:

```text
"hello|"                 -> "hello"|
print("hello|")          -> print("hello"|) -> print("hello")|
print(f"{name|}")        -> print(f"{name}|") -> print(f"{name}"|) -> print(f"{name}")|
items[index|]            -> items[index]|
list[dict[str, int|]]    -> list[dict[str, int]|] -> list[dict[str, int]]|
{"name": value|}         -> {"name": value}|
```

`|` marks the cursor and is not typed. Supported closers are single and triple
quotes plus `)`, `]`, and `}`. Detection follows Python tokens, including
multiline input, string prefixes, and f-string expressions. Tab processes an
active placeholder and an exact postfix template first, then falls back to
IPython completion, closer movement, or indentation. Ambiguous `< >`, colon,
and comma are not treated as closers.

Disable smart Tab jump while retaining postfix completion with:

```python
c.PostfixCompletionConfig.smart_tab_jump = False
```

## Runtime Template Commands

Add or override a template for the current IPython session:

```python
%postfix_template add debug "print({expr}=)"
%postfix_template add forin "for item in {expr}:\n{indent}    pass"
```

Disable, reset one, or reset all runtime changes:

```python
%postfix_template remove tuple
%postfix_template reset forin
%postfix_template reset --all
```

Runtime changes last only for the current session. Use
`%postfix_template list` to see built-in, custom, and disabled entries.

Persistent configuration belongs in
`~/.ipython/profile_default/ipython_config.py` by default. Create the profile
with `ipython profile create`; locate the active path with
`ipython locate profile default`. `IPYTHONDIR` or `--ipython-dir` can change
the IPython directory. See the [official IPython configuration guide](https://ipython.readthedocs.io/en/stable/development/config.html).

Template names must match `[A-Za-z_][A-Za-z0-9_]*`. Templates must include
`{expr}` and may also use `{indent}`. No other fields, conversions, or format
specifiers are allowed.

## Development

Run tests and style checks:

```bash
uv run --extra test pytest -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Run IPython against the current checkout without installing into system Python:

```bash
uv run --with ipython --with-editable . ipython
```

Then load `ipython_postfix_completion` in that IPython session.

Build and validate release artifacts:

```bash
uv run --extra dev python -m build
uv run --extra dev python -m twine check dist/*
```

## Publishing

Releases use GitHub Actions and PyPI Trusted Publishing. Configure the PyPI
publisher for the `fishandsheep/ipython-postfix-completion` repository, the
`publish.yml` workflow, and the `pypi` environment. Update the version in
`pyproject.toml`, push the change, then create and push the matching `v` tag.
The workflow checks the tag against the project version, runs tests, builds and
checks distributions, and publishes them. Published PyPI versions and release
tags are immutable; use a new version for fixes.

See [CHANGELOG.md](../CHANGELOG.md) for release history.
