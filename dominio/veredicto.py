"""Entidades que representan el resultado de evaluar un gasto."""

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Dict, List


class TipoVeredicto(str, Enum):
    """
    Los cuatro desenlaces posibles para un gasto.

    Hereda de `str` para que el valor se pueda serializar a JSON y comparar con
    el texto que devuelve el modelo sin conversiones intermedias.
    """

    # El gasto cumple la politica y puede aprobarse.
    APROBADO = "APROBADO"

    # El gasto incumple alguna clausula concreta de la politica.
    DENEGADO = "DENEGADO"

    # El gasto cumple en parte: hay un importe o un concepto separable que no
    # es reembolsable, pero el resto si lo es.
    PARCIAL = "PARCIAL"

    # No hay informacion suficiente para decidir. Es el veredicto que debe
    # emitirse antes que inventar: su presencia es una senal de buen criterio.
    REVISION = "REVISION"

    @classmethod
    def desde_texto(cls, texto: str) -> "TipoVeredicto":
        """
        Convierte el texto devuelto por el modelo en un valor del enumerado.

        Cualquier valor no reconocido se degrada a REVISION en lugar de provocar
        un error: si el modelo responde algo inesperado, lo correcto es pedir
        supervision humana, no romper la pantalla del alumno.
        """
        # Se normaliza a mayusculas y sin espacios para tolerar "aprobado ".
        candidato = (texto or "").strip().upper()
        for miembro in cls:
            if miembro.value == candidato:
                return miembro
        return cls.REVISION


@dataclass(frozen=True)
class Veredicto:
    """Decision del agente sobre un gasto concreto, con su justificacion."""

    # Identificador del gasto al que corresponde este veredicto.
    identificador_gasto: str

    # Decision emitida.
    tipo: TipoVeredicto

    # Numero o nombre de la clausula de la politica en la que se apoya.
    # Es el mecanismo de trazabilidad: sin clausula, el veredicto no es auditable.
    clausula: str

    # Explicacion breve en lenguaje natural, de una o dos frases.
    motivo: str

    # Datos del evento invocado por el gasto, cuando lo hay y el agente ha
    # conseguido verificarlo. Se recogen como campos separados y no dentro del
    # motivo por una razon concreta: la discrepancia entre la fecha del apunte y
    # el periodo del evento es el nucleo de la resolucion en estos casos, y
    # dejarla dentro de una frase libre significaria que su redaccion depende de
    # lo que el modelo decida escribir cada vez. Con los datos separados, la
    # aplicacion compone siempre la misma frase con el mismo rigor.
    evento: str = ""
    evento_desde: str = ""
    evento_hasta: str = ""

    @property
    def tiene_periodo_de_evento(self) -> bool:
        """Indica si consta el evento invocado y sus fechas de celebracion."""
        # Hacen falta las tres piezas: sin el nombre no se puede nombrar y sin
        # ambas fechas no se puede describir el periodo.
        return bool(
            self.evento.strip()
            and self.evento_desde.strip()
            and self.evento_hasta.strip()
        )

    @property
    def es_favorable(self) -> bool:
        """Indica si el gasto sale adelante sin objeciones."""
        return self.tipo is TipoVeredicto.APROBADO

    @property
    def requiere_persona(self) -> bool:
        """
        Indica si este veredicto debe pasar por una persona antes de cerrarse.

        Se agrupan REVISION y PARCIAL porque en ambos casos el agente esta
        declarando que su decision no es completa, que es exactamente el punto
        en que la supervision humana aporta valor.
        """
        return self.tipo in (TipoVeredicto.REVISION, TipoVeredicto.PARCIAL)


@dataclass
class ResultadoEvaluacion:
    """
    Resultado completo de una ejecucion: un veredicto por cada gasto.

    Se guarda ademas el contexto de la ejecucion -que politica se uso, si vino
    de la cache- porque la interfaz necesita comparar ejecuciones sucesivas para
    resaltar que ha cambiado respecto a la anterior.
    """

    # Veredictos indexados por identificador de gasto, para acceso directo.
    veredictos: Dict[str, Veredicto] = field(default_factory=dict)

    # Huella de la politica con la que se genero este resultado.
    huella_politica: str = ""

    # Indica si el resultado se sirvio desde la cache en lugar de llamar al modelo.
    procede_de_cache: bool = False

    # Identificador del modelo que lo genero, para mostrarlo como trazabilidad.
    modelo_utilizado: str = ""

    def anadir(self, veredicto: Veredicto) -> None:
        """Incorpora un veredicto al resultado."""
        # Si llegan dos veredictos para el mismo gasto, prevalece el ultimo.
        # Es una situacion anomala del modelo y no merece detener la ejecucion.
        self.veredictos[veredicto.identificador_gasto] = veredicto

    def obtener(self, identificador_gasto: str) -> Veredicto | None:
        """Devuelve el veredicto de un gasto, o None si el modelo lo omitio."""
        return self.veredictos.get(identificador_gasto)

    def recuento_por_tipo(self) -> Dict[TipoVeredicto, int]:
        """Cuenta cuantos gastos han caido en cada tipo de veredicto."""
        # Se inicializan todos los tipos a cero para que la interfaz pueda
        # pintar siempre las cuatro cifras, incluidas las que valen cero.
        recuento: Dict[TipoVeredicto, int] = {tipo: 0 for tipo in TipoVeredicto}
        for veredicto in self.veredictos.values():
            recuento[veredicto.tipo] += 1
        return recuento

    def identificadores_que_cambian(self, anterior: "ResultadoEvaluacion | None") -> List[str]:
        """
        Devuelve los gastos cuyo veredicto difiere respecto a una ejecucion previa.

        Este metodo sostiene el momento didactico central de la aplicacion:
        el alumno modifica una linea de la politica y ve resaltado, exactamente,
        que decisiones ha cambiado con ello.
        """
        # En la primera ejecucion no hay nada con que comparar.
        if anterior is None:
            return []

        cambiados: List[str] = []
        for identificador, veredicto in self.veredictos.items():
            veredicto_previo = anterior.obtener(identificador)
            # Un gasto cuenta como cambiado si no existia antes o si su tipo
            # de veredicto es distinto. Un cambio de redaccion en el motivo no
            # se considera un cambio de decision.
            if veredicto_previo is None or veredicto_previo.tipo is not veredicto.tipo:
                cambiados.append(identificador)
        return cambiados


def firma_estructural() -> str:
    """
    Devuelve una huella de la forma que tienen hoy las entidades del veredicto.

    Existe para resolver un problema propio de las aplicaciones que se
    redespliegan en caliente. Streamlit conserva entre ejecuciones tanto el
    estado de sesion como los recursos cacheados, de modo que tras un cambio de
    codigo pueden convivir objetos creados por la version anterior con codigo
    de la nueva. Si entretanto se ha anadido un campo, leerlo sobre un objeto
    viejo lanza un AttributeError y la pantalla se rompe, cosa que ocurriria
    delante de la clase.

    Incluyendo esta firma en la clave de los recursos cacheados y comprobandola
    sobre lo que hay en sesion, cualquier cambio en la estructura invalida
    automaticamente lo anterior. No hay que acordarse de subir ningun numero de
    version a mano, que es justo lo que nadie recuerda hacer.
    """
    return ",".join(campo.name for campo in fields(Veredicto))
