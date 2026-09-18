"""Entidades que representan un gasto individual y el conjunto de gastos."""

from dataclasses import dataclass
from typing import Iterator, List


@dataclass(frozen=True)
class Gasto:
    """
    Un unico apunte de gasto tal y como llega del fichero CSV.

    Se declara como `frozen` (inmutable) de forma deliberada: un gasto es un
    hecho ya ocurrido y ningun punto de la aplicacion deberia poder alterarlo.
    Si se necesita una version corregida, se crea un objeto nuevo.
    """

    # Identificador corto y legible (G-001). Es la referencia que el modelo
    # debe devolver en su respuesta para poder casar veredicto con gasto.
    identificador: str

    # Persona que presenta el gasto. Solo se usa para mostrar en pantalla.
    empleado: str

    # Fecha en que se produjo el gasto, en formato ISO (AAAA-MM-DD).
    # Se conserva como texto porque la politica de antiguedad la evalua el
    # modelo de lenguaje, no el codigo, y asi se evita una conversion inutil.
    fecha: str

    # Categoria declarada: alojamiento, dietas, transporte u otros.
    categoria: str

    # Ciudad donde se produjo el gasto. Es determinante porque la politica
    # establece limites distintos para algunas capitales.
    ciudad: str

    # Importe numerico del gasto.
    importe: float

    # Divisa del importe. La mayoria son euros, pero se admiten otras a
    # proposito: obligan al modelo a decidir que hacer con una conversion.
    moneda: str

    # Descripcion libre escrita por el empleado. Es el campo mas informativo
    # y el que obliga a razonar mas alla de comparar numeros.
    descripcion: str

    # Indica si se aporto justificante: "S" o "N".
    justificante: str

    @property
    def tiene_justificante(self) -> bool:
        """Traduce la marca textual del CSV a un valor logico."""
        # Se normaliza a mayusculas para tolerar "s", "S" o " S " en el fichero.
        return self.justificante.strip().upper() == "S"

    def a_linea_para_modelo(self) -> str:
        """
        Devuelve el gasto en una sola linea compacta para incluirlo en el prompt.

        El formato importa por economia: cada gasto ocupa unos 25 tokens en vez
        de los 60 que costaria un JSON indentado. Con doce gastos la diferencia
        es pequena, pero el mismo prompt debe seguir siendo viable si algun dia
        se evaluan cincuenta.
        """
        # Se marca el justificante como SI/NO para que sea inequivoco en el texto.
        marca_justificante = "SI" if self.tiene_justificante else "NO"
        return (
            f"{self.identificador} | {self.fecha} | {self.empleado} | "
            f"{self.categoria} | {self.ciudad} | {self.importe:.2f} {self.moneda} | "
            f"justificante={marca_justificante} | {self.descripcion}"
        )


class ConjuntoGastos:
    """
    Coleccion ordenada de gastos con las operaciones que necesita la aplicacion.

    Envolver la lista en una clase, en lugar de pasear una `list` por todo el
    codigo, permite anadir despues reglas de conjunto -detectar duplicados,
    agrupar por empleado- sin modificar a quien la consume.
    """

    def __init__(self, gastos: List[Gasto]) -> None:
        """Guarda una copia defensiva para que nadie altere la lista original."""
        self._gastos: List[Gasto] = list(gastos)

    def __len__(self) -> int:
        """Numero de gastos del conjunto."""
        return len(self._gastos)

    def __iter__(self) -> Iterator[Gasto]:
        """Permite recorrer el conjunto con un bucle `for` de forma natural."""
        return iter(self._gastos)

    @property
    def identificadores(self) -> List[str]:
        """Lista de identificadores, usada para validar la respuesta del modelo."""
        return [gasto.identificador for gasto in self._gastos]

    def buscar(self, identificador: str) -> Gasto | None:
        """
        Localiza un gasto por su identificador.

        Devuelve `None` en lugar de lanzar una excepcion porque el caso de no
        encontrarlo es esperable: el modelo puede inventarse un identificador y
        la aplicacion debe poder descartarlo con elegancia.
        """
        # Busqueda lineal: con docenas de gastos es mas que suficiente y evita
        # mantener un indice que habria que sincronizar.
        for gasto in self._gastos:
            if gasto.identificador == identificador:
                return gasto
        return None

    def a_bloque_para_modelo(self) -> str:
        """Serializa todos los gastos como un bloque de texto para el prompt."""
        # Una linea por gasto, en el mismo orden que el fichero de origen.
        return "\n".join(gasto.a_linea_para_modelo() for gasto in self._gastos)

    def importe_total(self) -> float:
        """
        Suma de los importes, sin convertir divisas.

        La ausencia de conversion es intencionada: el total se muestra como dato
        orientativo y convertir aqui daria una falsa sensacion de exactitud.
        """
        return sum(gasto.importe for gasto in self._gastos)
