"""Entidades que representan el resultado de evaluar un gasto."""

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Dict, List


# Raices con las que se reconoce cada tipo de veredicto cuando el modelo no
# devuelve la palabra exacta. Vive fuera del enumerado y no dentro de el porque
# Enum convierte en miembro cualquier atributo de clase que no sea un
# descriptor: declarada dentro, esta tupla se intentaba registrar como un quinto
# veredicto y la clase no llegaba a construirse.
#
# El orden importa y no es alfabetico: "APROBADO PARCIALMENTE" contiene las
# raices de dos tipos, y de los dos el que describe el caso es PARCIAL, asi que
# se comprueba antes.
RAICES_DE_VEREDICTO = (
    ("PARCIAL", ("PARCIAL",)),
    ("DENEGADO", ("DENEG", "RECHAZ", "NO REEMBOLS")),
    ("APROBADO", ("APROB", "ACEPT", "PROCEDE")),
    ("REVISION", ("REVIS", "ESCAL", "PENDIENTE", "SUPERVIS")),
)


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

        Se admite algo mas que la coincidencia exacta, y es a proposito. Aunque
        el prompt pide una de cuatro palabras, un modelo matiza con facilidad:
        devuelve "APROBADO CON EXCEPCIÓN" cuando el gasto procede por una
        excepcion de la politica, o "aprobado" en minusculas. Con coincidencia
        exacta todas esas respuestas caian en REVISION, y el efecto era el peor
        posible: el motivo explicaba que el gasto estaba dentro de limites
        mientras la aplicacion lo trataba como no resuelto, de modo que el
        alumno que lo aprobaba recibia un "incorrecto" contradicho por el texto
        que tenia justo debajo.

        Lo que no se reconoce sigue degradandose a REVISION, que es la salida
        prudente: pedir supervision humana en lugar de romper la pantalla.
        """
        candidato = (texto or "").strip().upper()

        # Coincidencia exacta primero: es el caso normal y no conviene que una
        # heuristica se interponga cuando el modelo ha respondido bien.
        for miembro in cls:
            if miembro.value == candidato:
                return miembro

        # Se retiran los acentos para que "REVISIÓN" case con la raiz "REVIS".
        sin_acentos = candidato.translate(
            str.maketrans("ÁÉÍÓÚÜÑ", "AEIOUUN")
        )

        for nombre, raices in RAICES_DE_VEREDICTO:
            if any(raiz in sin_acentos for raiz in raices):
                return cls(nombre)

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
    def decision_esperada(self) -> str:
        """
        Respuesta que se considera acertada para este veredicto.

        La correccion del ejercicio es binaria, asi que los cuatro tipos de
        veredicto tienen que caer de un lado o del otro. Solo APROBADO admite
        que el gasto se pague tal como viene. PARCIAL sostiene que una parte no
        es reembolsable y REVISION que el caso no puede cerrarse con los datos
        disponibles: en ambos, dar el gasto por bueno y mandarlo a pagar seria
        un error, de modo que la respuesta correcta es denegarlo y devolverlo a
        quien lo presento.
        """
        if self.tipo is TipoVeredicto.APROBADO:
            return "APROBADO"

        return "DENEGADO"


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


class Correccion(str, Enum):
    """
    Resultado de contrastar la decisión del alumno con la del agente.

    Se declara en el dominio y no en la interfaz porque es una regla del
    ejercicio, no una cuestión de presentación: decide qué se considera acertar
    y qué no, y conviene que esa definición esté en un solo sitio y pueda
    probarse sin levantar una pantalla.
    """

    # El alumno resolvió igual que el agente.
    ACERTADA = "ACERTADA"

    # El alumno resolvió lo contrario de lo que el agente había concluido.
    FALLADA = "FALLADA"



def corregir_decision(veredicto: Veredicto, decision: str) -> Correccion | None:
    """
    Contrasta la decisión del alumno con la resolución del agente.

    Devuelve None cuando el alumno todavía no se ha pronunciado, porque
    entonces no hay nada que corregir.

    La correccion es binaria a proposito. El agente maneja cuatro tipos de
    veredicto, pero el alumno solo dispone de dos botones, y el ejercicio
    consiste en decidir si el gasto se paga o no se paga. Cada veredicto se
    traduce por tanto a la respuesta que se espera de una persona que lo
    supervise, que es lo que devuelve decision_esperada.
    """
    if not decision:
        return None

    if decision == veredicto.decision_esperada:
        return Correccion.ACERTADA

    return Correccion.FALLADA
