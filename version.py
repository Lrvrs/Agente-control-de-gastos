"""Imprime la huella del código fuente de este repositorio.

Se ejecuta con `python3 version.py` y devuelve la misma cadena que la
aplicación muestra en el pie de su barra lateral. Comparar ambas responde sin
ambigüedad a si lo desplegado corresponde a lo que hay en el repositorio, que
es la duda recurrente cuando se itera varias veces al día.
"""

import hashlib
from pathlib import Path


def huella() -> str:
    """Calcula la huella recorriendo fuentes y datos en orden estable."""
    # El recorrido debe coincidir exactamente con el de la aplicación: mismos
    # ficheros y mismo orden, o las dos huellas no serían comparables.
    raiz = Path(__file__).resolve().parent
    resumen = hashlib.sha256()

    for ruta in sorted(raiz.rglob("*.py")) + sorted(raiz.glob("datos/*")):
        try:
            resumen.update(ruta.read_bytes())
        except OSError:
            continue

    return resumen.hexdigest()[:7]


if __name__ == "__main__":
    print(huella())
