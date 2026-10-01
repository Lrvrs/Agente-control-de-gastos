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

    # Se descartan las carpetas ocultas y los entornos virtuales: un .venv
    # dentro del proyecto -cualquiera que lo cree en local- arrastra miles de
    # .py ajenos y hace que la huella de esa maquina no coincida nunca con la
    # del despliegue, que no los tiene.
    fuentes = [
        ruta for ruta in sorted(raiz.rglob("*.py"))
        if not any(p.startswith(".") or p in ("venv", "site-packages", "node_modules")
                   for p in ruta.relative_to(raiz).parts)
    ]
    for ruta in fuentes + sorted(raiz.glob("datos/*")):
        try:
            resumen.update(ruta.read_bytes())
        except OSError:
            continue

    return resumen.hexdigest()[:7]


if __name__ == "__main__":
    print(huella())
