"""Menú de consola y entrada oculta de contraseñas, sin importar Tkinter."""

import getpass
import warnings

from .domain import CryptoLabError, ValidationError
from .forms import MODULES, Field, FormController


def read_password(prompt: str) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except getpass.GetPassWarning as error:
        raise ValidationError(
            "La terminal no permite ocultar contraseñas. Usa una terminal interactiva o la interfaz gráfica."
        ) from error


class ConsoleMenu:
    def __init__(self, controller: FormController, version: str):
        self._controller = controller
        self._version = version

    def run(self) -> int:
        try:
            while True:
                print("\nCryptoLab | {}".format(self._version))
                for index, module in enumerate(MODULES, 1):
                    print("{}. {}".format(index, module.title))
                print("0. Salir")
                selection = input("Opción: ").strip()
                if selection == "0":
                    return 0
                if not selection.isdigit() or not 1 <= int(selection) <= len(MODULES):
                    print("Selecciona un número del menú.")
                    continue
                self._run_module(MODULES[int(selection) - 1])
        except (EOFError, KeyboardInterrupt):
            print("\nSesión finalizada.")
            return 0

    def _run_module(self, module) -> None:
        print("\n{}\n{}".format(module.title, module.description))
        values = {field.name: field.default for field in module.fields}
        try:
            for field in module.fields:
                if field.visible(values):
                    values[field.name] = self._read_field(field)
            result = self._controller.execute(module.name, values)
            print("\n" + result.message)
        except CryptoLabError as error:
            print("\nError: {}".format(error))
        finally:
            # Reduce la duración de las referencias; Python no garantiza borrado físico.
            for field in module.fields:
                if field.kind == "password":
                    values[field.name] = ""

    def _read_field(self, field: Field) -> str:
        if field.kind == "choice":
            return self._choose(field)
        while True:
            suffix = " [{}]".format(field.default) if field.default else ""
            suffix += " (opcional)" if not field.required else ""
            prompt = field.label + suffix + ": "
            value = read_password(prompt) if field.kind == "password" else input(prompt)
            value = value if value else field.default
            try:
                field.validate(value)
                return value
            except ValidationError as error:
                print(error)

    @staticmethod
    def _choose(field: Field) -> str:
        for index, choice in enumerate(field.choices, 1):
            print("  {}. {}".format(index, choice))
        while True:
            value = input("{} [{}]: ".format(field.label, field.default)).strip()
            if not value:
                return field.default
            if value.isdigit() and 1 <= int(value) <= len(field.choices):
                return field.choices[int(value) - 1]
            if value in field.choices:
                return value
            print("Elige una de las opciones indicadas.")
