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

## Ejemplos y pruebas

El documento de [examples](examples/README.md) se usa para cifrado, hash y firma. Para generar un conjunto de prueba con claves y resultados nuevos, datos ficticios y una contraseña solicitada durante la ejecución:

~~~bash
mkdir demo
python3 examples/crear_demo.py --output demo
~~~

La carpeta de salida debe existir y estar vacía. El generador admite --openssl. No hay contraseña preestablecida ni claves privadas dentro del ZIP de fuente.