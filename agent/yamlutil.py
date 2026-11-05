"""Indent-sensitive reader for the config files shipped with this agent.

The subset is mappings, lists of mappings, scalars, and comments. It exists so
the agent installs on runtimes that do not have a PyYAML wheel.
"""

from __future__ import annotations


def load_yaml(text: str):
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        content = _strip_comment(raw.strip())
        if content:
            lines.append((indent, content))
    if not lines:
        return {}
    value, index = _parse(lines, 0, lines[0][0])
    if index != len(lines):
        raise ValueError("Could not parse the full YAML document")
    return value


def _parse(lines: list[tuple[int, str]], index: int, indent: int):
    if lines[index][1].startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_map(lines, index, indent)


def _parse_list(lines: list[tuple[int, str]], index: int, indent: int):
    items = []
    while index < len(lines) and lines[index][0] == indent and lines[index][1].startswith("- "):
        first = lines[index][1][2:].strip()
        index += 1
        if not first:
            if index < len(lines) and lines[index][0] > indent:
                nested, index = _parse(lines, index, lines[index][0])
                items.append(nested)
            else:
                items.append(None)
            continue
        if ":" not in first:
            items.append(_scalar(first))
            continue
        key, raw_value = _split(first)
        item: dict = {}
        if raw_value == "":
            if index < len(lines) and lines[index][0] > indent:
                nested, index = _parse(lines, index, lines[index][0])
                item[key] = nested
            else:
                item[key] = None
        else:
            item[key] = _scalar(raw_value)
        if index < len(lines) and lines[index][0] > indent and not lines[index][1].startswith("- "):
            nested, index = _parse_map(lines, index, lines[index][0])
            item.update(nested)
        items.append(item)
    return items, index


def _parse_map(lines: list[tuple[int, str]], index: int, indent: int):
    mapping: dict = {}
    while index < len(lines) and lines[index][0] == indent and not lines[index][1].startswith("- "):
        key, raw_value = _split(lines[index][1])
        index += 1
        if raw_value == "" and index < len(lines) and lines[index][0] > indent:
            nested, index = _parse(lines, index, lines[index][0])
            mapping[key] = nested
        else:
            mapping[key] = _scalar(raw_value)
    return mapping, index


def _split(content: str) -> tuple[str, str]:
    key, value = content.split(":", 1)
    return key.strip(), value.strip()


def _strip_comment(content: str) -> str:
    quoted = False
    quote = ""
    for index, char in enumerate(content):
        if char in {"'", '"'} and (index == 0 or content[index - 1] != "\\"):
            if quoted and char == quote:
                quoted = False
            elif not quoted:
                quoted = True
                quote = char
        elif char == "#" and not quoted:
            return content[:index].strip()
    return content


def _scalar(value: str):
    if value == "":
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "~"}:
        return None
    try:
        if any(char in value for char in ".eE"):
            return float(value)
        return int(value)
    except ValueError:
        return value
