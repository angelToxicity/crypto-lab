"""Casos de uso y contratos de sus dependencias; solo conocen el dominio."""

from datetime import datetime
from pathlib import Path
from typing import Callable, ContextManager, Optional, Protocol, Sequence, Tuple

from .domain import (
    CertificateDetails, CertificateFiles, CertificateIdentity, CertificateNames,
    DecryptionResult, HashAlgorithm, HashResult, OperationError, RsaPadding,
    TamperingResult, ValidationError, VerificationResult, validate_password,
)


class CryptoEngine(Protocol):
    def digest_file(self, source: Path, algorithm: HashAlgorithm) -> bytes: ...
    def digest_text(self, message: str, algorithm: HashAlgorithm) -> bytes: ...
    def rsa_bits(self, public_key: Path) -> int: ...
    def encrypt(self, source: Path, public_key: Path, output: Path, padding: RsaPadding) -> None: ...
    def decrypt(self, source: Path, private_key: Path, output: Path, password: str, padding: RsaPadding) -> None: ...
    def create_certificate(self, identity: CertificateIdentity, password: str, outputs: CertificateFiles) -> None: ...
    def sign(self, source: Path, private_key: Path, output: Path, password: str) -> None: ...
    def verify(self, document: Path, signature: Path, certificate: Path) -> bool: ...
    def certificate_details(self, certificate: Path) -> CertificateDetails: ...


class FileStore(Protocol):
    def input_file(self, path: Path, description: str) -> Path: ...
    def resolve(self, path: Path) -> Path: ...
    def size(self, path: Path) -> int: ...
    def outputs(self, destinations: Sequence[Path], inputs: Sequence[Path] = ()) -> ContextManager[Tuple[Path, ...]]: ...
    def temporary_directory(self) -> ContextManager[Path]: ...
    def write_bytes(self, path: Path, content: bytes) -> None: ...
    def read_message(self, path: Path) -> Optional[str]: ...
    def alter(self, source: Path, output: Path, old_text: Optional[str], new_text: Optional[str]) -> None: ...


class CryptoLabService:
    def __init__(self, engine: CryptoEngine, files: FileStore, clock: Callable[[], datetime]):
        self._engine = engine
        self._files = files
        self._clock = clock

    def hash_file(self, source: Path, output: Path, algorithm: HashAlgorithm) -> HashResult:
        source = self._files.input_file(source, "El archivo de entrada")
        digest = self._engine.digest_file(source, algorithm)
        return self._save_digest(digest, output, algorithm, source)

    def hash_text(self, message: str, output: Path, algorithm: HashAlgorithm) -> HashResult:
        digest = self._engine.digest_text(message, algorithm)
        return self._save_digest(digest, output, algorithm)

    def _save_digest(self, digest: bytes, output: Path, algorithm: HashAlgorithm, *inputs: Path) -> HashResult:
        if len(digest) != algorithm.size:
            raise OperationError("OpenSSL devolvió una longitud de hash inesperada.")
        output = self._files.resolve(output)
        with self._files.outputs((output,), inputs) as staged:
            self._files.write_bytes(staged[0], (digest.hex() + "\n").encode("ascii"))
        return HashResult(algorithm, digest.hex(), output)

    def encrypt_file(self, source: Path, key: Path, output: Path, padding: RsaPadding) -> Path:
        source = self._files.input_file(source, "El mensaje")
        key = self._files.input_file(key, "La clave pública")
        limit = padding.message_limit(self._engine.rsa_bits(key))
        size = self._files.size(source)
        if size > limit:
            raise ValidationError(
                "El mensaje ocupa {} bytes; el perfil {} admite {} con esta clave."
                .format(size, padding.value, limit)
            )
        output = self._files.resolve(output)
        with self._files.outputs((output,), (source, key)) as staged:
            self._engine.encrypt(source, key, staged[0], padding)
        return output

    def encrypt_text(self, message: str, key: Path, output: Path, padding: RsaPadding) -> Path:
        with self._files.temporary_directory() as directory:
            source = directory / "message.txt"
            self._files.write_bytes(source, message.encode("utf-8"))
            return self.encrypt_file(source, key, output, padding)

    def decrypt_file(self, source: Path, key: Path, output: Path, password: str, padding: RsaPadding) -> DecryptionResult:
        validate_password(password)
        source = self._files.input_file(source, "El archivo cifrado")
        key = self._files.input_file(key, "La clave privada")
        output = self._files.resolve(output)
        with self._files.outputs((output,), (source, key)) as staged:
            self._engine.decrypt(source, key, staged[0], password, padding)
        return DecryptionResult(output, self._files.read_message(output))

    def create_certificate(self, identity: CertificateIdentity, password: str, directory: Path, names: CertificateNames) -> CertificateFiles:
        validate_password(password, required=True)
        bundle = names.in_directory(self._files.resolve(directory))
        with self._files.outputs(bundle.paths()) as staged:
            self._engine.create_certificate(identity, password, CertificateFiles(*staged))
        return bundle

    def sign_file(self, source: Path, key: Path, output: Path, password: str) -> Path:
        validate_password(password)
        source = self._files.input_file(source, "El documento")
        key = self._files.input_file(key, "La clave privada")
        output = self._files.resolve(output)
        with self._files.outputs((output,), (source, key)) as staged:
            self._engine.sign(source, key, staged[0], password)
        return output

    def verify_file(self, source: Path, signature: Path, certificate: Path) -> VerificationResult:
        source = self._files.input_file(source, "El documento")
        signature = self._files.input_file(signature, "La firma")
        certificate = self._files.input_file(certificate, "El certificado")
        valid = self._engine.verify(source, signature, certificate)
        details = self._engine.certificate_details(certificate)
        return VerificationResult(valid, details, details.is_current(self._clock()))

    def demonstrate_tampering(self, source: Path, signature: Path, certificate: Path, output: Path,
                              old_text: Optional[str] = None, new_text: Optional[str] = None) -> TamperingResult:
        if old_text is not None and (not old_text or old_text == (new_text or "")):
            raise ValidationError("El reemplazo debe cambiar un texto no vacío.")
        original = self.verify_file(source, signature, certificate)
        if not original.signature_valid:
            raise ValidationError("La firma original no es válida. Corrige los archivos antes de demostrar la alteración.")
        source = self._files.input_file(source, "El documento")
        signature = self._files.input_file(signature, "La firma")
        certificate = self._files.input_file(certificate, "El certificado")
        output = self._files.resolve(output)
        with self._files.outputs((output,), (source, signature, certificate)) as staged:
            self._files.alter(source, staged[0], old_text, new_text)
            altered = self.verify_file(staged[0], signature, certificate)
            if altered.signature_valid:
                raise OperationError("La alteración no produjo el cambio de firma esperado.")
        return TamperingResult(output, original, altered)
