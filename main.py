"""Entrada portable: ejecutar desde cualquier carpeta con Python 3.8+."""

import sys


if __name__ == "__main__":
    if sys.version_info < (3, 8):
        print("Se requiere Python 3.8 o posterior.", file=sys.stderr)
        raise SystemExit(2)
    from cryptolab.app import main

    raise SystemExit(main())
