"""Genera claves y resultados nuevos con datos ficticios y contraseña del usuario."""

import argparse
import sys
from pathlib import Path

# Permite ejecutar el archivo directamente sin instalar el paquete.
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from cryptolab.app import build_service
from cryptolab.domain import (
    CertificateIdentity, CertificateNames, CryptoLabError, HashAlgorithm,
    RsaPadding, ValidationError,
)
from cryptolab.openssl import OpenSSLRunner
from cryptolab.console import read_password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Carpeta existente y vacía de resultados.")
    parser.add_argument("--openssl", help="Ejecutable OpenSSL si no está en PATH.")
    args = parser.parse_args()
    try:
        runner = OpenSSLRunner(args.openssl)
        print(runner.validate())
        output = args.output.expanduser().resolve()
        if not output.is_dir() or any(output.iterdir()):
            raise ValidationError("Selecciona una carpeta existente y vacía para la demostración.")
        password = read_password("Contraseña nueva para las claves de ejemplo: ")
        if password != read_password("Confirmar contraseña: "):
            raise ValidationError("Las contraseñas no coinciden.")
        service = build_service(runner)
        bundle = service.create_certificate(
            CertificateIdentity("Persona Ejemplo", "Laboratorio Academico", "ES"),
            password, output, CertificateNames(),
        )
        source = PROJECT / "examples" / "documento.txt"
        encrypted = service.encrypt_file(source, bundle.public_key,
                                         output / "mensaje_cifrado.bin", RsaPadding.PKCS1)
        service.decrypt_file(encrypted, bundle.private_key, output / "mensaje_descifrado.txt",
                             password, RsaPadding.PKCS1)
        service.hash_file(source, output / "hash.sha256", HashAlgorithm.SHA256)
        signature = service.sign_file(source, bundle.private_key,
                                       output / "firma.bin", password)
        result = service.demonstrate_tampering(
            source, signature, bundle.certificate, output / "documento_alterado.txt",
        )
        print("Resultados: {}".format(output))
        print("Firma original: {}. Firma alterada: {}.".format(
            result.original.signature_valid, result.altered.signature_valid,
        ))
        return 0
    except (CryptoLabError, OSError) as error:
        print("Error: {}".format(error), file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("\nDemostración cancelada.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
