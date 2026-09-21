"""Composicion de la pantalla principal de la aplicacion."""

import hashlib
from pathlib import Path

import streamlit as st

from aplicacion.control_uso import ControlUso
from aplicacion.redactor_cuerpo_correo import GeneradorCuerpoCorreo
from aplicacion.servicio_evaluacion import ServicioEvaluacion
from dominio.correo import RedactorCorreo
from dominio.gasto import ConjuntoGastos
from dominio.politica import Politica
from dominio.veredicto import (
    Correccion,
    ResultadoEvaluacion,
    corregir_decision,
    firma_estructural,
)
from infraestructura.buscador_web import FabricaBuscadores
from infraestructura.cache_evaluaciones import CacheEvaluaciones
from infraestructura.configuracion import Configuracion
from infraestructura.proveedor_llm import ErrorProveedorLLM, FabricaProveedores
from infraestructura.repositorio_datos import ErrorFicheroGastos, RepositorioDatos
from interfaz.componentes import Componentes
from interfaz.estilos import GestorEstilos, Paleta


class VistaPrincipal:
    """
    Orquesta la pantalla: estado, barra lateral, controles y resultados.

    Concentra aqui todo el trato con `st.session_state` para que el resto del
    proyecto no dependa de Streamlit y siga siendo codigo Python corriente.
    """

    # Claves del estado de sesion. Se declaran como constantes para evitar
    # erratas silenciosas, que son el fallo tipico al usar cadenas sueltas.
    CLAVE_RESULTADO_ACTUAL = "resultado_actual"
    CLAVE_RESULTADO_ANTERIOR = "resultado_anterior"
    # Almacen del texto de la politica. NO es la clave del widget, y esa
    # separacion es deliberada: Streamlit borra del estado de sesion las claves
    # de los widgets que no se dibujan en una ejecucion, de modo que guardar ahi
    # el dato lo hace vulnerable a cualquier cambio en el orden de pintado. Con
    # el valor en una clave propia, que la biblioteca nunca toca, el contenido
    # sobrevive pase lo que pase en la pantalla.
    CLAVE_TEXTO_POLITICA = "politica_almacenada"

    # Clave del cuadro de texto. Puede ser descartada por Streamlit sin
    # consecuencias, porque el valor bueno esta en la anterior.
    CLAVE_WIDGET_POLITICA = "widget_politica"
    CLAVE_ACCESO_CONCEDIDO = "acceso_concedido"
    CLAVE_GASTOS_SUBIDOS = "gastos_subidos"
    CLAVE_NOMBRE_FICHERO = "nombre_fichero_subido"
    CLAVE_CORREO_ABIERTO = "correo_abierto"
    CLAVE_CORREOS_ENVIADOS = "correos_enviados"
    CLAVE_DECISIONES = "decisiones_alumno"
    CLAVE_TRAZA = "traza_verificacion"
    CLAVE_BIENVENIDA_CERRADA = "bienvenida_cerrada"
    CLAVE_RESOLUCION_ABIERTA = "resolucion_abierta"

    def __init__(self) -> None:
        """Construye las dependencias de la vista una sola vez por ejecucion."""
        self._configuracion = Configuracion()
        self._repositorio = RepositorioDatos()

        # La cache se guarda como recurso de Streamlit para que sobreviva a los
        # reejecutados de script y se comparta entre todas las sesiones, que es
        # justamente lo que permite que la primera evaluacion del aula sirva
        # para todos los alumnos que no hayan tocado la politica.
        self._cache = VistaPrincipal._obtener_cache_compartida(firma_estructural())

        # El buscador tambien se comparte entre sesiones, porque su cache
        # interna es lo que hace viable el uso en aula: treinta alumnos
        # evaluando el mismo fichero formulan las mismas consultas y una
        # sola busqueda real sirve para todos.
        self._buscador = VistaPrincipal._obtener_buscador_compartido(
            self._configuracion.busqueda.clave_api
        )

        # Control de cupo, individual de cada alumno.
        self._control_uso = ControlUso(self._configuracion.aula.limite_evaluaciones)

    @staticmethod
    @st.cache_resource
    def _obtener_cache_compartida(firma: str) -> CacheEvaluaciones:
        """Devuelve la unica instancia de cache del proceso."""
        # El decorador garantiza que Streamlit construye el objeto una sola vez
        # y devuelve siempre la misma referencia a todas las sesiones.
        #
        # La firma estructural forma parte de la clave a proposito: al cambiar
        # la forma de las entidades, Streamlit construye una cache nueva y
        # descarta la anterior, que contendria objetos de la version antigua.
        return CacheEvaluaciones()

    @staticmethod
    @st.cache_resource
    def _obtener_buscador_compartido(clave_api: str):
        """Devuelve la unica instancia de buscador del proceso."""
        # La clave forma parte de la firma para que, si se cambia en el panel de
        # secretos, Streamlit construya un buscador nuevo en lugar de seguir
        # usando el anterior con las credenciales viejas.
        return FabricaBuscadores.crear(clave_api)

    # ------------------------------------------------------------------
    # Punto de entrada
    # ------------------------------------------------------------------

    def renderizar(self) -> None:
        """Pinta la pantalla completa, de arriba abajo."""
        # El estilo debe aplicarse antes que cualquier otro elemento para que no
        # se vea un parpadeo con el aspecto por defecto de Streamlit.
        GestorEstilos.aplicar()
        self._preparar_estado()

        # Puerta de acceso opcional. Si no hay contrasena configurada, no se
        # muestra nada y la aplicacion queda abierta.
        if not self._verificar_acceso():
            return

        self._renderizar_barra_lateral()

        Componentes.banner_superior()
        self._renderizar_cabecera()

        # El selector de fichero va antes que el resto porque determina sobre
        # que datos se trabaja en toda la pantalla.
        self._renderizar_selector_fichero()
        gastos = self._gastos_en_curso()

        self._renderizar_resumen(gastos)
        self._renderizar_editor_politica(gastos)
        self._renderizar_resultados(gastos)

        # La bienvenida se abre al final, cuando el resto de la pantalla ya se
        # ha compuesto. El orden importa y no por estetica: Streamlit descarta
        # el estado de los widgets que no se dibujan en una ejecucion, de modo
        # que interrumpir el pintado dejaba el cuadro de la politica vacio al
        # cerrar la ventana. Dibujarlo todo y superponer la modal encima evita
        # el problema de raiz, y visualmente es lo mismo porque la modal oscurece
        # el fondo.
        self._mostrar_bienvenida()

    # ------------------------------------------------------------------
    # Estado y acceso
    # ------------------------------------------------------------------

    def _preparar_estado(self) -> None:
        """Inicializa las claves del estado de sesion si es la primera visita."""
        # La politica arranca con el texto por defecto del repositorio; a partir
        # de ahi el alumno la edita y su version vive en la sesion.
        # Se restituye si falta, si vale None o si quedo en blanco. Las tres
        # situaciones son posibles -y la ultima se dio en produccion, heredada
        # de una version anterior que perdia el estado del widget- y las tres
        # dejan la aplicacion inservible, porque una politica vacia no se puede
        # construir. Restituir el texto por defecto es siempre preferible a que
        # el alumno se encuentre la pantalla rota.
        if not (st.session_state.get(self.CLAVE_TEXTO_POLITICA) or "").strip():
            st.session_state[self.CLAVE_TEXTO_POLITICA] = (
                self._repositorio.cargar_politica().texto
            )

        # Las dos ultimas ejecuciones se conservan para poder comparar y
        # resaltar que veredictos han cambiado.
        st.session_state.setdefault(self.CLAVE_RESULTADO_ACTUAL, None)
        st.session_state.setdefault(self.CLAVE_RESULTADO_ANTERIOR, None)

        # Y se descartan si proceden de una version anterior del codigo. El
        # estado de sesion sobrevive a los redespliegues, de modo que sin esta
        # comprobacion un veredicto antiguo llegaria a un codigo que espera
        # campos que aquel no tiene.
        self._descartar_resultados_caducados()
        st.session_state.setdefault(self.CLAVE_ACCESO_CONCEDIDO, False)

        # Gastos subidos por el alumno. Mientras valga None se usan los de
        # ejemplo, de modo que la aplicacion es utilizable desde el segundo
        # uno sin necesidad de buscar ningun fichero en el ordenador.
        st.session_state.setdefault(self.CLAVE_GASTOS_SUBIDOS, None)
        st.session_state.setdefault(self.CLAVE_NOMBRE_FICHERO, "")

        # Identificador del gasto cuyo correo se esta mostrando, o None.
        st.session_state.setdefault(self.CLAVE_CORREO_ABIERTO, None)

        # Registro de los correos ya autorizados en esta sesion. Se guarda
        # como lista y no como conjunto para conservar el orden: el orden
        # en que el alumno fue autorizando es informacion util al comentar
        # despues que decisiones tomo y en que secuencia.
        st.session_state.setdefault(self.CLAVE_CORREOS_ENVIADOS, [])

        # Decisiones del alumno, indexadas por identificador de gasto.
        # Se guardan aparte de los veredictos del agente precisamente para
        # poder compararlas: el valor del ejercicio esta en la diferencia
        # entre lo que propuso el sistema y lo que decidio la persona.
        st.session_state.setdefault(self.CLAVE_DECISIONES, {})

        # Traza de la ultima verificacion: que consulto el agente y que
        # encontro. Se conserva para poder mostrarla junto a los veredictos.
        st.session_state.setdefault(self.CLAVE_TRAZA, [])

        # La bienvenida se muestra una vez por sesion. Quien recargue la
        # pagina volvera a verla, que es el comportamiento correcto en un
        # aula: cada alumno la ve al entrar y nadie la ve repetida.
        st.session_state.setdefault(self.CLAVE_BIENVENIDA_CERRADA, False)

        # Gasto cuya resolucion se esta consultando, o None.
        st.session_state.setdefault(self.CLAVE_RESOLUCION_ABIERTA, None)

    def _mostrar_bienvenida(self) -> None:
        """
        Abre la ventana de bienvenida la primera vez que se entra.

        Se invoca al final del renderizado, con el resto de la pantalla ya
        compuesta, y la modal se superpone oscureciendo el fondo.
        """
        if st.session_state[self.CLAVE_BIENVENIDA_CERRADA]:
            return

        # Se da por vista en el momento de abrirla, no al pulsar Continuar. Una
        # modal de Streamlit puede cerrarse tambien con su aspa o pulsando
        # fuera, y en esos dos casos el boton no llega a ejecutarse: la marca
        # quedaba sin poner y la ventana reaparecia en el siguiente repintado,
        # por ejemplo al seleccionar un fichero de gastos.
        st.session_state[self.CLAVE_BIENVENIDA_CERRADA] = True

        # Sin ilustracion no hay bienvenida que mostrar. Se comprueba antes de
        # abrir la ventana para no presentar un marco vacio si el fichero no
        # esta, que es el caso de cualquiera que clone el repositorio.
        ruta = Path(__file__).resolve().parent.parent / "activos" / "bienvenida.png"
        if not ruta.exists():
            st.session_state[self.CLAVE_BIENVENIDA_CERRADA] = True
            return

        @st.dialog("Agente de gastos · ESIC", width="large")
        def ventana() -> None:
            """Contenido de la ventana de bienvenida."""
            Componentes.imagen_a_ancho_completo(st, str(ruta))

            st.markdown(
                '<div class="bienvenida-pie">'
                'Vas a supervisar a un agente que revisa gastos de viaje '
                'contra la política de la empresa.<br>'
                'Él decide; tú confirmas o corriges.'
                '</div>',
                unsafe_allow_html=True,
            )

            if st.button("Continuar", type="primary", use_container_width=True):
                st.rerun()

        ventana()

    def _descartar_resultados_caducados(self) -> None:
        """Elimina de la sesion los resultados de una version anterior."""
        # Basta con examinar un veredicto cualquiera: todos se construyen con la
        # misma clase, de modo que si uno tiene los campos actuales los tienen
        # todos.
        esperados = set(firma_estructural().split(","))

        for clave in (self.CLAVE_RESULTADO_ACTUAL, self.CLAVE_RESULTADO_ANTERIOR):
            resultado = st.session_state.get(clave)
            if resultado is None:
                continue

            veredictos = getattr(resultado, "veredictos", None)
            if not veredictos:
                continue

            muestra = next(iter(veredictos.values()))
            presentes = set(vars(muestra).keys())

            # Si falta algun campo de los que el codigo actual espera leer, el
            # resultado entero se descarta: es preferible que el alumno vuelva a
            # pulsar Evaluar a que la pantalla reviente.
            if not esperados.issubset(presentes):
                st.session_state[clave] = None
                st.session_state[self.CLAVE_CORREO_ABIERTO] = None

    def _verificar_acceso(self) -> bool:
        """
        Comprueba la contrasena de clase, si se ha configurado alguna.

        Devuelve True cuando se puede continuar. La puerta existe porque la URL
        de la aplicacion es publica y la clave de API que consume es compartida.
        """
        contrasena_esperada = self._configuracion.aula.contrasena

        # Sin contrasena configurada, la aplicacion queda abierta.
        if not contrasena_esperada:
            return True

        # Una vez validada, no se vuelve a pedir en la misma sesion.
        if st.session_state[self.CLAVE_ACCESO_CONCEDIDO]:
            return True

        st.markdown(
            '<div class="etiqueta-seccion">Acceso</div>'
            '<div class="titulo-pagina">Agente de gastos</div>',
            unsafe_allow_html=True,
        )
        introducida = st.text_input("Contraseña de clase", type="password")

        # Comparacion directa: el valor no protege ningun dato sensible, solo
        # evita que la URL publica sea consumida por quien no esta en el aula.
        if introducida and introducida == contrasena_esperada:
            st.session_state[self.CLAVE_ACCESO_CONCEDIDO] = True
            st.rerun()

        # Mensaje solo si se ha escrito algo y no coincide, para no mostrar un
        # error al alumno antes de que haya tenido ocasion de teclear.
        if introducida:
            st.error("La contraseña no es correcta.")

        return False

    # ------------------------------------------------------------------
    # Barra lateral
    # ------------------------------------------------------------------

    @staticmethod
    @st.cache_data
    def _huella_del_codigo() -> str:
        """
        Devuelve una huella corta del codigo fuente que se esta ejecutando.

        Sirve para responder de un vistazo a una pregunta que aparece en cada
        iteracion: si lo que corre en el servidor es lo ultimo que se subio.
        Comparar la huella que muestra la aplicacion con la que imprime el
        repositorio resuelve la duda sin conjeturas, y evita perseguir fallos
        que en realidad ya estaban corregidos.

        Se calcula una sola vez por proceso, de modo que su coste es
        irrelevante.
        """
        raiz = Path(__file__).resolve().parent.parent
        resumen = hashlib.sha256()

        # Se recorren los fuentes en orden estable para que la huella sea
        # reproducible, y se incluyen tambien los datos, porque un cambio en la
        # politica o en los gastos tambien es un cambio de version.
        for ruta in sorted(raiz.rglob("*.py")) + sorted(raiz.glob("datos/*")):
            try:
                resumen.update(ruta.read_bytes())
            except OSError:
                # Un fichero ilegible no debe impedir el arranque.
                continue

        return resumen.hexdigest()[:7]

    def _renderizar_barra_lateral(self) -> None:
        """Pinta la identidad, la navegacion y el pie tecnico."""
        Componentes.marca_lateral()

        # La navegacion es por ahora informativa: la aplicacion tiene una sola
        # pantalla. Se deja preparada la estructura para cuando se anadan las
        # rondas del juego de aprobar y denegar.
        Componentes.elemento_navegacion(
            "Política", "editar reglas y evaluar", activo=True
        )
        Componentes.elemento_navegacion(
            "Partida", "aprobar o denegar (próximamente)", activo=False
        )

        # Dato tecnico de trazabilidad: que modelo esta respondiendo y cuanto
        # cupo le queda al alumno. Es informacion que evita preguntas en clase.
        modelo = self._configuracion.llm.modelo
        # Se indica tambien si el agente dispone de herramienta de
        # verificacion. Es informacion relevante para interpretar sus
        # veredictos: sin ella, escalara todo lo que dependa de un hecho
        # externo, y conviene que eso no se confunda con un fallo.
        Componentes.pie_lateral(
            f"modelo · {modelo}\n"
            f"verificación · {self._buscador.nombre}\n"
            f"evaluaciones · {self._control_uso.realizadas}/"
            f"{self._control_uso.limite}\n"
            f"versión · {VistaPrincipal._huella_del_codigo()}"
        )

    # ------------------------------------------------------------------
    # Secciones de contenido
    # ------------------------------------------------------------------

    def _renderizar_cabecera(self) -> None:
        """Pinta la etiqueta, el titulo y el parrafo explicativo."""
        Componentes.cabecera(
            etiqueta="Panel",
            titulo="Agente de gastos en base a política corporativa",
            entradilla_html=(
                "El agente evalúa cada apunte de viaje contra la "
                "<strong>política corporativa</strong> que tienes abajo, y "
                "para cada uno redacta el correo que enviaría al empleado o a "
                "su responsable. "
                "Cambia una regla, vuelve a evaluar y observa qué decisiones "
                "se mueven: el comportamiento del sistema lo decide el texto "
                "que escribes, no el modelo."
            ),
        )

    def _renderizar_resumen(self, gastos: ConjuntoGastos) -> None:
        """Pinta la fila de tarjetas con el estado de la ejecucion."""
        columna_a, columna_b, columna_c = st.columns(3)

        with columna_a:
            Componentes.tarjeta(
                titulo="Gastos",
                dato=f"{len(gastos)} apuntes",
                nota=self._describir_origen_gastos(gastos),
                color=Paleta.AZUL,
            )

        with columna_b:
            # La politica en curso es la que el alumno tenga en el cuadro de
            # texto, no la del fichero, de ahi que se lea del estado.
            politica_actual = self._politica_en_curso()
            Componentes.tarjeta(
                titulo="Política",
                dato=f"{politica_actual.numero_de_lineas} líneas",
                nota=self._describir_estado_politica(politica_actual),
                color=Paleta.MORADO,
            )

        with columna_c:
            Componentes.tarjeta(
                titulo="Cupo",
                dato=f"{self._control_uso.restantes} evaluaciones",
                nota="Los resultados servidos desde caché no consumen cupo.",
                color=Paleta.VERDE,
            )

    def _renderizar_editor_politica(self, gastos: ConjuntoGastos) -> None:
        """Pinta el cuadro de texto de la politica y el boton de evaluar."""
        st.markdown(
            '<div class="etiqueta-seccion" style="margin-top:14px">'
            'Política de viajes · editable</div>',
            unsafe_allow_html=True,
        )

        # El cuadro se inicializa con el valor almacenado y devuelve lo que el
        # alumno haya escrito, que se guarda de vuelta en el almacen. Ese viaje
        # de ida y vuelta es lo que hace que el contenido no dependa de la
        # supervivencia de la clave del widget.
        texto = st.text_area(
            label="Política",
            value=st.session_state[self.CLAVE_TEXTO_POLITICA],
            key=self.CLAVE_WIDGET_POLITICA,
            height=260,
            label_visibility="collapsed",
        )
        st.session_state[self.CLAVE_TEXTO_POLITICA] = texto

        columna_boton, columna_aviso = st.columns([1, 3])

        with columna_boton:
            # El boton se desactiva al agotar el cupo, en lugar de dejar que se
            # pulse y falle, que seria una frustracion evitable.
            pulsado = st.button(
                "Evaluar gastos",
                type="primary",
                disabled=not self._control_uso.puede_evaluar,
                use_container_width=True,
            )

        with columna_aviso:
            if not self._control_uso.puede_evaluar:
                st.warning("Has agotado tu cupo de evaluaciones en esta sesión.")

        if pulsado:
            self._ejecutar_evaluacion(gastos)

    def _renderizar_resultados(self, gastos: ConjuntoGastos) -> None:
        """Pinta la tabla de veredictos y el recuento, si ya hay resultados."""
        resultado: ResultadoEvaluacion | None = st.session_state[
            self.CLAVE_RESULTADO_ACTUAL
        ]

        # Antes de la primera evaluacion no hay nada que mostrar; se explica que
        # debe hacer el alumno en lugar de dejar la mitad inferior en blanco.
        if resultado is None:
            st.info(
                "Pulsa **Evaluar gastos** para que el agente aplique la "
                "política. Después cambia una regla y vuelve a evaluar."
            )
            return

        anterior: ResultadoEvaluacion | None = st.session_state[
            self.CLAVE_RESULTADO_ANTERIOR
        ]
        cambiados = resultado.identificadores_que_cambian(anterior)

        self._renderizar_recuento(resultado, cambiados)

        self._renderizar_traza_verificacion()

        st.markdown(
            '<div class="etiqueta-seccion" style="margin-top:18px">'
            'Veredictos</div>',
            unsafe_allow_html=True,
        )
        self._renderizar_lista_interactiva(gastos, resultado, cambiados)

    def _renderizar_recuento(
        self, resultado: ResultadoEvaluacion, cambiados: list
    ) -> None:
        """Pinta el recuento por tipo de veredicto y los cambios detectados."""
        # Ya no se pinta el recuento por tipo de veredicto. Aparecia encima de
        # la lista y anticipaba el reparto de resoluciones -cuantas aprobadas,
        # cuantas denegadas- antes de que nadie hubiera revisado nada, con lo
        # que el ejercicio se convertia en adivinar que gastos caian en cada
        # cubo en lugar de juzgar cada uno por su cuenta.

        # Mensaje de cambios: es el que da sentido al ejercicio, asi que se
        # muestra de forma destacada y solo cuando hay algo que contar.
        if cambiados:
            st.success(
                f"Tu cambio en la política ha movido "
                f"**{len(cambiados)}** veredicto(s): "
                f"{', '.join(cambiados)}. Aparecen resaltados en la tabla."
            )

        # Trazabilidad discreta del origen del resultado.
        origen = "caché" if resultado.procede_de_cache else "modelo"
        st.caption(
            f"Resultado obtenido de {origen} · "
            f"modelo {resultado.modelo_utilizado or 'no indicado'}"
        )

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def _ejecutar_evaluacion(self, gastos: ConjuntoGastos) -> None:
        """Lanza la evaluacion y guarda el resultado en el estado de sesion."""
        try:
            politica = self._politica_en_curso()
        except ValueError:
            # La politica vacia se rechaza aqui, antes de gastar una llamada.
            st.error("La política no puede quedar vacía.")
            return

        try:
            proveedor = FabricaProveedores.crear(self._configuracion.llm)
        except ErrorProveedorLLM as error:
            # Falta de credenciales: el mensaje debe orientar a quien despliega,
            # no al alumno, porque no es algo que el pueda resolver.
            st.error(
                f"{error} Revisa el apartado Secrets del panel de Streamlit."
            )
            return

        servicio = ServicioEvaluacion(
            proveedor=proveedor, cache=self._cache, buscador=self._buscador
        )

        # El indicador de progreso importa: sin el, tres segundos de espera se
        # perciben como una aplicacion que no responde.
        with st.spinner(
            "El agente está verificando los datos y aplicando tu política..."
        ):
            try:
                resultado = servicio.evaluar(politica, gastos)
            except ErrorProveedorLLM as error:
                # Se distingue la saturacion del resto para poder sugerir la
                # accion correcta, que en ese caso es sencillamente esperar.
                if error.es_limite_de_ritmo:
                    st.warning(
                        f"{error} Espera unos segundos y vuelve a pulsar."
                    )
                else:
                    st.error(str(error))
                return

        # La ejecucion previa pasa a ser la anterior, para poder comparar.
        st.session_state[self.CLAVE_RESULTADO_ANTERIOR] = st.session_state[
            self.CLAVE_RESULTADO_ACTUAL
        ]
        st.session_state[self.CLAVE_RESULTADO_ACTUAL] = resultado
        st.session_state[self.CLAVE_TRAZA] = servicio.traza_verificacion

        # Solo descuenta cupo una llamada real al modelo.
        if not resultado.procede_de_cache:
            self._control_uso.registrar_uso()

        # Se vuelve a ejecutar el script para que las tarjetas de cupo y los
        # resultados se pinten ya con los valores actualizados.
        st.rerun()

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    def _renderizar_selector_fichero(self) -> None:
        """Pinta el control de subida del fichero de gastos."""
        st.markdown(
            '<div class="etiqueta-seccion">Fichero de gastos</div>',
            unsafe_allow_html=True,
        )

        columna_subida, columna_estado = st.columns([2, 1])

        with columna_subida:
            subido = st.file_uploader(
                "Sube tu fichero de gastos",
                type=["csv", "xlsx", "xlsm"],
                label_visibility="collapsed",
            )

        with columna_estado:
            # Boton para volver al fichero de ejemplo. Solo tiene sentido
            # mostrarlo cuando hay un fichero propio cargado.
            if st.session_state[self.CLAVE_GASTOS_SUBIDOS] is not None:
                if st.button("Volver al ejemplo", use_container_width=True):
                    self._descartar_fichero_subido()
                    st.rerun()

        # Se procesa el fichero solo cuando cambia, no en cada reejecutado del
        # script, que en Streamlit ocurre con cualquier interaccion.
        if subido is not None and subido.name != st.session_state[self.CLAVE_NOMBRE_FICHERO]:
            self._procesar_fichero_subido(subido)

    def _procesar_fichero_subido(self, subido) -> None:
        """Lee y valida el fichero, y lo guarda en el estado si es correcto."""
        try:
            gastos = self._repositorio.cargar_gastos_subidos(
                subido.name, subido.getvalue()
            )
        except ErrorFicheroGastos as error:
            # Error del fichero: es algo que el alumno puede corregir, asi que
            # el mensaje describe el problema concreto y no se guarda nada.
            st.error(f"{error}")
            return
        except Exception as error:
            # Cualquier otro fallo se reporta sin traza, para no romper la
            # pantalla delante de la clase.
            st.error(f"No se ha podido procesar el fichero: {error}")
            return

        st.session_state[self.CLAVE_GASTOS_SUBIDOS] = gastos
        st.session_state[self.CLAVE_NOMBRE_FICHERO] = subido.name

        # Los resultados anteriores corresponden a otros gastos y dejarlos
        # visibles induciria a error, asi que se descartan.
        st.session_state[self.CLAVE_RESULTADO_ACTUAL] = None
        st.session_state[self.CLAVE_RESULTADO_ANTERIOR] = None

        st.success(f"Cargado **{subido.name}** con {len(gastos)} gastos.")

    def _descartar_fichero_subido(self) -> None:
        """Vuelve al fichero de ejemplo incluido en la aplicacion."""
        st.session_state[self.CLAVE_GASTOS_SUBIDOS] = None
        st.session_state[self.CLAVE_NOMBRE_FICHERO] = ""
        st.session_state[self.CLAVE_RESULTADO_ACTUAL] = None
        st.session_state[self.CLAVE_RESULTADO_ANTERIOR] = None

    def _gastos_en_curso(self):
        """Devuelve los gastos del alumno si los hay, o los de ejemplo."""
        subidos = st.session_state[self.CLAVE_GASTOS_SUBIDOS]
        if subidos is not None:
            return subidos
        return self._repositorio.cargar_gastos()

    def _obtener_generador(self) -> GeneradorCuerpoCorreo | None:
        """Devuelve el redactor de correos, o None si no hay modelo disponible."""
        # Sin credenciales no se puede redactar nada, pero tampoco debe fallar:
        # el correo se compondra con las plantillas fijas.
        if not self._configuracion.llm.esta_configurado:
            return None

        try:
            proveedor = FabricaProveedores.crear(self._configuracion.llm)
        except ErrorProveedorLLM:
            return None

        return VistaPrincipal._obtener_generador_compartido(
            proveedor, self._configuracion.llm.modelo, firma_estructural()
        )

    @staticmethod
    @st.cache_resource
    def _obtener_generador_compartido(_proveedor, modelo: str, firma: str):
        """Devuelve el unico generador del proceso para un modelo dado."""
        # El proveedor lleva guion bajo para que Streamlit no intente calcular
        # su huella, que no es serializable. El nombre del modelo si entra en la
        # firma: al cambiarlo desde el panel de secretos se construye un
        # generador nuevo y se descarta la cache de textos del anterior.
        return GeneradorCuerpoCorreo(_proveedor)

    def _renderizar_traza_verificacion(self) -> None:
        """
        Muestra que decidio comprobar el agente y que encontro.

        Es el panel que convierte el uso de la herramienta en algo observable.
        Sin el, el alumno ve aparecer un veredicto y no tiene forma de saber si
        el sistema consulto una fuente o improviso; con el, puede leer la
        consulta que el propio agente formulo y el dato en que se apoyo.
        """
        traza = st.session_state[self.CLAVE_TRAZA]

        # Sin verificacion no se muestra nada: un panel vacio solo estorbaria.
        if not traza:
            return

        with st.expander(
            f"Qué comprobó el agente antes de decidir ({len(traza)} consultas)",
            expanded=False,
        ):
            for resultado in traza:
                st.markdown(f"**{resultado.consulta}**")

                if not resultado.hay_informacion:
                    # Declarar el hueco es informacion valiosa: explica por que
                    # un gasto acabo en revision.
                    st.caption("Sin información disponible.")
                    continue

                if resultado.resumen:
                    st.write(resultado.resumen)

                if resultado.fuentes:
                    st.caption("Fuentes: " + " · ".join(resultado.fuentes))

    # Proporciones de las columnas de cada fila. Se declaran una sola vez
    # para que la cabecera y las filas de datos queden siempre alineadas.
    PROPORCIONES_FILA = [0.7, 3.9, 1.2, 1.6, 0.6, 0.6, 0.6]

    def _renderizar_lista_interactiva(self, gastos, resultado, cambiados) -> None:
        """
        Pinta la lista de gastos con los controles de revision de cada uno.

        Sustituye a la tabla estatica anterior. El motivo es funcional: no hay
        forma de intercalar botones dentro de una tabla HTML en Streamlit, y el
        ejercicio necesita que el alumno pueda pronunciarse sobre cada gasto sin
        salir de la fila que esta leyendo. Se construye por tanto sobre una
        rejilla de columnas, conservando el aspecto anterior mediante estilos.
        """
        st.caption(
            "El agente ya ha decidido. Tu trabajo es revisarlo: confirma con "
            "**✓** o corrige con **✗**. Con **✉** ves el correo que se enviaría."
        )

        cambiados_conjunto = set(cambiados)
        decisiones = st.session_state[self.CLAVE_DECISIONES]
        enviados = st.session_state[self.CLAVE_CORREOS_ENVIADOS]

        Componentes.cabecera_lista(st.columns(self.PROPORCIONES_FILA))
        Componentes.separador()

        for gasto in gastos:
            veredicto = resultado.obtener(gasto.identificador)

            # No deberia ocurrir, porque el analizador rellena los ausentes,
            # pero una fila sin veredicto se omite antes que romper la pantalla.
            if veredicto is None:
                continue

            self._renderizar_fila(
                gasto, veredicto,
                resaltado=gasto.identificador in cambiados_conjunto,
                decision=decisiones.get(gasto.identificador, ""),
                enviado=gasto.identificador in enviados,
            )

        # Marcador del aula, debajo de la lista. Estaba escrito desde hace
        # varias versiones pero nadie lo llamaba, de modo que no se pintaba en
        # ningun momento. Ahora que la correccion es binaria encaja sin
        # ambiguedad: cada gasto revisado cae en aciertos o en fallos.
        self._renderizar_balance(gastos, resultado)

        # Si hay un correo seleccionado, se abre la ventana emergente.
        identificador = st.session_state[self.CLAVE_CORREO_ABIERTO]
        if identificador:
            self._mostrar_correo(identificador, gastos, resultado)

        pendiente = st.session_state[self.CLAVE_RESOLUCION_ABIERTA]
        if pendiente:
            self._mostrar_resolucion(pendiente, gastos, resultado)

    def _renderizar_fila(self, gasto, veredicto, resaltado, decision, enviado) -> None:
        """Pinta una fila completa: datos, veredicto, decision y controles."""
        columnas = st.columns(self.PROPORCIONES_FILA)

        with columnas[0]:
            Componentes.celda_identificador(gasto.identificador, resaltado)
        with columnas[1]:
            Componentes.celda_concepto(gasto)
        with columnas[2]:
            Componentes.celda_importe(gasto)
        with columnas[3]:
            Componentes.celda_decision(decision, discrepa=False)

        # Los tres controles de la fila. Etiquetas de un solo caracter para que
        # quepan sin descuadrar la rejilla, con ayuda emergente que explica que
        # hace cada uno, porque un icono suelto no es autoexplicativo.
        with columnas[4]:
            if st.button(
                "✓", key=f"ap_{gasto.identificador}",
                help="Aprobar este gasto",
                use_container_width=True,
            ):
                self._registrar_decision(gasto.identificador, "APROBADO")

        with columnas[5]:
            if st.button(
                "✗", key=f"de_{gasto.identificador}",
                help="Denegar este gasto",
                use_container_width=True,
            ):
                self._registrar_decision(gasto.identificador, "DENEGADO")

        with columnas[6]:
            # El sobre cambia cuando el correo ya se autorizo, para que el
            # estado sea visible sin abrir la ventana.
            if st.button(
                "✓✉" if enviado else "✉",
                key=f"co_{gasto.identificador}",
                help="Ver el correo que enviaría el agente",
                use_container_width=True,
            ):
                st.session_state[self.CLAVE_CORREO_ABIERTO] = gasto.identificador
                st.rerun()

        Componentes.separador()

    def _registrar_decision(self, identificador: str, decision: str) -> None:
        """Guarda la decision del alumno sobre un gasto y repinta la pantalla."""
        # Pulsar de nuevo el mismo boton retira la decision. Permite corregirse
        # sin tener que recargar la pagina y perder todo lo demas.
        decisiones = st.session_state[self.CLAVE_DECISIONES]
        if decisiones.get(identificador) == decision:
            decisiones.pop(identificador, None)
        else:
            decisiones[identificador] = decision

            # Al pronunciarse, se abre la resolucion del agente. El orden
            # importa: el alumno decide primero y lee despues el razonamiento,
            # de modo que la pantalla funciona como comprobacion de su criterio
            # y no como una respuesta que copiar.
            st.session_state[self.CLAVE_RESOLUCION_ABIERTA] = identificador

        st.rerun()

    def _renderizar_balance(self, gastos, resultado) -> None:
        """Pinta el marcador de aciertos, fallos y gastos sin revisar."""
        decisiones = st.session_state[self.CLAVE_DECISIONES]

        coincidencias = 0
        discrepancias = 0
        for gasto in gastos:
            decision = decisiones.get(gasto.identificador, "")
            if not decision:
                continue

            veredicto = resultado.obtener(gasto.identificador)
            if veredicto is None:
                continue

            # Se reutiliza la misma regla que corrige al alumno en la ventana,
            # para que el recuento de abajo no pueda contradecir lo que se le
            # acaba de decir gasto por gasto.
            if corregir_decision(veredicto, decision) is Correccion.ACERTADA:
                coincidencias += 1
            else:
                discrepancias += 1

        pendientes = len(gastos) - coincidencias - discrepancias

        # Antes de revisar nada no hay balance que mostrar.
        if coincidencias == 0 and discrepancias == 0:
            return

        columna_a, columna_b, columna_c = st.columns(3)
        with columna_a:
            Componentes.tarjeta(
                "Correctos", str(coincidencias), "", Paleta.VERDE
            )
        with columna_b:
            Componentes.tarjeta(
                "Incorrectos", str(discrepancias),
                "Revisa el motivo de cada uno.", Paleta.ROJO,
            )
        with columna_c:
            Componentes.tarjeta(
                "Sin revisar", str(pendientes), "", Paleta.ETIQUETA
            )

    def _mostrar_resolucion(self, identificador, gastos, resultado) -> None:
        """
        Muestra el razonamiento del agente sobre un gasto concreto.

        Se abre cuando el alumno se pronuncia, no antes. Esa secuencia -decidir
        primero, leer despues- convierte la pantalla en una comprobacion del
        propio criterio en lugar de en una respuesta que copiar, que es lo que
        ocurriria si el razonamiento estuviera visible de antemano.
        """
        # La seleccion se consume al abrir, por el mismo motivo que en la
        # ventana del correo: si quedara puesta, se reabriria sola.
        st.session_state[self.CLAVE_RESOLUCION_ABIERTA] = None

        gasto = gastos.buscar(identificador)
        veredicto = resultado.obtener(identificador)
        if gasto is None or veredicto is None:
            return

        decision = st.session_state[self.CLAVE_DECISIONES].get(identificador, "")

        @st.dialog(f"Gasto {gasto.identificador}", width="small")
        def ventana() -> None:
            """Contenido de la pantalla de resolucion."""
            Componentes.pantalla_resolucion(gasto, veredicto, decision)

            if st.button("Cerrar", type="primary", use_container_width=True):
                st.rerun()

        ventana()

    def _mostrar_correo(self, identificador, gastos, resultado) -> None:
        """Abre la ventana emergente con el correo del gasto indicado."""
        gasto = gastos.buscar(identificador)
        veredicto = resultado.obtener(identificador)

        # La seleccion se consume aqui, antes de abrir nada. Si se dejara
        # puesta, cualquier reejecutado posterior de la pantalla -pulsar
        # aprobar, por ejemplo- volveria a abrir la ventana, que es lo que
        # ocurria al cerrarla con la aspa del marco en lugar del boton.
        st.session_state[self.CLAVE_CORREO_ABIERTO] = None

        # Si el gasto o su veredicto ya no existen -por ejemplo porque el
        # alumno ha subido otro fichero- no hay nada que mostrar.
        if gasto is None or veredicto is None:
            return

        # El cuerpo lo redacta el modelo, no una plantilla. Se genera al abrir
        # el correo y no al evaluar: una evaluacion de diez gastos no dispara
        # diez llamadas, y las que se produzcan se reparten solas conforme el
        # alumno va abriendo mensajes. Si el servicio no responde, se devuelve
        # cadena vacia y el redactor recurre a la plantilla fija.
        redactor = RedactorCorreo()
        destinatario = redactor.nombre_destinatario(gasto, veredicto)

        explicacion = ""
        generador = self._obtener_generador()
        if generador is not None:
            with st.spinner("Redactando el correo..."):
                explicacion = generador.generar(gasto, veredicto, destinatario)

        correo = redactor.redactar(gasto, veredicto, explicacion)

        # st.dialog necesita envolver una funcion; se define aqui dentro para
        # que capture el correo ya redactado sin pasarlo por el estado.
        @st.dialog(f"Correo · {gasto.identificador}", width="large")
        def ventana() -> None:
            """Contenido de la ventana emergente."""
            enviados = st.session_state[self.CLAVE_CORREOS_ENVIADOS]
            ya_enviado = gasto.identificador in enviados

            Componentes.ventana_correo(correo, enviado=ya_enviado)

            columna_izquierda, columna_derecha = st.columns(2)

            with columna_izquierda:
                # Enviar cierra la ventana. Es lo que hace un cliente de correo
                # y lo que el gesto significa: una vez autorizado el envio, ya
                # no hay nada que revisar en esa pantalla. El acuse queda en la
                # lista, donde la referencia aparece marcada.
                if not ya_enviado:
                    if st.button(
                        "Enviar correo",
                        type="primary",
                        use_container_width=True,
                        key=f"enviar_{gasto.identificador}",
                    ):
                        enviados.append(gasto.identificador)
                        st.rerun()
                else:
                    st.caption("Este correo ya fue autorizado.")

            with columna_derecha:
                # Al cerrar hay que limpiar la seleccion; si no, la ventana se
                # reabriria en el siguiente reejecutado del script.
                if st.button(
                    "Cancelar",
                    use_container_width=True,
                    key=f"cerrar_{gasto.identificador}",
                ):
                    st.rerun()

        ventana()

    def _politica_en_curso(self) -> Politica:
        """
        Construye la entidad Politica con el texto que hay en pantalla.

        Si por cualquier via ese texto llegase vacio, se recurre al del
        repositorio en lugar de propagar una excepcion. Esta salvaguarda es la
        ultima de tres, y existe porque este metodo se invoca desde el pintado
        de la pantalla: un fallo aqui no produce un mensaje de error, produce
        una pagina rota, que es lo unico que no puede ocurrir durante una clase.
        """
        texto = st.session_state.get(self.CLAVE_TEXTO_POLITICA) or ""

        if not texto.strip():
            politica = self._repositorio.cargar_politica()
            st.session_state[self.CLAVE_TEXTO_POLITICA] = politica.texto
            return politica

        return Politica(texto=texto)

    def _describir_origen_gastos(self, gastos) -> str:
        """Indica si los gastos son los de ejemplo o los que subio el alumno."""
        # El importe total se muestra siempre; el origen solo cambia el prefijo.
        total = f"{gastos.importe_total():,.2f} declarados"
        nombre = st.session_state[self.CLAVE_NOMBRE_FICHERO]
        if nombre:
            return f"Tu fichero: {nombre}. {total}."
        return f"Fichero de ejemplo. {total}."

    def _describir_estado_politica(self, politica_actual: Politica) -> str:
        """Indica si el alumno ha modificado la politica original."""
        # Se compara con la del repositorio por huella, de modo que un cambio de
        # sangrado o una linea en blanco no cuenten como modificacion real.
        original = self._repositorio.cargar_politica()
        if politica_actual.difiere_de(original):
            return "Modificada por ti respecto a la original."
        return "Sin modificar. Cambia una regla y vuelve a evaluar."
