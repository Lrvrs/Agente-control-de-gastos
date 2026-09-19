"""Entidad que representa el correo que el agente propone enviar."""

from dataclasses import dataclass
from typing import List

from dominio.gasto import Gasto
from dominio.veredicto import TipoVeredicto, Veredicto


@dataclass(frozen=True)
class CorreoSimulado:
    """
    Un correo redactado por el agente a partir del veredicto de un gasto.

    Es deliberadamente una simulacion: no existe ningun servidor de correo
    detras y ningun mensaje sale de la aplicacion. Lo que se muestra es la
    accion que el agente ejecutaria si estuviera autorizado a hacerlo, que es
    el punto didactico: el alumno ve la consecuencia de la decision antes de
    que ocurra, y es el quien decide si esa consecuencia es aceptable.
    """

    # Remitente. Siempre el buzon del control de gestion, nunca una persona
    # real: el correo lo emite un sistema en nombre de una funcion.
    remitente_nombre: str
    remitente_direccion: str

    # Destinatario principal y copia, ambos derivados del veredicto.
    destinatario_nombre: str
    destinatario_direccion: str
    copia_direccion: str

    # Asunto y cuerpo ya redactados.
    asunto: str
    cuerpo: str

    @property
    def tiene_copia(self) -> bool:
        """Indica si el mensaje lleva a alguien en copia."""
        return bool(self.copia_direccion)


class RedactorCorreo:
    """
    Redacta el correo correspondiente a cada veredicto.

    No se pide al modelo de lenguaje que escriba estos mensajes, y es una
    decision consciente. Una comunicacion administrativa con consecuencias
    -aprobar o denegar el reembolso de un gasto- debe ser previsible, uniforme
    entre empleados y auditable. Generarla con un modelo introduciria variacion
    donde no aporta nada y quitaria trazabilidad donde mas hace falta.

    El modelo decide; la plantilla comunica. Son dos responsabilidades
    distintas y conviene que lo sigan siendo.
    """

    # Identidad corporativa ficticia. ACME es una empresa inventada y las
    # direcciones usan el dominio reservado .example precisamente para que
    # ningun mensaje pueda dirigirse por error a un buzon real.
    DOMINIO = "acme.example"
    CONTROLLER_NOMBRE = "Marta Delgado"
    CONTROLLER_CARGO = "Business Controller"
    CONTROLLER_AREA = "Control de Gestión · ACME Iberia"

    # Buzon del responsable, al que se escala lo que no puede resolverse solo.
    RESPONSABLE_NOMBRE = "Responsable de departamento"
    RESPONSABLE_DIRECCION = f"responsable.departamento@{DOMINIO}"

    # Asunto segun el desenlace. Se mantiene corto y sin ambiguedad, porque el
    # asunto es lo unico que muchos destinatarios llegan a leer.
    ASUNTOS = {
        TipoVeredicto.APROBADO: "Gasto {id} aprobado para reembolso",
        TipoVeredicto.DENEGADO: "Gasto {id} no reembolsable",
        TipoVeredicto.PARCIAL: "Gasto {id} reembolsable parcialmente",
        TipoVeredicto.REVISION: "Gasto {id} pendiente de revisión",
    }

    # Segundo parrafo. No repite la resolucion, que ya se ha explicado en el
    # racional de apertura: indica su consecuencia practica, que es la duda
    # inmediata de quien recibe el mensaje.
    APERTURAS = {
        TipoVeredicto.APROBADO: (
            "El importe se incluirá en la próxima liquidación mensual, sin que "
            "sea necesaria ninguna gestión adicional por tu parte."
        ),
        TipoVeredicto.DENEGADO: (
            "En consecuencia, el importe no se incorporará a la liquidación "
            "del periodo."
        ),
        TipoVeredicto.PARCIAL: (
            "Se liquidará únicamente la parte cubierta por la política; el "
            "importe correspondiente a los conceptos excluidos quedará fuera "
            "de la liquidación."
        ),
        TipoVeredicto.REVISION: (
            "El apunte queda en suspenso y no se liquidará mientras no se "
            "registre una decisión al respecto."
        ),
    }

    # Parrafo de cierre segun el desenlace.
    CIERRES = {
        TipoVeredicto.APROBADO: (
            "No es necesaria ninguna acción por tu parte."
        ),
        TipoVeredicto.DENEGADO: (
            "Si consideras que concurren circunstancias excepcionales, puedes "
            "solicitar una revisión a tu responsable directo en el plazo de "
            "diez días hábiles."
        ),
        TipoVeredicto.PARCIAL: (
            "Si dispones de documentacion adicional que permita desglosar los "
            "conceptos, remítela a este mismo buzón."
        ),
        TipoVeredicto.REVISION: (
            "Una vez tomes una decisión, regístrala en el sistema para que "
            "quede constancia en el expediente del gasto."
        ),
    }

    def redactar(self, gasto: Gasto, veredicto: Veredicto) -> CorreoSimulado:
        """Compone el correo que corresponde a este gasto y este veredicto."""
        # El destinatario depende del desenlace: lo que el agente resuelve por
        # si solo se comunica al empleado; lo que no sabe resolver se escala.
        # Esa bifurcacion es la segunda decision del agente, ademas del propio
        # veredicto, y es la que lo distingue de un simple clasificador.
        if veredicto.tipo is TipoVeredicto.REVISION:
            destinatario_nombre = self.RESPONSABLE_NOMBRE
            destinatario_direccion = self.RESPONSABLE_DIRECCION
            copia = self._direccion_de(gasto.empleado)
        else:
            destinatario_nombre = gasto.empleado
            destinatario_direccion = self._direccion_de(gasto.empleado)
            # Las denegaciones y los reembolsos parciales van en copia al
            # responsable, porque afectan al presupuesto de su area.
            copia = (
                self.RESPONSABLE_DIRECCION
                if veredicto.tipo in (TipoVeredicto.DENEGADO, TipoVeredicto.PARCIAL)
                else ""
            )

        asunto = self.ASUNTOS[veredicto.tipo].format(id=gasto.identificador)

        return CorreoSimulado(
            remitente_nombre=f"{self.CONTROLLER_NOMBRE} · {self.CONTROLLER_CARGO}",
            remitente_direccion=f"control.gestion@{self.DOMINIO}",
            destinatario_nombre=destinatario_nombre,
            destinatario_direccion=destinatario_direccion,
            copia_direccion=copia,
            asunto=asunto,
            cuerpo=self._componer_cuerpo(gasto, veredicto, destinatario_nombre),
        )

    def _componer_cuerpo(
        self, gasto: Gasto, veredicto: Veredicto, destinatario: str
    ) -> str:
        """
        Redacta el cuerpo completo del mensaje.

        El orden de los bloques no es casual. El mensaje abre con el razonamiento
        que ha llevado a la resolucion, antes que con cualquier otra cosa, porque
        es lo unico que el destinatario necesita leer para entender que ha pasado
        y por que. El detalle del gasto y el resto de la informacion van despues,
        como respaldo de esa explicacion y no como preambulo de ella.

        Esa decision tiene ademas una lectura de gobernanza: un sistema que
        comunica primero su criterio y luego los datos se puede auditar leyendo
        un parrafo, mientras que uno que entierra el motivo al final obliga a
        reconstruirlo.
        """
        # El saludo usa solo el nombre de pila cuando se dirige a una persona.
        nombre_pila = destinatario.split()[0] if destinatario else "Hola"

        # Parrafo de racional. Enlaza en prosa la resolucion, la clausula
        # aplicada y el motivo concreto, de modo que quien lo reciba entienda
        # la decision sin consultar ninguna tabla.
        racional = self._componer_racional(gasto, veredicto)

        # El bloque de detalle reproduce el apunte tal y como se presento. Es
        # lo que permite al destinatario identificar el gasto sin abrir ningun
        # sistema, y deja constancia de sobre que datos se decidio.
        justificante = "Sí" if gasto.tiene_justificante else "No"
        detalle = (
            f"    Referencia:    {gasto.identificador}\n"
            f"    Fecha:         {gasto.fecha}\n"
            f"    Concepto:      {gasto.descripcion}\n"
            f"    Categoría:     {gasto.categoria}\n"
            f"    Ciudad:        {gasto.ciudad}\n"
            f"    Importe:       {self._formatear_importe(gasto.importe, gasto.moneda)}\n"
            f"    Justificante:  {justificante}"
        )

        partes: List[str] = [
            f"Estimado/a {nombre_pila}:",
            "",
            racional,
            "",
            self.APERTURAS[veredicto.tipo],
            "",
            "DETALLE DEL GASTO",
            detalle,
            "",
            self.CIERRES[veredicto.tipo],
            "",
            "Un saludo,",
            "",
            self.CONTROLLER_NOMBRE,
            f"{self.CONTROLLER_CARGO} · {self.CONTROLLER_AREA}",
            f"control.gestion@{self.DOMINIO}",
        ]
        return "\n".join(partes)

    def _componer_racional(self, gasto: Gasto, veredicto: Veredicto) -> str:
        """
        Redacta el parrafo de apertura con el razonamiento de la resolucion.

        Se construye en prosa a partir de tres piezas: que gasto es, que se ha
        resuelto y por que. La cita de la clausula va integrada en la frase, no
        como referencia suelta al final, porque el objetivo es que se lea como
        una explicacion y no como un codigo administrativo.
        """
        # Verbo acorde a la resolucion. Evita la formula neutra "se ha
        # resuelto", que obliga al lector a deducir el sentido de la decision.
        verbos = {
            TipoVeredicto.APROBADO: "se aprueba",
            TipoVeredicto.DENEGADO: "no puede aprobarse",
            TipoVeredicto.PARCIAL: "se aprueba solo en parte",
            TipoVeredicto.REVISION: "no ha podido resolverse de forma automática",
        }
        verbo = verbos[veredicto.tipo]

        # Referencia a la clausula, omitida cuando el agente no supo indicar
        # ninguna: es preferible una frase mas corta que una cita vacia.
        clausula = (veredicto.clausula or "").strip()
        if clausula and clausula.lower() not in ("sin indicar", "-", "none"):
            referencia = f", en aplicación de la cláusula {clausula} de la política de viajes,"
        else:
            referencia = ""

        # El motivo se incorpora tal cual lo redacto el agente, garantizando
        # que termina en punto para que el parrafo cierre correctamente.
        motivo = veredicto.motivo.strip()
        if motivo and not motivo.endswith("."):
            motivo += "."

        return (
            f"Tras revisar el gasto {gasto.identificador}, de "
            f"{self._formatear_importe(gasto.importe, gasto.moneda)} y con fecha "
            f"{gasto.fecha}, "
            f"correspondiente a «{gasto.descripcion}»{referencia} "
            f"{verbo}. {motivo}"
        )

    def _formatear_importe(self, importe: float, moneda: str) -> str:
        """Devuelve el importe con el formato numerico espanol."""
        # Python formatea a la inglesa, asi que se intercambian los separadores
        # usando una marca intermedia para no pisar el resultado a mitad.
        ingles = f"{importe:,.2f}"
        espanol = ingles.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
        return f"{espanol} {moneda}"

    def _direccion_de(self, nombre: str) -> str:
        """Construye la direccion de correo a partir del nombre del empleado."""
        # Convencion habitual: nombre.apellido@dominio, en minusculas y sin
        # acentos. Las direcciones son ficticias, asi que basta con que sean
        # coherentes y verosimiles.
        sin_acentos = (
            nombre.lower()
            .replace("á", "a").replace("é", "e").replace("í", "i")
            .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
        )
        partes = [p for p in sin_acentos.split() if p]
        usuario = ".".join(partes[:2]) if partes else "empleado"
        return f"{usuario}@{self.DOMINIO}"
