# IPython Postfix Completion

Configurable postfix completion extension for IPython.

Package on PyPI: `ipython-postfix-completion`

## Install

Install from PyPI:

```bash
python -m pip install ipython-postfix-completion
```

Install from a local checkout:

```bash
python -m pip install -e .
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

Built-in names include:

```text
dict if len list not par print raise return set str tuple while yield
```

Use `%postfix_template list` in IPython to see the exact effective set, including
custom and disabled templates.

## Local Validation

Run tests:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

Build and check release artifacts:

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
```

Validate the wheel in a clean local virtual environment:

```bash
python -m venv .venv-check
.venv-check/bin/python -m pip install dist/ipython_postfix_completion-0.1.0-py3-none-any.whl
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
python -m twine upload dist/*
```

After the first upload creates the project on PyPI, prefer a project-scoped API
token for future releases.
