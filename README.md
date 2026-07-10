# IPython Postfix Completion

Configurable postfix completion extension for IPython.

Package on PyPI: `ipython-postfix-completion`

## Install

Install into the current Python environment with `uv`:

```bash
uvx --with ipython-postfix-completion ipython
```

Install into the current ipython environment with `uv`:

```bash
uv tool install ipython --with ipython-postfix-completion
```

## Load

Inside IPython:

```python
%load_ext ipython_postfix_completion
```

To load it automatically, add this to `ipython_config.py`:

```python
c.InteractiveShellApp.extensions = ["ipython_postfix_completion"]
```

## Quick Example: Add a `for` Template

Add a template for the current IPython session:

```python
%postfix_template add for "for item in {expr}:\n{indent}    "
```

Use it:

```python
items.for<Tab>
```

It expands to:

```python
for item in items:
    
```

Runtime templates only affect the current IPython session. Put templates in
`ipython_config.py` if you want them to persist.

## Runtime Magic

List effective templates:

```python
%postfix_template list
```

Add or override a template for the current session:

```python
%postfix_template add debug "print({expr}=)"
%postfix_template add forin "for item in {expr}:\n{indent}    "
```

Disable a template for the current session:

```python
%postfix_template remove tuple
```

Reset one runtime change:

```python
%postfix_template reset forin
```

Reset all runtime changes:

```python
%postfix_template reset --all
```

## Persistent Config

Add persistent templates in `ipython_config.py`:

```python
c.PostfixCompletionConfig.templates = {
    "debug": "print({expr}=)",
    "forin": "for item in {expr}:\n{indent}    ",
}

c.PostfixCompletionConfig.disabled_templates = ["tuple"]
```

Smart Tab jump is enabled by default. Disable it while keeping postfix
completion with:

```python
c.PostfixCompletionConfig.smart_tab_jump = False
```

Template names must match `[A-Za-z_][A-Za-z0-9_]*`.

Templates must include `{expr}` and may also use `{indent}`. No other template
fields are allowed.

## `.var` Placeholder

The built-in `.var` template creates an assignment and selects `key` as an
editable placeholder:

```text
"hello".var<Tab>  ->  key = "hello"
                       ^^^ selected
```

While `key` remains selected:

- Tab accepts `key` and moves cursor to the end of the assignment.
- Enter behaves like Tab for this selection only; press Enter again to submit.
- Any other typed text replaces `key` with a custom variable name.

## Smart Tab Jump

When cursor is immediately before a valid Python closing token, Tab moves over
it without changing source text. Repeated Tab presses exit nested constructs:

```text
"hello|"                 -> "hello"|
print("hello|")          -> print("hello"|) -> print("hello")|
print(f"{name|}")        -> print(f"{name}|") -> print(f"{name}"|) -> print(f"{name}")|
items[index|]            -> items[index]|
list[dict[str, int|]]    -> list[dict[str, int]|] -> list[dict[str, int]]|
{"name": value|}         -> {"name": value}|
```

`|` marks cursor and is not typed. Supported closers are single and triple
quotes plus `)`, `]`, and `}`. Detection follows Python tokens, including
multiline input, string prefixes, and f-string expressions. Tab still accepts
the `.var` name selection or an exact postfix template first; otherwise it
falls back to IPython completion or indentation. Ambiguous `< >`, colon, and
comma are intentionally excluded.

## Built-in Templates

Default templates:

| Name | Expansion |
| --- | --- |
| `print` | `print({expr})` |
| `len` | `len({expr})` |
| `not` | `not {expr}` |
| `par` | `({expr})` |
| `var` | `key = {expr}`; selects `key`; Tab or Enter accepts it |
| `await` | `await {expr}` |
| `return` | `return {expr}` |
| `if` | `if {expr}:\n{indent}    ` |
| `while` | `while {expr}:\n{indent}    ` |
| `raise` | `raise {expr}` |
| `yield` | `yield {expr}` |
| `str` | `str({expr})` |
| `list` | `list({expr})` |
| `set` | `set({expr})` |
| `dict` | `dict({expr})` |
| `tuple` | `tuple({expr})` |

Use `%postfix_template list` in IPython to see the exact effective set, including
custom and disabled templates.

## Local Validation

Run tests:

```bash
uv run --extra test pytest -q
```

Build and check release artifacts:

```bash
uv run --extra dev python -m build
uv run --extra dev python -m twine check dist/*
```

Validate the wheel in a clean local virtual environment:

```bash
uv venv .venv-check
uv pip install --python .venv-check/bin/python dist/*.whl
.venv-check/bin/ipython
```

Then inside IPython:

```python
%load_ext ipython_postfix_completion
%postfix_template add for "for item in {expr}:\n{indent}    "
%postfix_template list
```

## Publish

Publishing uses GitHub Actions and PyPI Trusted Publishing. Configure the
existing PyPI project once under **Manage > Publishing > Add a new publisher**:

| Setting | Value |
| --- | --- |
| Owner | `fishandsheep` |
| Repository | `ipython-postfix-completion` |
| Workflow | `publish.yml` |
| Environment | `pypi` |

For each release, update `project.version` in `pyproject.toml`, commit and push
the change, then create a matching `v` tag. For example, after changing the
version to `0.1.1`:

```bash
git tag v0.1.1
git push origin v0.1.1
```

The workflow verifies the tag against `project.version`, runs tests, builds and
checks both distributions, then publishes them to PyPI using a short-lived OIDC
credential. The already-published `0.1.0` release cannot be uploaded again.
