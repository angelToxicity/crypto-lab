"""Selección automática, distribución en columnas y restauración de la consola."""

import io
import os
import re
import unittest
from contextlib import contextmanager, nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from cryptolab.console import ConsoleMenu
from cryptolab.domain import HashAlgorithm, HashResult
from cryptolab.forms import FormController
from cryptolab.terminal import TerminalMenu, _decode_key, _read_posix_key, _read_windows_key


class TerminalMenuTests(unittest.TestCase):
    def select(self, keys, options=("Primera", "Segunda", "Tercera"), initial=0, size=(80, 24),
               descriptions=()):
        output = io.StringIO()
        with patch("cryptolab.terminal._key_reader", return_value=nullcontext(Mock(side_effect=keys))), \
             patch("cryptolab.terminal.shutil.get_terminal_size", return_value=os.terminal_size(size)), \
             patch("sys.stdout", new=output):
            selected = TerminalMenu().select("Prueba", options, initial, descriptions)
        return selected, output.getvalue()

    def test_arrows_move_the_x_and_enter_confirms_the_current_option(self):
        selected, output = self.select(["right", "right", "enter"])
        self.assertEqual(2, selected)
        self.assertIn("[x] Primera", output)
        self.assertIn("[x] Segunda", output)
        self.assertIn("[x] Tercera", output)
        frames = output.split("\x1b[H\x1b[2J")[1:]
        self.assertTrue(all(frame.count("[x]") == 1 for frame in frames))
        self.assertIn("[ ] Segunda", frames[-1])

    def test_first_option_is_already_marked_before_pressing_a_key(self):
        selected, output = self.select(["enter"])
        self.assertEqual(0, selected)
        last_frame = output.split("\x1b[H\x1b[2J")[-1]
        self.assertIn("[x] Primera", last_frame)
        self.assertEqual(1, last_frame.count("[x]"))

    def test_right_arrow_moves_selection_without_a_separate_marking_step(self):
        selected, _ = self.select(["right", "enter"])
        self.assertEqual(1, selected)

    def test_enter_preserves_the_field_default(self):
        selected, output = self.select(["enter"], initial=2)
        self.assertEqual(2, selected)
        self.assertIn("[x] Tercera", output)

    def test_up_wraps_to_last_option(self):
        selected, _ = self.select(["up", "enter"])
        self.assertEqual(2, selected)

    def test_home_returns_to_first_option(self):
        selected, _ = self.select(["end", "home", "enter"])
        self.assertEqual(0, selected)

    def test_long_list_scrolls_within_terminal_height(self):
        options = tuple("Opción {}".format(index) for index in range(1, 31))
        selected, output = self.select(["end", "enter"], options, size=(60, 10))
        frame = output.split("\x1b[H\x1b[2J")[-1]
        self.assertEqual(29, selected)
        self.assertIn("[x] Opción 30", frame)
        self.assertIn("de 30", frame)
        self.assertNotIn("[ ] Opción 1\n", frame)
        self.assertLessEqual(len(frame.splitlines()), 10)

    def test_grid_uses_equal_cells_across_the_terminal_width(self):
        options = ("Uno", "Dos", "Tres", "Cuatro", "Cinco", "Seis", "Siete")
        for width, columns in ((80, 2), (120, 4), (200, 7)):
            with self.subTest(width=width):
                _, output = self.select(["enter"], options, size=(width, 24))
                frame = output.split("\x1b[H\x1b[2J")[-1]
                plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", frame)
                rows = [line for line in plain.splitlines() if "[ ]" in line or "[x]" in line]
                positions = [match.start() for match in re.finditer(r"\[[ x]\]", rows[0])]
                self.assertEqual(columns, len(positions))
                self.assertEqual(3, positions[0])
                self.assertTrue(all(len(row) == width - 1 for row in rows))
                distances = [right - left for left, right in zip(positions, positions[1:])]
                self.assertLessEqual(max(distances) - min(distances), 1)

    def test_grid_arrows_follow_rows_and_columns_with_an_incomplete_last_row(self):
        options = tuple("Opción {}".format(index) for index in range(7))
        cases = (
            (0, ["down"], 3), (0, ["down", "down"], 6),
            (0, ["down", "down", "down"], 0), (0, ["up"], 6),
            (1, ["down", "down"], 1), (2, ["up"], 5),
            (5, ["down"], 2), (6, ["right"], 0), (0, ["left"], 6),
        )
        for initial, keys, expected in cases:
            with self.subTest(initial=initial, keys=keys):
                selected, output = self.select(keys + ["enter"], options, initial, size=(100, 24))
                self.assertEqual(expected, selected)
                frame = output.split("\x1b[H\x1b[2J")[-1]
                self.assertIn("[x] " + options[expected], frame)
                self.assertEqual(1, frame.count("[x]"))

    def test_option_rows_and_text_blocks_have_breathing_room(self):
        options = ("Cifrar / descifrar", "Calcular hash", "Crear certificado", "Firmar documento",
                   "Verificar firma", "Demostrar alteración", "Salir")
        description = "Calcula y guarda SHA-256 o MD5. MD5 se incluye para la práctica académica."
        _, output = self.select(["enter"], options, initial=1, size=(110, 14),
                                descriptions=("", description))
        frame = output.split("\x1b[H\x1b[2J")[-1]
        plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", frame)
        lines = plain.splitlines()
        option_rows = [index for index, line in enumerate(lines) if "[ ]" in line or "[x]" in line]
        self.assertEqual([2, 2], [right - left for left, right in zip(option_rows, option_rows[1:])])
        description_row = next(index for index, line in enumerate(lines) if description in line)
        controls_row = next(index for index, line in enumerate(lines) if "Flechas:" in line)
        self.assertEqual("", lines[0])
        self.assertEqual("", lines[option_rows[0] - 1])
        self.assertEqual(2, description_row - option_rows[-1])
        self.assertEqual(2, controls_row - description_row)
        self.assertTrue(all(not line or line.startswith("  ") for line in lines))
        self.assertNotIn("Opciones 1-7", plain)
        self.assertLessEqual(len(lines), 14)

    def test_description_wraps_into_two_readable_lines(self):
        description = "Calcula SHA-256 o MD5 y guarda el resultado para la práctica académica."
        _, output = self.select(["enter"], options=("Calcular hash",), size=(50, 18),
                                descriptions=(description,))
        frame = output.split("\x1b[H\x1b[2J")[-1]
        plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", frame)
        lines = plain.splitlines()
        start = next(index for index, line in enumerate(lines) if "Calcula SHA-256" in line)
        self.assertEqual(description, " ".join(line.strip() for line in lines[start:start + 2]))
        self.assertEqual("", lines[start - 1])
        self.assertEqual("", lines[start + 2])

    def test_narrow_terminal_uses_one_full_width_column(self):
        options = ("Uno", "Dos", "Tres", "Cuatro", "Cinco", "Seis", "Siete")
        _, output = self.select(["enter"], options, size=(25, 24))
        frame = output.split("\x1b[H\x1b[2J")[-1]
        plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", frame)
        rows = [line for line in plain.splitlines() if "[ ]" in line or "[x]" in line]
        self.assertEqual(len(options), len(rows))
        self.assertTrue(all(len(row) == 24 and row.count("[") == 1 for row in rows))

    def test_resizing_reflows_options_and_preserves_the_active_selection(self):
        options = tuple("Opción {}".format(index) for index in range(7))
        sizes = [os.terminal_size(size) for size in ((80, 24), (25, 10), (120, 24))]
        with patch("cryptolab.terminal._key_reader", return_value=nullcontext(Mock(side_effect=["right", "down", "enter"]))), \
             patch("cryptolab.terminal.shutil.get_terminal_size", side_effect=sizes), \
             patch("sys.stdout", new=io.StringIO()) as output:
            selected = TerminalMenu().select("Prueba", options, initial=1)
        self.assertEqual(3, selected)
        frames = output.getvalue().split("\x1b[H\x1b[2J")[1:]
        for frame, expected, size in zip(frames, (1, 2, 3), sizes):
            self.assertIn("[x] " + options[expected], frame)
            self.assertEqual(1, frame.count("[x]"))
            plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", frame)
            self.assertTrue(all(len(line) <= size.columns - 1 for line in plain.splitlines()))
            self.assertLessEqual(len(plain.splitlines()), size.lines)

    def test_page_keys_move_and_can_return_to_start(self):
        options = tuple(str(index) for index in range(30))
        selected, _ = self.select(["page_down", "enter"], options, size=(60, 10))
        self.assertGreater(selected, 1)
        self.assertLess(selected, len(options) - 1)
        selected, _ = self.select(["page_down", "page_up", "enter"], options, size=(60, 10))
        self.assertEqual(0, selected)

    def test_narrow_terminal_clips_lines_and_sanitizes_labels(self):
        _, output = self.select(["enter"], options=("Opción muy larga\ncon salto",), size=(20, 6))
        frame = output.split("\x1b[H\x1b[2J")[-1]
        plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", frame)
        self.assertTrue(all(len(line) <= 19 for line in plain.splitlines()))
        self.assertLessEqual(len(plain.splitlines()), 6)

    def test_escape_cancels_and_restores_screen(self):
        selected, output = self.select(["cancel"])
        self.assertIsNone(selected)
        self.assertTrue(output.endswith("\x1b[0m\x1b[?25h\x1b[?1049l"))

    def test_interrupt_restores_cursor_screen_and_keyboard_session(self):
        restored = []

        @contextmanager
        def session():
            try:
                yield Mock(side_effect=KeyboardInterrupt)
            finally:
                restored.append(True)

        with patch("cryptolab.terminal._key_reader", side_effect=session), \
             patch("sys.stdout", new=io.StringIO()) as output:
            with self.assertRaises(KeyboardInterrupt):
                TerminalMenu().select("Prueba", ("Opción",))
        self.assertEqual([True], restored)
        self.assertTrue(output.getvalue().endswith("\x1b[0m\x1b[?25h\x1b[?1049l"))


class KeyboardTests(unittest.TestCase):
    def test_windows_extended_keys_and_selection_keys(self):
        for raw, expected in ((["\xe0", "P"], "down"), (["\x00", "H"], "up"),
                              (["\xe0", "M"], "right"), (["\xe0", "K"], "left"),
                              (["\xe0", "G"], "home"), (["\xe0", "O"], "end"),
                              (["\xe0", "I"], "page_up"), (["\xe0", "Q"], "page_down"),
                              (["x"], "enter"), (["X"], "enter"), ([" "], "enter"),
                              (["\r"], "enter"), (["\x1b"], "cancel")):
            with self.subTest(raw=raw):
                self.assertEqual(expected, _read_windows_key(Mock(side_effect=raw)))

    def test_posix_arrow_and_page_sequences(self):
        for sequence, expected in ((b"\x1b[A", "up"), (b"\x1b[B", "down"),
                                   (b"\x1b[C", "right"), (b"\x1b[D", "left"),
                                   (b"\x1b[5~", "page_up"), (b"\x1b[6~", "page_down")):
            with self.subTest(sequence=sequence), \
                 patch("cryptolab.terminal.os.read", side_effect=[bytes([byte]) for byte in sequence]), \
                 patch("select.select", return_value=([7], [], [])):
                self.assertEqual(expected, _read_posix_key(7))

    def test_escape_alone_does_not_wait_for_another_key(self):
        with patch("cryptolab.terminal.os.read", return_value=b"\x1b"), \
             patch("select.select", return_value=([], [], [])):
            self.assertEqual("cancel", _read_posix_key(7))

    def test_interrupt_and_eof_remain_session_exit_signals(self):
        with self.assertRaises(KeyboardInterrupt):
            _decode_key("\x03")
        for value in ("\x04", "\x1a", ""):
            with self.subTest(value=value), self.assertRaises(EOFError):
                _decode_key(value)


class InteractiveConsoleTests(unittest.TestCase):
    def test_full_hash_flow_with_arrows_restores_terminal_before_input(self):
        service = Mock()
        service.hash_text.return_value = HashResult(HashAlgorithm.MD5, "abc123", Path("hash.txt"))
        menu = ConsoleMenu(FormController(service), "OpenSSL de prueba")
        readers = iter([
            Mock(side_effect=["right", "enter"]),  # Calcular hash.
            Mock(side_effect=["enter"]),  # Texto, valor predeterminado.
            Mock(side_effect=["right", "enter"]),  # MD5.
            Mock(side_effect=["end", "enter"]),  # Salir.
        ])
        active = []

        @contextmanager
        def session():
            active.append(True)
            try:
                yield next(readers)
            finally:
                active.pop()

        answers = iter(["contenido", "hash.txt", ""])

        def entered(prompt):
            self.assertFalse(active, "La terminal debe restaurarse antes de leer texto.")
            return next(answers)

        with patch("cryptolab.terminal._key_reader", side_effect=session), \
             patch("builtins.input", side_effect=entered) as read, \
             patch("sys.stdout", new=io.StringIO()) as output:
            self.assertEqual(0, menu.run())
        self.assertIn("abc123", output.getvalue())
        self.assertIn("Pulsa Enter", read.call_args.args[0])
        service.hash_text.assert_called_once_with("contenido", Path("hash.txt"), HashAlgorithm.MD5)

    def test_escape_from_a_choice_returns_to_main_without_running_operation(self):
        controller = Mock()
        sessions = [nullcontext(Mock(side_effect=keys)) for keys in (
            ["right", "enter"], ["cancel"], ["cancel"],
        )]
        with patch("cryptolab.terminal._key_reader", side_effect=sessions), \
             patch("builtins.input") as entered, patch("sys.stdout", new=io.StringIO()) as output:
            self.assertEqual(0, ConsoleMenu(controller, "OpenSSL de prueba").run())
        controller.execute.assert_not_called()
        entered.assert_not_called()
        self.assertIn("Operación cancelada", output.getvalue())


if __name__ == "__main__":
    unittest.main()
