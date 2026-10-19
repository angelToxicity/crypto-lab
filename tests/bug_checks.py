"""Regresiones pendientes: ejecutar python3 -m unittest tests.bug_checks -v.

Las aserciones expresan el comportamiento esperado; fallan mientras persistan
los defectos. Este módulo requiere ejecución explícita y no abre ventanas.
"""

import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cryptolab.app import build_service
from cryptolab.console import ConsoleMenu
from cryptolab.domain import CertificateIdentity, CertificateNames, OperationError, RsaPadding, ValidationError
from cryptolab.forms import FormController, MODULES
from cryptolab.openssl import OpenSSLRunner
from cryptolab.terminal import TerminalUnavailable


class DecryptionChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable = os.environ.get("CRYPTOLAB_TEST_OPENSSL") or shutil.which("openssl")
        if not executable:
            raise unittest.SkipTest("No hay OpenSSL: define CRYPTOLAB_TEST_OPENSSL o añádelo a PATH.")
        cls.runner = OpenSSLRunner(executable)
        cls.version = cls.runner.validate()
        cls.service = build_service(cls.runner)
        cls.controller = FormController(cls.service)
        cls.scratch = tempfile.TemporaryDirectory(prefix="cryptolab-bug-checks-")
        cls.addClassCleanup(cls.scratch.cleanup)
        cls.directory = Path(cls.scratch.name)
        cls.password = "Clave ficticia para pruebas"
        cls.identity = cls.service.create_certificate(
            CertificateIdentity("Auditoria", "Pruebas temporales", "VE"),
            cls.password, cls.directory, CertificateNames(),
        )
        cls.original = "Mensaje conocido para comparar el resultado."
        cls.cipher = cls.service.encrypt_text(
            cls.original, cls.identity.public_key, cls.directory / "valido.bin", RsaPadding.PKCS1,
        )
        recovered = cls.service.decrypt_file(
            cls.cipher, cls.identity.private_key, cls.directory / "control.txt", cls.password, RsaPadding.PKCS1,
        )
        if recovered.message != cls.original:
            raise RuntimeError("Falló el control positivo de cifrado/descifrado.")

    def assert_not_reported_as_success(self, source, output):
        try:
            result = self.controller.execute("rsa", {
                "action": "Descifrar archivo", "padding": RsaPadding.PKCS1.value,
                "source": str(source), "key": str(self.identity.private_key),
                "password": self.password, "output": str(output),
            })
        except OperationError as error:
            self.assertNotIn("superó el límite", str(error), "Un timeout no confirma esta validación.")
            self.assertFalse(output.exists(), "Una operación rechazada no debe publicar una salida.")
            return
        self.assertFalse(
            result.success,
            "Se informó success=True para una entrada deliberadamente inválida. "
            "OpenSSL: {}. Salida creada: {}. Bytes: {}.".format(
                self.version, output.exists(), output.stat().st_size if output.exists() else 0,
            ),
        )

    def test_invalid_ciphertext_is_not_reported_as_success(self):
        source = self.directory / "ceros.bin"
        source.write_bytes(bytes(self.cipher.stat().st_size))
        self.assert_not_reported_as_success(source, self.directory / "ceros-descifrados.txt")

    def test_wrong_padding_profile_is_not_reported_as_success(self):
        source = self.service.encrypt_text(
            self.original, self.identity.public_key, self.directory / "oaep.bin", RsaPadding.OAEP_SHA256,
        )
        control = self.service.decrypt_file(
            source, self.identity.private_key, self.directory / "oaep-control.txt",
            self.password, RsaPadding.OAEP_SHA256,
        )
        self.assertEqual(self.original, control.message)
        self.assert_not_reported_as_success(source, self.directory / "oaep-como-pkcs1.txt")


class CertificatePathChecks(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Este caso comprueba las rutas con unidad de Windows.")
    def test_drive_relative_certificate_name_is_rejected(self):
        with self.assertRaises(ValidationError, msg="C:fuera.pem permite salir de D:/elegida."):
            CertificateNames(private_key="C:fuera.pem").in_directory(Path("D:/elegida"))


class ConsoleInputChecks(unittest.TestCase):
    def test_main_menu_recovers_after_a_decorative_number(self):
        menu = ConsoleMenu(Mock(), "OpenSSL de prueba")
        with patch.object(menu._selector, "select", side_effect=TerminalUnavailable), \
             patch("builtins.input", side_effect=["\u2460", "0"]), \
             patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(0, menu.run())

    def test_form_choice_recovers_after_a_superscript_number(self):
        menu = ConsoleMenu(Mock(), "OpenSSL de prueba")
        field = next(module for module in MODULES if module.name == "hash").fields[0]
        with patch.object(menu._selector, "select", side_effect=TerminalUnavailable), \
             patch("builtins.input", side_effect=["\u00b2", "2"]), \
             patch("sys.stdout", new=io.StringIO()):
            self.assertEqual("Archivo", menu._choose(field))


class BusyResizeChecks(unittest.TestCase):
    def test_resizing_keeps_inputs_disabled_while_a_job_is_running(self):
        try:
            from cryptolab.gui import CryptoLabWindow
        except ImportError:
            self.skipTest("Se necesita Tkinter importable; no se necesita una sesión gráfica.")

        # Controles sin escritorio: sus estados iniciales coinciden con ttk.
        def control(*args, **options):
            widget = Mock()
            widget.settings = dict(options)
            widget.settings.setdefault("state", "normal")
            widget.configure.side_effect = lambda **changes: widget.settings.update(changes)
            return widget

        module = next(item for item in MODULES if item.name == "hash")
        previous_input = control(state="disabled")
        window = SimpleNamespace(
            _busy=True, _columns=2, _canvas=Mock(), _canvas_item=1,
            _description=Mock(), _help_label=Mock(), _fields=Mock(),
            _module=module, _profile=Mock(), _inputs=[previous_input],
            _run_button=control(state="disabled", text="Procesando…"),
            _label=Mock(return_value=Mock()),
        )
        window._fields.winfo_children.return_value = [previous_input]
        window._variables = {
            field.name: Mock(get=Mock(return_value=field.default)) for field in module.fields
        }
        window._action_text = lambda: module.title
        window._render_fields = lambda: CryptoLabWindow._render_fields(window)

        with patch("cryptolab.gui.ttk.Frame", side_effect=control), \
             patch("cryptolab.gui.ttk.Entry", side_effect=control), \
             patch("cryptolab.gui.ttk.Combobox", side_effect=control), \
             patch("cryptolab.gui.ttk.Button", side_effect=control):
            CryptoLabWindow._resize_canvas(window, SimpleNamespace(width=600))

        self.assertTrue(window._busy)
        self.assertEqual(1, window._columns)
        self.assertTrue(window._inputs, "La prueba debe comprobar controles reconstruidos.")
        states = [widget.settings["state"] for widget in window._inputs]
        self.assertTrue(all(state == "disabled" for state in states),
                        "La operación sigue activa pero los controles tienen estados: {}.".format(states))


if __name__ == "__main__":
    unittest.main()
