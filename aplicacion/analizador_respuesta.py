"""Analisis y validacion de la respuesta JSON devuelta por el modelo."""

import json
from typing import Any, Dict, List

from dominio.gasto import ConjuntoGastos
from dominio.veredicto import ResultadoEvaluacion, TipoVeredicto, Veredicto


class AnalizadorRespuesta:
    """
    Convierte el texto devuelto por el modelo en entidades de dominio validadas.

    Esta clase parte de una premisa defensiva: la respuesta de un modelo de
    lenguaje es una entrada no confiable, igual que lo seria un formulario
    rellenado por un desconocido. Puede venir envuelta en texto, puede omitir
    gastos, puede inventarse identificadores y puede usar un veredicto que no
    existe. Ninguna de esas situaciones debe romper la pantalla del alumno en
    mitad de la clase, asi que todas se degradan a un resultado utilizable.
    """

    def analizar(
        self, texto_respuesta: str, gastos: ConjuntoGastos, nombre_modelo: str
    ) -> ResultadoEvaluacion:
        """
        Transforma la respuesta en un ResultadoEvaluacion completo y coherente.

        Se garantiza que el resultado contiene un veredicto por cada gasto del
        conjunto: los que el modelo haya omitido se rellenan con REVISION, de
        modo que la tabla de la interfaz nunca queda con huecos inexplicados.
        """
        resultado = ResultadoEvaluacion(modelo_utilizado=nombre_modelo)

        # Paso 1: obtener la lista de veredictos en bruto del JSON.
        veredictos_brutos = self._extraer_lista_de_veredictos(texto_respuesta)

        # Paso 2: convertir cada elemento, descartando los que no casan con
        # ningun gasto real. Un identificador inventado por el modelo no debe
        # aparecer en pantalla como si fuese un gasto de la empresa.
        for elemento in veredictos_brutos:
            veredicto = self._convertir_elemento(elemento, gastos)
            if veredicto is not None:
                resultado.anadir(veredicto)

        # Paso 3: completar los gastos que el modelo haya dejado sin evaluar.
        self._completar_ausentes(resultado, gastos)

        return resultado

    def _extraer_lista_de_veredictos(self, texto: str) -> List[Dict[str, Any]]:
        """
        Localiza y decodifica la lista de veredictos dentro del texto recibido.

        Aunque se pide al proveedor el modo JSON, no todos lo respetan siempre:
        algunos envuelven el objeto en un bloque de codigo Markdown. Por eso se
        limpia el texto antes de intentar decodificarlo.
        """
        # Se eliminan las vallas de bloque de codigo si el modelo las anadio.
        limpio = texto.strip()
        if limpio.startswith("```"):
            # Se descarta la primera linea (```json) y la ultima (```).
            lineas = limpio.splitlines()
            limpio = "\n".join(lineas[1:-1]) if len(lineas) > 2 else ""

        # Si aun asi hay texto alrededor, se recorta al primer objeto JSON.
        inicio = limpio.find("{")
        final = limpio.rfind("}")
        if inicio != -1 and final != -1 and final > inicio:
            limpio = limpio[inicio : final + 1]

        try:
            datos = json.loads(limpio)
        except (json.JSONDecodeError, TypeError):
            # JSON irrecuperable: se devuelve lista vacia y el paso posterior
            # rellenara todo con REVISION, que es la degradacion correcta.
            return []

        # Se admite tanto el objeto con la clave esperada como una lista suelta,
        # porque algunos modelos devuelven directamente el array.
        if isinstance(datos, dict):
            lista = datos.get("veredictos", [])
        elif isinstance(datos, list):
            lista = datos
        else:
            lista = []

        # Solo se conservan los elementos que sean diccionarios; cualquier otra
        # cosa dentro de la lista es ruido que no se puede interpretar.
        return [elemento for elemento in lista if isinstance(elemento, dict)]

    def _convertir_elemento(
        self, elemento: Dict[str, Any], gastos: ConjuntoGastos
    ) -> Veredicto | None:
        """
        Convierte un elemento del JSON en un Veredicto, o devuelve None.

        Se devuelve None cuando el identificador no corresponde a ningun gasto
        real del conjunto, que es la senal de que el modelo se lo ha inventado.
        """
        identificador = str(elemento.get("id", "")).strip()

        # Validacion clave: el identificador debe existir en los datos de origen.
        if gastos.buscar(identificador) is None:
            return None

        # El tipo se convierte con la funcion tolerante del enumerado, que
        # degrada cualquier valor desconocido a REVISION.
        tipo = TipoVeredicto.desde_texto(str(elemento.get("veredicto", "")))

        # La clausula y el motivo se normalizan a texto y se acotan en longitud
        # para que una respuesta desmedida no descuadre la tabla en pantalla.
        clausula = str(elemento.get("clausula", "")).strip() or "sin indicar"
        motivo = str(elemento.get("motivo", "")).strip()[:240]

        return Veredicto(
            identificador_gasto=identificador,
            tipo=tipo,
            clausula=clausula,
            motivo=motivo or "El modelo no aporto motivo.",
        )

    def _completar_ausentes(
        self, resultado: ResultadoEvaluacion, gastos: ConjuntoGastos
    ) -> None:
        """
        Anade un veredicto de REVISION por cada gasto que el modelo no evaluo.

        Marcar el hueco de forma explicita es mejor que dejarlo vacio: el alumno
        ve que ese gasto quedo sin decidir, que es informacion relevante sobre el
        comportamiento del agente y no un fallo de la aplicacion.
        """
        for gasto in gastos:
            if resultado.obtener(gasto.identificador) is None:
                resultado.anadir(
                    Veredicto(
                        identificador_gasto=gasto.identificador,
                        tipo=TipoVeredicto.REVISION,
                        clausula="sin indicar",
                        motivo="El modelo no devolvio veredicto para este gasto.",
                    )
                )
