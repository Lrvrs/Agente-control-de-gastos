"""Tope diario de evaluaciones reales para toda el aula, no por alumno."""

import threading
from datetime import date, datetime, timezone
from typing import Callable


class ErrorCuotaDiaria(Exception):
    """El aula ha gastado las evaluaciones reales de hoy."""


class CuotaDiariaGlobal:
    """
    Cuenta las evaluaciones que han llegado de verdad al modelo en el dia.

    El cupo por alumno (ControlUso) vive en su sesion y se reinicia al recargar
    la pagina, asi que no protege la cuota diaria que todos comparten: veinte
    alumnos con cinco intentos son cien evaluaciones, y una recarga devuelve
    los cinco. Este contador vive en el proceso, como la cache, y por eso ve a
    todos a la vez y sobrevive a los refrescos.

    El dia se mide en UTC porque es cuando el proveedor repone su cupo diario:
    contar por hora local abriria una ventana de horas en la que el contador
    dice que hay cupo y el proveedor ya no lo tiene, o al reves.

    Se pierde si la app se reinicia o se duerme. Es inocuo: el proveedor sigue
    aplicando su propio limite, y lo unico que se pierde es el aviso amable.
    """

    def __init__(
        self,
        limite: int,
        hoy: Callable[[], date] | None = None,
    ) -> None:
        """Fija el tope; `hoy` se inyecta para poder probar el cambio de dia."""
        self._limite = limite
        self._hoy = hoy or (lambda: datetime.now(timezone.utc).date())
        self._dia = self._hoy()
        self._realizadas = 0
        self._cerrojo = threading.Lock()

    def _reiniciar_si_cambio_el_dia(self) -> None:
        """Pone el contador a cero al empezar un dia nuevo. Exige el cerrojo."""
        hoy = self._hoy()
        if hoy != self._dia:
            self._dia = hoy
            self._realizadas = 0

    @property
    def limite(self) -> int:
        """Evaluaciones reales permitidas al dia."""
        return self._limite

    @property
    def realizadas(self) -> int:
        """Evaluaciones reales hechas hoy."""
        with self._cerrojo:
            self._reiniciar_si_cambio_el_dia()
            return self._realizadas

    @property
    def agotada(self) -> bool:
        """Indica si ya no quedan evaluaciones reales hoy."""
        return self.realizadas >= self._limite

    def registrar(self) -> None:
        """
        Anota una evaluacion real.

        Se llama despues de la llamada y no antes: la mayoria de las pulsaciones
        las sirve la cache y no deben contar. El precio es que varias
        evaluaciones simultaneas justo en el limite pueden pasarse en una o dos,
        y no merece un cerrojo que reservase huecos por adelantado.
        """
        with self._cerrojo:
            self._reiniciar_si_cambio_el_dia()
            self._realizadas += 1
