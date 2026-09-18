"""Cliente del modelo de lenguaje, intercambiable entre proveedores."""

from abc import ABC, abstractmethod

from openai import OpenAI

from infraestructura.configuracion import ConfiguracionLLM


class ErrorProveedorLLM(Exception):
    """
    Error controlado al hablar con el proveedor.

    Existe para que la interfaz pueda distinguir un fallo del servicio externo
    de un fallo propio de la aplicacion y mostrar al alumno un mensaje util en
    lugar de una traza de Python.
    """

    def __init__(self, mensaje: str, es_limite_de_ritmo: bool = False) -> None:
        """Guarda si el error fue por exceder el ritmo permitido."""
        super().__init__(mensaje)
        # Este indicador permite a la capa superior reintentar solo cuando tiene
        # sentido: si la cuota se agoto, reintentar de inmediato solo empeora.
        self.es_limite_de_ritmo = es_limite_de_ritmo


class ProveedorLLM(ABC):
    """
    Contrato minimo que debe cumplir cualquier proveedor de modelo.

    Se define como clase abstracta para dejar explicito lo unico que la
    aplicacion necesita: enviar un par de mensajes y recibir texto.
    """

    @abstractmethod
    def completar(self, instruccion_sistema: str, mensaje_usuario: str) -> str:
        """Envia la peticion al modelo y devuelve su respuesta en texto plano."""

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

    def __init__(self, configuracion: ConfiguracionLLM) -> None:
        """Construye el cliente con las credenciales indicadas."""
        self._configuracion = configuracion

        # El cliente se crea una sola vez y se reutiliza: abrir una conexion
        # nueva por peticion multiplicaria la latencia percibida.
        self._cliente = OpenAI(
            api_key=configuracion.clave_api,
            base_url=configuracion.url_base,
            timeout=self.TIEMPO_MAXIMO_ESPERA,
            max_retries=0,  # Los reintentos se gestionan en la capa superior.
        )

    @property
    def nombre_modelo(self) -> str:
        """Identificador del modelo configurado."""
        return self._configuracion.modelo

    def completar(self, instruccion_sistema: str, mensaje_usuario: str) -> str:
        """
        Envia una unica peticion al modelo con los dos mensajes indicados.

        Se hace una sola llamada por evaluacion completa, no una por gasto. Esa
        decision es la que permite que treinta alumnos usen la aplicacion a la
        vez: con una llamada por gasto serian cientos de peticiones en rafaga y
        ningun plan gratuito lo soportaria.
        """
        try:
            respuesta = self._cliente.chat.completions.create(
                model=self._configuracion.modelo,
                temperature=self.TEMPERATURA,
                messages=[
                    {"role": "system", "content": instruccion_sistema},
                    {"role": "user", "content": mensaje_usuario},
                ],
                # Se pide explicitamente un objeto JSON. Los proveedores que
                # soportan este modo garantizan sintaxis valida, lo que elimina
                # la causa mas frecuente de fallo al analizar la respuesta.
                response_format={"type": "json_object"},
            )
        except Exception as error:
            # Se traduce cualquier excepcion del SDK a un error propio para que
            # la interfaz no tenga que conocer las clases del proveedor.
            raise self._traducir_error(error) from error

        # Una respuesta sin contenido es anomala pero posible; se trata como
        # error controlado en lugar de dejar que falle al indexar.
        if not respuesta.choices:
            raise ErrorProveedorLLM("El proveedor devolvio una respuesta vacia.")

        contenido = respuesta.choices[0].message.content
        return contenido or ""

    def _traducir_error(self, error: Exception) -> ErrorProveedorLLM:
        """
        Convierte la excepcion del SDK en un error de dominio con mensaje util.

        Se detecta en particular el exceso de ritmo porque es el fallo esperable
        cuando una clase entera pulsa el boton casi a la vez, y merece un
        tratamiento distinto -reintentar- que un error de credenciales.
        """
        texto = str(error).lower()

        # El codigo 429 y las menciones a cuota indican limite de ritmo.
        if "429" in texto or "rate limit" in texto or "quota" in texto:
            return ErrorProveedorLLM(
                "El servicio esta recibiendo muchas peticiones a la vez.",
                es_limite_de_ritmo=True,
            )

        # Credenciales invalidas: el mensaje debe apuntar a la causa real para
        # que quien despliega sepa que revisar el panel de secretos.
        if "401" in texto or "unauthorized" in texto or "api key" in texto:
            return ErrorProveedorLLM(
                "La clave de API no es valida o no esta configurada."
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
        return ProveedorCompatibleOpenAI(configuracion)
