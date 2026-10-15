"""Reglas, errores y resultados sin entrada/salida ni dependencias externas."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple


class CryptoLabError(Exception):
    """Base de los errores esperados de la aplicación."""


class ValidationError(CryptoLabError):
    """Los datos no satisfacen las condiciones del caso de uso."""


class DependencyError(CryptoLabError):
    """Una dependencia de ejecución falta o no es compatible."""


class OperationError(CryptoLabError):
    """Una operación externa o de archivos no pudo completarse."""


class HashAlgorithm(Enum):
    SHA256 = "SHA-256"
    MD5 = "MD5"

    @property
    def openssl_name(self) -> str:
        return self.name.lower()

    @property
    def size(self) -> int:
        return 32 if self is self.SHA256 else 16


class RsaPadding(Enum):
    PKCS1 = "PKCS#1 v1.5 (práctica)"
    OAEP_SHA256 = "OAEP / SHA-256"

    def message_limit(self, bits: int) -> int:
        overhead = 11 if self is RsaPadding.PKCS1 else 66
        return (bits + 7) // 8 - overhead


def validate_password(password: str, required: bool = False) -> None:
    if required and not password:
        raise ValidationError("La clave privada nueva necesita una contraseña.")
    if any(character in password for character in ("\r", "\n", "\x00")):
        raise ValidationError("La contraseña no puede contener saltos de línea ni NUL.")


@dataclass(frozen=True)
class CertificateIdentity:
    common_name: str
    organization: str
    country: str
    state: str = ""
    locality: str = ""

    def __post_init__(self) -> None:
        limits = {"common_name": 64, "organization": 64, "state": 128, "locality": 128}
        for field, limit in limits.items():
            value = getattr(self, field).strip()
            if any(ord(character) < 32 for character in value):
                raise ValidationError("Los datos de identidad contienen caracteres de control.")
            if len(value) > limit:
                raise ValidationError("{} supera {} caracteres.".format(field, limit))
            object.__setattr__(self, field, value)
        if not self.common_name or not self.organization:
            raise ValidationError("El nombre y la organización son obligatorios.")
        country = self.country.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", country):
            raise ValidationError("Indica el país mediante dos letras, por ejemplo VE o ES.")
        object.__setattr__(self, "country", country)

@dataclass(frozen=True)
class CertificateFiles:
    private_key: Path
    request: Path
    certificate: Path
    public_key: Path

    def paths(self) -> Tuple[Path, ...]:
        return (self.private_key, self.request, self.certificate, self.public_key)


@dataclass(frozen=True)
class CertificateNames:
    private_key: str = "private_key.pem"
    request: str = "csr.pem"
    certificate: str = "certificate.pem"
    public_key: str = "public_key.pem"

    def in_directory(self, directory: Path) -> CertificateFiles:
        names = (self.private_key, self.request, self.certificate, self.public_key)
        for name in names:
            if (not name or name in (".", "..") or "/" in name or "\\" in name
                    or any(ord(char) < 32 for char in name)):
                raise ValidationError("Cada nombre de salida debe ser un nombre de archivo simple.")
            if name != name.strip():
                raise ValidationError("Los nombres de salida no pueden empezar o terminar con espacios.")
        if len({name.casefold() for name in names}) != len(names):
            raise ValidationError("Los cuatro archivos del certificado necesitan nombres distintos.")
        return CertificateFiles(*(Path(directory) / name for name in names))


@dataclass(frozen=True)
class CertificateDetails:
    subject: str
    valid_from: datetime
    valid_until: datetime

    def is_current(self, now: datetime) -> bool:
        return self.valid_from <= now <= self.valid_until


@dataclass(frozen=True)
class VerificationResult:
    signature_valid: bool
    certificate: CertificateDetails
    certificate_current: bool


@dataclass(frozen=True)
class HashResult:
    algorithm: HashAlgorithm
    hexadecimal: str
    output: Path


@dataclass(frozen=True)
class DecryptionResult:
    output: Path
    message: Optional[str]


@dataclass(frozen=True)
class TamperingResult:
    output: Path
    original: VerificationResult
    altered: VerificationResult
