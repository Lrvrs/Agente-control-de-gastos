"""Lectura centralizada de la configuracion y de los secretos."""

from dataclasses import dataclass
from pathlib import Path
import os

import streamlit as st


@dataclass(frozen=True)
class ConfiguracionLLM:
    """Datos necesarios para hablar con el proveedor del modelo de lenguaje."""

    # Clave de API del proveedor. Nunca se muestra en pantalla ni se registra.
    clave_api: str

    # URL base del servicio. Es el parametro que permite cambiar de proveedor
    # sin tocar codigo, porque Groq, Gemini y OpenRouter exponen todos una API
    # compatible con la de OpenAI.
    url_base: str

    # Identificador del modelo concreto dentro de ese proveedor.
    modelo: str

    @property
    def esta_configurado(self) -> bool:
        """Indica si hay credenciales suficientes para intentar una llamada."""
        # Basta con comprobar la clave: la URL y el modelo tienen valor por
        # defecto, pero sin clave ninguna llamada puede prosperar.
        return bool(self.clave_api.strip())


@dataclass(frozen=True)
class ConfiguracionBusqueda:
    """Credenciales de la herramienta de verificacion de hechos."""

    # Clave del servicio de busqueda. Si esta vacia, el agente funciona sin
    # capacidad de verificar y escala los gastos que dependan de un hecho
    # externo, que es una degradacion controlada y no un fallo.
    clave_api: str

    @property
    def esta_configurado(self) -> bool:
        """Indica si el agente dispone de herramienta de busqueda."""
        return bool(self.clave_api.strip())


@dataclass(frozen=True)
class ConfiguracionAula:
    """Parametros que controlan el uso de la aplicacion durante la clase."""

    # Contrasena opcional de acceso. Si esta vacia, la aplicacion queda abierta.
    contrasena: str

    # Numero maximo de evaluaciones que puede lanzar un alumno en su sesion.
    # Protege la cuota compartida del plan gratuito y, de paso, obliga al alumno
    # a pensar que quiere cambiar antes de pulsar el boton.
    limite_evaluaciones: int


class Configuracion:
    """
    Punto unico de acceso a la configuracion de la aplicacion.

    Lee primero de los secretos de Streamlit -que es de donde vendran en el
    despliegue en la nube- y cae a variables de entorno como alternativa. De este
    modo el mismo codigo funciona en Streamlit Community Cloud y en cualquier
    otro entorno sin ramificaciones repartidas por el resto del proyecto.
    """

    # Valores por defecto: apuntan a Groq porque es el proveedor gratuito con
    # menor latencia, que en una demostracion en directo se nota.
    #
    # El modelo NO puede ser llama-3.3-70b-versatile: Groq lo clasifica en su
    # nivel Enterprise y una cuenta gratuita recibe un 404 de modelo
    # inexistente al invocarlo, que es un mensaje enganoso porque el modelo
    # existe y lo que falta es el permiso. Se usa gpt-oss-120b, que si esta
    # disponible en el nivel gratuito.
    URL_BASE_POR_DEFECTO = "https://api.groq.com/openai/v1"
    MODELO_POR_DEFECTO = "openai/gpt-oss-120b"
    LIMITE_EVALUACIONES_POR_DEFECTO = 5

    def __init__(self) -> None:
        """Carga la configuracion una sola vez al construir el objeto."""
        # Se resuelve una unica vez si hay fichero de secretos, para no repetir
        # la comprobacion en cada uno de los valores que se leen despues.
        self._secretos_disponibles = self._existe_fichero_de_secretos()

        self._llm = self._cargar_llm()
        self._busqueda = ConfiguracionBusqueda(
            clave_api=self._leer("busqueda", "clave_api")
        )
        self._aula = self._cargar_aula()

    @property
    def llm(self) -> ConfiguracionLLM:
        """Configuracion del proveedor del modelo de lenguaje."""
        return self._llm

    @property
    def busqueda(self) -> ConfiguracionBusqueda:
        """Configuracion de la herramienta de verificacion."""
        return self._busqueda

    @property
    def aula(self) -> ConfiguracionAula:
        """Configuracion de uso en el aula."""
        return self._aula

    @staticmethod
    def _existe_fichero_de_secretos() -> bool:
        """
        Comprueba si hay algun fichero de secretos antes de acceder a st.secrets.

        Esta comprobacion previa es imprescindible y no es una precaucion
        teorica: cuando no existe fichero de secretos, Streamlit no se limita a
        lanzar una excepcion, sino que ademas escribe un mensaje de error en
        ingles directamente en la pagina. Ese mensaje es invisible para un
        bloque try y acabaria mostrandose al alumno tantas veces como valores
        se intenten leer. Mirando primero el sistema de ficheros se evita del
        todo entrar en ese camino.

        Se consultan las dos rutas que utiliza Streamlit: la del proyecto y la
        del directorio personal del usuario, que es la que emplea Streamlit
        Community Cloud para depositar lo que se escribe en su panel.
        """
        rutas_posibles = (
            Path(".streamlit") / "secrets.toml",
            Path.home() / ".streamlit" / "secrets.toml",
        )
        return any(ruta.exists() for ruta in rutas_posibles)

    def _leer(self, seccion: str, clave: str, por_defecto: str = "") -> str:
        """
        Busca un valor en los secretos de Streamlit y, si no esta, en el entorno.

        El orden importa: en el despliegue en la nube el valor bueno esta en los
        secretos, mientras que las variables de entorno son la alternativa para
        cualquier otro entorno de ejecucion.
        """
        # Primera fuente: los secretos de Streamlit, solo si realmente existen.
        if self._secretos_disponibles:
            try:
                if seccion in st.secrets and clave in st.secrets[seccion]:
                    return str(st.secrets[seccion][clave])
            except Exception:
                # Un fichero presente pero mal formado se trata como ausencia de
                # valor: es preferible arrancar con los valores por defecto que
                # dejar la aplicacion inservible por una coma mal puesta.
                pass

        # Segunda fuente: variable de entorno con el nombre SECCION_CLAVE.
        nombre_variable = f"{seccion.upper()}_{clave.upper()}"
        return os.environ.get(nombre_variable, por_defecto)

    def _cargar_llm(self) -> ConfiguracionLLM:
        """Construye la configuracion del proveedor a partir de las fuentes."""
        return ConfiguracionLLM(
            clave_api=self._leer("llm", "clave_api"),
            url_base=self._leer("llm", "url_base", self.URL_BASE_POR_DEFECTO),
            modelo=self._leer("llm", "modelo", self.MODELO_POR_DEFECTO),
        )

    def _cargar_aula(self) -> ConfiguracionAula:
        """Construye la configuracion de aula a partir de las fuentes."""
        # El limite llega como texto y puede venir mal escrito; ante cualquier
        # duda se aplica el valor por defecto en lugar de dejar la aplicacion
        # sin limite, que es el escenario que agota la cuota compartida.
        limite_bruto = self._leer(
            "aula", "limite_evaluaciones", str(self.LIMITE_EVALUACIONES_POR_DEFECTO)
        )
        try:
            limite = int(limite_bruto)
        except ValueError:
            limite = self.LIMITE_EVALUACIONES_POR_DEFECTO

        return ConfiguracionAula(
            contrasena=self._leer("aula", "contrasena"),
            limite_evaluaciones=max(1, limite),
        )
