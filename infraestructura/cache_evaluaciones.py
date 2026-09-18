"""Cache en memoria de evaluaciones ya realizadas."""

from typing import Dict, Optional

from dominio.veredicto import ResultadoEvaluacion


class CacheEvaluaciones:
    """
    Guarda resultados indexados por la combinacion de politica y gastos.

    Su motivo de existir es economico y pedagogico a la vez. Durante la clase,
    buena parte de los alumnos pulsara el boton de evaluar antes de modificar
    nada: todos ellos comparten exactamente la misma politica por defecto y el
    mismo juego de gastos, de modo que una sola llamada real al modelo sirve
    para todos. Eso descarga la cuota compartida justo en el minuto de mayor
    concurrencia, que es el arranque de la sesion.

    La cache vive en memoria del proceso y, por tanto, se comparte entre todas
    las sesiones de la misma aplicacion desplegada. Es intencionado: si fuese
    por sesion no serviria de nada para el caso que interesa.
    """

    # Numero maximo de entradas. Con una clase de cuarenta alumnos y varias
    # politicas distintas cada uno, este techo no se alcanza; existe para que
    # una sesion muy larga no haga crecer la memoria del contenedor sin limite.
    MAXIMO_ENTRADAS = 200

    def __init__(self) -> None:
        """Inicializa el almacen vacio."""
        # Se usa un diccionario ordinario: desde Python 3.7 conserva el orden de
        # insercion, lo que permite descartar la entrada mas antigua sin
        # estructuras adicionales.
        self._entradas: Dict[str, ResultadoEvaluacion] = {}

    def _construir_clave(self, huella_politica: str, huella_gastos: str) -> str:
        """Compone la clave que identifica de forma unica una evaluacion."""
        # La clave incluye ambas huellas porque el resultado depende de las dos:
        # la misma politica sobre gastos distintos da veredictos distintos.
        return f"{huella_politica}::{huella_gastos}"

    def obtener(
        self, huella_politica: str, huella_gastos: str
    ) -> Optional[ResultadoEvaluacion]:
        """Devuelve el resultado guardado, o None si no hay ninguno."""
        clave = self._construir_clave(huella_politica, huella_gastos)
        return self._entradas.get(clave)

    def guardar(
        self,
        huella_politica: str,
        huella_gastos: str,
        resultado: ResultadoEvaluacion,
    ) -> None:
        """Almacena un resultado, desalojando el mas antiguo si hace falta."""
        # Politica de desalojo sencilla: se elimina la entrada mas antigua.
        # No se implementa un algoritmo mas fino porque el volumen no lo exige y
        # la complejidad adicional no se pagaria con ninguna mejora observable.
        if len(self._entradas) >= self.MAXIMO_ENTRADAS:
            clave_mas_antigua = next(iter(self._entradas))
            del self._entradas[clave_mas_antigua]

        clave = self._construir_clave(huella_politica, huella_gastos)
        self._entradas[clave] = resultado

    @property
    def numero_de_entradas(self) -> int:
        """Entradas vivas en la cache, util para mostrar en un panel tecnico."""
        return len(self._entradas)
