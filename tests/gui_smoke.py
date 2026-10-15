"""Prueba de escritorio opcional: python3 -m unittest tests.gui_smoke -v."""

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from cryptolab.app import build_service
from cryptolab.openssl import OpenSSLRunner
from cryptolab.forms import FormController
from cryptolab.forms import MODULES


class DesktopSmokeTest(unittest.TestCase):
    def test_navigation_background_hash_and_close_while_working(self):
        try:
            import tkinter
            from cryptolab.gui import CryptoLabWindow
        except ImportError:
            self.skipTest("Tkinter no está disponible.")
        executable = os.environ.get("CRYPTOLAB_TEST_OPENSSL") or shutil.which("openssl")
        if not executable:
            self.skipTest("OpenSSL no está disponible.")
        runner = OpenSSLRunner(executable, timeout=10)
        controller = FormController(build_service(runner))
        try:
            window = CryptoLabWindow(controller, runner.validate())
        except tkinter.TclError as error:
            self.skipTest("No hay escritorio gráfico: {}".format(error))
        try:
            window.update()
            window.withdraw()
            for module in MODULES:
                window._select_module(module)
                window.update_idletasks()
                self.assertEqual(module.name, window._module.name)
                if module.name == "certificate":
                    bounds = window._canvas.bbox("all")
                    self.assertGreater(bounds[3], window._canvas.winfo_height())

            module = next(item for item in MODULES if item.name == "hash")
            window._select_module(module)
            window._variables["message"].set("Texto conservado al redimensionar")
            window.deiconify()
            window.geometry("800x620")
            window.update()
            self.assertEqual(1, window._columns)
            self.assertEqual("Texto conservado al redimensionar", window._variables["message"].get())
            for control in window._inputs:
                self.assertLessEqual(control.winfo_rootx() + control.winfo_width(),
                                     window._fields.winfo_rootx() + window._fields.winfo_width() + 1)
            window.withdraw()
            with tempfile.TemporaryDirectory(prefix="CryptoLab GUI ") as directory:
                output = Path(directory) / "hash.txt"
                window._variables["message"].set("abc")
                window._variables["output"].set(str(output))
                window._start_operation()
                deadline = time.monotonic() + 10
                while window._busy and time.monotonic() < deadline:
                    window.update()
                    time.sleep(0.01)
                self.assertFalse(window._busy, "La ventana no recuperó el control.")
                self.assertEqual(
                    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                    output.read_text(encoding="ascii").strip(),
                )

                second = Path(directory) / "al cerrar.txt"
                window._variables["output"].set(str(second))
                window._start_operation()
                window._request_close()
                self.assertTrue(window._closing)
                while window._busy and time.monotonic() < deadline:
                    window.update()
                    time.sleep(0.01)
                self.assertTrue(second.exists(), "El cierre interrumpió la publicación.")
        finally:
            window._executor.shutdown(wait=True)
            try:
                window.destroy()
            except tkinter.TclError:
                pass
