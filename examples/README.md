# Archivos de ejemplo

`documento.txt` es el mensaje ficticio de entrada. `crear_demo.py` genera un conjunto completo para practicar los seis módulos, en una carpeta de salida vacía:

```bash
mkdir demo
python3 examples/crear_demo.py --output demo
```

El generador crea una clave privada cifrada, su CSR, certificado autofirmado X.509 v3 y clave pública. También cifra y descifra el documento, guarda los hashes MD5 y SHA-256, genera una firma y produce una copia alterada. La contraseña de la clave se solicita dos veces y no se escribe en los archivos de ejemplo.

| Archivo generado | Uso |
|---|---|
| `documento_original.txt` | Mensaje de entrada para cifrar, resumir, firmar y verificar. |
| `private_key.pem` | Clave privada cifrada; el generador solicita la contraseña al usarla. |
| `public_key.pem` | Clave pública para cifrar con RSA. |
| `certificate.pem` | Certificado autofirmado que se selecciona al verificar. |
| `csr.pem` | Solicitud de certificado generada junto con el par de claves. |
| `mensaje_cifrado.bin` / `mensaje_descifrado.txt` | Salidas del cifrado y descifrado RSA. Usa el perfil PKCS#1 v1.5 para descifrar. |
| `hash.md5` / `hash.sha256` | Resúmenes del documento original. |
| `firma.bin` | Firma RSA/SHA-256 del documento original. |
| `documento_alterado.txt` | Copia modificada cuya firma debe resultar inválida. |
| `LEEME.txt` | Notas breves sobre el conjunto generado. |

El generador informa `Firma original: True` y `Firma alterada: False` cuando termina correctamente. Los campos de nombres y organización son ficticios. No uses estas claves para proteger información real. Cada ejecución genera claves nuevas; la contraseña elegida no queda guardada.

Los archivos criptográficos no se versionan. Si la entrega necesita incluir un conjunto ya generado, crea uno con datos ficticios y adjúntalo explícitamente al ZIP; conserva la clave privada cifrada y no incluyas contraseñas reales.
