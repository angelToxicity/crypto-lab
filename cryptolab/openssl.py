"""Adaptador de comandos OpenSSL con ejecución directa, limitada y sin shell."""

import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence, Tuple

from .domain import (
    CertificateDetails, CertificateFiles, CertificateIdentity, DependencyError,
    HashAlgorithm, OperationError, RsaPadding, ValidationError, validate_password,
)


class OpenSSLRunner:
    REQUIRED_COMMANDS = {"dgst", "genpkey", "pkeyutl", "req", "rsa", "x509"}

    def __init__(self, executable: Optional[str] = None, timeout: int = 120):
        if timeout <= 0:
            raise DependencyError("El tiempo límite debe ser mayor que cero.")
        candidate = str(Path(executable).expanduser()) if executable else "openssl"
        found = shutil.which(candidate)
        if not found:
            raise DependencyError(
                "No se encontró el ejecutable OpenSSL. Debe estar en PATH o indicarse "
                "con --openssl /ruta/al/ejecutable. No se instalaron paquetes."
            )
        self.executable = str(Path(found).resolve())
        self.timeout = timeout

    def validate(self) -> str:
        version = self.run(["version"]).stdout.decode("utf-8", errors="replace").strip()
        match = re.match(r"OpenSSL\s+(\d+)\.(\d+)\.(\d+)", version)
        if not match or tuple(map(int, match.groups())) < (1, 1, 1):
            raise DependencyError("Se requiere OpenSSL 1.1.1 o posterior. Detectado: {}".format(version))
        available = self.run(["list", "-commands"]).stdout.decode("ascii", errors="replace").split()
        missing = self.REQUIRED_COMMANDS.difference(available)
        if missing:
            raise DependencyError("OpenSSL no ofrece los comandos requeridos: {}.".format(", ".join(sorted(missing))))
        for name, size in (("sha256", 32), ("md5", 16)):
            try:
                result = self.run(["dgst", "-" + name, "-binary"])
                if len(result.stdout) != size:
                    raise OperationError("Longitud de resumen inesperada.")
            except OperationError as error:
                raise DependencyError("El OpenSSL seleccionado no permite {} con su configuración actual.".format(name)) from error
        return version

    def run(self, arguments: Sequence[str], input_data: Optional[bytes] = None,
            allowed_codes: Tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
        environment = os.environ.copy()
        environment.update({"LC_ALL": "C", "LANG": "C"})
        try:
            result = subprocess.run(
                [self.executable] + list(arguments),
                input=input_data if input_data is not None else b"",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                shell=False, timeout=self.timeout, check=False, env=environment,
            )
        except subprocess.TimeoutExpired as error:
            raise OperationError("OpenSSL superó el límite de {} segundos.".format(self.timeout)) from error
        except OSError as error:
            raise DependencyError("No se pudo iniciar OpenSSL: {}.".format(error)) from error
        if result.returncode not in allowed_codes:
            self.raise_failure(arguments[0], result)
        return result

    @staticmethod
    def raise_failure(operation: str, result: subprocess.CompletedProcess) -> None:
        raw = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        if any(marker in raw.lower() for marker in ("bad decrypt", "bad password", "unable to get passphrase")):
            detail = "No se pudo abrir la clave privada; revisa su contraseña y formato."
        else:
            detail = "\n".join(raw.splitlines()[-3:])[-800:] or "Sin detalles de diagnóstico."
        raise OperationError("OpenSSL / {} (código {}): {}".format(operation, result.returncode, detail))


class OpenSSLEngine:
    def __init__(self, runner: OpenSSLRunner):
        self._runner = runner

    def digest_file(self, source: Path, algorithm: HashAlgorithm) -> bytes:
        return self._runner.run(["dgst", "-" + algorithm.openssl_name, "-binary", str(source)]).stdout

    def digest_text(self, message: str, algorithm: HashAlgorithm) -> bytes:
        return self._runner.run(
            ["dgst", "-" + algorithm.openssl_name, "-binary"],
            input_data=message.encode("utf-8"),
        ).stdout

    def rsa_bits(self, public_key: Path) -> int:
        result = self._runner.run(["rsa", "-pubin", "-in", str(public_key), "-text", "-noout"])
        match = re.search(rb"Public-Key:\s*\((\d+) bit\)", result.stdout)
        if not match:
            raise ValidationError("No se pudo leer una clave pública RSA en formato PEM.")
        bits = int(match.group(1))
        return bits

    @staticmethod
    def _encryption_options(padding: RsaPadding):
        if padding is RsaPadding.PKCS1:
            return ["-pkeyopt", "rsa_padding_mode:pkcs1"]
        return [
            "-pkeyopt", "rsa_padding_mode:oaep",
            "-pkeyopt", "rsa_oaep_md:sha256",
            "-pkeyopt", "rsa_mgf1_md:sha256",
        ]

    @staticmethod
    def _password_input(password: str) -> bytes:
        validate_password(password)
        return password.encode("utf-8") + b"\n"

    def encrypt(self, source: Path, public_key: Path, output: Path, padding: RsaPadding) -> None:
        self._runner.run([
            "pkeyutl", "-encrypt", "-pubin", "-inkey", str(public_key),
            "-in", str(source), "-out", str(output),
        ] + self._encryption_options(padding))

    def decrypt(self, source: Path, private_key: Path, output: Path, password: str, padding: RsaPadding) -> None:
        self._runner.run([
            "pkeyutl", "-decrypt", "-inkey", str(private_key),
            "-in", str(source), "-out", str(output), "-passin", "stdin",
        ] + self._encryption_options(padding), input_data=self._password_input(password))

    def create_certificate(self, identity: CertificateIdentity, password: str, outputs: CertificateFiles) -> None:
        password_input = self._password_input(password)
        self._runner.run([
            "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:3072",
            "-aes-256-cbc", "-pass", "stdin", "-out", str(outputs.private_key),
        ], input_data=password_input)
        with tempfile.TemporaryDirectory(prefix="cryptolab-cert-") as directory:
            request_config = Path(directory) / "request.cnf"
            request_config.write_text(self._request_configuration(identity), encoding="utf-8")
            self._runner.run([
                "req", "-new", "-sha256", "-utf8", "-key", str(outputs.private_key),
                "-passin", "stdin", "-out", str(outputs.request), "-config", str(request_config),
            ], input_data=password_input)
            extensions = Path(directory) / "extensions.cnf"
            extensions.write_text(
                "[lab]\nbasicConstraints=critical,CA:FALSE\n"
                "keyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\n",
                encoding="ascii",
            )
            self._runner.run([
                "x509", "-req", "-sha256", "-days", "365",
                "-in", str(outputs.request), "-signkey", str(outputs.private_key),
                "-passin", "stdin", "-out", str(outputs.certificate),
                "-extfile", str(extensions), "-extensions", "lab",
            ], input_data=password_input)
        self._runner.run([
            "x509", "-in", str(outputs.certificate), "-pubkey", "-noout",
            "-out", str(outputs.public_key),
        ])

    @staticmethod
    def _request_configuration(identity: CertificateIdentity) -> str:
        values = (("C", identity.country), ("ST", identity.state), ("L", identity.locality),
                  ("O", identity.organization), ("CN", identity.common_name))
        lines = ["[req]", "prompt=no", "distinguished_name=dn", "utf8=yes", "string_mask=utf8only", "[dn]"]
        for name, value in values:
            if value:
                quoted = value.replace("\\", "\\\\").replace("$", "\\$").replace('"', '\\"')
                lines.append('{}="{}"'.format(name, quoted))
        return "\n".join(lines) + "\n"

    def sign(self, source: Path, private_key: Path, output: Path, password: str) -> None:
        with tempfile.TemporaryDirectory(prefix="cryptolab-sign-") as directory:
            digest = Path(directory) / "document.sha256"
            self._runner.run(["dgst", "-sha256", "-binary", "-out", str(digest), str(source)])
            self._runner.run([
                "pkeyutl", "-sign", "-inkey", str(private_key),
                "-in", str(digest), "-out", str(output), "-passin", "stdin",
                "-pkeyopt", "digest:sha256", "-pkeyopt", "rsa_padding_mode:pkcs1",
            ], input_data=self._password_input(password))

    def verify(self, document: Path, signature: Path, certificate: Path) -> bool:
        with tempfile.TemporaryDirectory(prefix="cryptolab-verify-") as directory:
            public_key = Path(directory) / "public_key.pem"
            digest = Path(directory) / "document.sha256"
            self._runner.run(["x509", "-in", str(certificate), "-pubkey", "-noout", "-out", str(public_key)])
            self.rsa_bits(public_key)
            self._runner.run(["dgst", "-sha256", "-binary", "-out", str(digest), str(document)])
            result = self._runner.run([
                "pkeyutl", "-verify", "-pubin", "-inkey", str(public_key),
                "-in", str(digest), "-sigfile", str(signature),
                "-pkeyopt", "digest:sha256", "-pkeyopt", "rsa_padding_mode:pkcs1",
            ], allowed_codes=(0, 1))
            if result.returncode == 0:
                return True
            if b"Signature Verification Failure" in result.stdout:
                return False
            self._runner.raise_failure("verificación", result)
        return False

    def certificate_details(self, certificate: Path) -> CertificateDetails:
        result = self._runner.run([
            "x509", "-in", str(certificate), "-noout", "-subject",
            "-startdate", "-enddate", "-nameopt", "utf8",
        ])
        fields = {}
        for line in result.stdout.decode("utf-8", errors="replace").splitlines():
            if "=" in line:
                name, value = line.split("=", 1)
                fields[name.strip()] = value.strip()
        try:
            return CertificateDetails(
                fields["subject"], self._parse_date(fields["notBefore"]),
                self._parse_date(fields["notAfter"]),
            )
        except (KeyError, ValueError) as error:
            raise OperationError("No se pudieron interpretar los datos del certificado.") from error

    @staticmethod
    def _parse_date(value: str) -> datetime:
        # No usa strptime(%b): los meses de OpenSSL no dependen del idioma de Python.
        months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
        month, day, time, year, zone = value.split()
        if zone != "GMT":
            raise ValueError("Zona horaria inesperada.")
        hours, minutes, seconds = map(int, time.split(":"))
        return datetime(int(year), months.index(month) + 1, int(day), hours, minutes, seconds, tzinfo=timezone.utc)
