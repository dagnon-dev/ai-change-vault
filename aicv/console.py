from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from textwrap import wrap

BOX = {
    "top_left": "┌",
    "top_right": "┐",
    "bottom_left": "└",
    "bottom_right": "┘",
    "horizontal": "─",
    "vertical": "│",
    "left_sep": "├",
    "right_sep": "┤",
    "middle_sep": "┼",
    "top_sep": "┬",
    "bottom_sep": "┴",
}


@dataclass(frozen=True)
class Table:
    title: str
    headers: Sequence[str]
    rows: Sequence[Sequence[object]]


def render_banner(title: str, subtitle: str | None = None, width: int = 76) -> str:
    lines = [title]
    if subtitle:
        lines.append(subtitle)
    content_width = max(len(line) for line in lines)
    box_width = max(width, content_width + 6)
    inner_width = box_width - 4
    rendered = [BOX["top_left"] + BOX["horizontal"] * (box_width - 2) + BOX["top_right"]]
    rendered.append(_render_single_line(title, inner_width, center=True))
    if subtitle:
        rendered.append(_render_single_line(subtitle, inner_width, center=True))
    rendered.append(BOX["bottom_left"] + BOX["horizontal"] * (box_width - 2) + BOX["bottom_right"])
    return "\n".join(rendered)


def render_key_value_table(title: str, items: Iterable[tuple[str, object]], width: int = 76) -> str:
    rows = [(key, _stringify(value)) for key, value in items]
    return render_table(Table(title=title, headers=("Field", "Value"), rows=rows), width=width)


def render_table(table: Table, width: int = 76) -> str:
    columns = len(table.headers)
    rows = [tuple(_stringify(cell) for cell in row) for row in table.rows]
    widths = [len(header) for header in table.headers]
    for row in rows:
        for index, cell in enumerate(row):
            for line in _wrap_cell(cell, 30):
                widths[index] = max(widths[index], len(line))
    total_width = sum(widths) + (columns - 1) * 3 + 4
    if total_width > width:
        shrink = total_width - width
        widths = _shrink_widths(widths, shrink, minimum=10)

    top = _border("top_left", "top_sep", "top_right", widths)
    sep = _border("left_sep", "middle_sep", "right_sep", widths)
    bottom = _border("bottom_left", "bottom_sep", "bottom_right", widths)
    out = [table.title, top, _render_row(table.headers, widths, header=True), sep]
    for row in rows:
        wrapped = [_wrap_cell(cell, widths[index]) for index, cell in enumerate(row)]
        height = max((len(cell_lines) for cell_lines in wrapped), default=1)
        for line_index in range(height):
            row_values = [
                wrapped[col][line_index] if line_index < len(wrapped[col]) else ""
                for col in range(columns)
            ]
            out.append(_render_row(row_values, widths))
    out.append(bottom)
    return "\n".join(out)


def render_status_table(title: str, items: Iterable[tuple[str, object]], width: int = 76) -> str:
    rows = [(key, _stringify(value)) for key, value in items]
    return render_table(Table(title=title, headers=("Status", "Value"), rows=rows), width=width)


def _render_single_line(text: str, inner_width: int, *, center: bool = False) -> str:
    pad = max(inner_width - 2, 0)
    cell = text.center(pad) if center else text.ljust(pad)
    return f"{BOX['vertical']} {cell} {BOX['vertical']}"


def _render_row(values: Sequence[object], widths: Sequence[int], *, header: bool = False) -> str:
    rendered = []
    for index, value in enumerate(values):
        text = _stringify(value)
        cell = text.center(widths[index]) if header else text.ljust(widths[index])
        rendered.append(cell)
    return f"{BOX['vertical']} " + f" {BOX['vertical']} ".join(rendered) + f" {BOX['vertical']}"


def _border(left: str, middle: str, right: str, widths: Sequence[int]) -> str:
    pieces = [BOX["horizontal"] * (width + 2) for width in widths]
    return BOX[left] + BOX[middle].join(pieces) + BOX[right]


def _wrap_cell(value: str, width: int) -> list[str]:
    if not value:
        return [""]
    return wrap(value, width=width, break_long_words=False, break_on_hyphens=False) or [value]


def _shrink_widths(widths: list[int], shrink: int, minimum: int) -> list[int]:
    result = widths[:]
    while shrink > 0:
        index = max(range(len(result)), key=lambda i: result[i])
        if result[index] <= minimum:
            break
        result[index] -= 1
        shrink -= 1
    return result


def _stringify(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)
