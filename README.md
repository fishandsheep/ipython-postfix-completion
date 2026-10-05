# IPython Postfix Completion

Complete Python expressions with postfix templates in IPython: type an
expression, a dot, and a template name, then press Tab.

## Install

```bash
uv tool install ipython --with ipython-postfix-completion
```

Start IPython and load the extension:

```python
%load_ext ipython_postfix_completion
```

## Common Templates

`items.for<Tab>` creates a loop. Tab selects `item`, then `pass`; type to
replace a selection.

```python
for item in items:
    pass
```

An integer literal is wrapped in `range(...)`, so `10.for<Tab>` produces
`for item in range(10):`.

`items.fori<Tab>` creates an indexed loop. Tab selects `i`, `value`, then
`pass`. For an integer literal, it uses `enumerate(range(n))`.

`condition.if<Tab>` creates an `if` block with a selected `pass`:

```python
if condition:
    pass
```

`condition.ef<Tab>` creates `if`/`elif`/`else` branches. Tab selects each
placeholder in order: `pass`, `cond`, `pass`, `pass`. The `cond` selection
does not include its colon.

Other built-ins: `print`, `len`, `not`, `par`, `var`, `await`, `return`,
`while`, `raise`, `yield`, `str`, `list`, `set`, `dict`, `tuple`, `type`, and
`range`. Use `%postfix_template list` to see their expansions.

Shift+Tab moves back to the previous placeholder. Custom Tab navigation is
supported in terminal IPython.

## Load Automatically

The default configuration file is:

```text
~/.ipython/profile_default/ipython_config.py
```

Create it with:

```bash
ipython profile create
```

Add the extension and any persistent templates there:

```python
c.InteractiveShellApp.extensions = ["ipython_postfix_completion"]
c.PostfixCompletionConfig.templates = {
    "debug": "print({expr}=)",
}
```

`IPYTHONDIR` and `--ipython-dir` can change the configuration directory. Use
`ipython locate profile default` to find the active profile. See the [official
IPython configuration guide](https://ipython.readthedocs.io/en/stable/development/config.html).

For runtime template commands, detailed behavior, and contributor or release
steps, see [the extended guide](docs/REFERENCE.md).
