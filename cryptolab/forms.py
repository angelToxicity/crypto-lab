"""Formularios y controlador compartidos por consola y escritorio."""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Tuple

from .domain import (
    CertificateIdentity, CertificateNames, HashAlgorithm, RsaPadding,
    ValidationError, VerificationResult,
)
from .service import CryptoLabService


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"
    default: str = ""
    choices: Tuple[str, ...] = ()
    required: bool = True
    condition: Optional[Tuple[str, Tuple[str, ...]]] = None
    suggestion: str = ""

    def visible(self, values: Mapping[str, str]) -> bool:
        return self.condition is None or values.get(self.condition[0]) in self.condition[1]

    def validate(self, value: str) -> None:
        meaningful = value if self.kind in ("password", "literal") else value.strip()
        if self.required and not meaningful:
            raise ValidationError("Completa el campo: {}.".format(self.label))
        if self.kind == "choice" and value not in self.choices:
            raise ValidationError("Selecciona una opción válida para {}.".format(self.label))


@dataclass(frozen=True)
class Module:
    name: str
    title: str
    description: str
    fields: Tuple[Field, ...]


RSA_ACTIONS = ("Cifrar texto", "Cifrar archivo", "Descifrar archivo")
SOURCE_CHOICES = ("Texto", "Archivo")
ALTERATIONS = ("Añadir salto de línea", "Reemplazar texto")

MODULES = (
    Module("rsa", "Cifrar / descifrar",
           "RSA para mensajes breves. Usa el mismo perfil de relleno al cifrar y descifrar.", (
        Field("action", "Acción", "choice", RSA_ACTIONS[0], RSA_ACTIONS),
        Field("padding", "Perfil RSA", "choice", RsaPadding.PKCS1.value, tuple(item.value for item in RsaPadding)),
        Field("message", "Mensaje", required=False, condition=("action", ("Cifrar texto",))),
        Field("source", "Archivo de entrada", "file", condition=("action", ("Cifrar archivo", "Descifrar archivo"))),
        Field("key", "Clave PEM (pública al cifrar, privada al descifrar)", "file"),
        Field("password", "Contraseña de clave privada", "password", required=False,
              condition=("action", ("Descifrar archivo",))),
        Field("output", "Guardar resultado como", "save", suggestion="resultado.bin"),
    )),
    Module("hash", "Calcular hash",
           "Calcula y guarda SHA-256 o MD5. MD5 se incluye para la práctica académica.", (
        Field("source_kind", "Tipo de entrada", "choice", SOURCE_CHOICES[0], SOURCE_CHOICES),
        Field("message", "Texto a resumir", required=False, condition=("source_kind", ("Texto",))),
        Field("source", "Archivo de entrada", "file", condition=("source_kind", ("Archivo",))),
        Field("algorithm", "Algoritmo", "choice", HashAlgorithm.SHA256.value, tuple(item.value for item in HashAlgorithm)),
        Field("output", "Guardar hash como", "save", suggestion="hash.sha256"),
    )),
    Module("certificate", "Crear certificado",
           "Genera clave privada cifrada, CSR, certificado X.509 v3 y clave pública. Elige una carpeta existente y los nombres.", (
        Field("common_name", "Nombre del titular"),
        Field("organization", "Organización"),
        Field("country", "País (dos letras)"),
        Field("state", "Estado o provincia", required=False),
        Field("locality", "Localidad", required=False),
        Field("directory", "Carpeta de salida", "folder"),
        Field("private_name", "Nombre de clave privada", default="private_key.pem"),
        Field("request_name", "Nombre de solicitud CSR", default="csr.pem"),
        Field("certificate_name", "Nombre de certificado", default="certificate.pem"),
        Field("public_name", "Nombre de clave pública", default="public_key.pem"),
        Field("password", "Contraseña para la clave privada", "password"),
        Field("confirmation", "Confirmar contraseña", "password"),
    )),
    Module("sign", "Firmar documento",
           "Calcula el hash SHA-256 binario y lo firma con RSA. El documento permanece intacto.", (
        Field("source", "Documento", "file"),
        Field("key", "Clave privada PEM", "file"),
        Field("password", "Contraseña de clave privada", "password", required=False),
        Field("output", "Guardar firma como", "save", suggestion="firma.bin"),
    )),
    Module("verify", "Verificar firma",
           "Comprueba la firma y muestra la vigencia del certificado. La identidad requiere una comprobación externa.", (
        Field("source", "Documento", "file"),
        Field("signature", "Firma digital", "file"),
        Field("certificate", "Certificado del firmante", "file"),
    )),
    Module("tamper", "Demostrar alteración",
           "Primero verifica el original; después crea una copia modificada y verifica que la firma falle.", (
        Field("source", "Documento original", "file"),
        Field("signature", "Firma original", "file"),
        Field("certificate", "Certificado del firmante", "file"),
        Field("alteration", "Tipo de cambio", "choice", ALTERATIONS[0], ALTERATIONS),
        Field("old_text", "Texto a reemplazar", "literal", condition=("alteration", ("Reemplazar texto",))),
        Field("new_text", "Texto nuevo", "literal", required=False, condition=("alteration", ("Reemplazar texto",))),
        Field("output", "Guardar copia alterada como", "save", suggestion="documento_alterado.txt"),
    )),
)


@dataclass(frozen=True)
class PresentationResult:
    success: bool
    message: str


def describe_verification(result: VerificationResult) -> str:
    certificate = result.certificate
    return "\n".join((
        "FIRMA VÁLIDA" if result.signature_valid else "FIRMA NO VÁLIDA",
        "Sujeto: " + certificate.subject,
        "Vigencia: {} a {}.".format(certificate.valid_from.isoformat(), certificate.valid_until.isoformat()),
        "Certificado vigente." if result.certificate_current else "Certificado fuera de su período de vigencia.",
        "El certificado autofirmado no acredita por sí solo la identidad del titular.",
    ))


class FormController:
    def __init__(self, service: CryptoLabService):
        self._service = service
        self._handlers = {
            "rsa": self._rsa, "hash": self._hash, "certificate": self._certificate,
            "sign": self._sign, "verify": self._verify, "tamper": self._tamper,
        }

    def execute(self, module_name: str, entered: Mapping[str, str]) -> PresentationResult:
        module = next((module for module in MODULES if module.name == module_name), None)
        if module is None:
            raise ValidationError("Operación desconocida.")
        values = {field.name: field.default for field in module.fields}
        values.update(entered)
        for field in module.fields:
            if not field.visible(values):
                continue
            field.validate(values[field.name])
        return self._handlers[module_name](values)

    def _rsa(self, values) -> PresentationResult:
        padding = RsaPadding(values["padding"])
        key, output = Path(values["key"].strip()), Path(values["output"].strip())
        action = values["action"]
        if action == "Cifrar texto":
            result = self._service.encrypt_text(values["message"], key, output, padding)
        elif action == "Cifrar archivo":
            result = self._service.encrypt_file(Path(values["source"].strip()), key, output, padding)
        else:
            result = self._service.decrypt_file(
                Path(values["source"].strip()), key, output, values["password"], padding,
            )
            text = result.message if result.message is not None else "(Resultado binario o no mostrable como UTF-8.)"
            return PresentationResult(True, "Descifrado: {}\n\n{}".format(result.output, text))
        return PresentationResult(True, "Cifrado guardado en {}.\nPerfil: {}.".format(result, padding.value))

    def _hash(self, values) -> PresentationResult:
        algorithm, output = HashAlgorithm(values["algorithm"]), Path(values["output"].strip())
        if values["source_kind"] == "Archivo":
            result = self._service.hash_file(Path(values["source"].strip()), output, algorithm)
        else:
            result = self._service.hash_text(values["message"], output, algorithm)
        return PresentationResult(True, "{}: {}\nSalida: {}".format(algorithm.value, result.hexadecimal, result.output))

    def _certificate(self, values) -> PresentationResult:
        if values["password"] != values["confirmation"]:
            raise ValidationError("Las contraseñas no coinciden.")
        identity = CertificateIdentity(
            values["common_name"], values["organization"], values["country"],
            values["state"], values["locality"],
        )
        names = CertificateNames(
            private_key=values["private_name"], request=values["request_name"],
            certificate=values["certificate_name"], public_key=values["public_name"],
        )
        bundle = self._service.create_certificate(identity, values["password"], Path(values["directory"].strip()), names)
        return PresentationResult(True, "\n".join((
            "Identidad de laboratorio creada.",
            "Clave privada cifrada: " + str(bundle.private_key),
            "CSR: " + str(bundle.request), "Certificado: " + str(bundle.certificate),
            "Clave pública: " + str(bundle.public_key),
        )))

    def _sign(self, values) -> PresentationResult:
        output = self._service.sign_file(
            Path(values["source"].strip()), Path(values["key"].strip()),
            Path(values["output"].strip()), values["password"],
        )
        return PresentationResult(True, "Firma RSA / SHA-256 guardada en {}.".format(output))

    def _verify(self, values) -> PresentationResult:
        result = self._service.verify_file(
            Path(values["source"].strip()), Path(values["signature"].strip()), Path(values["certificate"].strip()),
        )
        return PresentationResult(result.signature_valid, describe_verification(result))

    def _tamper(self, values) -> PresentationResult:
        replace = values["alteration"] == "Reemplazar texto"
        result = self._service.demonstrate_tampering(
            Path(values["source"].strip()), Path(values["signature"].strip()), Path(values["certificate"].strip()),
            Path(values["output"].strip()), values["old_text"] if replace else None,
            values["new_text"] if replace else None,
        )
        return PresentationResult(True, "Firma original: válida.\nFirma de la copia alterada: no válida.\nCopia: {}".format(result.output))
