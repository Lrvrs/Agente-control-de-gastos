"""
Agente de control de gastos - ESIC University.

Punto de entrada de la aplicacion. Su unica responsabilidad es configurar la
pagina y delegar en la vista principal: toda la logica vive en los paquetes
dominio, infraestructura, aplicacion e interfaz.

Ejecucion prevista: Streamlit Community Cloud. La aplicacion no requiere nada
instalado en el equipo de quien la usa; el alumno accede por una URL.
"""

import streamlit as st

from interfaz.vista_principal import VistaPrincipal


def configurar_pagina() -> None:
    """Fija el titulo, el icono y la disposicion de la pagina."""
    # La configuracion de pagina debe ser la primera llamada a Streamlit del
    # script; en caso contrario la biblioteca lanza una excepcion.
    st.set_page_config(
        page_title="Agente de control de gastos · ESIC",
        page_icon="📋",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def main() -> None:
    """Arranca la aplicacion."""
    configurar_pagina()

    # La vista se construye en cada reejecutado del script, que es el modelo de
    # funcionamiento de Streamlit; los objetos costosos se cachean dentro.
    vista = VistaPrincipal()
    vista.renderizar()


# Streamlit ejecuta el fichero como script, no como modulo importado, de modo
# que esta guarda es la que dispara la aplicacion.
if __name__ == "__main__":
    main()
