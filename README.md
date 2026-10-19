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

En una terminal interactiva, el menú principal y los campos con opciones se manejan con el teclado:

- La opción activa aparece marcada con **`[x]` desde el inicio**. Las flechas mueven esa misma marca; siempre hay una sola opción seleccionada.
- **Izquierda / Derecha**: recorrer las opciones; **Arriba / Abajo**: cambiar de fila conservando la columna. Si solo hay una fila, arriba y abajo también recorren sus opciones. **Inicio / Fin**: ir a los extremos.
- **RePág / AvPág**: desplazarse una página cuando la lista no cabe en pantalla.
- **Enter, X o Espacio**: abrir o confirmar la opción marcada.
- **Esc o Q**: volver al menú desde una lista de opciones, o salir desde el menú principal.

Las opciones se distribuyen en columnas del mismo ancho, con márgenes laterales, espacio entre columnas y una línea en blanco entre filas. El título, la descripción y los controles se presentan en bloques separados; la descripción se ajusta en hasta dos líneas y la opción activa se resalta. El contador de opciones aparece cuando hace falta desplazarse. La cantidad de columnas se adapta al ancho disponible y al tamaño de los nombres; en terminales estrechas se usa una sola columna. Si falta altura, el espaciado se reduce para mantener visible la selección y los controles. Al cambiar el tamaño de la terminal, la siguiente interacción ajusta la distribución conservando la opción seleccionada.

Después de cada operación se mantiene el resultado visible hasta pulsar Enter. Los mensajes y las rutas se escriben de la forma habitual, y las contraseñas permanecen ocultas. El selector utiliza la biblioteca estándar de Python y adapta el desplazamiento al tamaño de la terminal en Windows y Linux. Si la entrada o la salida están redirigidas, o la terminal no admite el selector, se usa el menú numérico.

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
  terminal.py          Selector con flechas, marcado [x] y desplazamiento
  gui.py               Ventana Tkinter
  app.py               Opciones de inicio y composición de dependencias
examples/              Documento ficticio y generador de demostración
tests/                 Pruebas del núcleo, interfaces y OpenSSL
requirements.txt       Vacío
~~~

Clean Architecture se mantiene por dependencias: el dominio no realiza entrada/salida; los casos de uso reciben motor, archivos y reloj mediante el constructor. Consola y ventana comparten un controlador. Solo app.py conecta las implementaciones concretas. No hay framework ni contenedor de inyección.

## Ejemplos y pruebas

El documento de [examples](examples/README.md) se usa para cifrado, hash y firma. Para generar un conjunto de prueba con claves y resultados nuevos, datos ficticios y una contraseña solicitada durante la ejecución:

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

El selector de consola cuenta con 23 pruebas de selección automática, navegación, columnas uniformes, márgenes, separación entre bloques, ajuste de descripciones, cambio de tamaño, cancelación, listas largas, lectura de teclas y restauración de la terminal. La suite completa de 58 pruebas automáticas pasó en Windows 11 con Python 3.12.14 y OpenSSL 3.5.4, y en Ubuntu 24.04.3 LTS sobre WSL2 con Python 3.12.3 y OpenSSL 3.0.13 (paquete `3.0.13-0ubuntu3.7`). También se comprobó el teclado en terminales reales de Windows y Ubuntu, incluidos el menú principal y las opciones de un formulario. El arranque automático a consola funciona cuando no hay ventana disponible. En el Python de Ubuntu instalado en WSL falta Tkinter. En Ubuntu 24.04 con Tkinter y Xvfb, el smoke test de escritorio pasó y la prueba de redimensionado reprodujo el defecto de controles. La ejecución de Ubuntu 22.04 y Python 3.8 continúa pendiente.

### Pruebas de la interfaz Tkinter

Requieren un entorno Linux con Tkinter y escritorio, o Xvfb. El smoke test valida navegación y hash. La comprobación de redimensionado es una regresión conocida y debe fallar mientras siga el defecto:

~~~bash
python3 -m unittest tests.gui_smoke -v
xvfb-run -a python3 -m unittest tests.gui_busy_resize -v
~~~

## Entrega

El ZIP contiene el código, las pruebas y los ejemplos, sin cachés, entornos virtuales o claves generadas. El informe PDF solicitado por el profesor es un entregable separado: debe incluir datos reales del estudiante, capturas de los seis módulos, versiones del entorno y análisis de alteración/no repudio.

Referencias: [comandos OpenSSL](https://docs.openssl.org/3.0/man1/), [Python subprocess](https://docs.python.org/3.8/library/subprocess.html) y [Tkinter](https://docs.python.org/3/library/tkinter.html).

