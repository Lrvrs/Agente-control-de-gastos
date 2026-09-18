"""Composicion de la pantalla principal de la aplicacion."""

import streamlit as st

from aplicacion.control_uso import ControlUso
from aplicacion.servicio_evaluacion import ServicioEvaluacion
from dominio.correo import RedactorCorreo
from dominio.gasto import ConjuntoGastos
from dominio.politica import Politica
from dominio.veredicto import ResultadoEvaluacion, TipoVeredicto
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
    CLAVE_TEXTO_POLITICA = "texto_politica"
    CLAVE_ACCESO_CONCEDIDO = "acceso_concedido"
    CLAVE_GASTOS_SUBIDOS = "gastos_subidos"
    CLAVE_NOMBRE_FICHERO = "nombre_fichero_subido"
    CLAVE_CORREO_ABIERTO = "correo_abierto"
    CLAVE_CORREOS_ENVIADOS = "correos_enviados"
    CLAVE_DECISIONES = "decisiones_alumno"

    def __init__(self) -> None:
        """Construye las dependencias de la vista una sola vez por ejecucion."""
        self._configuracion = Configuracion()
        self._repositorio = RepositorioDatos()

        # La cache se guarda como recurso de Streamlit para que sobreviva a los
        # reejecutados de script y se comparta entre todas las sesiones, que es
        # justamente lo que permite que la primera evaluacion del aula sirva
        # para todos los alumnos que no hayan tocado la politica.
        self._cache = VistaPrincipal._obtener_cache_compartida()

        # Control de cupo, individual de cada alumno.
        self._control_uso = ControlUso(self._configuracion.aula.limite_evaluaciones)

    @staticmethod
    @st.cache_resource
    def _obtener_cache_compartida() -> CacheEvaluaciones:
        """Devuelve la unica instancia de cache del proceso."""
        # El decorador garantiza que Streamlit construye el objeto una sola vez
        # y devuelve siempre la misma referencia a todas las sesiones.
        return CacheEvaluaciones()

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

    # ------------------------------------------------------------------
    # Estado y acceso
    # ------------------------------------------------------------------

    def _preparar_estado(self) -> None:
        """Inicializa las claves del estado de sesion si es la primera visita."""
        # La politica arranca con el texto por defecto del repositorio; a partir
        # de ahi el alumno la edita y su version vive en la sesion.
        if self.CLAVE_TEXTO_POLITICA not in st.session_state:
            st.session_state[self.CLAVE_TEXTO_POLITICA] = (
                self._repositorio.cargar_politica().texto
            )

        # Las dos ultimas ejecuciones se conservan para poder comparar y
        # resaltar que veredictos han cambiado.
        st.session_state.setdefault(self.CLAVE_RESULTADO_ACTUAL, None)
        st.session_state.setdefault(self.CLAVE_RESULTADO_ANTERIOR, None)
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
        Componentes.pie_lateral(
            f"modelo · {modelo}\n"
            f"evaluaciones · {self._control_uso.realizadas}/"
            f"{self._control_uso.limite}"
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

        # El cuadro de texto escribe directamente en el estado de sesion a
        # traves de su clave, de modo que el valor persiste entre reejecutados.
        st.text_area(
            label="Política",
            key=self.CLAVE_TEXTO_POLITICA,
            height=260,
            label_visibility="collapsed",
        )

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
        recuento = resultado.recuento_por_tipo()

        # Cuatro columnas, una por tipo de veredicto, mas la nota de cambios.
        columnas = st.columns(4)
        tipos_y_colores = [
            (TipoVeredicto.APROBADO, Paleta.VERDE),
            (TipoVeredicto.DENEGADO, Paleta.ROJO),
            (TipoVeredicto.PARCIAL, Paleta.AMBAR),
            (TipoVeredicto.REVISION, Paleta.MORADO),
        ]

        for columna, (tipo, color) in zip(columnas, tipos_y_colores):
            with columna:
                Componentes.tarjeta(
                    titulo=tipo.value,
                    dato=str(recuento[tipo]),
                    nota="",
                    color=color,
                )

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

        servicio = ServicioEvaluacion(proveedor=proveedor, cache=self._cache)

        # El indicador de progreso importa: sin el, tres segundos de espera se
        # perciben como una aplicacion que no responde.
        with st.spinner("El agente está aplicando tu política..."):
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

    # Proporciones de las columnas de cada fila. Se declaran una sola vez
    # para que la cabecera y las filas de datos queden siempre alineadas.
    PROPORCIONES_FILA = [0.7, 3.3, 1.1, 1.4, 1.5, 0.55, 0.55, 0.55]

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

        self._renderizar_balance(gastos, resultado)

        # Si hay un correo seleccionado, se abre la ventana emergente.
        identificador = st.session_state[self.CLAVE_CORREO_ABIERTO]
        if identificador:
            self._mostrar_correo(identificador, gastos, resultado)

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
            Componentes.celda_veredicto(veredicto)
        with columnas[4]:
            # Se considera discrepancia cuando el alumno dice algo distinto de
            # lo que dijo el agente. Los veredictos que el agente no resuelve
            # -PARCIAL y REVISION- no cuentan como discrepancia: ahi no propuso
            # nada que contradecir, sino que pidio precisamente una decision.
            discrepa = self._hay_discrepancia(veredicto, decision)
            Componentes.celda_decision(decision, discrepa)

        # Los tres controles de la fila. Etiquetas de un solo caracter para que
        # quepan sin descuadrar la rejilla, con ayuda emergente que explica que
        # hace cada uno, porque un icono suelto no es autoexplicativo.
        with columnas[5]:
            if st.button(
                "✓", key=f"ap_{gasto.identificador}",
                help="Aprobar este gasto",
                use_container_width=True,
            ):
                self._registrar_decision(gasto.identificador, "APROBADO")

        with columnas[6]:
            if st.button(
                "✗", key=f"de_{gasto.identificador}",
                help="Denegar este gasto",
                use_container_width=True,
            ):
                self._registrar_decision(gasto.identificador, "DENEGADO")

        with columnas[7]:
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
        st.rerun()

    def _hay_discrepancia(self, veredicto, decision: str) -> bool:
        """Indica si la decision del alumno contradice al agente."""
        # Sin decision no hay nada que comparar.
        if not decision:
            return False

        # PARCIAL y REVISION no son propuestas cerradas: el agente esta
        # pidiendo que decida una persona, asi que lo que el alumno resuelva
        # ahi no contradice nada.
        if veredicto.requiere_persona:
            return False

        return veredicto.tipo.value != decision

    def _renderizar_balance(self, gastos, resultado) -> None:
        """Pinta el recuento de coincidencias, discrepancias y pendientes."""
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

            if self._hay_discrepancia(veredicto, decision):
                discrepancias += 1
            else:
                coincidencias += 1

        pendientes = len(gastos) - coincidencias - discrepancias

        # Antes de revisar nada no hay balance que mostrar.
        if coincidencias == 0 and discrepancias == 0:
            return

        columna_a, columna_b, columna_c = st.columns(3)
        with columna_a:
            Componentes.tarjeta(
                "Coincides con el agente", str(coincidencias), "", Paleta.VERDE
            )
        with columna_b:
            Componentes.tarjeta(
                "Discrepas", str(discrepancias),
                "Justifica cada una citando la cláusula.", Paleta.ROJO,
            )
        with columna_c:
            Componentes.tarjeta(
                "Sin revisar", str(pendientes), "", Paleta.ETIQUETA
            )

    def _mostrar_correo(self, identificador, gastos, resultado) -> None:
        """Abre la ventana emergente con el correo del gasto indicado."""
        gasto = gastos.buscar(identificador)
        veredicto = resultado.obtener(identificador)

        # Si el gasto o su veredicto ya no existen -por ejemplo porque el
        # alumno ha subido otro fichero- se descarta la seleccion en silencio.
        if gasto is None or veredicto is None:
            st.session_state[self.CLAVE_CORREO_ABIERTO] = None
            return

        correo = RedactorCorreo().redactar(gasto, veredicto)

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
                # El boton de envio desaparece una vez usado. Es deliberado:
                # en la vida real un correo no se puede desenviar, y que el
                # boton no vuelva a ofrecerse traslada esa irreversibilidad.
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
                    "Cerrar",
                    use_container_width=True,
                    key=f"cerrar_{gasto.identificador}",
                ):
                    st.session_state[self.CLAVE_CORREO_ABIERTO] = None
                    st.rerun()

        ventana()

    def _politica_en_curso(self) -> Politica:
        """Construye la entidad Politica con el texto que hay en pantalla."""
        return Politica(texto=st.session_state[self.CLAVE_TEXTO_POLITICA])

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
