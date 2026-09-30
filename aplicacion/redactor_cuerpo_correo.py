"""Redacción del cuerpo del correo mediante el modelo de lenguaje."""

from typing import Dict

from dominio.correo import formatear_fecha, formatear_importe
from dominio.gasto import Gasto
from dominio.veredicto import TipoVeredicto, Veredicto
from infraestructura.proveedor_llm import ErrorProveedorLLM, ProveedorLLM


class GeneradorCuerpoCorreo:
    """
    Pide al modelo que redacte la explicación que abre el correo.

    Sustituye a las plantillas fijas que se usaban antes, pero solo en la parte
    que es prosa. El reparto queda así: el modelo escribe, el código aporta los
    datos y compone la ficha formal del pie.

    Ese reparto responde a un riesgo concreto. Un modelo que redacta libremente
    sobre un gasto puede deslizar una cifra aproximada, una fecha redondeada o
    una referencia a una cláusula que no aplica, y en una comunicación que
    deniega un reembolso eso es inadmisible. Por eso el prompt entrega los datos
    ya verificados y prohíbe expresamente aportar cualquier otro: el modelo pone
    el lenguaje, no los hechos.

    La generación es perezosa y se cachea. Un correo se redacta cuando alguien
    lo abre, no al evaluar, de modo que una evaluación de diez gastos no dispara
    diez llamadas sino ninguna, y las que luego se produzcan se reparten solas
    en el tiempo conforme el alumno va abriendo mensajes.
    """

    # Instrucción de sistema. Fija el papel, el formato y, sobre todo, el
    # límite: escribir sí, inventar no.
    INSTRUCCION = """\
Eres el responsable de control de gestión de una empresa y redactas el correo \
con el que comunicas la resolución de un gasto de viaje.

Escribe exactamente dos párrafos, en castellano y en primera persona.

En el primero explicas qué has revisado y a qué conclusión has llegado. Si en \
los datos aparece una discrepancia de fechas con un evento, es lo primero que \
debe quedar claro, con las dos fechas completas.

En el segundo dices qué ocurre ahora y qué esperas del destinatario.

Reglas que no puedes incumplir:

1. Utiliza únicamente los datos que se te entregan. No aportes ninguna cifra, \
fecha, nombre, importe ni referencia normativa que no figure en ellos, ni \
siquiera aproximada.
2. No incluyas saludo, despedida, firma ni ficha de datos: de eso se encarga \
la aplicación. Escribe solo los dos párrafos.
3. Registro profesional. Ni coloquial ni burocrático: escribes a un compañero \
sobre una decisión con consecuencias económicas.
4. Nada de viñetas, encabezados ni negritas. Prosa corrida.
5. No excedas las ciento veinte palabras en total."""

    def __init__(self, proveedor: ProveedorLLM) -> None:
        """Recibe el mismo proveedor que utiliza el resto de la aplicación."""
        self._proveedor = proveedor

        # Caché de cuerpos ya redactados. Evita pagar una llamada cada vez que
        # el alumno reabre el mismo correo, cosa que hará al comparar unos con
        # otros. Se comparte entre sesiones cuando el generador se construye
        # como recurso compartido.
        self._cache: Dict[str, str] = {}

    def generar(
        self, gasto: Gasto, veredicto: Veredicto, destinatario: str
    ) -> str:
        """
        Devuelve los dos párrafos de explicación, o cadena vacía si falla.

        La cadena vacía es una respuesta legítima y no un error: quien la reciba
        recurrirá a la plantilla fija. Esa salida garantiza que en clase nunca
        se abra un correo en blanco porque el modelo no respondiera.
        """
        clave = self._componer_clave(gasto, veredicto, destinatario)
        if clave in self._cache:
            return self._cache[clave]

        try:
            respuesta = self._proveedor.completar(
                self.INSTRUCCION,
                self._componer_datos(gasto, veredicto, destinatario),
            )
        except ErrorProveedorLLM:
            return ""

        cuerpo = self._limpiar(respuesta)

        # Solo se guarda lo aprovechable: cachear una respuesta vacía impediría
        # volver a intentarlo cuando el servicio se recupere.
        if cuerpo:
            self._cache[clave] = cuerpo

        return cuerpo

    def _componer_clave(
        self, gasto: Gasto, veredicto: Veredicto, destinatario: str
    ) -> str:
        """Construye la clave de caché de este correo concreto."""
        # Incluye todo lo que puede alterar la redacción. Si el alumno cambia la
        # política y el veredicto pasa de aprobado a denegado, la clave cambia y
        # el correo se redacta de nuevo.
        return "|".join(
            [
                gasto.identificador,
                veredicto.tipo.value,
                veredicto.clausula,
                veredicto.motivo,
                veredicto.evento,
                veredicto.evento_desde,
                veredicto.evento_hasta,
                destinatario,
            ]
        )

    def _componer_datos(
        self, gasto: Gasto, veredicto: Veredicto, destinatario: str
    ) -> str:
        """
        Compone el bloque de hechos que el modelo puede utilizar.

        Todo lo que el correo necesita afirmar está aquí. Lo que no esté, el
        modelo no debe escribirlo, y así se le indica en la instrucción.
        """
        justificante = "sí" if gasto.tiene_justificante else "no"

        lineas = [
            "DATOS DE LA RESOLUCIÓN",
            f"Destinatario: {destinatario}",
            f"Referencia del gasto: {gasto.identificador}",
            f"Empleado que lo presenta: {gasto.empleado}",
            f"Fecha del gasto: {formatear_fecha(gasto.fecha)}",
            f"Concepto declarado: {gasto.descripcion}",
            f"Categoría: {gasto.categoria}",
            f"Ciudad: {gasto.ciudad}",
            f"Importe: {formatear_importe(gasto.importe, gasto.moneda)}",
            f"Aporta justificante: {justificante}",
            f"Resolución adoptada: {veredicto.tipo.value}",
            f"Cláusula aplicada: {veredicto.clausula}",
            f"Motivo de la resolución: {veredicto.motivo}",
        ]

        # El periodo del evento solo se incluye cuando consta verificado. Es el
        # dato que sostiene la discrepancia y debe llegar completo.
        if veredicto.tiene_periodo_de_evento:
            lineas.append(f"Evento invocado: {veredicto.evento}")
            # Las fechas se entregan ya escritas en castellano. Si se pasan en
            # formato ISO, el modelo las copia tal cual al correo y el empleado
            # acaba leyendo "del 2026-06-09 al 2026-06-11".
            lineas.append(
                f"Fechas reales de celebración: del "
                f"{formatear_fecha(veredicto.evento_desde)} al "
                f"{formatear_fecha(veredicto.evento_hasta)}"
            )

        # Se explicita el papel del destinatario, porque no se escribe igual a
        # quien presenta el gasto que a quien debe decidir sobre el.
        if veredicto.tipo is TipoVeredicto.REVISION:
            lineas.append(
                "Papel del destinatario: es el responsable al que se eleva el "
                "gasto para que decida, no quien lo presentó."
            )
        else:
            lineas.append(
                "Papel del destinatario: es la persona que presentó el gasto."
            )

        return "\n".join(lineas)

    def _limpiar(self, respuesta: str) -> str:
        """
        Retira de la respuesta lo que el modelo no debía haber incluido.

        Pese a la instrucción, es frecuente que añada un saludo o una firma. En
        lugar de reintentar la llamada, que costaría cuota, se eliminan esas
        líneas: el resultado es el mismo y no consume nada.
        """
        # Encabezados que delatan un saludo o una despedida al principio o al
        # final del texto.
        prefijos_saludo = (
            "hola", "estimado", "estimada", "buenos días", "buenas tardes",
        )
        prefijos_cierre = (
            "un saludo", "saludos", "atentamente", "cordialmente", "gracias,",
        )

        lineas = [l.strip() for l in respuesta.strip().splitlines()]
        utiles = []

        for linea in lineas:
            if not linea:
                continue

            minuscula = linea.lower()

            # Se descartan saludos, despedidas y la firma que suele seguirlas.
            if minuscula.startswith(prefijos_saludo) and linea.endswith(":"):
                continue
            if minuscula.startswith(prefijos_cierre):
                break

            utiles.append(linea)

        # Se recomponen los parrafos separados por una linea en blanco.
        return "\n\n".join(utiles)
