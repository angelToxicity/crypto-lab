"""Archivos temporales y publicación exclusiva, sin exigir enlaces duros."""

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Sequence, Tuple

from .domain import OperationError, ValidationError


class LocalFileStore:
    @staticmethod
    def resolve(path: Path) -> Path:
        try:
            absolute = Path(path).expanduser().absolute()
            return absolute.parent.resolve() / absolute.name
        except (OSError, ValueError, RuntimeError) as error:
            raise ValidationError("La ruta no se puede resolver: {}.".format(path)) from error

    def input_file(self, path: Path, description: str) -> Path:
        path = self.resolve(path)
        if not path.is_file():
            raise ValidationError("{} no existe o no es un archivo regular: {}.".format(description, path))
        return path.resolve()

    @staticmethod
    def size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError as error:
            raise OperationError("No se pudo consultar el tamaño de {}.".format(path)) from error

    @contextmanager
    def temporary_directory(self) -> Iterator[Path]:
        try:
            with tempfile.TemporaryDirectory(prefix="cryptolab-") as directory:
                yield Path(directory)
        except OSError as error:
            raise OperationError("No se pudo completar la operación de archivos: {}.".format(error)) from error

    @contextmanager
    def outputs(self, destinations: Sequence[Path], inputs: Sequence[Path] = ()) -> Iterator[Tuple[Path, ...]]:
        targets = tuple(self.resolve(path) for path in destinations)
        keys = [os.path.normcase(str(path)) for path in targets]
        reserved = {os.path.normcase(str(self.resolve(path))) for path in inputs}
        if len(set(keys)) != len(keys) or reserved.intersection(keys):
            raise ValidationError("Las salidas deben ser distintas entre sí y de las entradas.")
        for target in targets:
            if not target.parent.is_dir():
                raise ValidationError("La carpeta de salida no existe: {}.".format(target.parent))
            if os.path.lexists(str(target)):
                raise ValidationError("La salida ya existe; elige otro nombre: {}.".format(target))

        created = []
        try:
            with self.temporary_directory() as directory:
                staged = tuple(directory / "output-{}".format(index) for index in range(len(targets)))
                yield staged
                # O_EXCL impide reemplazar un archivo incluso si aparece después de validar.
                for source, target in zip(staged, targets):
                    with source.open("rb") as content:
                        descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        created.append(target)
                        with os.fdopen(descriptor, "wb") as output:
                            shutil.copyfileobj(content, output)
        except BaseException as error:
            # Solo retiramos las salidas creadas por esta transacción.
            cleanup_errors = []
            for target in reversed(created):
                try:
                    target.unlink()
                except OSError as cleanup_error:
                    cleanup_errors.append(str(cleanup_error))
            if cleanup_errors:
                raise OperationError(
                    "Falló la operación y no se pudieron retirar todas sus salidas: {}."
                    .format("; ".join(cleanup_errors))
                ) from error
            if isinstance(error, OSError):
                raise OperationError("No se pudieron guardar las salidas: {}.".format(error)) from error
            raise

    @staticmethod
    def write_bytes(path: Path, content: bytes) -> None:
        try:
            path.write_bytes(content)
        except OSError as error:
            raise OperationError("No se pudo escribir el archivo temporal: {}.".format(error)) from error

    @staticmethod
    def read_message(path: Path) -> Optional[str]:
        try:
            with path.open("rb") as content:
                raw = content.read(8193)
            return raw.decode("utf-8") if len(raw) <= 8192 else None
        except UnicodeDecodeError:
            return None
        except OSError as error:
            raise OperationError("No se pudo leer el mensaje descifrado: {}.".format(error)) from error

    def alter(self, source: Path, output: Path, old_text: Optional[str], new_text: Optional[str]) -> None:
        with source.open("rb") as original, output.open("wb") as altered:
            if old_text is None:
                shutil.copyfileobj(original, altered)
                altered.write(b"\n")
                return
            old = old_text.encode("utf-8")
            new = (new_text or "").encode("utf-8")
            pending = b""
            while True:
                chunk = original.read(65536)
                pending += chunk
                position = pending.find(old)
                if position >= 0:
                    altered.write(pending[:position] + new + pending[position + len(old):])
                    shutil.copyfileobj(original, altered)
                    return
                if not chunk:
                    raise ValidationError("El texto a reemplazar no aparece en el documento.")
                keep = len(old) - 1
                if len(pending) > keep:
                    boundary = len(pending) - keep
                    altered.write(pending[:boundary])
                    pending = pending[boundary:]
