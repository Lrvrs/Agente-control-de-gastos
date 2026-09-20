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
    RESPONSABLE_NOMBRE = "Carlos Mena"
    RESPONSABLE_DIRECCION = f"carlos.mena@{DOMINIO}"

    # Asunto segun el desenlace. Se mantiene corto y sin ambiguedad, porque el
    # asunto es lo unico que muchos destinatarios llegan a leer.
    ASUNTOS = {
        TipoVeredicto.APROBADO: "Gasto {id} aprobado para reembolso",
        TipoVeredicto.DENEGADO: "Gasto {id} no reembolsable",
        TipoVeredicto.PARCIAL: "Gasto {id} reembolsable parcialmente",
        TipoVeredicto.REVISION: "Gasto {id} pendiente de revisión",
    }

    # Primera frase del mensaje, que abre el parrafo de explicacion. A partir
    # de aqui el registro es el de una persona que ha revisado el apunte y
    # cuenta lo que ha visto, no el de un sistema que notifica una resolucion.
    APERTURAS = {
        TipoVeredicto.APROBADO: "He revisado tu gasto {id} y está todo correcto.",
        TipoVeredicto.DENEGADO: (
            "He estado revisando tu gasto {id} y me temo que no voy a poder "
            "reembolsártelo."
        ),
        TipoVeredicto.PARCIAL: (
            "He revisado tu gasto {id} y puedo reembolsarte una parte, pero no "
            "el total."
        ),
        TipoVeredicto.REVISION: (
            "Te paso el gasto {id} porque no consigo resolverlo por mi cuenta."
        ),
    }

    # Segundo parrafo: que ocurre ahora y que se espera de quien lee. Cierra la
    # duda inmediata del destinatario en lugar de repetir la resolucion.
    PETICIONES = {
        TipoVeredicto.APROBADO: (
            "Lo incluyo en la liquidación de este mes, así que no tienes que "
            "hacer nada."
        ),
        TipoVeredicto.DENEGADO: (
            "De momento lo dejo fuera de la liquidación. Si crees que hay algo "
            "que se me escapa, dímelo y lo volvemos a mirar."
        ),
        TipoVeredicto.PARCIAL: (
            "Liquido la parte que sí entra. Si puedes desglosarme el resto, "
            "mándamelo y lo ajusto."
        ),
        TipoVeredicto.REVISION: (
            "¿Puedes echarle un vistazo y decirme cómo lo dejamos? Mientras "
            "tanto lo mantengo en suspenso."
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
        Redacta el cuerpo del mensaje.

        La estructura responde a como lee una persona. Arriba, en dos parrafos
        de lenguaje corriente, va lo unico que el destinatario necesita saber:
        que se ha mirado, que se ha encontrado y que pasa ahora. Abajo, separado
        y despues de la firma, queda el bloque formal con las referencias.

        El orden no es una preferencia estetica. Un mensaje que empieza por una
        ficha de datos obliga a reconstruir el razonamiento; uno que empieza
        explicando se entiende de una lectura. Y como el proposito de la
        aplicacion es ensenar a supervisar decisiones automaticas, el mensaje
        que produce deberia ser el primero en ponerselo facil a quien supervisa.
        """
        # Saludo con el nombre de pila. El registro es el de un companero que
        # escribe, no el de un sistema que notifica.
        nombre_pila = destinatario.split()[0] if destinatario else "Hola"

        partes: List[str] = [
            f"Hola {nombre_pila}:",
            "",
            self._componer_explicacion(gasto, veredicto),
            "",
            self.PETICIONES[veredicto.tipo],
            "",
            "Un saludo,",
            self.CONTROLLER_NOMBRE,
            f"{self.CONTROLLER_CARGO} · {self.CONTROLLER_AREA}",
            "",
            "",
            # Separador que marca el cambio de registro: lo de arriba se lee,
            # lo de abajo se consulta.
            "—" * 46,
            "DATOS DEL APUNTE",
            self._componer_ficha(gasto, veredicto),
        ]
        return "\n".join(partes)

    def _componer_explicacion(self, gasto: Gasto, veredicto: Veredicto) -> str:
        """
        Redacta el parrafo en el que se cuenta que se ha visto.

        Encadena la apertura con el motivo que elaboro el agente. Cuando ese
        motivo contiene una discrepancia concreta -una fecha que no encaja con
        el periodo de un evento, una empresa que no aparece por ningun lado-, es
        precisamente eso lo que queda en la primera linea del mensaje, que es
        donde tiene que estar.
        """
        apertura = self.APERTURAS[veredicto.tipo].format(id=gasto.identificador)

        # El motivo llega tal y como lo redacto el agente, y hay que acoplarlo
        # a la frase anterior: el modelo suele empezarlo en minuscula, de modo
        # que al encadenarlo tras un punto quedaria mal escrito. Se ajusta la
        # primera letra sin tocar el resto, para no alterar lo que redacto.
        motivo = veredicto.motivo.strip()
        if motivo:
            motivo = motivo[0].upper() + motivo[1:]

        # Se asegura el punto final para que el parrafo cierre bien.
        if motivo and not motivo.endswith((".", "?", "!")):
            motivo += "."

        # Sin motivo se recurre a una formula neutra antes que dejar la frase
        # colgando, aunque es una situacion que el analizador ya evita.
        if not motivo:
            motivo = "No consta el detalle de la revisión."

        return f"{apertura} {motivo}"

    def _componer_ficha(self, gasto: Gasto, veredicto: Veredicto) -> str:
        """
        Compone el bloque formal que cierra el mensaje.

        Reune en un solo sitio todo lo que hace falta para auditar la decision:
        el apunte tal y como se presento, la resolucion y la clausula aplicada.
        Va al final porque es material de consulta, no de lectura.
        """
        justificante = "Sí" if gasto.tiene_justificante else "No"

        # La clausula puede no constar cuando el agente no supo identificarla.
        # Se declara como tal en lugar de dejar el campo vacio, porque la
        # ausencia de referencia normativa es en si misma un dato relevante.
        clausula = (veredicto.clausula or "").strip()
        if not clausula or clausula.lower() in ("sin indicar", "-", "none"):
            clausula = "no identificada"

        return (
            f"Referencia:    {gasto.identificador}\n"
            f"Empleado:      {gasto.empleado}\n"
            f"Fecha:         {gasto.fecha}\n"
            f"Concepto:      {gasto.descripcion}\n"
            f"Categoría:     {gasto.categoria}\n"
            f"Ciudad:        {gasto.ciudad}\n"
            f"Importe:       {self._formatear_importe(gasto.importe, gasto.moneda)}\n"
            f"Justificante:  {justificante}\n"
            f"Resolución:    {veredicto.tipo.value}\n"
            f"Cláusula:      {clausula}"
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
