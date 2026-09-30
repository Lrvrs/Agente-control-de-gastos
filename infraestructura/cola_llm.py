"""Cola global que limita cuantas llamadas al modelo viajan a la vez."""

import threading
from contextlib import contextmanager
from typing import Callable, Iterator

from infraestructura.proveedor_llm import ErrorProveedorLLM, ProveedorLLM


class ColaGlobal:
    """
    Semaforo compartido por todas las sesiones del proceso.

    Streamlit ejecuta cada sesion en su propio hilo pero dentro de un unico
    proceso, asi que un semaforo creado una vez y compartido ve a todos los
    alumnos. Sin el, veinte pulsaciones simultaneas son veinte peticiones a la
    vez contra un limite de 30 por minuto y 8.000 tokens por minuto: la
    mayoria recibiria un 429 y la clase veria fallos justo al empezar. Con el,
    solo unas pocas viajan a la vez y el resto espera su turno, que es una
    espera y no un error.
    """

    # Llamadas simultaneas permitidas. Tres deja margen bajo el limite de
    # tokens por minuto sin que la cola se alargue de forma perceptible.
    MAXIMO_SIMULTANEAS = 3

    # Espera maxima por un turno, en segundos. Pasado ese tiempo se devuelve
    # un error de ritmo, que la capa superior ya sabe reintentar: esperar sin
    # fin dejaria al alumno mirando una pantalla que parece colgada.
    ESPERA_MAXIMA = 90.0

    def __init__(self, maximo: int | None = None) -> None:
        """Crea el semaforo con el tope indicado o el de la clase."""
        self._semaforo = threading.BoundedSemaphore(maximo or self.MAXIMO_SIMULTANEAS)

    @contextmanager
    def turno(
        self,
        al_esperar: Callable[[], None] | None = None,
        al_reanudar: Callable[[], None] | None = None,
    ) -> Iterator[None]:
        """
        Reserva un hueco mientras dura el bloque.

        Las dos funciones avisan a la pantalla solo cuando de verdad hay que
        esperar: si hay hueco libre no se llama a ninguna, para que el caso
        normal no parpadee con un mensaje de cola que dura un instante.
        """
        if not self._semaforo.acquire(blocking=False):
            if al_esperar:
                al_esperar()

            obtenido = self._semaforo.acquire(timeout=self.ESPERA_MAXIMA)

            if al_reanudar:
                al_reanudar()

            if not obtenido:
                raise ErrorProveedorLLM(
                    "Hay muchas evaluaciones en curso y no ha llegado tu turno.",
                    es_limite_de_ritmo=True,
                )

        try:
            yield
        finally:
            # El hueco se libera siempre, incluso si la llamada falla: un
            # error que lo retuviera iria cerrando la cola para todos.
            self._semaforo.release()


class ProveedorConCola(ProveedorLLM):
    """
    Envuelve a un proveedor para que sus llamadas pasen por la cola global.

    Es un decorador y no una modificacion del proveedor real para que el resto
    de la aplicacion no note la diferencia: sigue recibiendo un ProveedorLLM.
    """

    def __init__(
        self,
        proveedor: ProveedorLLM,
        cola: ColaGlobal,
        al_esperar: Callable[[], None] | None = None,
        al_reanudar: Callable[[], None] | None = None,
    ) -> None:
        """Guarda el proveedor real, la cola y los avisos a la pantalla."""
        self._proveedor = proveedor
        self._cola = cola
        self._al_esperar = al_esperar
        self._al_reanudar = al_reanudar

    @property
    def nombre_modelo(self) -> str:
        """Identificador del modelo del proveedor envuelto."""
        return self._proveedor.nombre_modelo

    def completar(self, *args, **kwargs) -> str:
        """Espera turno y delega la llamada en el proveedor real."""
        with self._cola.turno(self._al_esperar, self._al_reanudar):
            return self._proveedor.completar(*args, **kwargs)
