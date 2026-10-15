"""Requiere OpenSSL real; ausencia explícita = prueba omitida, no éxito simulado."""

import os
import importlib.util
import io
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptolab.app import build_service
from cryptolab.domain import (
    CertificateIdentity, CertificateNames, HashAlgorithm, OperationError,
    RsaPadding, ValidationError,
)
from cryptolab.openssl import OpenSSLRunner


class OpenSSLIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable = os.environ.get("CRYPTOLAB_TEST_OPENSSL") or shutil.which("openssl")
        if not executable:
            raise unittest.SkipTest("No hay OpenSSL: define CRYPTOLAB_TEST_OPENSSL o añádelo a PATH.")
        cls.runner = OpenSSLRunner(executable)
        cls.version = cls.runner.validate()
        cls.service = build_service(cls.runner)
        cls.scratch = tempfile.TemporaryDirectory(prefix="CryptoLab integración espacios ")
        cls.addClassCleanup(cls.scratch.cleanup)
        cls.directory = Path(cls.scratch.name)
        cls.password = "Contraseña de prueba sin valor real 2026!"
        cls.identity = cls.service.create_certificate(
            CertificateIdentity('Evaluación / Grupo + "$HOME" #literal', "Universidad de ejemplo", "ES"),
            cls.password, cls.directory,
            CertificateNames("clave privada.pem", "solicitud CSR.pem", "certificado.pem", "clave pública.pem"),
        )
        cls.document = cls.directory / "documento á.txt"
        cls.document.write_bytes("Documento académico.\nContenido íntegro.".encode("utf-8"))
        cls.signature = cls.service.sign_file(
            cls.document, cls.identity.private_key, cls.directory / "firma.bin", cls.password,
        )

    def test_known_hash_vectors_and_saved_file(self):
        expected = {
            HashAlgorithm.SHA256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            HashAlgorithm.MD5: "900150983cd24fb0d6963f7d28e17f72",
        }
        for algorithm, digest in expected.items():
            with self.subTest(algorithm=algorithm):
                result = self.service.hash_text("abc", self.directory / (algorithm.name + ".hash"), algorithm)
                self.assertEqual(digest, result.hexadecimal)
                self.assertEqual(digest + "\n", result.output.read_text(encoding="ascii"))

    def test_certificate_is_v3_encrypted_and_has_valid_csr(self):
        self.assertIn(b"BEGIN ENCRYPTED PRIVATE KEY", self.identity.private_key.read_bytes())
        text = self.runner.run(["x509", "-in", str(self.identity.certificate), "-noout", "-text"]).stdout
        self.assertIn(b"Version: 3", text)
        self.runner.run(["req", "-in", str(self.identity.request), "-verify", "-noout"])
        details = self.service.verify_file(self.document, self.signature, self.identity.certificate)
        self.assertTrue(details.signature_valid)
        self.assertTrue(details.certificate_current)
        self.assertIn("Evaluación", details.certificate.subject)
        self.assertIn("$HOME", details.certificate.subject)
        self.assertIn("#literal", details.certificate.subject)
        if os.name == "posix":
            self.assertEqual(0, stat.S_IMODE(self.identity.private_key.stat().st_mode) & 0o077)

    def test_rsa_roundtrip_for_both_explicit_profiles(self):
        for padding in RsaPadding:
            with self.subTest(padding=padding):
                message = "Mensaje con á y un salto.\nSegunda línea."
                encrypted = self.service.encrypt_text(message, self.identity.public_key,
                                                       self.directory / (padding.name + ".bin"), padding)
                decrypted = self.service.decrypt_file(
                    encrypted, self.identity.private_key, self.directory / (padding.name + ".txt"),
                    self.password, padding,
                )
                self.assertEqual(message, decrypted.message)

    def test_practice_profile_interoperates_with_the_document_commands(self):
        message = "Compatibilidad con la práctica.".encode("utf-8")
        cipher = self.service.encrypt_text(message.decode("utf-8"), self.identity.public_key,
                                           self.directory / "practica.bin", RsaPadding.PKCS1)
        recovered = self.runner.run([
            "pkeyutl", "-decrypt", "-inkey", str(self.identity.private_key),
            "-in", str(cipher), "-passin", "stdin",
        ], input_data=(self.password + "\n").encode("utf-8")).stdout
        self.assertEqual(message, recovered)

    def test_wrong_password_does_not_publish_a_partial_file(self):
        output = self.directory / "firma fallida.bin"
        with self.assertRaises(OperationError):
            self.service.sign_file(self.document, self.identity.private_key, output, "incorrecta")
        self.assertFalse(output.exists())

    def test_oversized_utf8_message_is_rejected_by_bytes(self):
        with self.assertRaises(ValidationError):
            self.service.encrypt_text("á" * 160, self.identity.public_key,
                                      self.directory / "demasiado.bin", RsaPadding.OAEP_SHA256)
        self.assertFalse((self.directory / "demasiado.bin").exists())

    def test_valid_signature_then_alteration_and_original_preserved(self):
        original = self.document.read_bytes()
        result = self.service.demonstrate_tampering(
            self.document, self.signature, self.identity.certificate,
            self.directory / "copia alterada.txt", "íntegro", "modificado",
        )
        self.assertTrue(result.original.signature_valid)
        self.assertFalse(result.altered.signature_valid)
        self.assertEqual(original, self.document.read_bytes())
        self.assertFalse(self.service.verify_file(result.output, self.signature, self.identity.certificate).signature_valid)

    def test_invalid_certificate_is_an_operational_error_not_an_invalid_signature(self):
        invalid = self.directory / "invalido.pem"
        invalid.write_text("esto no es un certificado", encoding="ascii")
        with self.assertRaises(OperationError):
            self.service.verify_file(self.document, self.signature, invalid)

    def test_shipped_example_generates_new_artifacts_without_a_preset_password(self):
        script = Path(__file__).resolve().parents[1] / "examples" / "crear_demo.py"
        spec = importlib.util.spec_from_file_location("cryptolab_demo", str(script))
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", list(sys.path)):
            spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix="CryptoLab demo ") as directory, \
             patch.object(sys, "argv", [str(script), "--output", directory, "--openssl", self.runner.executable]), \
             patch.object(module, "read_password", return_value=self.password), \
             patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(0, module.main())
            output = Path(directory)
            self.assertTrue((output / "csr.pem").is_file())
            self.assertTrue((output / "firma.bin").is_file())
            self.assertNotEqual((output / "documento_alterado.txt").read_bytes(), (script.parent / "documento.txt").read_bytes())


if __name__ == "__main__":
    unittest.main()
