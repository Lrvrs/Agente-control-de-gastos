"""Primera pasada del agente: decidir qué hechos necesita verificar."""

import json
from typing import List

from dominio.gasto import ConjuntoGastos
from infraestructura.proveedor_llm import ErrorProveedorLLM, ProveedorLLM


class PlanificadorVerificacion:
    """
    Pregunta al modelo qué necesita comprobar antes de resolver.

    Esta clase implementa el paso que convierte el sistema en un agente y no en
    una cadena de llamadas: no es la aplicación quien decide qué buscar, sino el
    propio modelo, que lee los gastos y declara qué hechos externos no puede
    dar por ciertos. La aplicación se limita a ejecutar esas consultas y a
    devolverle los resultados.

    Esa diferencia importa en clase. Con un sistema agéntico de caja negra el
    alumno ve aparecer un veredicto sin más; aquí puede verse en pantalla qué
    decidió mirar el agente, qué encontró y qué concluyó. Es el ciclo de
    razonamiento, acción y observación hecho visible.
    """

    # Tope de consultas por evaluación. Protege la cuota del servicio de
    # búsqueda y, sobre todo, acota el tamaño del contexto de la segunda
    # llamada, que es lo que desbordaba con los sistemas de caja negra.
    MAXIMO_CONSULTAS = 8

    INSTRUCCION = """\
Eres la primera fase de un agente de control de gastos. Todavía no resuelves \
nada: tu única tarea es decidir qué hechos externos necesitan comprobación \
antes de poder decidir sobre estos gastos.

Un hecho externo es cualquier afirmación de la descripción que no puedas dar \
por cierta con lo que tienes delante y que sea comprobable en fuentes \
públicas: que una feria exista y cuándo se celebra, que una empresa sea real, \
qué clase de establecimiento es un local, en qué ciudad se encuentra, si una \
fecha es festivo en una localidad concreta, qué distancia separa dos lugares \
o si una zona dispone de transporte público.

Antes de decidir qué comprobar, lee la política que se incluye más abajo: es \
ella la que determina qué hechos resultan relevantes. Si una cláusula hace \
depender su resolución de algo externo, ese algo hay que comprobarlo aunque \
no figure en esta lista de ejemplos.

No propongas comprobar lo que ya está en los datos: importes, fechas del \
apunte, categorías o si se aportó justificante. Eso no se busca, se lee.

Formula cada consulta como la escribiría una persona en un buscador, \
incluyendo el año cuando importe. Agrupa: si varios gastos dependen del mismo \
hecho, una sola consulta.

Responde únicamente con un objeto JSON de esta forma:

{"consultas": [{"texto": "fechas de la feria TECMA 2026 Madrid", "motivo": \
"verificar el periodo de celebración invocado en E-001"}]}

Si ningún gasto depende de un hecho externo, devuelve la lista vacía."""

    def __init__(self, proveedor: ProveedorLLM) -> None:
        """Recibe el mismo proveedor que usa el resto de la aplicación."""
        self._proveedor = proveedor

    def planificar(self, gastos: ConjuntoGastos, politica=None) -> List[str]:
        """
        Devuelve las consultas que el agente considera necesarias.

        Ante cualquier problema devuelve una lista vacía en lugar de propagar el
        error: la verificación es una capacidad añadida, y si esta fase falla lo
        razonable es continuar sin ella y dejar que la segunda pasada resuelva
        con la información de que disponga.
        """
        # La política viaja también en esta primera llamada. Omitirla abarataba
        # la petición, pero dejaba la decisión de qué verificar clavada en el
        # texto de esta instrucción: añadir una cláusula que dependiera de un
        # hecho nuevo no cambiaba nada en la fase de planificación, y eso
        # contradice lo que la aplicación promete, que es que el comportamiento
        # lo decida la política y no el código.
        mensaje = self._componer_mensaje(gastos, politica)

        try:
            respuesta = self._proveedor.completar(self.INSTRUCCION, mensaje)
        except ErrorProveedorLLM:
            return []

        return self._extraer_consultas(respuesta)

    def _componer_mensaje(self, gastos: ConjuntoGastos, politica=None) -> str:
        """Compone la política y la lista de descripciones que hay que examinar."""
        # Bloque de política. Es opcional para que el planificador siga siendo
        # utilizable sin ella, que es como lo ejercitan las pruebas.
        cabecera = ""
        if politica is not None:
            cabecera = (
                "POLÍTICA DE GASTOS VIGENTE\n"
                "==========================\n"
                f"{politica.texto}\n\n"
            )

        lineas = [
            f"{gasto.identificador} | {gasto.fecha} | {gasto.ciudad} | "
            f"{gasto.descripcion}"
            for gasto in gastos
        ]
        return (
            cabecera
            + "GASTOS A EXAMINAR\n"
            "=================\n"
            "Formato: id | fecha | ciudad | descripción\n\n"
            + "\n".join(lineas)
            + f"\n\nDevuelve como máximo {self.MAXIMO_CONSULTAS} consultas."
        )

    def _extraer_consultas(self, respuesta: str) -> List[str]:
        """Interpreta la respuesta y devuelve las consultas como texto."""
        # Se aplica la misma tolerancia que en el resto del proyecto: la
        # respuesta puede venir envuelta en un bloque de código o con prosa
        # alrededor, y nada de eso debe romper la evaluación.
        limpio = respuesta.strip()
        if limpio.startswith("```"):
            lineas = limpio.splitlines()
            limpio = "\n".join(lineas[1:-1]) if len(lineas) > 2 else ""

        inicio, final = limpio.find("{"), limpio.rfind("}")
        if inicio != -1 and final > inicio:
            limpio = limpio[inicio : final + 1]

        try:
            datos = json.loads(limpio)
        except (json.JSONDecodeError, TypeError):
            return []

        if not isinstance(datos, dict):
            return []

        consultas: List[str] = []
        for elemento in datos.get("consultas", []):
            # Se admite tanto el objeto con motivo como la cadena suelta, porque
            # algunos modelos simplifican la estructura pedida.
            if isinstance(elemento, dict):
                texto = str(elemento.get("texto", "")).strip()
            else:
                texto = str(elemento).strip()

            # Se descartan las vacías y las repetidas, que solo gastarían cuota.
            if texto and texto not in consultas:
                consultas.append(texto)

        return consultas[: self.MAXIMO_CONSULTAS]
