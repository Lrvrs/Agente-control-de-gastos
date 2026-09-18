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

    # Parrafo de apertura segun el desenlace.
    APERTURAS = {
        TipoVeredicto.APROBADO: (
            "Te confirmamos que el gasto que se detalla a continuacion ha sido "
            "revisado y cumple la política de viajes vigente. Se tramitará su "
            "reembolso en la próxima liquidación mensual."
        ),
        TipoVeredicto.DENEGADO: (
            "Te informamos de que el gasto que se detalla a continuacion no "
            "puede ser reembolsado, al no ajustarse a la política de viajes "
            "vigente."
        ),
        TipoVeredicto.PARCIAL: (
            "Te informamos de que el gasto que se detalla a continuacion es "
            "reembolsable solo en parte. El importe correspondiente a los "
            "conceptos no cubiertos por la política quedará excluido de la "
            "liquidación."
        ),
        TipoVeredicto.REVISION: (
            "Elevamos a tu criterio el gasto que se detalla a continuacion. La "
            "información disponible no permite determinar con certeza si se "
            "ajusta a la política de viajes, por lo que requiere una decisión "
            "por tu parte."
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
        """Redacta el cuerpo completo del mensaje."""
        # El saludo usa solo el nombre de pila cuando se dirige a una persona.
        nombre_pila = destinatario.split()[0] if destinatario else "Hola"

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
            f"    Importe:       {gasto.importe:.2f} {gasto.moneda}\n"
            f"    Justificante:  {justificante}"
        )

        # La motivacion cita la clausula aplicada. Sin esa referencia el
        # mensaje seria una decision sin fundamento explicito, que es
        # justamente lo que una politica de gobernanza debe impedir.
        motivacion = (
            f"    Resolución:    {veredicto.tipo.value}\n"
            f"    Cláusula:      {veredicto.clausula}\n"
            f"    Motivo:        {veredicto.motivo}"
        )

        partes: List[str] = [
            f"Estimado/a {nombre_pila}:",
            "",
            self.APERTURAS[veredicto.tipo],
            "",
            "DETALLE DEL GASTO",
            detalle,
            "",
            "RESOLUCIÓN",
            motivacion,
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
