"""Selector de consola con teclado, sin dependencias externas."""

import os
import shutil
import sys
import textwrap
from contextlib import contextmanager
from typing import Optional, Sequence


class TerminalUnavailable(Exception):
    """La entrada o la salida no admiten un selector interactivo."""


def _decode_key(value: str) -> str:
    if value == "\x03":
        raise KeyboardInterrupt
    if value in ("\x04", "\x1a", ""):
        raise EOFError
    return {
        "\r": "enter", "\n": "enter", "x": "enter", "X": "enter", " ": "enter",
        "\x1b": "cancel", "q": "cancel", "Q": "cancel",
        "\x1b[A": "up", "\x1b[B": "down", "\x1bOA": "up", "\x1bOB": "down",
        "\x1b[C": "right", "\x1b[D": "left", "\x1bOC": "right", "\x1bOD": "left",
        "\x1b[H": "home", "\x1bOH": "home", "\x1b[1~": "home",
        "\x1b[F": "end", "\x1bOF": "end", "\x1b[4~": "end",
        "\x1b[5~": "page_up", "\x1b[6~": "page_down",
        "\xe0H": "up", "\xe0P": "down", "\xe0G": "home", "\xe0O": "end",
        "\xe0M": "right", "\xe0K": "left",
        "\xe0I": "page_up", "\xe0Q": "page_down",
    }.get(value, "ignore")


def _read_windows_key(getwch) -> str:
    value = getwch()
    if value in ("\x00", "\xe0"):
        value = "\xe0" + getwch()
    return _decode_key(value)


def _read_posix_key(descriptor: int) -> str:
    import select

    value = os.read(descriptor, 1)
    if value == b"\x1b":
        # Esc sola cancela; las flechas envían una secuencia de varios bytes.
        while len(value) < 16 and select.select([descriptor], [], [], 0.05)[0]:
            following = os.read(descriptor, 1)
            if not following:
                break
            value += following
            if len(value) > 2 and (following.isalpha() or following == b"~"):
                break
    return _decode_key(value.decode("latin-1"))


@contextmanager
def _key_reader():
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise TerminalUnavailable
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetConsoleMode.restype = wintypes.BOOL
        kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.SetConsoleMode.restype = wintypes.BOOL
        try:
            handle = msvcrt.get_osfhandle(sys.stdout.fileno())
        except (OSError, ValueError):
            raise TerminalUnavailable
        original = wintypes.DWORD()
        if not kernel.GetConsoleMode(handle, ctypes.byref(original)):
            raise TerminalUnavailable
        if not kernel.SetConsoleMode(handle, original.value | 0x0004):
            raise TerminalUnavailable
        try:
            yield lambda: _read_windows_key(msvcrt.getwch)
        finally:
            kernel.SetConsoleMode(handle, original.value)
    else:
        import termios
        import tty

        if os.environ.get("TERM") == "dumb":
            raise TerminalUnavailable
        try:
            descriptor = sys.stdin.fileno()
            original = termios.tcgetattr(descriptor)
        except (OSError, ValueError, termios.error):
            raise TerminalUnavailable
        try:
            tty.setcbreak(descriptor)
        except (OSError, termios.error):
            termios.tcsetattr(descriptor, termios.TCSADRAIN, original)
            raise TerminalUnavailable
        try:
            yield lambda: _read_posix_key(descriptor)
        finally:
            termios.tcsetattr(descriptor, termios.TCSADRAIN, original)


class TerminalMenu:
    def select(self, title: str, options: Sequence[str], initial: int = 0,
               descriptions: Sequence[str] = ()) -> Optional[int]:
        if not options:
            raise ValueError("El selector necesita al menos una opción.")
        current = max(0, min(initial, len(options) - 1))
        top_row = 0
        with _key_reader() as read_key:
            try:
                # La pantalla alternativa conserva resultados y formularios en el historial.
                sys.stdout.write("\x1b[?1049h\x1b[?25l")
                while True:
                    top_row, page_rows, columns = self._draw(title, options, current, top_row, descriptions)
                    key = read_key()
                    if key in ("left", "right"):
                        current = (current + (1 if key == "right" else -1)) % len(options)
                    elif key in ("up", "down"):
                        step = 1 if key == "down" else -1
                        if columns == len(options):
                            # En una sola fila, también se puede recorrer con arriba/abajo.
                            current = (current + step) % len(options)
                        else:
                            column = current % columns
                            column_rows = (len(options) - 1 - column) // columns + 1
                            row = (current // columns + step) % column_rows
                            current = row * columns + column
                    elif key == "home":
                        current = 0
                    elif key == "end":
                        current = len(options) - 1
                    elif key == "page_up":
                        current = max(0, current - page_rows * columns)
                    elif key == "page_down":
                        current = min(len(options) - 1, current + page_rows * columns)
                    elif key == "enter":
                        return current
                    elif key == "cancel":
                        return None
            finally:
                sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
                sys.stdout.flush()

    @staticmethod
    def _draw(title, options, current, top_row, descriptions):
        size = shutil.get_terminal_size(fallback=(80, 24))
        width, height = max(1, size.columns - 1), max(3, size.lines)
        margin = 2 if width >= 40 else (1 if width >= 12 else 0)
        content_width = max(1, width - 2 * margin)
        indent = " " * margin

        def clean(text):
            return "".join(char if char.isprintable() else " " for char in text)

        def clipped(text, limit=content_width):
            text = clean(text)
            return text if len(text) <= limit else text[:max(0, limit - 3)] + "." * min(3, limit)

        labels = [clean(option) for option in options]
        gap = 4 if content_width >= 60 else 2
        minimum_cell = max(24, max(len(label) for label in labels) + 6)
        columns = min(len(options), max(1, (content_width + gap) // (minimum_cell + gap)))
        cell_width, remainder = divmod(content_width - gap * (columns - 1), columns)
        widths = [cell_width + (column < remainder) for column in range(columns)]
        total_rows = (len(options) + columns - 1) // columns

        name, separator, version = clean(title).partition(" | ")
        header = [""] if height >= 12 else []
        if height >= 18 and separator:
            header.extend([
                indent + "\x1b[1m" + clipped(name) + "\x1b[0m",
                indent + "\x1b[2m" + clipped(version) + "\x1b[0m",
            ])
        else:
            header.append(indent + "\x1b[1m" + clipped(title) + "\x1b[0m")
        if height >= 7:
            header.append("")

        footer = [""] if height >= 7 else []
        description = clean(descriptions[current]) if current < len(descriptions) else ""
        if description and height >= 10:
            if content_width >= 4:
                footer.extend(textwrap.wrap(description, width=content_width, max_lines=2, placeholder="..."))
            else:
                footer.append(clipped(description))
            footer.append("")
        controls_start = len(footer)
        footer.extend([
            "Flechas: mover   Enter/X/Espacio: abrir",
            "Inicio/Fin: extremos   RePag/AvPag: página   Esc/Q: volver",
        ] if height > 4 else ["Flechas: mover | Enter: abrir | Esc: volver"])
        if height >= 18:
            footer.append("")

        row_gap = 1 if height >= 10 else 0

        def visible_rows():
            available = height - len(header) - len(footer)
            return max(1, (available + row_gap) // (1 + row_gap))

        page_rows = visible_rows()
        scrolling = total_rows > page_rows and height >= 7
        if scrolling:
            footer.insert(controls_start, "")  # Contador de opciones visibles.
            page_rows = visible_rows()
        current_row = current // columns
        top_row = max(0, min(top_row, current_row, total_rows - page_rows))
        if current_row >= top_row + page_rows:
            top_row = current_row - page_rows + 1
        bottom_row = min(total_rows, top_row + page_rows)

        lines = list(header)
        for row in range(top_row, bottom_row):
            if row > top_row:
                lines.extend([""] * row_gap)
            cells = []
            for column, cell_width in enumerate(widths):
                index = row * columns + column
                text = "[{}] {}".format("x" if index == current else " ", labels[index]) if index < len(options) else ""
                padding = 1 if cell_width >= 6 else 0
                inner_width = cell_width - 2 * padding
                cell = " " * padding + clipped(text, inner_width).ljust(inner_width) + " " * padding
                cells.append("\x1b[1;7m" + cell + "\x1b[0m" if index == current else cell)
            lines.append(indent + (" " * gap).join(cells) + indent)
        if scrolling:
            footer[controls_start] = "Opciones {}-{} de {}".format(
                top_row * columns + 1, min(bottom_row * columns, len(options)), len(options),
            )
        for index, line in enumerate(footer):
            if not line:
                lines.append("")
            elif index >= controls_start:
                lines.append(indent + "\x1b[2m" + clipped(line) + "\x1b[0m")
            else:
                lines.append(indent + clipped(line))
        sys.stdout.write("\x1b[H\x1b[2J" + "\n".join(lines))
        sys.stdout.flush()
        return top_row, page_rows, columns
