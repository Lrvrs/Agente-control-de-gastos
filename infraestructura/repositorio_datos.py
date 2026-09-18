"""Carga de los datos de partida desde el sistema de ficheros."""

import csv
from pathlib import Path

from dominio.gasto import ConjuntoGastos, Gasto
from dominio.politica import Politica


class RepositorioDatos:
    """
    Acceso de solo lectura a los ficheros de datos incluidos en el repositorio.

    Se aisla aqui para que el resto de la aplicacion no sepa nada de rutas ni de
    formatos: si manana los gastos vinieran de una hoja de calculo o de una base
    de datos, solo cambiaria esta clase.
    """

    # Nombres de los ficheros de partida. Se declaran como constantes de clase
    # para que la ruta no quede dispersa en varias cadenas literales.
    FICHERO_GASTOS = "gastos_demo.csv"
    FICHERO_POLITICA = "politica_viajes.md"

    def __init__(self, carpeta_datos: Path | None = None) -> None:
        """
        Fija la carpeta de datos.

        Por defecto se calcula relativa a este fichero y no al directorio de
        trabajo, porque Streamlit Community Cloud no garantiza cual es el
        directorio actual al arrancar la aplicacion.
        """
        if carpeta_datos is None:
            # padre de infraestructura/ -> raiz del proyecto -> datos/
            carpeta_datos = Path(__file__).resolve().parent.parent / "datos"
        self._carpeta = carpeta_datos

    def cargar_gastos(self) -> ConjuntoGastos:
        """Lee el CSV de gastos de ejemplo y devuelve el conjunto de dominio."""
        ruta = self._carpeta / self.FICHERO_GASTOS

        # Se abre con utf-8-sig para tolerar el marcador de orden de bytes que
        # Excel anade al exportar a CSV en Windows, un origen habitual de fallos.
        with ruta.open("r", encoding="utf-8-sig", newline="") as fichero:
            lector = csv.DictReader(fichero)
            gastos = [self._fila_a_gasto(fila) for fila in lector]

        return ConjuntoGastos(gastos)

    def cargar_gastos_desde_texto(self, contenido: str) -> ConjuntoGastos:
        """
        Construye el conjunto de gastos a partir del contenido de un CSV subido.

        Se separa de `cargar_gastos` porque el fichero que sube un alumno no
        esta en disco: llega en memoria desde el navegador.
        """
        # `splitlines` normaliza los tres estilos de salto de linea posibles,
        # de modo que da igual si el CSV se genero en Windows, macOS o Linux.
        lector = csv.DictReader(contenido.splitlines())
        gastos = [self._fila_a_gasto(fila) for fila in lector]
        return ConjuntoGastos(gastos)

    def cargar_politica(self) -> Politica:
        """Lee la politica de viajes por defecto."""
        ruta = self._carpeta / self.FICHERO_POLITICA
        return Politica(texto=ruta.read_text(encoding="utf-8"))

    def _fila_a_gasto(self, fila: dict) -> Gasto:
        """
        Convierte una fila del CSV en una entidad Gasto.

        Cada campo se limpia de espacios sobrantes porque un CSV editado a mano
        en una hoja de calculo suele traerlos y provocarian comparaciones
        fallidas mas adelante.
        """
        # El importe se convierte admitiendo la coma decimal, que es lo que
        # escribe una hoja de calculo configurada en espanol.
        importe_bruto = str(fila.get("importe", "0")).strip().replace(",", ".")
        try:
            importe = float(importe_bruto)
        except ValueError:
            # Un importe ilegible se registra como cero: el modelo lo vera y
            # deberia emitir REVISION, que es el comportamiento deseado.
            importe = 0.0

        return Gasto(
            identificador=str(fila.get("id", "")).strip(),
            empleado=str(fila.get("empleado", "")).strip(),
            fecha=str(fila.get("fecha", "")).strip(),
            categoria=str(fila.get("categoria", "")).strip(),
            ciudad=str(fila.get("ciudad", "")).strip(),
            importe=importe,
            moneda=str(fila.get("moneda", "EUR")).strip().upper(),
            descripcion=str(fila.get("descripcion", "")).strip(),
            justificante=str(fila.get("justificante", "N")).strip(),
        )
