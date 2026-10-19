"""Prueba explícita de regresión Tk: python3 -m unittest tests.gui_busy_resize -v.

Ejecutar bajo Xvfb cuando no haya un escritorio disponible. La prueba usa un
controlador lento simulado y no llama a OpenSSL ni crea archivos de salida.
"""

import time
import unittest

from cryptolab.forms import MODULES, PresentationResult


class SlowController:
    def execute(self, module_name, values):
        time.sleep(2)
        return PresentationResult(True, "Operación de prueba terminada.")


class BusyResizeSmokeTest(unittest.TestCase):
    def test_real_tk_controls_stay_disabled_when_narrowing_while_busy(self):
        try:
            import tkinter
            from cryptolab.gui import CryptoLabWindow
        except ImportError:
            self.skipTest("Se necesita Tkinter dentro de la imagen.")

        try:
            window = CryptoLabWindow(SlowController(), "Prueba Tkinter en Ubuntu")
        except tkinter.TclError as error:
            self.skipTest("Se necesita una pantalla X11 o Xvfb: {}".format(error))

        try:
            window.geometry("1000x650")
            window._select_module(next(module for module in MODULES if module.name == "hash"))
            window.update()
            self.assertEqual(2, window._columns, "El control inicial debe mostrar dos columnas.")

            window._start_operation()
            self.assertTrue(window._busy)
            window.geometry("760x540")
            window.update()

            self.assertEqual(1, window._columns, "El ancho reducido debe activar una columna.")
            states = [str(control.cget("state")) for control in window._inputs]
            self.assertTrue(states, "La prueba debe inspeccionar los controles Tk reconstruidos.")
            self.assertTrue(
                all(state == "disabled" for state in states),
                "La operación sigue activa, pero Tk devolvió estos estados: {}.".format(states),
            )
        finally:
            deadline = time.monotonic() + 8
            while window._busy and time.monotonic() < deadline:
                try:
                    window.update()
                except tkinter.TclError:
                    break
                time.sleep(0.01)
            window._executor.shutdown(wait=True)
            try:
                window.destroy()
            except tkinter.TclError:
                pass


if __name__ == "__main__":
    unittest.main()
