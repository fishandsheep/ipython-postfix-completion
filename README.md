# IPython Postfix Completion

Configurable postfix completion extension for IPython.

Package on PyPI: `ipython-postfix-completion`

## Install

Install into the current Python environment with `uv`:

```bash
uvx --with ipython-postfix-completion ipython
```

Install into the current Python environment with `pip`:

```bash
pip install ipython-postfix-completion
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

Template names must match `[A-Za-z_][A-Za-z0-9_]*`.

Templates must include `{expr}` and may also use `{indent}`. No other template
fields are allowed.

## Built-in Templates

Default templates:

| Name | Expansion |
| --- | --- |
| `print` | `print({expr})` |
| `len` | `len({expr})` |
| `not` | `not {expr}` |
| `par` | `({expr})` |
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

Upload to PyPI:

```bash
uv run --extra dev python -m twine upload dist/*
```

After the first upload creates the project on PyPI, prefer a project-scoped API
token for future releases.
