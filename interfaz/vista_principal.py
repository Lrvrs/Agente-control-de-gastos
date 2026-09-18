"""Composicion de la pantalla principal de la aplicacion."""

import streamlit as st

from aplicacion.control_uso import ControlUso
from aplicacion.servicio_evaluacion import ServicioEvaluacion
from dominio.gasto import ConjuntoGastos
from dominio.politica import Politica
from dominio.veredicto import ResultadoEvaluacion, TipoVeredicto
from infraestructura.cache_evaluaciones import CacheEvaluaciones
from infraestructura.configuracion import Configuracion
from infraestructura.proveedor_llm import ErrorProveedorLLM, FabricaProveedores
from infraestructura.repositorio_datos import RepositorioDatos
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

        # Los datos de gastos son fijos en esta version de la demo.
        gastos = self._repositorio.cargar_gastos()

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
        introducida = st.text_input("Contrasena de clase", type="password")

        # Comparacion directa: el valor no protege ningun dato sensible, solo
        # evita que la URL publica sea consumida por quien no esta en el aula.
        if introducida and introducida == contrasena_esperada:
            st.session_state[self.CLAVE_ACCESO_CONCEDIDO] = True
            st.rerun()

        # Mensaje solo si se ha escrito algo y no coincide, para no mostrar un
        # error al alumno antes de que haya tenido ocasion de teclear.
        if introducida:
            st.error("La contrasena no es correcta.")

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
            "Politica", "editar reglas y evaluar", activo=True
        )
        Componentes.elemento_navegacion(
            "Partida", "aprobar o denegar (proximamente)", activo=False
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
            titulo="La politica manda",
            entradilla_html=(
                "Abajo tienes los gastos de un mes y la <strong>politica de "
                "viajes</strong> de la empresa. El agente evalua cada gasto "
                "aplicando <strong>solo</strong> esa politica. "
                "Cambia una regla, vuelve a evaluar y observa que decisiones "
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
                nota=f"Importe declarado: {gastos.importe_total():,.2f} "
                     f"(sin convertir divisas)",
                color=Paleta.AZUL,
            )

        with columna_b:
            # La politica en curso es la que el alumno tenga en el cuadro de
            # texto, no la del fichero, de ahi que se lea del estado.
            politica_actual = self._politica_en_curso()
            Componentes.tarjeta(
                titulo="Politica",
                dato=f"{politica_actual.numero_de_lineas} lineas",
                nota=self._describir_estado_politica(politica_actual),
                color=Paleta.MORADO,
            )

        with columna_c:
            Componentes.tarjeta(
                titulo="Cupo",
                dato=f"{self._control_uso.restantes} evaluaciones",
                nota="Los resultados servidos desde cache no consumen cupo.",
                color=Paleta.VERDE,
            )

    def _renderizar_editor_politica(self, gastos: ConjuntoGastos) -> None:
        """Pinta el cuadro de texto de la politica y el boton de evaluar."""
        st.markdown(
            '<div class="etiqueta-seccion" style="margin-top:14px">'
            'Politica de viajes · editable</div>',
            unsafe_allow_html=True,
        )

        # El cuadro de texto escribe directamente en el estado de sesion a
        # traves de su clave, de modo que el valor persiste entre reejecutados.
        st.text_area(
            label="Politica",
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
                st.warning("Has agotado tu cupo de evaluaciones en esta sesion.")

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
                "politica. Despues cambia una regla y vuelve a evaluar."
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
        Componentes.tabla_veredictos(gastos, resultado, cambiados)

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
                f"Tu cambio en la politica ha movido "
                f"**{len(cambiados)}** veredicto(s): "
                f"{', '.join(cambiados)}. Aparecen resaltados en la tabla."
            )

        # Trazabilidad discreta del origen del resultado.
        origen = "cache" if resultado.procede_de_cache else "modelo"
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
            st.error("La politica no puede quedar vacia.")
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
        with st.spinner("El agente esta aplicando tu politica..."):
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

    def _politica_en_curso(self) -> Politica:
        """Construye la entidad Politica con el texto que hay en pantalla."""
        return Politica(texto=st.session_state[self.CLAVE_TEXTO_POLITICA])

    def _describir_estado_politica(self, politica_actual: Politica) -> str:
        """Indica si el alumno ha modificado la politica original."""
        # Se compara con la del repositorio por huella, de modo que un cambio de
        # sangrado o una linea en blanco no cuenten como modificacion real.
        original = self._repositorio.cargar_politica()
        if politica_actual.difiere_de(original):
            return "Modificada por ti respecto a la original."
        return "Sin modificar. Cambia una regla y vuelve a evaluar."
