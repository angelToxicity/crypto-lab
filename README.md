# CryptoLab UCV

Aplicación académica para los seis módulos de la práctica OpenSSL. Incluye consola completa y ventana Tkinter opcional; se ejecuta sin instalar el proyecto como paquete.

## Requisitos e inicio

Linux, Python 3.8+ y OpenSSL 1.1.1+ con los comandos y algoritmos comprobados por el diagnóstico. Se necesitan permisos de lectura, escritura en la salida elegida y acceso a la carpeta temporal. Ubuntu 22.04 es el entorno recomendado por el enunciado; WSL no es obligatorio.

Desde la carpeta extraída:

~~~bash
python3 main.py --check
python3 main.py --cli
~~~

Para la ventana, se necesitan Tkinter y una sesión gráfica:

~~~bash
python3 main.py --gui
~~~

Sin argumentos se intenta abrir la ventana y se ofrece consola si no está disponible. --gui informa el error si no puede abrirla; --cli no importa Tkinter. --check diagnostica dependencias sin crear claves ni documentos.

OpenSSL se busca en PATH; también puede indicarse con --openssl /ruta/al/openssl. --timeout SEGUNDOS limita cada comando (120 segundos por defecto). --help muestra las opciones. Las rutas relativas se interpretan desde el directorio de trabajo de la terminal. Las rutas con espacios se entrecomillan en comandos de terminal, y se escriben sin comillas de shell dentro de los formularios.

requirements.txt está vacío; no se necesitan paquetes de pip. El entorno virtual es opcional. El programa no instala dependencias. Para habilitar voluntariamente Tkinter en el Python del sistema Ubuntu:

~~~bash
sudo apt update
sudo apt install python3-tk
python3 -m tkinter
~~~

La consola permite evaluar todas las operaciones sin instalar Tkinter.

La ventana usa el diseño de la maqueta: navegación lateral, tarjetas y controles redondeados, campos en dos columnas y resultados destacados. Se adapta a una columna al reducir el ancho. Colores y controles se dibujan con Tkinter/ttk; no requiere paquetes de temas, imágenes externas ni instalar tipografías. La barra de título sigue perteneciendo al sistema operativo.

## Funciones y criterios

1. Cifrar texto o archivo breve y descifrar mostrando el mensaje UTF-8.
2. Calcular MD5 o SHA-256 y guardar el hash.
3. Generar clave privada cifrada, CSR, certificado X.509 v3 y clave pública, con carpeta y nombres elegidos por el usuario.
4. Firmar el hash SHA-256 binario de un documento.
5. Verificar con la clave pública del certificado; informar la vigencia por separado.
6. Crear una copia alterada, después de verificar el original, y comprobar que la firma falle.

Todas las operaciones criptográficas invocan comandos OpenSSL mediante subprocess, sin shell ni bibliotecas criptográficas de Python. Las contraseñas se capturan ocultas y se pasan por entrada estándar; no se guardan en argumentos o archivos. Python no garantiza borrado físico de contraseñas en memoria.

Se elige explícitamente el perfil RSA: PKCS#1 v1.5 para interoperar con los comandos del enunciado, u OAEP / SHA-256. Se debe usar el mismo al descifrar. Las claves nuevas tienen 3072 bits: admiten 373 y 318 bytes respectivamente. El tamaño de una clave importada se consulta a OpenSSL. No se incluye cifrado híbrido para archivos grandes.

La firma usa RSA PKCS#1 v1.5 y SHA-256. El certificado es autofirmado: una firma válida no acredita por sí sola la identidad del titular. MD5 se incluye para la actividad académica.

Las salidas existentes se conservan. Se retiran temporales y salidas propias de una operación fallida; no se promete publicación atómica de un conjunto de archivos. La CSR usa configuración temporal UTF-8 con valores escapados, sin depender del openssl.cnf del equipo.

## Organización

~~~text
main.py                Inicio y comprobación de versión Python
cryptolab/
  domain.py            Reglas, errores y resultados
  service.py           Casos de uso y contratos de sus dependencias
  openssl.py           Comandos y ejecutor de procesos
  files.py             Archivos temporales y salidas sin sobrescritura
  forms.py             Formularios y controlador compartidos
  console.py           Menú y entrada oculta de contraseñas
  gui.py               Ventana Tkinter
  app.py               Opciones de inicio y composición de dependencias
examples/              Documento ficticio y generador de demostración
tests/                 Pruebas del núcleo, interfaces y OpenSSL
requirements.txt       Vacío
~~~

Clean Architecture se mantiene por dependencias: el dominio no realiza entrada/salida; los casos de uso reciben motor, archivos y reloj mediante el constructor. Consola y ventana comparten un controlador. Solo app.py conecta las implementaciones concretas. No hay framework ni contenedor de inyección.

## Ejemplos y pruebas

El documento de examples se usa para cifrado, hash y firma. Para generar claves y resultados nuevos, con datos ficticios y contraseña solicitada al ejecutarlos:

~~~bash
mkdir demo
python3 examples/crear_demo.py --output demo
~~~

La carpeta de salida debe existir y estar vacía. El generador admite --openssl. No hay contraseña preestablecida ni claves privadas dentro del ZIP de fuente.

~~~bash
python3 -m unittest discover -s tests -v
~~~

Las pruebas usan unittest, incluido en Python. Si OpenSSL no está en PATH, seleccionar el ejecutable con la variable CRYPTOLAB_TEST_OPENSSL. Sin OpenSSL las pruebas de integración se omiten: eso no valida las operaciones criptográficas.

La comprobación de ventana es opcional y requiere escritorio:

~~~bash
python3 -m unittest tests.gui_smoke -v
~~~

Validación local: 35 pruebas automáticas y una de escritorio satisfactorias, con Windows 11, Python 3.12.3 y OpenSSL 3.2.2. Cubren vectores de hash, CSR y certificado, ambos perfiles RSA, firma, alteración, errores, archivos y límites de dependencias. Se comprueba sintaxis Python 3.8, pero queda pendiente ejecutar esta versión en Ubuntu 22.04 y en un intérprete Python 3.8. No se presenta esa compatibilidad como validada.

## Entrega

El ZIP contiene el código, las pruebas y los ejemplos, sin cachés, entornos virtuales o claves generadas. El informe PDF solicitado por el profesor es un entregable separado: debe incluir datos reales del estudiante, capturas de los seis módulos, versiones del entorno y análisis de alteración/no repudio.

Referencias: [comandos OpenSSL](https://docs.openssl.org/3.0/man1/), [Python subprocess](https://docs.python.org/3.8/library/subprocess.html) y [Tkinter](https://docs.python.org/3/library/tkinter.html).

