"""Control del numero de evaluaciones que puede lanzar cada alumno."""

import streamlit as st


class ControlUso:
    """
    Limita las evaluaciones por sesion para proteger la cuota compartida.

    Todos los alumnos de la clase comparten una unica clave de API, de modo que
    la cuota es un recurso comun. Sin limite, una sola persona pulsando el boton
    repetidamente puede dejar sin servicio al resto.

    Tiene ademas un efecto pedagogico buscado: saber que quedan tres intentos
    obliga a decidir que se quiere cambiar en la politica antes de pulsar, en
    lugar de probar al azar.
    """

    # Clave con la que se guarda el contador en el estado de la sesion.
    CLAVE_CONTADOR = "control_uso_evaluaciones_realizadas"

    def __init__(self, limite: int) -> None:
        """Fija el limite y asegura que el contador existe en la sesion."""
        self._limite = limite

        # El estado de sesion de Streamlit es propio de cada pestana del
        # navegador, asi que este contador es individual de cada alumno aunque
        # todos usen la misma aplicacion desplegada.
        if self.CLAVE_CONTADOR not in st.session_state:
            st.session_state[self.CLAVE_CONTADOR] = 0

    @property
    def realizadas(self) -> int:
        """Numero de evaluaciones ya consumidas en esta sesion."""
        return int(st.session_state[self.CLAVE_CONTADOR])

    @property
    def limite(self) -> int:
        """Numero maximo de evaluaciones permitidas."""
        return self._limite

    @property
    def restantes(self) -> int:
        """Evaluaciones que aun puede lanzar el alumno."""
        # Se acota a cero para que nunca se muestre un numero negativo.
        return max(0, self._limite - self.realizadas)

    @property
    def puede_evaluar(self) -> bool:
        """Indica si queda cupo disponible."""
        return self.restantes > 0

    def registrar_uso(self) -> None:
        """
        Descuenta una evaluacion del cupo.

        Se llama solo cuando ha habido una llamada real al modelo. Los
        resultados servidos desde la cache no consumen cupo, porque no consumen
        cuota del proveedor y penalizarlos desincentivaria justo lo que interesa.
        """
        st.session_state[self.CLAVE_CONTADOR] = self.realizadas + 1
