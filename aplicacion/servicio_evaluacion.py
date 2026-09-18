"""Caso de uso principal: evaluar un conjunto de gastos contra una politica."""

import hashlib
import time

from aplicacion.analizador_respuesta import AnalizadorRespuesta
from aplicacion.constructor_prompt import ConstructorPrompt
from dominio.gasto import ConjuntoGastos
from dominio.politica import Politica
from dominio.veredicto import ResultadoEvaluacion
from infraestructura.cache_evaluaciones import CacheEvaluaciones
from infraestructura.proveedor_llm import ErrorProveedorLLM, ProveedorLLM


class ServicioEvaluacion:
    """
    Orquesta el flujo completo de una evaluacion.

    La secuencia es siempre la misma: mirar la cache, construir el prompt,
    llamar al modelo una sola vez, analizar la respuesta y guardar el resultado.
    Concentrar ese orden en un unico punto evita que la interfaz tenga que
    conocer ninguno de los pasos intermedios.
    """

    # Numero de reintentos ante un error de ritmo. Se mantiene bajo: si el
    # servicio esta saturado, insistir mucho agrava el problema para todos.
    REINTENTOS_ANTE_SATURACION = 2

    # Espera entre reintentos, en segundos. Suficiente para que se libere la
    # ventana de ritmo sin que el alumno perciba que la aplicacion se ha colgado.
    ESPERA_ENTRE_REINTENTOS = 3.0

    def __init__(
        self,
        proveedor: ProveedorLLM,
        cache: CacheEvaluaciones,
        constructor: ConstructorPrompt | None = None,
        analizador: AnalizadorRespuesta | None = None,
    ) -> None:
        """
        Recibe sus colaboradores en lugar de construirlos.

        Esta inyeccion permite sustituir el proveedor por uno simulado al probar
        la aplicacion sin consumir cuota, sin tocar esta clase.
        """
        self._proveedor = proveedor
        self._cache = cache
        self._constructor = constructor or ConstructorPrompt()
        self._analizador = analizador or AnalizadorRespuesta()

    def evaluar(
        self, politica: Politica, gastos: ConjuntoGastos
    ) -> ResultadoEvaluacion:
        """
        Evalua los gastos contra la politica y devuelve el resultado.

        Puede lanzar ErrorProveedorLLM si el modelo no responde; la interfaz es
        responsable de traducir ese error a un mensaje comprensible.
        """
        huella_gastos = self._calcular_huella_gastos(gastos)

        # Paso 1: cache. Es el camino mas frecuente al principio de la clase,
        # cuando todos evaluan con la politica por defecto sin haberla tocado.
        resultado_en_cache = self._cache.obtener(politica.huella, huella_gastos)
        if resultado_en_cache is not None:
            # Se devuelve una copia marcada como procedente de cache para que la
            # interfaz pueda indicarlo sin alterar la entrada almacenada.
            return self._marcar_como_cache(resultado_en_cache)

        # Paso 2: construir los dos mensajes de la peticion.
        instruccion = self._constructor.construir_instruccion_sistema()
        mensaje = self._constructor.construir_mensaje_usuario(politica, gastos)

        # Paso 3: llamar al modelo, con reintentos solo ante saturacion.
        texto_respuesta = self._llamar_con_reintentos(instruccion, mensaje)

        # Paso 4: analizar la respuesta y validarla contra los gastos reales.
        resultado = self._analizador.analizar(
            texto_respuesta, gastos, self._proveedor.nombre_modelo
        )
        resultado.huella_politica = politica.huella

        # Paso 5: guardar para que la siguiente peticion identica salga gratis.
        self._cache.guardar(politica.huella, huella_gastos, resultado)

        return resultado

    def _llamar_con_reintentos(self, instruccion: str, mensaje: str) -> str:
        """
        Realiza la llamada al modelo reintentando solo si el error es de ritmo.

        La distincion importa: reintentar ante una clave invalida no arregla
        nada y solo alarga la espera, mientras que reintentar ante un 429 suele
        funcionar porque la ventana de ritmo se libera en segundos.
        """
        ultimo_error: ErrorProveedorLLM | None = None

        # Se intenta una vez mas de lo indicado porque el primer intento no es
        # un reintento: con dos reintentos hay tres llamadas posibles en total.
        for numero_intento in range(self.REINTENTOS_ANTE_SATURACION + 1):
            try:
                return self._proveedor.completar(instruccion, mensaje)
            except ErrorProveedorLLM as error:
                ultimo_error = error

                # Si el error no es de ritmo, no tiene sentido insistir.
                if not error.es_limite_de_ritmo:
                    raise

                # Si aun quedan intentos, se espera antes del siguiente.
                if numero_intento < self.REINTENTOS_ANTE_SATURACION:
                    time.sleep(self.ESPERA_ENTRE_REINTENTOS)

        # Agotados los intentos se propaga el ultimo error conocido.
        raise ultimo_error if ultimo_error else ErrorProveedorLLM("Fallo desconocido.")

    def _calcular_huella_gastos(self, gastos: ConjuntoGastos) -> str:
        """Huella estable del conjunto de gastos, para indexar la cache."""
        # Se construye sobre la misma serializacion que se envia al modelo, de
        # modo que dos conjuntos que producirian el mismo prompt comparten clave.
        contenido = gastos.a_bloque_para_modelo()
        return hashlib.sha256(contenido.encode("utf-8")).hexdigest()[:16]

    def _marcar_como_cache(self, original: ResultadoEvaluacion) -> ResultadoEvaluacion:
        """Devuelve el resultado senalado como servido desde la cache."""
        # Se crea un objeto nuevo en lugar de mutar el guardado: si se modificase
        # la entrada de cache, la marca quedaria fijada para siempre.
        copia = ResultadoEvaluacion(
            veredictos=dict(original.veredictos),
            huella_politica=original.huella_politica,
            procede_de_cache=True,
            modelo_utilizado=original.modelo_utilizado,
        )
        return copia
