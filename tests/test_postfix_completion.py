from unittest.mock import Mock

import pytest

from IPython import get_ipython
from IPython.core.completer import provisionalcompleter
from IPython.core.error import UsageError
from IPython.terminal.shortcuts import create_ipython_shortcuts
from IPython.terminal.ptutils import IPythonPTCompleter
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document

import ipython_postfix_completion as postfix


def _set_postfix_config(ip, **values):
    section = ip.config.PostfixCompletionConfig
    old_values = {
        name: section[name] for name in values if name in section
    }
    missing = {name for name in values if name not in section}
    for name, value in values.items():
        section[name] = value
    return old_values, missing


def _restore_postfix_config(ip, old_values, missing):
    section = ip.config.PostfixCompletionConfig
    for name in missing:
        section.pop(name, None)
    for name, value in old_values.items():
        section[name] = value


def _completion_texts(text):
    ip = get_ipython()
    ip.Completer.use_jedi = False
    with provisionalcompleter():
        return [
            completion.text
            for completion in ip.Completer.completions(text=text, offset=len(text))
            if completion.type == "postfix"
        ]


def _single_completion_text(text):
    completions = _completion_texts(text)
    assert len(completions) == 1
    return completions[0]


def test_postfix_matcher_expands_basic_templates():
    ip = get_ipython()
    postfix.load_ipython_extension(ip)
    try:
        assert "print(1)" in _completion_texts("1.print")
        assert "len(items)" in _completion_texts("items.len")
        assert "if value:\n    " in _completion_texts("value.if")
        assert "print(foo(a + b))" in _completion_texts("foo(a + b).print")
    finally:
        postfix.unload_ipython_extension(ip)


@pytest.mark.parametrize(
    "template, source, expected",
    [
        ("not", "x.not", "not x"),
        ("par", "x.par", "(x)"),
        ("var", "result.var", "result = "),
        ("await", "task.await", "await task"),
        ("return", "x.return", "return x"),
        ("if", "x.if", "if x:\n    "),
        ("while", "x.while", "while x:\n    "),
        ("print", "x.print", "print(x)"),
        ("len", "items.len", "len(items)"),
        ("raise", "err.raise", "raise err"),
        ("yield", "x.yield", "yield x"),
        ("str", "x.str", "str(x)"),
        ("list", "x.list", "list(x)"),
        ("set", "x.set", "set(x)"),
        ("dict", "x.dict", "dict(x)"),
        ("tuple", "x.tuple", "tuple(x)"),
    ],
)
def test_all_supported_templates_expand(template, source, expected):
    ip = get_ipython()
    postfix.load_ipython_extension(ip)
    try:
        assert _single_completion_text(source) == expected
    finally:
        postfix.unload_ipython_extension(ip)


def test_postfix_matcher_shows_templates_after_trigger():
    ip = get_ipython()
    postfix.load_ipython_extension(ip)
    try:
        completions = _completion_texts("x.")
        assert "print(x)" in completions
        assert "len(x)" in completions
        assert "not x" in completions
    finally:
        postfix.unload_ipython_extension(ip)


def test_postfix_matcher_preserves_indentation():
    ip = get_ipython()
    postfix.load_ipython_extension(ip)
    try:
        with provisionalcompleter():
            completions = [
                completion
                for completion in ip.Completer.completions(
                    text="    print(x).print", offset=len("    print(x).print")
                )
                if completion.type == "postfix"
            ]

        assert len(completions) == 1
        completion = completions[0]
        line = "    print(x).print"
        assert line[: completion.start] + completion.text == "    print(print(x))"
    finally:
        postfix.unload_ipython_extension(ip)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("    x.if", "    if x:\n        "),
        ("    x.while", "    while x:\n        "),
    ],
)
def test_block_templates_preserve_indentation(source, expected):
    ip = get_ipython()
    postfix.load_ipython_extension(ip)
    try:
        with provisionalcompleter():
            completions = [
                completion
                for completion in ip.Completer.completions(
                    text=source, offset=len(source)
                )
                if completion.type == "postfix"
            ]

        assert len(completions) == 1
        completion = completions[0]
        assert source[: completion.start] + completion.text == expected
    finally:
        postfix.unload_ipython_extension(ip)


def test_postfix_matcher_rejects_invalid_expressions():
    ip = get_ipython()
    postfix.load_ipython_extension(ip)
    try:
        assert _completion_texts("x = 1.print") == []
        assert _completion_texts("x # c.print") == []
        assert _completion_texts("'x.print") == []
        assert _completion_texts("value.unknown") == []
    finally:
        postfix.unload_ipython_extension(ip)


def test_config_adds_custom_template():
    ip = get_ipython()
    old_values, missing = _set_postfix_config(
        ip, templates={"debug": "print({expr}=)"}
    )
    try:
        postfix.load_ipython_extension(ip)
        assert _single_completion_text("x.debug") == "print(x=)"
    finally:
        postfix.unload_ipython_extension(ip)
        _restore_postfix_config(ip, old_values, missing)


def test_config_overrides_builtin_template():
    ip = get_ipython()
    old_values, missing = _set_postfix_config(
        ip, templates={"print": "display({expr})"}
    )
    try:
        postfix.load_ipython_extension(ip)
        assert _single_completion_text("x.print") == "display(x)"
    finally:
        postfix.unload_ipython_extension(ip)
        _restore_postfix_config(ip, old_values, missing)


def test_config_disables_template():
    ip = get_ipython()
    old_values, missing = _set_postfix_config(ip, disabled_templates=["tuple"])
    try:
        postfix.load_ipython_extension(ip)
        assert _completion_texts("x.tuple") == []
    finally:
        postfix.unload_ipython_extension(ip)
        _restore_postfix_config(ip, old_values, missing)


def test_config_custom_template_preserves_indentation():
    ip = get_ipython()
    old_values, missing = _set_postfix_config(
        ip, templates={"forin": "for item in {expr}:\n{indent}    "}
    )
    try:
        postfix.load_ipython_extension(ip)
        with provisionalcompleter():
            completions = [
                completion
                for completion in ip.Completer.completions(
                    text="    xs.forin", offset=len("    xs.forin")
                )
                if completion.type == "postfix"
            ]

        assert len(completions) == 1
        completion = completions[0]
        assert "    xs.forin"[: completion.start] + completion.text == (
            "    for item in xs:\n        "
        )
    finally:
        postfix.unload_ipython_extension(ip)
        _restore_postfix_config(ip, old_values, missing)


def test_postfix_template_magic_add_remove_reset_and_list(capsys):
    ip = get_ipython()
    postfix.load_ipython_extension(ip)
    try:
        ip.run_line_magic("postfix_template", 'add debug "print({expr}=)"')
        assert _single_completion_text("x.debug") == "print(x=)"

        ip.run_line_magic("postfix_template", "remove tuple")
        assert _completion_texts("x.tuple") == []

        ip.run_line_magic("postfix_template", "list")
        output = capsys.readouterr().out
        assert "debug\tcustom\tprint({expr}=)" in output
        assert "tuple\tdisabled\t<disabled>" in output

        ip.run_line_magic("postfix_template", "reset tuple")
        assert _single_completion_text("x.tuple") == "tuple(x)"

        ip.run_line_magic("postfix_template", "reset debug")
        assert _completion_texts("x.debug") == []
    finally:
        postfix.unload_ipython_extension(ip)


def test_postfix_template_magic_reset_all():
    ip = get_ipython()
    postfix.load_ipython_extension(ip)
    try:
        ip.run_line_magic("postfix_template", "add print display({expr})")
        ip.run_line_magic("postfix_template", "remove tuple")
        assert _single_completion_text("x.print") == "display(x)"
        assert _completion_texts("x.tuple") == []

        ip.run_line_magic("postfix_template", "reset --all")
        assert _single_completion_text("x.print") == "print(x)"
        assert _single_completion_text("x.tuple") == "tuple(x)"
    finally:
        postfix.unload_ipython_extension(ip)


@pytest.mark.parametrize(
    "line, message",
    [
        ("add 1bad print({expr})", "Invalid postfix template name"),
        ("add bad print(x)", "must include {expr}"),
        ("add bad print({foo})", "unknown field"),
    ],
)
def test_postfix_template_magic_rejects_invalid_templates(line, message):
    ip = get_ipython()
    postfix.load_ipython_extension(ip)
    try:
        with pytest.raises(UsageError, match=message):
            ip.run_line_magic("postfix_template", line)
    finally:
        postfix.unload_ipython_extension(ip)


def test_unload_discards_runtime_templates_but_config_reload_still_applies():
    ip = get_ipython()
    old_values, missing = _set_postfix_config(
        ip, templates={"debug": "print({expr}=)"}
    )
    try:
        postfix.load_ipython_extension(ip)
        ip.run_line_magic("postfix_template", "add temp repr({expr})")
        assert _single_completion_text("x.debug") == "print(x=)"
        assert _single_completion_text("x.temp") == "repr(x)"

        postfix.unload_ipython_extension(ip)
        postfix.load_ipython_extension(ip)
        assert _single_completion_text("x.debug") == "print(x=)"
        assert _completion_texts("x.temp") == []
    finally:
        postfix.unload_ipython_extension(ip)
        _restore_postfix_config(ip, old_values, missing)


def test_unload_restores_existing_postfix_template_magic():
    ip = get_ipython()
    original = lambda line: line
    previous = ip.magics_manager.magics["line"].get("postfix_template")
    previous_attr = getattr(
        ip.magics_manager.user_magics, "postfix_template", None
    )
    had_previous_attr = hasattr(ip.magics_manager.user_magics, "postfix_template")
    ip.register_magic_function(original, "line", "postfix_template")
    try:
        postfix.load_ipython_extension(ip)
        assert ip.magics_manager.magics["line"]["postfix_template"] is not original

        postfix.unload_ipython_extension(ip)
        assert ip.magics_manager.magics["line"]["postfix_template"] is original
        assert ip.magics_manager.user_magics.postfix_template is original
    finally:
        postfix.unload_ipython_extension(ip)
        if previous is None:
            ip.magics_manager.magics["line"].pop("postfix_template", None)
        else:
            ip.magics_manager.magics["line"]["postfix_template"] = previous
        if had_previous_attr:
            ip.magics_manager.user_magics.postfix_template = previous_attr
        else:
            try:
                delattr(ip.magics_manager.user_magics, "postfix_template")
            except AttributeError:
                pass


def test_load_and_unload_register_matcher_and_restore_key_bindings():
    ip = get_ipython()
    ip.pt_app = Mock()
    ip.pt_app.key_bindings = create_ipython_shortcuts(ip)
    ip.pt_app.completer = IPythonPTCompleter(shell=ip)
    original_key_bindings = ip.pt_app.key_bindings
    original_completer = ip.pt_app.completer

    try:
        postfix.load_ipython_extension(ip)

        assert postfix.postfix_matcher in ip.Completer.custom_matchers
        assert ip.pt_app.key_bindings is not original_key_bindings
        assert ip.pt_app.completer is not original_completer
        assert (
            getattr(ip.meta, "postfix_completion").original_key_bindings
            is original_key_bindings
        )
        assert (
            getattr(ip.meta, "postfix_completion").original_completer
            is original_completer
        )

        postfix.unload_ipython_extension(ip)

        assert postfix.postfix_matcher not in ip.Completer.custom_matchers
        assert ip.pt_app.key_bindings is original_key_bindings
        assert ip.pt_app.completer is original_completer
        assert not hasattr(ip.meta, "postfix_completion")
    finally:
        postfix.unload_ipython_extension(ip)
        ip.pt_app = None


def test_load_without_prompt_toolkit_app_only_registers_matcher():
    ip = get_ipython()
    old_pt_app = getattr(ip, "pt_app", None)
    ip.pt_app = None
    try:
        postfix.load_ipython_extension(ip)
        assert postfix.postfix_matcher in ip.Completer.custom_matchers
        assert getattr(ip.meta, "postfix_completion").original_key_bindings is None
    finally:
        postfix.unload_ipython_extension(ip)
        ip.pt_app = old_pt_app


def test_extension_manager_loads_postfix_extension():
    ip = get_ipython()
    postfix.unload_ipython_extension(ip)

    try:
        result = ip.extension_manager.load_extension("ipython_postfix_completion")
        assert result is None
        assert postfix.postfix_matcher in ip.Completer.custom_matchers
    finally:
        ip.extension_manager.unload_extension("ipython_postfix_completion")
        postfix.unload_ipython_extension(ip)


def test_exact_postfix_tab_expands_buffer():
    buffer = Buffer(document=Document("1.print", cursor_position=len("1.print")))

    assert postfix._expand_buffer(buffer)
    assert buffer.text == "print(1)"


def test_exact_postfix_tab_preserves_indentation():
    buffer = Buffer(
        document=Document("    x.print", cursor_position=len("    x.print"))
    )

    assert postfix._expand_buffer(buffer)
    assert buffer.text == "    print(x)"


def test_insert_trigger_starts_completion_for_valid_expression():
    buffer = Buffer(document=Document("x", cursor_position=len("x")))
    started = []
    buffer.start_completion = lambda select_first=False: started.append(select_first)

    assert postfix._insert_trigger_and_maybe_complete(buffer)
    assert buffer.text == "x."
    assert started == [False]


def test_insert_trigger_skips_completion_for_invalid_expression():
    buffer = Buffer(document=Document("'x", cursor_position=len("'x")))
    started = []
    buffer.start_completion = lambda select_first=False: started.append(select_first)

    assert not postfix._insert_trigger_and_maybe_complete(buffer)
    assert buffer.text == "'x."
    assert started == []


def test_non_exact_postfix_tab_does_not_expand_buffer():
    buffer = Buffer(document=Document("1.pr", cursor_position=len("1.pr")))

    assert not postfix._expand_buffer(buffer)
    assert buffer.text == "1.pr"


def test_prompt_toolkit_postfix_completion_display_and_style():
    ip = get_ipython()
    postfix.load_ipython_extension(ip)
    try:
        wrapped = postfix.PostfixPTCompleter(IPythonPTCompleter(shell=ip))
        with provisionalcompleter():
            completions = list(
                wrapped._get_completions("x.", len("x."), len("x."), ip.Completer)
            )
        postfix_completions = [
            completion
            for completion in completions
            if completion.display_meta_text == "postfix"
        ]

        assert postfix_completions
        assert any(
            completion.display_text == ".print -> print(x)"
            for completion in postfix_completions
        )
        assert {completion.style for completion in postfix_completions} == {
            "bg:#44475a #f8f8f2"
        }
        assert {completion.selected_style for completion in postfix_completions} == {
            "bg:#6272a4 #ffffff"
        }
    finally:
        postfix.unload_ipython_extension(ip)


def test_prompt_toolkit_postfix_completion_uses_configured_style():
    ip = get_ipython()
    old_values, missing = _set_postfix_config(
        ip,
        style="bg:#111111 #eeeeee",
        selected_style="bg:#222222 #ffffff",
    )
    postfix.load_ipython_extension(ip)
    try:
        wrapped = postfix.PostfixPTCompleter(IPythonPTCompleter(shell=ip))
        with provisionalcompleter():
            completions = list(
                wrapped._get_completions("x.", len("x."), len("x."), ip.Completer)
            )
        postfix_completions = [
            completion
            for completion in completions
            if completion.display_meta_text == "postfix"
        ]

        assert postfix_completions
        assert {completion.style for completion in postfix_completions} == {
            "bg:#111111 #eeeeee"
        }
        assert {completion.selected_style for completion in postfix_completions} == {
            "bg:#222222 #ffffff"
        }
    finally:
        postfix.unload_ipython_extension(ip)
        _restore_postfix_config(ip, old_values, missing)
