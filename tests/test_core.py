"""Reglas, casos de uso, archivos y límites de dependencia."""

import ast
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from cryptolab.domain import (
    CertificateDetails, CertificateIdentity, CertificateNames, OperationError,
    RsaPadding, ValidationError, validate_password,
)
from cryptolab.service import CryptoLabService
from cryptolab.files import LocalFileStore
from cryptolab.openssl import OpenSSLRunner


class DomainTests(unittest.TestCase):
    def test_identity_has_no_implicit_country_and_preserves_user_characters(self):
        identity = CertificateIdentity("Ana / Pérez + Grupo", "Universidad", "es")
        self.assertEqual("ES", identity.country)
        self.assertEqual("Ana / Pérez + Grupo", identity.common_name)
        with self.assertRaises(ValidationError):
            CertificateIdentity("Ana", "Universidad", "")

    def test_output_names_cannot_escape_directory_or_collide_after_transfer(self):
        for name in ("../clave.pem", r"sub\clave.pem", "", ".."):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                CertificateNames(private_key=name).in_directory(Path("salida"))
        with self.assertRaises(ValidationError):
            CertificateNames(private_key="CLAVE.pem", public_key="clave.pem").in_directory(Path("salida"))

    def test_padding_limits_are_measured_in_bytes(self):
        self.assertEqual(373, RsaPadding.PKCS1.message_limit(3072))
        self.assertEqual(318, RsaPadding.OAEP_SHA256.message_limit(3072))
        self.assertEqual(190, RsaPadding.OAEP_SHA256.message_limit(2048))

    def test_password_line_injection_is_rejected(self):
        for value in ("clave\nsegunda", "clave\r", "clave\x00"):
            with self.subTest(value=repr(value)), self.assertRaises(ValidationError):
                validate_password(value)
        with self.assertRaises(ValidationError):
            validate_password("", required=True)
        validate_password("")  # Clave importada sin contraseña.

    def test_certificate_validity_is_independent_of_signature_and_locale(self):
        before = datetime(2026, 1, 1, tzinfo=timezone.utc)
        after = datetime(2027, 1, 1, tzinfo=timezone.utc)
        certificate = CertificateDetails("CN=Ejemplo", before, after)
        self.assertTrue(certificate.is_current(before))
        self.assertFalse(certificate.is_current(datetime(2028, 1, 1, tzinfo=timezone.utc)))


class FileStoreTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="CryptoLab espacios ")
        self.addCleanup(self.scratch.cleanup)
        self.directory = Path(self.scratch.name)
        self.files = LocalFileStore()

    def test_existing_file_is_never_replaced(self):
        output = self.directory / "existente.txt"
        output.write_bytes(b"conservar")
        with self.assertRaises(ValidationError):
            with self.files.outputs((output,)):
                self.fail("No debe abrir una transacción para una salida existente.")
        self.assertEqual(b"conservar", output.read_bytes())

    def test_failed_operation_leaves_no_partial_output(self):
        output = self.directory / "fallido.bin"
        with self.assertRaises(RuntimeError):
            with self.files.outputs((output,)) as staged:
                staged[0].write_bytes(b"parcial")
                raise RuntimeError("fallo externo")
        self.assertFalse(output.exists())

    def test_publication_race_preserves_other_file_and_rolls_back_own_files(self):
        first, second = self.directory / "primero.bin", self.directory / "segundo.bin"
        with self.assertRaises(OperationError):
            with self.files.outputs((first, second)) as staged:
                staged[0].write_bytes(b"uno")
                staged[1].write_bytes(b"dos")
                second.write_bytes(b"otro proceso")
        self.assertFalse(first.exists())
        self.assertEqual(b"otro proceso", second.read_bytes())

    def test_dangling_symlink_is_not_used_as_an_output(self):
        output = self.directory / "enlace.txt"
        target = self.directory / "objetivo.txt"
        try:
            output.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("La cuenta o el sistema no permiten crear enlaces simbólicos.")
        with self.assertRaises(ValidationError):
            with self.files.outputs((output,)):
                self.fail("No debe seguir un enlace de salida.")
        self.assertFalse(target.exists())

    def test_replacement_across_read_boundary_preserves_all_other_bytes(self):
        original = self.directory / "original.txt"
        content = b"x" * 65534 + "frase á".encode("utf-8") + b"fin" * 30000
        original.write_bytes(content)
        output = self.directory / "alterado.txt"
        with self.files.outputs((output,), (original,)) as staged:
            self.files.alter(original, staged[0], "frase á", "nuevo")
        self.assertEqual(content.replace("frase á".encode("utf-8"), b"nuevo", 1), output.read_bytes())
        self.assertEqual(content, original.read_bytes())

    def test_duplicate_output_paths_are_rejected(self):
        output = self.directory / "mismo.txt"
        with self.assertRaises(ValidationError):
            with self.files.outputs((output, output)):
                self.fail("Las salidas deben ser únicas.")


ROOT = Path(__file__).resolve().parents[1]


class ArchitectureTests(unittest.TestCase):
    def test_dependencies_point_toward_the_core(self):
        forbidden = {
            "domain": {"service", "openssl", "files", "forms", "console", "gui", "app", "subprocess", "tkinter"},
            "service": {"openssl", "files", "forms", "console", "gui", "app", "subprocess", "tkinter"},
            "forms": {"openssl", "files", "app", "subprocess", "tkinter"},
            "console": {"openssl", "files", "app", "subprocess", "tkinter"},
            "gui": {"openssl", "files", "app", "subprocess"},
        }
        for layer, disallowed in forbidden.items():
            source = ROOT / "cryptolab" / (layer + ".py")
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    self.assertFalse(set(name.split(".")).intersection(disallowed), (source, name))

    def test_source_uses_python38_syntax(self):
        for directory in ("cryptolab", "tests", "examples"):
            for source in (ROOT / directory).rglob("*.py"):
                with self.subTest(source=source.relative_to(ROOT)):
                    ast.parse(source.read_text(encoding="utf-8"), feature_version=8)

    def test_entrypoint_can_show_help_from_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(ROOT / "main.py"), "--help"],
                cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(b"--cli", result.stdout)

    def test_missing_executable_has_actionable_error_without_traceback(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), "--cli", "--openssl", "cryptolab-no-existe-123"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn(b"--openssl", result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)


class ProcessBoundaryTests(unittest.TestCase):
    def test_external_process_has_no_shell_or_inherited_interactive_stdin(self):
        runner = OpenSSLRunner(sys.executable)
        completed = subprocess.CompletedProcess([], 0, b"resultado", b"")
        with patch("cryptolab.openssl.subprocess.run", return_value=completed) as execute:
            runner.run(["version"])
        self.assertFalse(execute.call_args.kwargs["shell"])
        self.assertEqual(b"", execute.call_args.kwargs["input"])
        self.assertEqual("C", execute.call_args.kwargs["env"]["LC_ALL"])

    def test_timeout_is_translated_and_does_not_expose_password(self):
        runner = OpenSSLRunner(sys.executable, timeout=1)
        with patch("cryptolab.openssl.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("openssl", 1, stderr=b"clave-no-publicar")):
            with self.assertRaises(OperationError) as captured:
                runner.run(["pkeyutl"], input_data=b"clave-no-publicar")
        self.assertNotIn("clave-no-publicar", str(captured.exception))


class UseCaseTests(unittest.TestCase):
    def test_tamper_requires_a_valid_original_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("document.txt", "firma.bin", "cert.pem")]
            for path in paths:
                path.write_bytes(b"ejemplo")
            engine = Mock()
            engine.verify.return_value = False
            engine.certificate_details.return_value = CertificateDetails(
                "CN=Ejemplo", datetime(2020, 1, 1, tzinfo=timezone.utc),
                datetime(2100, 1, 1, tzinfo=timezone.utc),
            )
            service = CryptoLabService(engine, LocalFileStore(), lambda: datetime.now(timezone.utc))
            output = Path(directory) / "alterado.txt"
            with self.assertRaises(ValidationError):
                service.demonstrate_tampering(*paths, output)
            self.assertFalse(output.exists())
            self.assertEqual(1, engine.verify.call_count)
