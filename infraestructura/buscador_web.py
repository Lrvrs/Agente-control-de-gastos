"""Herramienta de búsqueda web que el agente utiliza para verificar hechos."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List

import httpx


@dataclass(frozen=True)
class ResultadoBusqueda:
    """Lo que la herramienta devuelve para una consulta concreta."""

    # Consulta tal y como el agente pidio verificarla.
    consulta: str

    # Sintesis breve de lo encontrado, ya redactada por el buscador.
    resumen: str

    # Fragmentos de las paginas mas relevantes, con su origen.
    fragmentos: List[str] = field(default_factory=list)

    # Direcciones de las fuentes, para poder citarlas en el veredicto.
    fuentes: List[str] = field(default_factory=list)

    @property
    def hay_informacion(self) -> bool:
        """Indica si la busqueda devolvio algo aprovechable."""
        return bool(self.resumen.strip() or self.fragmentos)

    def a_bloque_para_modelo(self) -> str:
        """Formatea el resultado para incorporarlo al contexto del agente."""
        # Sin informacion se declara de forma explicita. Es importante: ante un
        # hueco el modelo tiende a rellenarlo con lo que recuerda, mientras que
        # ante una afirmacion clara de que no se encontro nada hace lo que debe,
        # que es escalar el gasto en lugar de inventarse la respuesta.
        if not self.hay_informacion:
            return f"CONSULTA: {self.consulta}\nRESULTADO: sin información disponible."

        lineas = [f"CONSULTA: {self.consulta}"]
        if self.resumen.strip():
            lineas.append(f"RESUMEN: {self.resumen.strip()}")
        for fragmento in self.fragmentos:
            lineas.append(f"- {fragmento}")
        if self.fuentes:
            lineas.append(f"FUENTES: {', '.join(self.fuentes)}")
        return "\n".join(lineas)


class BuscadorWeb(ABC):
    """
    Contrato de la herramienta de busqueda.

    Se define como abstraccion para que la aplicacion no dependa de un proveedor
    concreto, igual que ocurre con el modelo de lenguaje. Tambien permite
    sustituirlo por una implementacion simulada al probar, sin consumir cuota.
    """

    @abstractmethod
    def buscar(self, consulta: str) -> ResultadoBusqueda:
        """Ejecuta una consulta y devuelve lo encontrado."""

    @property
    @abstractmethod
    def nombre(self) -> str:
        """Identificador del servicio, para mostrarlo como trazabilidad."""

    @property
    def puede_verificar(self) -> bool:
        """
        Indica si esta herramienta es capaz de comprobar algo.

        Permite a quien la use saltarse la fase de planificacion cuando no hay
        nada que buscar. No es una optimizacion menor: esa fase consume una
        llamada al modelo, y sin clave configurada seria una llamada gastada en
        preparar consultas que nadie va a ejecutar.
        """
        return True


class BuscadorNulo(BuscadorWeb):
    """
    Implementacion que no busca nada.

    Es la que se utiliza cuando no hay clave configurada. En lugar de impedir
    que la aplicacion arranque, devuelve resultados vacios y deja que el agente
    haga lo correcto ante la falta de informacion: escalar a revision. De este
    modo la herramienta de verificacion es opcional y su ausencia se comporta
    como una limitacion declarada, no como una averia.
    """

    @property
    def nombre(self) -> str:
        """Identificador del buscador inactivo."""
        return "sin verificación"

    @property
    def puede_verificar(self) -> bool:
        """El buscador nulo no comprueba nada."""
        return False

    def buscar(self, consulta: str) -> ResultadoBusqueda:
        """Devuelve siempre un resultado vacio."""
        return ResultadoBusqueda(consulta=consulta, resumen="")


class BuscadorTavily(BuscadorWeb):
    """
    Buscador apoyado en la API de Tavily.

    Se elige este servicio por dos motivos practicos. Devuelve el contenido ya
    extraido y sintetizado, en lugar de una lista de enlaces que habria que
    descargar y limpiar, lo que reduce mucho el texto que acaba en el contexto
    del modelo. Y su plan gratuito no requiere tarjeta, condicion necesaria para
    una demostracion docente.
    """

    URL = "https://api.tavily.com/search"

    # Espera maxima por consulta. Corta a proposito: varias busquedas encadenadas
    # multiplicarian la espera, y en clase una pantalla parada se percibe como
    # una aplicacion rota.
    TIEMPO_MAXIMO_ESPERA = 12.0

    # Numero de resultados por consulta. Tres bastan para confirmar o descartar
    # un hecho y mantienen acotado el tamano del contexto, que es justamente lo
    # que desbordaba con los sistemas agenticos de caja negra.
    RESULTADOS_POR_CONSULTA = 3

    # Longitud maxima de cada fragmento. Recortar aqui evita que una pagina
    # extensa arrastre miles de tokens hasta la llamada al modelo.
    LONGITUD_MAXIMA_FRAGMENTO = 320

    def __init__(self, clave_api: str) -> None:
        """Guarda la clave del servicio."""
        self._clave = clave_api

    @property
    def nombre(self) -> str:
        """Identificador del servicio."""
        return "Tavily"

    def buscar(self, consulta: str) -> ResultadoBusqueda:
        """
        Ejecuta la consulta contra el servicio.

        Un fallo de red o del servicio no interrumpe la evaluacion: se devuelve
        un resultado vacio y el agente escalara el gasto por falta de
        informacion. Es preferible una resolucion prudente a una pantalla rota
        en mitad de la clase.
        """
        cuerpo = {
            "api_key": self._clave,
            "query": consulta,
            # Se pide la sintesis que elabora el propio servicio: ahorra al
            # modelo el trabajo de leer tres paginas enteras.
            "include_answer": True,
            "search_depth": "basic",
            "max_results": self.RESULTADOS_POR_CONSULTA,
        }

        try:
            respuesta = httpx.post(
                self.URL, json=cuerpo, timeout=self.TIEMPO_MAXIMO_ESPERA
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
        except Exception:
            # Cualquier fallo se traduce en ausencia de informacion.
            return ResultadoBusqueda(consulta=consulta, resumen="")

        return self._interpretar(consulta, datos)

    def _interpretar(self, consulta: str, datos: dict) -> ResultadoBusqueda:
        """Extrae del JSON del servicio lo que necesita el agente."""
        # La sintesis puede venir vacia si el servicio no la genero.
        resumen = str(datos.get("answer") or "").strip()

        fragmentos: List[str] = []
        fuentes: List[str] = []

        for resultado in datos.get("results", [])[: self.RESULTADOS_POR_CONSULTA]:
            if not isinstance(resultado, dict):
                continue

            # Se recorta el contenido para acotar el tamano del contexto.
            contenido = str(resultado.get("content") or "").strip()
            if contenido:
                fragmentos.append(contenido[: self.LONGITUD_MAXIMA_FRAGMENTO])

            url = str(resultado.get("url") or "").strip()
            if url:
                fuentes.append(url)

        return ResultadoBusqueda(
            consulta=consulta,
            resumen=resumen,
            fragmentos=fragmentos,
            fuentes=fuentes,
        )


class BuscadorConCache(BuscadorWeb):
    """
    Envoltorio que recuerda las consultas ya realizadas.

    Es la pieza que hace viable el uso en aula. Treinta alumnos evaluando el
    mismo fichero formulan exactamente las mismas consultas, de modo que una
    sola busqueda real sirve para todos. Sin esta capa, la misma clase agotaria
    la cuota mensual del plan gratuito en una tarde.

    La cache vive en memoria del proceso y se comparte entre todas las sesiones
    de la aplicacion desplegada, que es justo lo que interesa.
    """

    # Techo de entradas, para que una sesion muy larga no haga crecer la
    # memoria del contenedor sin limite.
    MAXIMO_ENTRADAS = 500

    def __init__(self, buscador: BuscadorWeb) -> None:
        """Envuelve un buscador real."""
        self._buscador = buscador
        self._entradas: Dict[str, ResultadoBusqueda] = {}

    @property
    def nombre(self) -> str:
        """Identificador del buscador envuelto."""
        return self._buscador.nombre

    @property
    def puede_verificar(self) -> bool:
        """Delega en el buscador envuelto."""
        return self._buscador.puede_verificar

    @property
    def consultas_cacheadas(self) -> int:
        """Numero de consultas distintas ya resueltas."""
        return len(self._entradas)

    def buscar(self, consulta: str) -> ResultadoBusqueda:
        """Devuelve el resultado guardado o lo solicita al buscador real."""
        # La clave se normaliza para que diferencias de mayusculas o espacios
        # no provoquen dos busquedas de lo mismo.
        clave = " ".join(consulta.lower().split())

        if clave in self._entradas:
            return self._entradas[clave]

        resultado = self._buscador.buscar(consulta)

        # Desalojo sencillo de la entrada mas antigua al alcanzar el techo.
        if len(self._entradas) >= self.MAXIMO_ENTRADAS:
            del self._entradas[next(iter(self._entradas))]

        self._entradas[clave] = resultado
        return resultado


class FabricaBuscadores:
    """Crea el buscador adecuado segun haya o no credenciales configuradas."""

    @staticmethod
    def crear(clave_api: str) -> BuscadorWeb:
        """Devuelve un buscador real con cache, o el buscador nulo."""
        # Sin clave se devuelve el buscador inactivo. La verificacion es una
        # capacidad opcional del agente y su ausencia debe degradar el
        # comportamiento, no impedir que la aplicacion funcione.
        if not clave_api or not clave_api.strip():
            return BuscadorNulo()

        return BuscadorConCache(BuscadorTavily(clave_api.strip()))
