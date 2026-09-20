"""Entidad que representa el correo que el agente propone enviar."""

from dataclasses import dataclass
from typing import List

from dominio.gasto import Gasto
from dominio.veredicto import TipoVeredicto, Veredicto


# Nombres de los meses. Se declaran aqui y no se recurre a la localizacion del
# sistema porque el servidor donde corre la aplicacion no tiene por que tener el
# idioma espanol instalado, y lo habitual es que no lo tenga.
MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def formatear_fecha(fecha_iso: str) -> str:
    """Convierte una fecha ISO en su forma escrita en castellano."""
    # Se admite cualquier texto: si no tiene el formato esperado se devuelve tal
    # cual, que es preferible a perder el dato.
    partes = fecha_iso.strip().split("-")
    if len(partes) != 3:
        return fecha_iso.strip()

    try:
        anio, mes, dia = int(partes[0]), int(partes[1]), int(partes[2])
    except ValueError:
        return fecha_iso.strip()

    if not 1 <= mes <= 12:
        return fecha_iso.strip()

    return f"{dia} de {MESES[mes - 1]} de {anio}"


def formatear_importe(importe: float, moneda: str) -> str:
    """Devuelve el importe con el formato numerico espanol."""
    # Python formatea a la inglesa, asi que se intercambian los separadores
    # usando una marca intermedia para no pisar el resultado a mitad.
    ingles = f"{importe:,.2f}"
    espanol = ingles.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{espanol} {moneda}"


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

    # Primera frase del mensaje, que abre el parrafo de explicacion. El
    # registro es el de un profesional que ha revisado el apunte y comunica el
    # resultado: directo y sin rodeos, pero sin la familiaridad de una nota
    # interna entre companeros. Es una comunicacion con consecuencias
    # economicas y su tono debe corresponderse con eso.
    APERTURAS = {
        TipoVeredicto.APROBADO: (
            "He revisado tu gasto {id} y es conforme a la política."
        ),
        TipoVeredicto.DENEGADO: (
            "He revisado tu gasto {id} y no procede su reembolso."
        ),
        TipoVeredicto.PARCIAL: (
            "He revisado tu gasto {id} y solo procede el reembolso de una "
            "parte del importe."
        ),
        TipoVeredicto.REVISION: (
            "Te traslado el gasto {id} porque no dispongo de elementos "
            "suficientes para resolverlo."
        ),
    }

    # Segundo parrafo: que ocurre ahora y que se espera de quien lee. Cierra la
    # duda inmediata del destinatario sin repetir la resolucion.
    PETICIONES = {
        TipoVeredicto.APROBADO: (
            "Queda incluido en la liquidación de este mes. No es necesaria "
            "ninguna gestión por tu parte."
        ),
        TipoVeredicto.DENEGADO: (
            "El importe queda excluido de la liquidación. Si dispones de "
            "información adicional que justifique el gasto, remítemela y lo "
            "revisaré de nuevo."
        ),
        TipoVeredicto.PARCIAL: (
            "Liquidaré la parte que cumple la política. Si puedes remitirme el "
            "desglose del resto, lo ajustaré."
        ),
        TipoVeredicto.REVISION: (
            "Te agradecería que lo valoraras y me indicaras cómo proceder. "
            "Mientras tanto queda en suspenso."
        ),
    }

    def redactar(
        self,
        gasto: Gasto,
        veredicto: Veredicto,
        explicacion: str = "",
    ) -> CorreoSimulado:
        """
        Compone el correo que corresponde a este gasto y este veredicto.

        Cuando se recibe una explicacion ya redactada -normalmente la que ha
        escrito el modelo- se utiliza en lugar de las plantillas fijas. El resto
        del mensaje, que es lo que debe ser exacto y uniforme, lo sigue
        componiendo esta clase: el saludo, la firma y la ficha del pie.
        """
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
            cuerpo=self._componer_cuerpo(
                gasto, veredicto, destinatario_nombre, explicacion
            ),
        )

    def nombre_destinatario(self, gasto: Gasto, veredicto: Veredicto) -> str:
        """
        Devuelve a quien se dirige el correo de este veredicto.

        Se expone como metodo publico porque quien redacta el cuerpo necesita
        saberlo: no se escribe igual a quien presento el gasto que al
        responsable al que se eleva para que decida.
        """
        if veredicto.tipo is TipoVeredicto.REVISION:
            return self.RESPONSABLE_NOMBRE
        return gasto.empleado

    def _componer_cuerpo(
        self,
        gasto: Gasto,
        veredicto: Veredicto,
        destinatario: str,
        explicacion: str = "",
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
        # Saludo con el nombre de pila. Se conserva el nombre para que el
        # mensaje siga sonando a persona, pero con la formula de cortesia que
        # corresponde a una comunicacion con efectos economicos.
        nombre_pila = destinatario.split()[0] if destinatario else "Hola"

        # Si el modelo ha redactado la explicacion, se usa tal cual: ya
        # contiene los dos parrafos, el del razonamiento y el de la peticion.
        # Si no, se recurre a las plantillas fijas, que garantizan que siempre
        # haya un correo aunque el servicio no responda.
        if explicacion.strip():
            bloque_explicacion = [explicacion.strip()]
        else:
            bloque_explicacion = [
                self._componer_explicacion(gasto, veredicto),
                "",
                self.PETICIONES[veredicto.tipo],
            ]

        partes: List[str] = [
            f"Estimado/a {nombre_pila}:",
            "",
            *bloque_explicacion,
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

        # El contraste de fechas, cuando existe, va como frase independiente y
        # despues del motivo: primero se dice que ha ocurrido y luego se aporta
        # el dato que lo sostiene.
        contraste = self._componer_contraste_de_fechas(gasto, veredicto)

        if contraste:
            return f"{apertura} {motivo} {contraste}"

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

        ficha = (
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

        # Si consta un evento verificado se anade al final de la ficha, con su
        # periodo completo, para dejar constancia de sobre que dato externo se
        # apoyo la resolucion.
        if veredicto.tiene_periodo_de_evento:
            desde = self._formatear_fecha(veredicto.evento_desde)
            hasta = self._formatear_fecha(veredicto.evento_hasta)
            ficha += (
                f"\nEvento:        {veredicto.evento.strip()}"
                f"\nCelebración:   del {desde} al {hasta}"
            )

        return ficha

    def _formatear_fecha(self, fecha_iso: str) -> str:
        """Delega en la funcion de modulo, compartida con el resto."""
        return formatear_fecha(fecha_iso)

    def _componer_contraste_de_fechas(
        self, gasto: Gasto, veredicto: Veredicto
    ) -> str:
        """
        Redacta la frase que confronta la fecha del gasto con la del evento.

        Es el dato decisivo en estos casos y por eso lo compone la aplicacion a
        partir de campos, en lugar de confiarlo a la redaccion del modelo. Asi
        la frase sale siempre igual, con las dos fechas completas y sin
        ambiguedad, y quien la lee puede comprobarla sin abrir nada mas.

        Devuelve cadena vacia cuando no consta el periodo del evento, porque en
        ese caso no hay nada que contrastar.
        """
        if not veredicto.tiene_periodo_de_evento:
            return ""

        fecha_gasto = self._formatear_fecha(gasto.fecha)
        desde = self._formatear_fecha(veredicto.evento_desde)
        hasta = self._formatear_fecha(veredicto.evento_hasta)
        evento = veredicto.evento.strip()

        # Se distingue si la fecha encaja o no, porque la conjuncion cambia el
        # sentido de la frase: una confirma y la otra senala la discrepancia.
        dentro = (
            veredicto.evento_desde.strip()
            <= gasto.fecha.strip()
            <= veredicto.evento_hasta.strip()
        )

        if dentro:
            return (
                f"El gasto es del {fecha_gasto} y {evento} se celebró del "
                f"{desde} al {hasta}, de modo que la estancia queda dentro "
                f"del periodo del evento."
            )

        return (
            f"El gasto es del {fecha_gasto}, mientras que {evento} se celebró "
            f"del {desde} al {hasta}. La fecha del apunte queda por tanto "
            f"fuera del periodo del evento."
        )

    def _formatear_importe(self, importe: float, moneda: str) -> str:
        """Delega en la funcion de modulo, compartida con el resto."""
        return formatear_importe(importe, moneda)

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
