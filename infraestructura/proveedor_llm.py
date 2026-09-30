"""Cliente del modelo de lenguaje, intercambiable entre proveedores."""

import re
import threading
import time
from abc import ABC, abstractmethod
from typing import Dict

from openai import OpenAI

from infraestructura.configuracion import ConfiguracionLLM


class ErrorProveedorLLM(Exception):
    """
    Error controlado al hablar con el proveedor.

    Existe para que la interfaz pueda distinguir un fallo del servicio externo
    de un fallo propio de la aplicacion y mostrar al alumno un mensaje util en
    lugar de una traza de Python.
    """

    def __init__(
        self,
        mensaje: str,
        es_limite_de_ritmo: bool = False,
        es_peticion_demasiado_grande: bool = False,
    ) -> None:
        """Guarda la naturaleza del fallo, que determina como reaccionar."""
        super().__init__(mensaje)

        # Exceso de ritmo: tiene sentido esperar y reintentar lo mismo.
        self.es_limite_de_ritmo = es_limite_de_ritmo

        # Peticion demasiado grande: reintentar lo mismo no sirve de nada, pero
        # si se parte el trabajo en dos mitades, cada una puede caber.
        self.es_peticion_demasiado_grande = es_peticion_demasiado_grande


def segundos_hasta_reintento(detalle: str) -> float | None:
    """
    Devuelve los segundos que pide esperar un 429, o None si no los dice.

    Groq los escribe dentro del mensaje ("Please try again in 7.66s", "in
    1m23.4s", "in 500ms"). Es un port del parser del proyecto Chatpdf, que ya
    tropezo con la trampa de abajo.
    """
    coincidencia = re.search(r"try again in ([0-9hms.]+)", detalle or "", re.I)
    if not coincidencia:
        return None

    # El punto final de la frase se cuela en el grupo ("500ms.") y sin quitarlo
    # la comprobacion de milisegundos no casa: "500m" se leeria como 500
    # MINUTOS y el modelo quedaria descartado durante horas.
    texto = coincidencia.group(1).rstrip(".")

    milisegundos = re.fullmatch(r"([\d.]+)ms", texto, re.I)
    if milisegundos:
        try:
            return float(milisegundos.group(1)) / 1000
        except ValueError:
            return None

    factor = {"h": 3600, "m": 60, "s": 1}
    total = 0.0
    alguna_unidad = False
    for valor, unidad in re.findall(r"([\d.]+)\s*(h|m|s)", texto, re.I):
        try:
            total += float(valor) * factor[unidad.lower()]
        except ValueError:
            return None
        alguna_unidad = True

    return total if alguna_unidad else None


class ProveedorLLM(ABC):
    """
    Contrato minimo que debe cumplir cualquier proveedor de modelo.

    Se define como clase abstracta para dejar explicito lo unico que la
    aplicacion necesita: enviar un par de mensajes y recibir texto.
    """

    @abstractmethod
    def completar(
        self, instruccion_sistema: str, mensaje_usuario: str,
        pedir_json: bool = True,
    ) -> str:
        """
        Envia la peticion al modelo y devuelve su respuesta en texto plano.

        Con pedir_json a falso no se solicita el modo JSON: es lo que necesita
        quien espera prosa, como el redactor de correos.
        """

    @property
    @abstractmethod
    def nombre_modelo(self) -> str:
        """Identificador del modelo, para mostrarlo como dato de trazabilidad."""


class ProveedorCompatibleOpenAI(ProveedorLLM):
    """
    Implementacion para cualquier servicio con API compatible con OpenAI.

    Groq, Google AI Studio y OpenRouter exponen los tres ese mismo contrato, de
    modo que cambiar de uno a otro se reduce a modificar la URL base y el nombre
    del modelo en los secretos, sin desplegar codigo nuevo. Esa reversibilidad
    es un requisito del proyecto: los limites de los planes gratuitos cambian.
    """

    # Tiempo maximo de espera de una respuesta, en segundos. Se mantiene corto
    # porque en clase una espera larga se percibe como una aplicacion rota, y
    # es preferible fallar pronto y ofrecer reintentar.
    TIEMPO_MAXIMO_ESPERA = 45.0

    # Temperatura baja: se busca consistencia entre ejecuciones, no creatividad.
    # Un veredicto sobre una politica deberia ser reproducible.
    TEMPERATURA = 0.1

    # Techo de tokens de salida. Se fija de forma explicita porque el limite
    # implicito de cada proveedor es distinto y, cuando se queda corto, la
    # respuesta llega cortada a media frase: el JSON deja de ser valido y la
    # evaluacion entera se degrada a revision sin que nada indique el motivo.
    # Con diez gastos la respuesta ronda los 1.500 tokens, asi que 4.000 deja
    # margen para un fichero mas grande sin encarecer las llamadas normales,
    # que solo consumen lo que realmente escriben.
    MAXIMO_TOKENS_DE_SALIDA = 4000

    # Hasta cuantos segundos se espera para reintentar el MISMO modelo tras un
    # 429. Mas alla compensa cambiar de modelo: el alumno mira el spinner.
    ESPERA_MAXIMA_MISMO_MODELO = 4.0

    # Modelos que han devuelto un 429 largo, con el instante (monotonic) en que
    # vuelven a estar disponibles. Es de clase y no de instancia porque el
    # proveedor se construye de nuevo en cada evaluacion, y sin memoria comun
    # cada una volveria a probar primero el modelo agotado y gastaria una
    # llamada en que se lo repitan. Se guarda un instante y no un booleano
    # porque Groq dice cuando se repone, y un modelo con el cupo del dia
    # agotado no debe reintentarse en horas.
    _enfriamiento: Dict[str, float] = {}
    _cerrojo_enfriamiento = threading.Lock()

    def __init__(self, configuracion: ConfiguracionLLM) -> None:
        """Construye el cliente con las credenciales indicadas."""
        self._configuracion = configuracion
        self._modelo_usado = ""

        # El cliente se crea una sola vez y se reutiliza: abrir una conexion
        # nueva por peticion multiplicaria la latencia percibida.
        #
        # La construccion se protege porque puede fallar por motivos ajenos a
        # las credenciales, tipicamente una incompatibilidad entre la version
        # del SDK y la de su cliente HTTP subyacente. Sin esta proteccion, ese
        # fallo sale a pantalla como una traza de Python delante de la clase.
        try:
            self._cliente = OpenAI(
                api_key=configuracion.clave_api,
                base_url=configuracion.url_base,
                timeout=self.TIEMPO_MAXIMO_ESPERA,
                max_retries=0,  # Los reintentos se gestionan en la capa superior.
            )
        except Exception as error:
            raise ErrorProveedorLLM(
                f"No se pudo inicializar el cliente del modelo: {error}"
            ) from error

    @property
    def nombre_modelo(self) -> str:
        """Identificador del modelo que respondio, o el principal si aun ninguno."""
        # Es el que respondio y no el configurado porque, con respaldo, pueden
        # ser distintos, y la pantalla debe decir quien escribio el veredicto.
        return self._modelo_usado or self._configuracion.modelo

    def completar(
        self, instruccion_sistema: str, mensaje_usuario: str,
        pedir_json: bool = True,
    ) -> str:
        """
        Envia una unica peticion al modelo con los dos mensajes indicados.

        Se hace una sola llamada por evaluacion completa, no una por gasto. Esa
        decision es la que permite que treinta alumnos usen la aplicacion a la
        vez: con una llamada por gasto serian cientos de peticiones en rafaga y
        ningun plan gratuito lo soportaria.
        """
        mensajes = [
            {"role": "system", "content": instruccion_sistema},
            {"role": "user", "content": mensaje_usuario},
        ]

        # Primer intento pidiendo explicitamente un objeto JSON. Los proveedores
        # que soportan este modo garantizan sintaxis valida, lo que elimina la
        # causa mas frecuente de fallo al analizar la respuesta.
        #
        # Quien espera prosa lo desactiva. Pedir ese modo sin que el prompt
        # mencione la palabra "json" lo rechaza el proveedor con un 400, y el
        # reintento de abajo gastaba una llamada entera, en plena saturacion,
        # solo para repetir lo mismo sin el parametro. Y si el modelo lo
        # aceptase, obligaria a responder en JSON donde se quiere un texto.
        try:
            respuesta = self._invocar(mensajes, pedir_json=pedir_json)
        except Exception as error:
            # No todos los modelos admiten el modo JSON. Los sistemas agenticos
            # con herramientas integradas, en particular, suelen rechazarlo.
            # Como el modelo se elige desde la configuracion y puede cambiarse
            # sin desplegar, la aplicacion debe tolerar ambos comportamientos:
            # ante un rechazo de ese parametro concreto se reintenta sin el, y
            # el analizador de respuestas, que ya es defensivo, se encarga del
            # resto. Cualquier otro error se propaga sin reintento.
            if not pedir_json or not self._es_rechazo_de_modo_json(error):
                raise self._traducir_error(error) from error

            try:
                respuesta = self._invocar(mensajes, pedir_json=False)
            except Exception as error_reintento:
                raise self._traducir_error(error_reintento) from error_reintento

        # Una respuesta sin contenido es anomala pero posible; se trata como
        # error controlado en lugar de dejar que falle al indexar.
        if not respuesta.choices:
            raise ErrorProveedorLLM("El proveedor devolvió una respuesta vacía.")

        contenido = respuesta.choices[0].message.content
        return contenido or ""

    def _invocar(self, mensajes: list, pedir_json: bool):
        """
        Llama al primer modelo disponible y pasa al siguiente ante un 429.

        Un 429 corto se resuelve esperando en el mismo modelo, y uno largo
        -el cupo del dia agotado, por ejemplo- se resuelve cambiando: esperar
        minutos delante de la clase no es una opcion. Cualquier otro error se
        propaga tal cual, porque otro modelo no arregla una clave invalida ni
        una peticion demasiado grande.
        """
        ultimo_error: Exception | None = None

        for modelo in self._modelos_por_orden():
            try:
                respuesta = self._invocar_modelo(modelo, mensajes, pedir_json)
            except Exception as error:
                espera = self._espera_de_limite(error)
                if espera is None:
                    raise

                ultimo_error = error

                # Espera corta: se reintenta el mismo modelo una vez, con
                # medio segundo de margen porque el reloj de Groq y el
                # nuestro no estan sincronizados.
                if espera <= self.ESPERA_MAXIMA_MISMO_MODELO:
                    time.sleep(espera + 0.5)
                    try:
                        respuesta = self._invocar_modelo(modelo, mensajes, pedir_json)
                    except Exception as error_reintento:
                        if self._espera_de_limite(error_reintento) is None:
                            raise
                        ultimo_error = error_reintento
                        self._marcar_enfriamiento(modelo, espera)
                        continue
                else:
                    self._marcar_enfriamiento(modelo, espera)
                    continue

            self._modelo_usado = modelo
            return respuesta

        # Todos los modelos limitados: se propaga el ultimo 429 para que la
        # capa superior lo traduzca y decida si reintentar.
        raise ultimo_error  # type: ignore[misc]

    def _invocar_modelo(self, modelo: str, mensajes: list, pedir_json: bool):
        """Realiza la llamada a un modelo concreto, con o sin modo JSON."""
        # Los parametros comunes se arman aparte para no duplicar la llamada.
        parametros = {
            "model": modelo,
            "temperature": self.TEMPERATURA,
            "max_tokens": self.MAXIMO_TOKENS_DE_SALIDA,
            "messages": mensajes,
        }

        # El modo JSON solo se anade cuando se va a pedir, porque enviarlo con
        # valor nulo no equivale a omitirlo en todas las implementaciones.
        if pedir_json:
            parametros["response_format"] = {"type": "json_object"}

        return self._cliente.chat.completions.create(**parametros)

    def _espera_de_limite(self, error: Exception) -> float | None:
        """
        Devuelve los segundos de espera si el error es un 429, o None si no lo es.

        Un 429 que no dice cuanto esperar se trata como largo (un minuto): sin
        dato, lo prudente es no quedarse esperando y probar con otro modelo.
        """
        texto = str(error)
        if "429" not in texto and "rate limit" not in texto.lower():
            return None

        segundos = segundos_hasta_reintento(texto)
        return 60.0 if segundos is None else segundos

    def _modelos_por_orden(self) -> list:
        """Modelos a probar: los disponibles primero, respetando la preferencia."""
        ahora = time.monotonic()
        todos = list(self._configuracion.lista_de_modelos)

        with self._cerrojo_enfriamiento:
            libres = [m for m in todos if self._enfriamiento.get(m, 0.0) <= ahora]
            # Si todos estan en enfriamiento se intenta igualmente, el que antes
            # se reponga primero: el plazo es una estimacion de Groq y puede
            # haberse quedado corto, y rendirse sin intentarlo seria peor.
            if not libres:
                libres = sorted(todos, key=lambda m: self._enfriamiento.get(m, 0.0))
        return libres

    def _marcar_enfriamiento(self, modelo: str, segundos: float) -> None:
        """Anota que un modelo no debe usarse hasta pasado el plazo dado."""
        with self._cerrojo_enfriamiento:
            self._enfriamiento[modelo] = time.monotonic() + segundos

    def _es_rechazo_de_modo_json(self, error: Exception) -> bool:
        """
        Indica si el error se debe a que el modelo no admite el modo JSON.

        Se distingue por el texto porque los proveedores no comparten codigos
        de error para este caso. La comprobacion es deliberadamente estrecha:
        solo se reintenta cuando el mensaje menciona el parametro en cuestion,
        de modo que un fallo de credenciales o de cuota no provoque una segunda
        llamada inutil que consumiria cupo.
        """
        texto = str(error).lower()
        menciona_parametro = "response_format" in texto or "json_object" in texto
        parece_peticion_invalida = (
            "400" in texto
            or "unsupported" in texto
            or "not supported" in texto
            or "invalid" in texto
        )
        return menciona_parametro and parece_peticion_invalida

    def _traducir_error(self, error: Exception) -> ErrorProveedorLLM:
        """
        Convierte la excepcion del SDK en un error de dominio con mensaje util.

        Se detecta en particular el exceso de ritmo porque es el fallo esperable
        cuando una clase entera pulsa el boton casi a la vez, y merece un
        tratamiento distinto -reintentar- que un error de credenciales.
        """
        texto = str(error).lower()

        # El codigo 413 indica que la peticion excede el tamano admitido. Con
        # sistemas agenticos aparece aunque el mensaje enviado sea pequeno,
        # porque las busquedas que realizan incorporan sus resultados al
        # contexto y es ese total, y no lo que envia la aplicacion, lo que
        # acaba desbordando el limite.
        if "413" in texto or "too large" in texto or "request_too_large" in texto:
            return ErrorProveedorLLM(
                "La peticion resulto demasiado grande para el modelo.",
                es_peticion_demasiado_grande=True,
            )

        # El codigo 429 y las menciones a cuota indican limite de ritmo.
        if "429" in texto or "rate limit" in texto or "quota" in texto:
            return ErrorProveedorLLM(
                "El servicio está recibiendo muchas peticiones a la vez.",
                es_limite_de_ritmo=True,
            )

        # Credenciales invalidas: el mensaje debe apuntar a la causa real para
        # que quien despliega sepa que revisar el panel de secretos.
        if "401" in texto or "unauthorized" in texto or "api key" in texto:
            return ErrorProveedorLLM(
                "La clave de API no es válida o no está configurada."
            )

        # Cualquier otro caso se reporta de forma generica pero identificable.
        return ErrorProveedorLLM(f"No se pudo contactar con el modelo: {error}")


class FabricaProveedores:
    """
    Crea el proveedor adecuado a partir de la configuracion.

    Hoy solo existe una implementacion, pero la fabrica deja preparado el punto
    de extension para anadir, por ejemplo, un proveedor simulado que devuelva
    respuestas fijas y permita ensayar la clase sin consumir cuota.
    """

    @staticmethod
    def crear(configuracion: ConfiguracionLLM) -> ProveedorLLM:
        """Devuelve una instancia de proveedor lista para usar."""
        # Se valida aqui, en el unico punto de creacion, para que ninguna parte
        # de la aplicacion pueda construir un proveedor sin credenciales.
        if not configuracion.esta_configurado:
            raise ErrorProveedorLLM(
                "No hay ninguna clave de API configurada para el modelo."
            )

        # Cualquier fallo de construccion se traduce a un error de dominio para
        # que la interfaz tenga garantizado que solo debe capturar un tipo.
        try:
            return ProveedorCompatibleOpenAI(configuracion)
        except ErrorProveedorLLM:
            raise
        except Exception as error:
            raise ErrorProveedorLLM(
                f"No se pudo crear el proveedor del modelo: {error}"
            ) from error
