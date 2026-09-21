"""Caso de uso principal: evaluar un conjunto de gastos contra una politica."""

import hashlib
import time
from typing import List, Tuple

from aplicacion.analizador_respuesta import AnalizadorRespuesta
from aplicacion.constructor_prompt import ConstructorPrompt
from aplicacion.planificador_verificacion import PlanificadorVerificacion
from dominio.gasto import ConjuntoGastos
from dominio.politica import Politica
from dominio.veredicto import ResultadoEvaluacion
from infraestructura.buscador_web import BuscadorWeb, ResultadoBusqueda
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

    # Numero minimo de gastos que debe tener un lote para que tenga sentido
    # seguir dividiendolo. Se fija en uno porque con los sistemas agenticos el
    # consumo no depende del numero de gastos sino del material que recuperan
    # por cada uno: reducir a un unico gasto por llamada es la unica forma de
    # acotarlo, y con frecuencia es la que acaba haciendo falta. Cuando un solo
    # gasto sigue sin caber, no hay nada que dividir y el error es legitimo.
    TAMANO_MINIMO_DE_LOTE = 1

    def __init__(
        self,
        proveedor: ProveedorLLM,
        cache: CacheEvaluaciones,
        buscador: BuscadorWeb | None = None,
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
        self._buscador = buscador
        self._planificador = PlanificadorVerificacion(proveedor)

        # Traza de la ultima verificacion, para poder mostrarla en pantalla. Es
        # lo que permite ensenar en clase que decidio buscar el agente y que
        # encontro, en lugar de presentar el veredicto como un oraculo.
        self.traza_verificacion: List[ResultadoBusqueda] = []
        self._constructor = constructor or ConstructorPrompt()
        self._analizador = analizador or AnalizadorRespuesta()

    def evaluar(
        self, politica: Politica, gastos: ConjuntoGastos,
        usar_cache: bool = True,
    ) -> ResultadoEvaluacion:
        """
        Evalua los gastos contra la politica y devuelve el resultado.

        Con usar_cache a falso se salta la consulta a la cache y se llama al
        modelo aunque haya una respuesta guardada para esa misma politica. El
        resultado nuevo si se guarda, sustituyendo al anterior. Sirve para
        repetir una evaluacion sin tener que alterar la politica, que es lo
        unico que cambiaba la clave y obligaba a modificar el texto para forzar
        una llamada.

        Puede lanzar ErrorProveedorLLM si el modelo no responde; la interfaz es
        responsable de traducir ese error a un mensaje comprensible.
        """
        huella_gastos = self._calcular_huella_gastos(gastos)

        # Paso 1: cache. Es el camino mas frecuente al principio de la clase,
        # cuando todos evaluan con la politica por defecto sin haberla tocado.
        entrada_en_cache = (
            self._cache.obtener(politica.huella, huella_gastos)
            if usar_cache
            else None
        )
        if entrada_en_cache is not None:
            resultado_en_cache, traza_guardada = entrada_en_cache

            # La traza se restituye junto con el resultado. Sin esto, servir una
            # evaluacion desde la cache dejaba el panel de verificacion vacio y
            # parecia que el agente no habia comprobado nada, cuando lo que
            # ocurria es que lo habia comprobado en la evaluacion original.
            self.traza_verificacion = list(traza_guardada)

            # Se devuelve una copia marcada como procedente de cache para que la
            # interfaz pueda indicarlo sin alterar la entrada almacenada.
            return self._marcar_como_cache(resultado_en_cache)

        # Paso 2: primera pasada. El agente decide que hechos externos necesita
        # comprobar y la aplicacion ejecuta esas busquedas. Si no hay
        # herramienta configurada, esta fase no hace nada y el bloque de hechos
        # queda vacio, lo que llevara al agente a escalar lo que dependa de uno.
        hechos = self._verificar_hechos(gastos, politica)

        # Paso 3: segunda pasada. Con los hechos en la mano, se emiten los
        # veredictos, partiendo el conjunto si el proveedor lo rechaza por
        # tamano. La division ocurre dentro de este metodo y es recursiva.
        resultado = self._evaluar_conjunto(politica, gastos, hechos)
        resultado.huella_politica = politica.huella

        # Paso 5: guardar para que la siguiente peticion identica salga gratis.
        self._cache.guardar(
            politica.huella, huella_gastos, resultado, self.traza_verificacion
        )

        return resultado

    def _verificar_hechos(
        self, gastos: ConjuntoGastos, politica: Politica | None = None
    ) -> str:
        """
        Ejecuta la fase de verificacion y devuelve los hechos comprobados.

        Devuelve una cadena vacia cuando no hay herramienta configurada o cuando
        el agente no considera que ningun gasto dependa de un hecho externo. En
        ambos casos la evaluacion continua: la verificacion es una capacidad
        adicional y su ausencia se traduce en resoluciones mas prudentes, no en
        un fallo.
        """
        # Se reinicia la traza en cada evaluacion, para que lo que se muestre en
        # pantalla corresponda siempre a la ejecucion en curso.
        self.traza_verificacion = []

        # Sin herramienta capaz de comprobar nada, se omite tambien la fase de
        # planificacion: preparar consultas que nadie va a ejecutar gastaria una
        # llamada al modelo sin obtener nada a cambio.
        if self._buscador is None or not self._buscador.puede_verificar:
            return ""

        # El agente decide que necesita mirar. La aplicacion no lo deduce.
        consultas = self._planificador.planificar(gastos, politica)
        if not consultas:
            return ""

        bloques: List[str] = []
        for consulta in consultas:
            resultado = self._buscador.buscar(consulta)
            self.traza_verificacion.append(resultado)
            bloques.append(resultado.a_bloque_para_modelo())

        return "\n\n".join(bloques)

    def _evaluar_conjunto(
        self, politica: Politica, gastos: ConjuntoGastos, hechos: str = "",
        es_repesca: bool = False,
    ) -> ResultadoEvaluacion:
        """
        Evalua un conjunto de gastos, dividiendolo si el proveedor lo rechaza.

        Un proveedor puede devolver que la peticion es demasiado grande aunque
        el mensaje enviado sea modesto. Ocurre de forma sistematica con los
        sistemas agenticos: cada busqueda que realizan incorpora sus resultados
        al contexto, de modo que el tamano real de la peticion depende de
        cuanto material recuperen y no de lo que la aplicacion escribio.

        Reintentar lo mismo no arregla nada, pero evaluar la mitad de los gastos
        genera la mitad de busquedas y suele caber. Por eso, ante ese error
        concreto, el conjunto se parte en dos y cada mitad se evalua por
        separado; si alguna sigue sin caber, se vuelve a partir. Los resultados
        parciales se combinan al final y el alumno no percibe la diferencia,
        salvo por una espera algo mayor.
        """
        instruccion = self._constructor.construir_instruccion_sistema()
        mensaje = self._constructor.construir_mensaje_usuario(
            politica, gastos, hechos
        )

        try:
            texto = self._llamar_con_reintentos(instruccion, mensaje)
        except ErrorProveedorLLM as error:
            # Solo el rechazo por tamano justifica dividir. Y solo mientras el
            # lote sea lo bastante grande como para que dividirlo cambie algo.
            if not error.es_peticion_demasiado_grande:
                raise
            if len(gastos) < self.TAMANO_MINIMO_DE_LOTE * 2:
                raise

            return self._evaluar_por_mitades(politica, gastos, hechos)

        resultado = self._analizador.analizar(
            texto, gastos, self._proveedor.nombre_modelo
        )

        # Una repesca no vuelve a repescarse: si el segundo intento tampoco
        # devuelve el gasto, se acepta el hueco y se deja constancia en
        # pantalla. Insistir mas convertiria un fallo puntual del modelo en una
        # espera larga delante de la clase.
        if es_repesca:
            return resultado

        return self._repescar_ausentes(politica, gastos, hechos, resultado)

    def _repescar_ausentes(
        self, politica: Politica, gastos: ConjuntoGastos, hechos: str,
        resultado: ResultadoEvaluacion,
    ) -> ResultadoEvaluacion:
        """
        Vuelve a pedir los gastos que el modelo dejo sin evaluar.

        Un modelo puede devolver una lista incompleta: se salta un apunte, o
        corta la respuesta antes de terminarla. Hasta ahora esos huecos se
        rellenaban con una revision cuyo motivo era "El modelo no devolvio
        veredicto para este gasto", un texto que no dice nada al alumno y que
        ademas le llegaba como si fuera el razonamiento del agente.

        La reparacion es barata y merece la pena: se vuelve a preguntar, pero
        solo por los gastos que faltan. El prompt resultante es mucho mas corto
        que el original, de modo que el fallo mas probable -haberse quedado sin
        espacio de salida- desaparece por si solo. Si la segunda llamada falla
        por cualquier motivo, se conserva el resultado original: la reparacion
        es un extra y nunca debe empeorar lo que ya se tenia.
        """
        ausentes = self._analizador.identificadores_sin_respuesta(resultado)
        if not ausentes:
            return resultado

        pendientes = ConjuntoGastos(
            [g for g in gastos if g.identificador in set(ausentes)]
        )

        try:
            segundo = self._evaluar_conjunto(
                politica, pendientes, hechos, es_repesca=True
            )
        except ErrorProveedorLLM:
            return resultado

        # Solo se sustituyen los huecos por veredictos que esta vez si vienen
        # del modelo. Un hueco que sigue siendo hueco se deja como estaba.
        nuevos_huecos = set(self._analizador.identificadores_sin_respuesta(segundo))
        for identificador, veredicto in segundo.veredictos.items():
            if identificador not in nuevos_huecos:
                resultado.anadir(veredicto)

        return resultado

    def _evaluar_por_mitades(
        self, politica: Politica, gastos: ConjuntoGastos, hechos: str = ""
    ) -> ResultadoEvaluacion:
        """Divide el conjunto en dos, evalua cada mitad y combina el resultado."""
        lista = list(gastos)
        mitad = len(lista) // 2

        # Cada mitad vuelve a entrar por el metodo general, de modo que puede
        # dividirse otra vez si tampoco cabe.
        # Los hechos ya verificados se reutilizan en ambas mitades: no se
        # vuelve a buscar nada al dividir, de modo que partir el trabajo no
        # multiplica el consumo de la cuota de busqueda.
        primera = self._evaluar_conjunto(
            politica, ConjuntoGastos(lista[:mitad]), hechos
        )
        segunda = self._evaluar_conjunto(
            politica, ConjuntoGastos(lista[mitad:]), hechos
        )

        # Se combinan en un unico resultado, conservando el modelo utilizado.
        combinado = ResultadoEvaluacion(
            modelo_utilizado=self._proveedor.nombre_modelo
        )
        for parcial in (primera, segunda):
            for veredicto in parcial.veredictos.values():
                combinado.anadir(veredicto)

        return combinado

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
