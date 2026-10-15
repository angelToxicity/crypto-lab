import builtins
import getpass
import io
import unittest
import warnings
from pathlib import Path
from unittest.mock import Mock, patch

from cryptolab.app import main
from cryptolab.domain import ValidationError
from cryptolab.domain import HashAlgorithm, HashResult
from cryptolab.console import ConsoleMenu
from cryptolab.forms import FormController
from cryptolab.console import read_password


class PresentationTests(unittest.TestCase):
    def test_unknown_choice_is_not_silently_interpreted_as_another_action(self):
        service = Mock()
        controller = FormController(service)
        with self.assertRaises(ValidationError):
            controller.execute("hash", {"source_kind": "desconocido", "output": "hash.txt"})
        service.hash_text.assert_not_called()
        service.hash_file.assert_not_called()

    def test_hash_text_mode_does_not_use_a_stale_hidden_file_field(self):
        service = Mock()
        output = Path("hash.txt")
        service.hash_text.return_value = HashResult(HashAlgorithm.SHA256, "ab", output)
        controller = FormController(service)
        controller.execute("hash", {"source_kind": "Texto", "source": "viejo.txt", "message": "", "output": str(output)})
        service.hash_text.assert_called_once_with("", output, HashAlgorithm.SHA256)
        service.hash_file.assert_not_called()

    def test_missing_required_output_is_reported_before_running_a_use_case(self):
        service = Mock()
        with self.assertRaises(ValidationError):
            FormController(service).execute("hash", {"message": "abc"})
        service.hash_text.assert_not_called()

    def test_console_does_not_echo_password_when_getpass_cannot_hide_it(self):
        def unavailable(prompt):
            warnings.warn("no echo control", getpass.GetPassWarning)
            return "no debe leerse"
        with patch("cryptolab.console.getpass.getpass", side_effect=unavailable):
            with self.assertRaises(ValidationError):
                read_password("Contraseña: ")

    def test_eof_closes_console_cleanly(self):
        menu = ConsoleMenu(Mock(), "OpenSSL de prueba")
        with patch("builtins.input", side_effect=EOFError), patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(0, menu.run())

    def test_full_console_hash_flow_uses_shared_controller(self):
        service = Mock()
        service.hash_text.return_value = HashResult(HashAlgorithm.SHA256, "abc123", Path("hash.txt"))
        menu = ConsoleMenu(FormController(service), "OpenSSL de prueba")
        answers = ["2", "1", "contenido", "1", "hash.txt", "0"]
        with patch("builtins.input", side_effect=answers), patch("sys.stdout", new=io.StringIO()) as output:
            self.assertEqual(0, menu.run())
        self.assertIn("abc123", output.getvalue())
        service.hash_text.assert_called_once_with("contenido", Path("hash.txt"), HashAlgorithm.SHA256)

    def test_forced_gui_does_not_silently_switch_to_console(self):
        runner = Mock()
        runner.validate.return_value = "OpenSSL de prueba"
        with patch("cryptolab.app.OpenSSLRunner", return_value=runner), \
             patch("cryptolab.app._run_gui", return_value=None), \
             patch("sys.stderr", new=io.StringIO()) as errors:
            self.assertEqual(2, main(["--gui"]))
        self.assertIn("--cli", errors.getvalue())

    def test_cli_never_imports_tkinter(self):
        original_import = builtins.__import__

        def without_tkinter(name, *args, **kwargs):
            if name == "tkinter" or name.startswith("tkinter."):
                raise AssertionError("La consola no debe importar Tkinter.")
            return original_import(name, *args, **kwargs)

        runner = Mock()
        runner.validate.return_value = "OpenSSL de prueba"
        with patch("cryptolab.app.OpenSSLRunner", return_value=runner), \
             patch("builtins.__import__", side_effect=without_tkinter), \
             patch("builtins.input", return_value="0"), patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(0, main(["--cli"]))


if __name__ == "__main__":
    unittest.main()
