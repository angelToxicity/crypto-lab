"""Punto de composición: conecta puertos, adaptadores e interfaces."""

import argparse
import importlib
import platform
import sys
from datetime import datetime, timezone
from typing import Optional, Sequence

from .service import CryptoLabService
from .domain import CryptoLabError, DependencyError
from .files import LocalFileStore
from .openssl import OpenSSLEngine, OpenSSLRunner
from .console import ConsoleMenu
from .forms import FormController


def build_service(runner: OpenSSLRunner) -> CryptoLabService:
    return CryptoLabService(OpenSSLEngine(runner), LocalFileStore(), lambda: datetime.now(timezone.utc))


def _positive_integer(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Debe ser un entero mayor que cero.")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CryptoLab: interfaz de los comandos OpenSSL para la práctica.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--cli", action="store_true", help="Usar consola sin importar Tkinter.")
    modes.add_argument("--gui", action="store_true", help="Exigir interfaz gráfica; informar si no está disponible.")
    parser.add_argument("--check", action="store_true", help="Diagnosticar requisitos y salir sin crear claves ni salidas.")
    parser.add_argument("--openssl", metavar="EJECUTABLE", help="Ruta o nombre explícito del ejecutable OpenSSL.")
    parser.add_argument("--timeout", type=_positive_integer, default=120, metavar="SEGUNDOS",
                        help="Límite por comando OpenSSL (predeterminado: 120).")
    return parser


def _check_environment(executable: Optional[str], timeout: int) -> int:
    print("Python: {}".format(platform.python_version()))
    print("Sistema: {} {} (la evaluación solicita Linux).".format(platform.system(), platform.release()))
    status = 0
    try:
        runner = OpenSSLRunner(executable, timeout)
        print("OpenSSL: {}\nEjecutable: {}".format(runner.validate(), runner.executable))
        print("Comandos requeridos: disponibles.")
        print("Hashes SHA-256 y MD5: disponibles.")
    except CryptoLabError as error:
        print("OpenSSL: {}".format(error))
        status = 2
    try:
        importlib.import_module("tkinter")
        print("Tkinter: importable; la disponibilidad del escritorio se comprueba al abrir la ventana.")
    except ImportError:
        print("Tkinter: no disponible. La interfaz de consola no lo necesita.")
    return status


def _run_gui(controller: FormController, version: str) -> Optional[int]:
    try:
        tkinter = importlib.import_module("tkinter")
    except ImportError:
        return None
    from .gui import CryptoLabWindow

    try:
        window = CryptoLabWindow(controller, version)
    except tkinter.TclError:
        return None
    window.mainloop()
    return 0


def main(arguments: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = _parser().parse_args(arguments)
    if args.check:
        return _check_environment(args.openssl, args.timeout)
    try:
        runner = OpenSSLRunner(args.openssl, args.timeout)
        version = runner.validate()
        controller = FormController(build_service(runner))
        if not args.cli:
            result = _run_gui(controller, version)
            if result is not None:
                return result
            if args.gui:
                raise DependencyError("No se puede abrir la ventana: se necesita Tkinter y una sesión gráfica. Usa --cli para consola.")
            print("No está disponible la ventana gráfica; se iniciará el menú de consola.")
        return ConsoleMenu(controller, version).run()
    except (CryptoLabError, OSError) as error:
        print("Error: {}".format(error), file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("\nSesión finalizada.")
        return 0
