"""Postfix completion extension for IPython."""

from __future__ import annotations

import ast
import io
import re
import string
import tokenize
from dataclasses import dataclass
from typing import Callable

from IPython.core.completer import (
    CompletionContext,
    SimpleCompletion,
    context_matcher,
)
from IPython.core.error import UsageError
from IPython.terminal.ptutils import IPythonPTCompleter
from traitlets import Dict as TraitletsDict
from traitlets import Bool
from traitlets import List as TraitletsList
from traitlets import Unicode
from traitlets.config.configurable import Configurable


_POSTFIX_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<body>.*)\.(?P<prefix>[A-Za-z_]*)$")
_PREFIX_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_STATE_NAME = "postfix_completion"
_STYLE = "bg:#44475a #f8f8f2"
_SELECTED_STYLE = "bg:#6272a4 #ffffff"
_TEMPLATE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_TEMPLATE_FIELDS = {"expr", "indent"}
_MAGIC_NAME = "postfix_template"
_NO_MAGIC = object()
_NO_MAGIC_ATTR = object()
_ACTIVE_STATE: "PostfixState | None" = None
_VAR_TEMPLATE = "key = {expr}"
_VAR_PLACEHOLDER = "key"
_PLACEHOLDER_ATTR = "_postfix_completion_placeholder"
_OPENING_BRACKETS = {"(": ")", "[": "]", "{": "}"}
_CLOSING_BRACKETS = {closer: opener for opener, closer in _OPENING_BRACKETS.items()}
_STRING_START_RE = re.compile(r"(?i)^(?P<prefix>[rubf]*)(?P<quote>'''|\"\"\"|'|\")")


class _TemplateFormatter(string.Formatter):
    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            return kwargs[key]
        return super().get_value(key, args, kwargs)


_FORMATTER = _TemplateFormatter()


DEFAULT_TEMPLATES: dict[str, str] = {
    "print": "print({expr})",
    "len": "len({expr})",
    "not": "not {expr}",
    "par": "({expr})",
    "var": _VAR_TEMPLATE,
    "await": "await {expr}",
    "return": "return {expr}",
    "if": "if {expr}:\n{indent}    ",
    "while": "while {expr}:\n{indent}    ",
    "raise": "raise {expr}",
    "yield": "yield {expr}",
    "str": "str({expr})",
    "list": "list({expr})",
    "set": "set({expr})",
    "dict": "dict({expr})",
    "tuple": "tuple({expr})",
}


class PostfixCompletionConfig(Configurable):
    """Configurable postfix completion templates."""

    templates = TraitletsDict(
        default_value={},
        help="Postfix template strings keyed by template name.",
    ).tag(config=True)
    disabled_templates = TraitletsList(
        Unicode(),
        default_value=[],
        help="Template names to disable.",
    ).tag(config=True)
    style = Unicode(
        _STYLE,
        help="Prompt-toolkit style for postfix completion menu entries.",
    ).tag(config=True)
    selected_style = Unicode(
        _SELECTED_STYLE,
        help="Prompt-toolkit selected style for postfix completion menu entries.",
    ).tag(config=True)
    smart_tab_jump = Bool(
        True,
        help="Move Tab over adjacent Python string and bracket closing tokens.",
    ).tag(config=True)


def _validate_template_name(name: str) -> None:
    if not _TEMPLATE_NAME_RE.match(name):
        raise UsageError(
            f"Invalid postfix template name {name!r}: expected [A-Za-z_][A-Za-z0-9_]*"
        )


def _validate_template(template: str) -> None:
    fields = {
        field_name
        for _, field_name, _, _ in _FORMATTER.parse(template)
        if field_name is not None
    }
    unknown = fields - _ALLOWED_TEMPLATE_FIELDS
    if unknown:
        names = ", ".join(sorted(f"{{{name}}}" for name in unknown))
        raise UsageError(
            "Postfix template may only use {expr} and {indent}; "
            f"unknown field(s): {names}"
        )
    if "expr" not in fields:
        raise UsageError("Postfix template must include {expr}.")


def _validate_templates(templates: dict[str, str]) -> None:
    for name, template in templates.items():
        _validate_template_name(name)
        if not isinstance(template, str):
            raise UsageError(f"Postfix template {name!r} must be a string.")
        _validate_template(template)


def _render_template(template: str, expr: str, indent: str = "") -> str:
    return _FORMATTER.format(template, expr=expr, indent=indent)


@dataclass
class PostfixState:
    matcher: Callable[[CompletionContext], dict]
    config: PostfixCompletionConfig
    original_key_bindings: object | None = None
    original_completer: object | None = None
    original_magic: object = _NO_MAGIC
    original_magic_attr: object = _NO_MAGIC_ATTR
    runtime_templates: dict[str, str] | None = None
    runtime_disabled_templates: set[str] | None = None

    def __post_init__(self) -> None:
        if self.runtime_templates is None:
            self.runtime_templates = {}
        if self.runtime_disabled_templates is None:
            self.runtime_disabled_templates = set()

    def effective_templates(self) -> dict[str, str]:
        _validate_templates(dict(self.config.templates))
        templates = dict(DEFAULT_TEMPLATES)
        templates.update(self.config.templates)
        templates.update(self.runtime_templates or {})
        disabled = set(self.config.disabled_templates) | (
            self.runtime_disabled_templates or set()
        )
        for name in disabled:
            templates.pop(name, None)
        return templates

    def template_origin(self, name: str) -> str:
        if name in (self.runtime_disabled_templates or set()) or name in set(
            self.config.disabled_templates
        ):
            return "disabled"
        if name in (self.runtime_templates or {}):
            return "custom"
        if name in self.config.templates:
            return "custom"
        if name in DEFAULT_TEMPLATES:
            return "builtin"
        return "custom"


def _line_prefix(line: str) -> tuple[str, str, str] | None:
    match = _POSTFIX_RE.match(line)
    if not match:
        return None
    expr = match.group("body")
    prefix = match.group("prefix")
    if not expr or (prefix and not _PREFIX_RE.match(prefix)):
        return None
    return match.group("indent"), expr, prefix


def _valid_expression(expr: str) -> bool:
    try:
        ast.parse(expr, mode="eval")
    except SyntaxError:
        return False

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(expr).readline))
    except tokenize.TokenError:
        return False

    meaningful = [
        token
        for token in tokens
        if token.type
        not in {
            tokenize.ENCODING,
            tokenize.ENDMARKER,
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
        }
    ]
    if not meaningful:
        return False
    if any(
        token.type in {tokenize.COMMENT, tokenize.ERRORTOKEN} for token in meaningful
    ):
        return False
    return meaningful[-1].end[1] == len(expr.rstrip())


def _state_or_default(state: PostfixState | None = None) -> PostfixState | None:
    return state or _ACTIVE_STATE


def _effective_templates(state: PostfixState | None = None) -> dict[str, str]:
    state = _state_or_default(state)
    if state is None:
        return dict(DEFAULT_TEMPLATES)
    return state.effective_templates()


def _apply_template(
    name: str, expr: str, indent: str = "", state: PostfixState | None = None
) -> str:
    return _render_template(_effective_templates(state)[name], expr, indent)


def _postfix_candidates(
    line: str, *, exact: bool = False, state: PostfixState | None = None
) -> tuple[str, list[str]]:
    parsed = _line_prefix(line)
    if parsed is None:
        return "", []
    indent, expr, prefix = parsed
    if not _valid_expression(expr):
        return "", []

    templates = _effective_templates(state)
    names = [
        name
        for name in templates
        if (name == prefix if exact else name.startswith(prefix))
    ]
    return f"{expr}.{prefix}", [
        _render_template(templates[name], expr, indent) for name in names
    ]


def _template_name(
    fragment: str,
    expansion: str,
    indent: str = "",
    state: PostfixState | None = None,
) -> str | None:
    expr, _, prefix = fragment.rpartition(".")
    for name, template in _effective_templates(state).items():
        if not name.startswith(prefix):
            continue
        if _render_template(template, expr, indent) == expansion:
            return name
    return None


@context_matcher(identifier="ipython_postfix_completion")
def postfix_matcher(context: CompletionContext) -> dict:
    line = context.line_with_cursor[: context.cursor_position]
    matched_fragment, candidates = _postfix_candidates(line)
    return {
        "completions": [
            SimpleCompletion(candidate, type="postfix") for candidate in candidates
        ],
        "matched_fragment": matched_fragment or context.token,
        "suppress": False,
    }


def _expand_buffer(buffer) -> bool:
    document = buffer.document
    line = document.current_line_before_cursor
    matched_fragment, candidates = _postfix_candidates(line, exact=True)
    if len(candidates) != 1:
        return False
    parsed = _line_prefix(line)
    buffer.delete_before_cursor(len(matched_fragment))
    expansion_start = buffer.cursor_position
    buffer.insert_text(candidates[0])
    if (
        parsed is not None
        and parsed[2] == "var"
        and _effective_templates().get("var") == _VAR_TEMPLATE
    ):
        _select_placeholder(
            buffer,
            expansion_start,
            expansion_start + len(_VAR_PLACEHOLDER),
            buffer.cursor_position,
        )
    return True


def _select_placeholder(buffer, start: int, end: int, final_cursor: int) -> None:
    from prompt_toolkit.selection import SelectionState, SelectionType

    buffer.cursor_position = end
    buffer.selection_state = SelectionState(start, SelectionType.CHARACTERS)
    buffer.selection_state.enter_shift_mode()
    setattr(buffer, _PLACEHOLDER_ATTR, (start, end, final_cursor))


def _has_active_placeholder(buffer) -> bool:
    placeholder = getattr(buffer, _PLACEHOLDER_ATTR, None)
    selection = buffer.selection_state
    if placeholder is None or selection is None:
        return False
    start, end, _ = placeholder
    return (
        selection.shift_mode
        and selection.original_cursor_position == start
        and buffer.cursor_position == end
        and buffer.text[start:end] == _VAR_PLACEHOLDER
    )


def _accept_placeholder(buffer) -> bool:
    if not _has_active_placeholder(buffer):
        return False
    _, _, final_cursor = getattr(buffer, _PLACEHOLDER_ATTR)
    buffer.exit_selection()
    buffer.cursor_position = final_cursor
    delattr(buffer, _PLACEHOLDER_ATTR)
    return True


def _line_offsets(source: str) -> list[int]:
    offsets = [0]
    offsets.extend(match.end() for match in re.finditer("\n", source))
    return offsets


def _absolute_token_position(
    position: tuple[int, int], line_offsets: list[int], source_length: int
) -> int:
    row, column = position
    if 0 < row <= len(line_offsets):
        return min(line_offsets[row - 1] + column, source_length)
    return source_length


def _python_tokens(source: str) -> list[tuple[tokenize.TokenInfo, int, int]]:
    line_offsets = _line_offsets(source)
    tokens: list[tuple[tokenize.TokenInfo, int, int]] = []
    generator = tokenize.generate_tokens(io.StringIO(source).readline)
    try:
        for token in generator:
            start = _absolute_token_position(token.start, line_offsets, len(source))
            end = _absolute_token_position(token.end, line_offsets, len(source))
            tokens.append((token, start, end))
    except (IndentationError, SyntaxError, tokenize.TokenError):
        # Incomplete interactive input is normal. Tokens emitted before the
        # error still describe whether the adjacent closer is syntactic.
        pass
    return tokens


def _string_parts(value: str) -> tuple[str, str] | None:
    match = _STRING_START_RE.match(value)
    if match is None:
        return None
    return match.group("prefix"), match.group("quote")


def _quoted_string_end(value: str, quote_start: int) -> int:
    quote = value[quote_start : quote_start + 3]
    delimiter = quote if quote in {"'''", '"""'} else value[quote_start]
    index = quote_start + len(delimiter)
    while index < len(value):
        if value.startswith(delimiter, index):
            backslashes = 0
            before = index - 1
            while before >= quote_start and value[before] == "\\":
                backslashes += 1
                before -= 1
            if backslashes % 2 == 0:
                return index + len(delimiter)
        index += 1
    return len(value)


def _fstring_brace_is_closing(value: str, cursor: int) -> bool:
    parts = _string_parts(value)
    if parts is None:
        return False
    prefix, quote = parts
    if "f" not in prefix.lower() or not value.endswith(quote):
        return False

    content_start = len(prefix) + len(quote)
    content_end = len(value) - len(quote)
    if not (content_start <= cursor < content_end) or value[cursor] != "}":
        return False

    # Each context is [kind, is_format_spec, bracket_stack]. Literal f-string
    # text and Python replacement expressions follow different brace rules.
    contexts: list[list[object]] = [["literal", False, []]]
    index = content_start
    while index <= cursor and contexts:
        kind, is_format_spec, bracket_stack = contexts[-1]
        character = value[index]

        if kind == "literal":
            if character == "{" and value.startswith("{{", index):
                index += 2
                continue
            if character == "{":
                contexts.append(["expression", False, []])
                index += 1
                continue
            if character == "}" and is_format_spec:
                if index == cursor:
                    return True
                contexts.pop()
                index += 1
                continue
            if character == "}" and value.startswith("}}", index):
                index += 2
                continue
            if character == "}":
                return False
            index += 1
            continue

        assert isinstance(bracket_stack, list)
        if character in {"'", '"'}:
            string_end = _quoted_string_end(value, index)
            if index < cursor < string_end:
                # A nested f-string can contain the candidate brace.
                prefix_start = index
                while prefix_start > content_start and value[prefix_start - 1] in (
                    "rRuUbBfF"
                ):
                    prefix_start -= 1
                nested = value[prefix_start:string_end]
                if "f" in value[prefix_start:index].lower():
                    return _fstring_brace_is_closing(nested, cursor - prefix_start)
                return False
            index = string_end
            continue
        if character == "#":
            newline = value.find("\n", index)
            if newline == -1 or cursor < newline:
                return False
            index = newline + 1
            continue
        if character in _OPENING_BRACKETS:
            bracket_stack.append(character)
            index += 1
            continue
        if character in _CLOSING_BRACKETS:
            if bracket_stack:
                if bracket_stack[-1] != _CLOSING_BRACKETS[character]:
                    return False
                bracket_stack.pop()
                index += 1
                continue
            if character == "}":
                if index == cursor:
                    return True
                contexts.pop()
                index += 1
                continue
            return False
        if character == ":" and not bracket_stack:
            contexts[-1] = ["literal", True, []]
            index += 1
            continue
        index += 1
    return False


def _string_closer_width(
    source: str,
    cursor: int,
    tokens: list[tuple[tokenize.TokenInfo, int, int]],
) -> int:
    fstring_end_types = {
        token_type
        for token_type in (
            getattr(tokenize, "FSTRING_END", None),
            getattr(tokenize, "TSTRING_END", None),
        )
        if token_type is not None
    }
    for token, start, end in tokens:
        if token.type in fstring_end_types and start == cursor:
            if token.string in {"'", '"', "'''", '"""'}:
                return len(token.string)
        if token.type != tokenize.STRING:
            continue
        parts = _string_parts(token.string)
        if parts is None:
            continue
        _, quote = parts
        if end - len(quote) == cursor and source.startswith(quote, cursor):
            return len(quote)
    return 0


def _bracket_closer_is_syntactic(
    source: str,
    cursor: int,
    tokens: list[tuple[tokenize.TokenInfo, int, int]],
) -> bool:
    closer = source[cursor]
    stack: list[str] = []
    for token, start, _ in tokens:
        if start > cursor:
            break
        if token.type != tokenize.OP or token.string not in (
            _OPENING_BRACKETS | _CLOSING_BRACKETS
        ):
            continue
        if start == cursor:
            return (
                token.string == closer
                and bool(stack)
                and (stack[-1] == _CLOSING_BRACKETS[closer])
            )
        if token.string in _OPENING_BRACKETS:
            stack.append(token.string)
        elif not stack or stack[-1] != _CLOSING_BRACKETS[token.string]:
            return False
        else:
            stack.pop()
    return False


def _fstring_brace_fallback(
    source: str,
    cursor: int,
    tokens: list[tuple[tokenize.TokenInfo, int, int]],
) -> bool:
    for token, start, end in tokens:
        if token.type == tokenize.STRING and start < cursor < end:
            return _fstring_brace_is_closing(token.string, cursor - start)
    return False


def _smart_tab_jump_width(source: str, cursor: int) -> int:
    if cursor >= len(source):
        return 0

    tokens = _python_tokens(source)
    quote_width = _string_closer_width(source, cursor, tokens)
    if quote_width:
        return quote_width

    if source[cursor] not in _CLOSING_BRACKETS:
        return 0
    line_start = source.rfind("\n", 0, cursor) + 1
    if not source[line_start:cursor].strip():
        return 0
    if _bracket_closer_is_syntactic(source, cursor, tokens):
        return 1
    if source[cursor] == "}" and _fstring_brace_fallback(source, cursor, tokens):
        return 1
    return 0


def _smart_tab_jump_enabled(state: PostfixState | None = None) -> bool:
    state = _state_or_default(state)
    return state is None or state.config.smart_tab_jump


def _can_smart_tab_jump(buffer, state: PostfixState | None = None) -> bool:
    if not _smart_tab_jump_enabled(state) or _has_active_placeholder(buffer):
        return False
    if _postfix_candidates(
        buffer.document.current_line_before_cursor, exact=True, state=state
    )[1]:
        return False
    return bool(_smart_tab_jump_width(buffer.text, buffer.cursor_position))


def _jump_over_closer(buffer) -> bool:
    width = _smart_tab_jump_width(buffer.text, buffer.cursor_position)
    if not width:
        return False
    if buffer.complete_state is not None:
        buffer.cancel_completion()
        width = _smart_tab_jump_width(buffer.text, buffer.cursor_position)
        if not width:
            return False
    buffer.cursor_position += width
    return True


def _insert_trigger_and_maybe_complete(buffer) -> bool:
    buffer.insert_text(".")
    if not _postfix_candidates(buffer.document.current_line_before_cursor)[1]:
        return False
    buffer.start_completion(select_first=False)
    return True


def _make_key_bindings(state: PostfixState | None = None):
    from prompt_toolkit.application.current import get_app
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.key_binding import KeyBindings

    key_bindings = KeyBindings()

    @Condition
    def has_exact_postfix() -> bool:
        buffer = get_app().current_buffer
        return bool(
            _postfix_candidates(
                buffer.document.current_line_before_cursor,
                exact=True,
                state=state,
            )[1]
        )

    @Condition
    def has_active_placeholder() -> bool:
        return _has_active_placeholder(get_app().current_buffer)

    @Condition
    def can_smart_tab_jump() -> bool:
        return _can_smart_tab_jump(get_app().current_buffer, state)

    @key_bindings.add("tab", filter=has_active_placeholder)
    def accept_placeholder(event) -> None:
        _accept_placeholder(event.current_buffer)

    @key_bindings.add("enter", filter=has_active_placeholder)
    def accept_placeholder_with_enter(event) -> None:
        _accept_placeholder(event.current_buffer)

    @key_bindings.add("tab", filter=has_exact_postfix)
    def expand_postfix(event) -> None:
        _expand_buffer(event.current_buffer)

    @key_bindings.add("tab", filter=can_smart_tab_jump)
    def smart_tab_jump(event) -> None:
        _jump_over_closer(event.current_buffer)

    @key_bindings.add(".")
    def insert_trigger(event) -> None:
        _insert_trigger_and_maybe_complete(event.current_buffer)

    return key_bindings


def _strip_optional_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value[1:-1]
        if isinstance(parsed, str):
            return parsed
    return value


def _postfix_template_magic(line: str) -> None:
    state = _ACTIVE_STATE
    if state is None:
        raise UsageError("Postfix completion extension is not loaded.")

    command_line = line.strip()
    if not command_line:
        raise UsageError("Usage: %postfix_template list|add|remove|reset ...")

    command, _, rest = command_line.partition(" ")
    rest = rest.strip()

    if command == "list":
        if rest:
            raise UsageError("Usage: %postfix_template list")
        _list_postfix_templates(state)
        return

    if command == "add":
        name, sep, template = rest.partition(" ")
        if not sep or not template.strip():
            raise UsageError("Usage: %postfix_template add NAME TEMPLATE")
        template = _strip_optional_quotes(template)
        _validate_template_name(name)
        _validate_template(template)
        assert state.runtime_templates is not None
        assert state.runtime_disabled_templates is not None
        state.runtime_templates[name] = template
        state.runtime_disabled_templates.discard(name)
        return

    if command == "remove":
        if not rest or " " in rest:
            raise UsageError("Usage: %postfix_template remove NAME")
        _validate_template_name(rest)
        assert state.runtime_templates is not None
        assert state.runtime_disabled_templates is not None
        state.runtime_templates.pop(rest, None)
        state.runtime_disabled_templates.add(rest)
        return

    if command == "reset":
        if rest == "--all":
            assert state.runtime_templates is not None
            assert state.runtime_disabled_templates is not None
            state.runtime_templates.clear()
            state.runtime_disabled_templates.clear()
            return
        if not rest or " " in rest:
            raise UsageError("Usage: %postfix_template reset NAME|--all")
        _validate_template_name(rest)
        assert state.runtime_templates is not None
        assert state.runtime_disabled_templates is not None
        state.runtime_templates.pop(rest, None)
        state.runtime_disabled_templates.discard(rest)
        return

    raise UsageError("Usage: %postfix_template list|add|remove|reset ...")


def _list_postfix_templates(state: PostfixState) -> None:
    effective = state.effective_templates()
    names = (
        set(DEFAULT_TEMPLATES)
        | set(state.config.templates)
        | set(state.runtime_templates or {})
        | set(state.config.disabled_templates)
        | set(state.runtime_disabled_templates or set())
    )
    for name in sorted(names):
        origin = state.template_origin(name)
        template = effective.get(name, "<disabled>")
        print(f"{name}\t{origin}\t{template}")


class PostfixPTCompleter(IPythonPTCompleter):
    """Prompt-toolkit adapter that gives postfix completions distinct display."""

    def __init__(self, wrapped: IPythonPTCompleter):
        super().__init__(
            ipy_completer=getattr(wrapped, "_ipy_completer", None),
            shell=getattr(wrapped, "shell", None),
        )
        self._wrapped = wrapped

    def _get_completions(self, body, offset, cursor_position, ipyc):
        from IPython.core.completer import _deduplicate_completions
        from prompt_toolkit.completion import Completion

        completions = _deduplicate_completions(body, ipyc.completions(body, offset))
        for completion in completions:
            if completion.type != "postfix":
                yield from self._wrapped._get_completions(
                    body, offset, cursor_position, _SingleCompletion(completion)
                )
                continue

            fragment = body[completion.start : completion.end]
            line_start = body.rfind("\n", 0, completion.start) + 1
            indent = body[line_start : completion.start]
            state = _state_or_default()
            key = _template_name(fragment, completion.text, indent, state) or "postfix"
            display = f".{key} -> {completion.text}"
            config = state.config if state is not None else None
            yield Completion(
                completion.text,
                start_position=completion.start - offset,
                display=display,
                display_meta="postfix",
                style=config.style if config is not None else _STYLE,
                selected_style=(
                    config.selected_style if config is not None else _SELECTED_STYLE
                ),
            )


class _SingleCompletion:
    def __init__(self, completion):
        self._completion = completion
        self.debug = False

    def completions(self, body, offset):
        yield self._completion


def _install_completer(ip, state: PostfixState) -> None:
    pt_app = getattr(ip, "pt_app", None)
    if pt_app is None:
        return
    original = getattr(pt_app, "completer", None)
    if not isinstance(original, IPythonPTCompleter):
        return

    state.original_completer = original
    pt_app.completer = PostfixPTCompleter(original)


def _install_key_binding(ip, state: PostfixState) -> None:
    pt_app = getattr(ip, "pt_app", None)
    if pt_app is None:
        return
    original = getattr(pt_app, "key_bindings", None)
    if original is None:
        return

    from prompt_toolkit.key_binding import merge_key_bindings

    state.original_key_bindings = original
    # prompt-toolkit resolves the last active binding. Keep extension bindings
    # last so their filtered Tab cases win while native bindings remain fallback.
    pt_app.key_bindings = merge_key_bindings([original, _make_key_bindings(state)])


def load_ipython_extension(ip) -> None:
    global _ACTIVE_STATE
    existing = getattr(ip.meta, _STATE_NAME, None)
    if existing is not None:
        return

    config = PostfixCompletionConfig(parent=ip)
    _validate_templates(dict(config.templates))
    for name in config.disabled_templates:
        _validate_template_name(name)

    state = PostfixState(matcher=postfix_matcher, config=config)
    state.original_magic = ip.magics_manager.magics["line"].get(_MAGIC_NAME, _NO_MAGIC)
    state.original_magic_attr = getattr(
        ip.magics_manager.user_magics, _MAGIC_NAME, _NO_MAGIC_ATTR
    )
    ip.Completer.custom_matchers.insert(0, postfix_matcher)
    ip.register_magic_function(_postfix_template_magic, "line", _MAGIC_NAME)
    _install_completer(ip, state)
    _install_key_binding(ip, state)
    setattr(ip.meta, _STATE_NAME, state)
    _ACTIVE_STATE = state


def unload_ipython_extension(ip) -> None:
    global _ACTIVE_STATE
    state = getattr(ip.meta, _STATE_NAME, None)
    if state is None:
        return

    try:
        ip.Completer.custom_matchers.remove(state.matcher)
    except ValueError:
        pass

    pt_app = getattr(ip, "pt_app", None)
    if pt_app is not None and state.original_key_bindings is not None:
        pt_app.key_bindings = state.original_key_bindings
    if pt_app is not None and state.original_completer is not None:
        pt_app.completer = state.original_completer

    current_magic = ip.magics_manager.magics["line"].get(_MAGIC_NAME)
    if current_magic is _postfix_template_magic:
        if state.original_magic is _NO_MAGIC:
            ip.magics_manager.magics["line"].pop(_MAGIC_NAME, None)
            if getattr(ip.magics_manager, "user_magics", None) is not None:
                try:
                    delattr(ip.magics_manager.user_magics, _MAGIC_NAME)
                except AttributeError:
                    pass
        else:
            ip.magics_manager.magics["line"][_MAGIC_NAME] = state.original_magic
            if state.original_magic_attr is _NO_MAGIC_ATTR:
                try:
                    delattr(ip.magics_manager.user_magics, _MAGIC_NAME)
                except AttributeError:
                    pass
            else:
                setattr(
                    ip.magics_manager.user_magics,
                    _MAGIC_NAME,
                    state.original_magic_attr,
                )

    try:
        del ip.meta[_STATE_NAME]
    except KeyError:
        pass
    if _ACTIVE_STATE is state:
        _ACTIVE_STATE = None
