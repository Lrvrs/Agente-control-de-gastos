"""Componentes visuales reutilizables de la aplicacion."""

from html import escape
import inspect
from pathlib import Path
from typing import List

import streamlit as st

from dominio.correo import CorreoSimulado
from dominio.gasto import ConjuntoGastos
from dominio.veredicto import Correccion, corregir_decision
from interfaz.estilos import Paleta


class Componentes:
    """
    Fragmentos de interfaz que se pintan mas de una vez o que encapsulan HTML.

    Se agrupan como metodos estaticos de una clase, en lugar de funciones
    sueltas, para que el espacio de nombres deje claro de donde sale cada pieza
    cuando se lea la vista principal.
    """

    # Nombres de fichero admitidos para el logotipo institucional. Se buscan en
    # este orden y se usa el primero que exista.
    NOMBRES_LOGOTIPO = ("logo-esic.png", "logo-esic.svg", "logo-esic.jpg")


    @staticmethod
    def imagen_a_ancho_completo(contenedor, ruta: str) -> None:
        """
        Pinta una imagen ocupando todo el ancho disponible.

        Existe porque Streamlit renombro el parametro que controla eso: las
        versiones antiguas lo llaman use_column_width y las recientes
        use_container_width, y pasar el que no toca lanza una excepcion.

        Se resuelve consultando la firma de la funcion en tiempo de ejecucion en
        lugar de fijar uno de los dos nombres. Asi la aplicacion sigue
        funcionando tanto si algun dia se actualiza la version fijada en las
        dependencias como si se mantiene la actual, y el problema no vuelve a
        aparecer en el peor momento posible.
        """
        parametros = inspect.signature(contenedor.image).parameters

        if "use_container_width" in parametros:
            contenedor.image(ruta, use_container_width=True)
        elif "use_column_width" in parametros:
            contenedor.image(ruta, use_column_width=True)
        else:
            # Sin ninguno de los dos, se pinta al tamano natural: menos vistoso,
            # pero preferible a no mostrar nada.
            contenedor.image(ruta)

    @staticmethod
    def banner_superior() -> None:
        """
        Pinta el espacio reservado para el banner de cabecera.

        Se deja como marcador visible y no como hueco en blanco para que sea
        evidente que el espacio esta reservado a proposito. Sustituirlo por la
        imagen definitiva afecta solo a este metodo.
        """
        st.markdown(
            '<div class="banner-hueco">Espacio reservado para el banner</div>',
            unsafe_allow_html=True,
        )

    @staticmethod
    def marca_lateral() -> None:
        """Pinta el bloque de identidad en la cabecera de la barra lateral."""
        # Se busca el logotipo en la carpeta de activos. No se distribuye con el
        # repositorio por tratarse de una marca registrada, de modo que la
        # ausencia del fichero es el caso normal y debe resolverse con elegancia.
        carpeta_activos = Path(__file__).resolve().parent.parent / "activos"
        ruta_logotipo = None
        for nombre in Componentes.NOMBRES_LOGOTIPO:
            candidato = carpeta_activos / nombre
            if candidato.exists():
                ruta_logotipo = candidato
                break

        if ruta_logotipo is not None:
            # Con logotipo disponible se muestra la imagen a su ancho natural.
            Componentes.imagen_a_ancho_completo(st.sidebar, str(ruta_logotipo))
        else:
            # Sin logotipo se recurre a un cuadro con las iniciales, que mantiene
            # la composicion de la barra lateral intacta.
            st.sidebar.markdown(
                '<div class="marca">'
                '  <div class="marca-sigla">ESIC</div>'
                '  <div>'
                '    <div class="marca-nombre">Agente de gastos</div>'
                '    <div class="marca-sub">ESIC University</div>'
                '  </div>'
                '</div>',
                unsafe_allow_html=True,
            )

    @staticmethod
    def elemento_navegacion(titulo: str, descripcion: str, activo: bool) -> None:
        """Pinta una entrada del menu lateral, resaltada si esta activa."""
        # La clase adicional controla el fondo azul del elemento seleccionado.
        clase = "nav-item nav-item-activo" if activo else "nav-item"
        st.sidebar.markdown(
            f'<div class="{clase}">'
            f'  <div class="nav-titulo">{escape(titulo)}</div>'
            f'  <div class="nav-desc">{escape(descripcion)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    @staticmethod
    def pie_lateral(texto: str) -> None:
        """Pinta el dato tecnico al pie de la barra lateral."""
        st.sidebar.markdown(
            f'<div class="lateral-pie">{escape(texto)}</div>',
            unsafe_allow_html=True,
        )

    @staticmethod
    def cabecera(etiqueta: str, titulo: str, entradilla_html: str) -> None:
        """
        Pinta la cabecera de la pagina: etiqueta, titulo y parrafo de entrada.

        La entradilla se recibe ya como HTML porque incluye texto en negrita, y
        escaparla entera impediria ese resalte.
        """
        st.markdown(
            f'<div class="etiqueta-seccion">{escape(etiqueta)}</div>'
            f'<div class="titulo-pagina">{escape(titulo)}</div>'
            f'<div class="entradilla">{entradilla_html}</div>',
            unsafe_allow_html=True,
        )

    @staticmethod
    def tarjeta(titulo: str, dato: str, nota: str, color: str) -> None:
        """Pinta una tarjeta con filete de color, dato destacado y nota."""
        # El filete lateral se aplica en linea porque su color cambia en cada uso
        # y generar una clase CSS por color seria innecesariamente prolijo.
        st.markdown(
            f'<div class="tarjeta" style="border-left:3px solid {color}">'
            f'  <div class="tarjeta-titulo" style="color:{color}">'
            f'    {escape(titulo)}</div>'
            f'  <div class="tarjeta-dato">{escape(dato)}</div>'
            f'  <div class="tarjeta-nota">{escape(nota)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    @staticmethod
    def cabecera_lista(columnas) -> None:
        """Pinta la fila de encabezados de la lista de gastos."""
        # Los rotulos se reparten sobre las mismas columnas que las filas de
        # datos, de modo que todo queda alineado sin usar una tabla HTML.
        titulos = ["Id", "Gasto", "Importe", "Tu decisión", "", "", ""]
        for columna, titulo in zip(columnas, titulos):
            with columna:
                st.markdown(
                    f'<div class="fila-cabecera">{escape(titulo)}</div>',
                    unsafe_allow_html=True,
                )

    @staticmethod
    def celda_identificador(identificador: str, resaltado: bool) -> None:
        """Pinta el identificador del gasto, marcado si su veredicto cambio."""
        # El asterisco senala que este veredicto se movio respecto a la
        # ejecucion anterior, que es lo que el alumno debe mirar primero.
        marca = (
            f'<span class="marca-cambio">•</span>' if resaltado else ""
        )
        st.markdown(
            f'<div class="mono" style="padding-top:6px">'
            f'{escape(identificador)}{marca}</div>',
            unsafe_allow_html=True,
        )

    @staticmethod
    def celda_concepto(gasto) -> None:
        """Pinta la descripcion del gasto con sus metadatos debajo."""
        st.markdown(
            f'<div class="celda-concepto">{escape(gasto.descripcion)}<br>'
            f'<span class="celda-meta">{escape(gasto.categoria)} · '
            f'{escape(gasto.ciudad)} · {escape(gasto.fecha)} · '
            f'{escape(gasto.empleado)}</span></div>',
            unsafe_allow_html=True,
        )

    @staticmethod
    def celda_importe(gasto) -> None:
        """Pinta el importe alineado en tipografia monoespaciada."""
        st.markdown(
            f'<div class="mono" style="padding-top:6px">'
            f'{gasto.importe:.2f} {escape(gasto.moneda)}</div>',
            unsafe_allow_html=True,
        )

    @staticmethod
    def celda_decision(decision: str, discrepa: bool) -> None:
        """Pinta la decision del alumno, marcando si difiere de la del agente."""
        # Sin decision todavia se indica de forma discreta, para que el alumno
        # distinga lo que le falta por revisar de lo que ya ha resuelto.
        if not decision:
            st.markdown(
                '<div class="sin-decidir" style="padding-top:8px">'
                'sin revisar</div>',
                unsafe_allow_html=True,
            )
            return

        color = Paleta.VERDE if decision == "APROBADO" else Paleta.ROJO
        marca = '<span class="discrepa">DISCREPAS</span>' if discrepa else ""
        st.markdown(
            f'<div style="padding-top:4px">'
            f'  <span class="distintivo" '
            f'        style="background:{color}1A;color:{color}">'
            f'    {escape(decision)}</span>{marca}'
            f'</div>',
            unsafe_allow_html=True,
        )

    @staticmethod
    def separador() -> None:
        """Pinta la linea que separa una fila de la siguiente."""
        st.markdown('<div class="separador-fila"></div>', unsafe_allow_html=True)

    @staticmethod
    def ventana_correo(correo: CorreoSimulado, enviado: bool = False) -> None:
        """
        Pinta el correo simulado con el aspecto de una ventana de redaccion.

        Se reproduce la disposicion de un cliente de correo -De, Para, CC,
        Asunto y cuerpo- porque el reconocimiento visual es la mitad del
        efecto: el alumno entiende de un vistazo que esto es lo que llegaria
        a la bandeja de entrada de una persona.
        """
        # El aviso va primero y no se puede cerrar. Es una decision de
        # honestidad: en ningun momento debe caber duda de que no sale ningun
        # mensaje de la aplicacion. Cambia de texto y de color una vez el
        # alumno ha autorizado el envio, para que la diferencia entre borrador
        # y hecho consumado sea inmediata.
        if enviado:
            st.markdown(
                '<div class="correo-enviado">YA AUTORIZADO · '
                'Este mensaje se envió en esta sesión. Ningún correo sale '
                'realmente de la aplicación.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="correo-aviso">BORRADOR · SIMULACIÓN · '
                'Revisa el mensaje antes de autorizar el envío. '
                'Nada sale de la aplicación.</div>',
                unsafe_allow_html=True,
            )

        # Los campos de cabecera. Todo el contenido se escapa porque procede
        # de los datos del gasto y del texto que redacta el modelo.
        campos = [
            ("De:", f"{escape(correo.remitente_nombre)} "
                    f"<small>&lt;{escape(correo.remitente_direccion)}&gt;</small>"),
            ("Para:", f"{escape(correo.destinatario_nombre)} "
                      f"<small>&lt;{escape(correo.destinatario_direccion)}&gt;</small>"),
        ]

        # La copia solo aparece cuando existe, igual que en un cliente real.
        if correo.tiene_copia:
            campos.append(
                ("CC:", f"<small>&lt;{escape(correo.copia_direccion)}&gt;</small>")
            )

        campos.append(("Asunto:", escape(correo.asunto)))

        for etiqueta, valor in campos:
            st.markdown(
                f'<div class="correo-campo">'
                f'  <div class="correo-etiqueta">{escape(etiqueta)}</div>'
                f'  <div class="correo-valor">{valor}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # El cuerpo se escapa entero y se respeta su formato con white-space.
        st.markdown(
            f'<div class="correo-cuerpo">{escape(correo.cuerpo)}</div>',
            unsafe_allow_html=True,
        )

    # Texto de cada desenlace de la correccion. El titulo dice si acerto y el
    # detalle explica en una linea que hizo el agente, para que el alumno no
    # tenga que deducirlo del bloque de razonamiento que viene despues.
    # Clase CSS, icono, titulo y coletilla de cada desenlace. El texto del
    # detalle se completa en la pantalla con el veredicto del agente, que es el
    # dato que el alumno necesita para situar su propia respuesta.
    # Clase CSS, icono y titulo de cada desenlace. No se nombra el tipo de
    # veredicto: al alumno se le dice si acerto, y el porque va en la frase del
    # motivo. Los nombres internos -APROBADO, PARCIAL, REVISION- pertenecen al
    # agente y no aportan nada a quien esta aprendiendo a supervisarlo.
    TEXTOS_CORRECCION = {
        Correccion.ACERTADA: ("correccion-acertada", "\u2713", "Correcto"),
        Correccion.FALLADA: ("correccion-fallada", "\u2717", "Incorrecto"),
        Correccion.MATIZADA: (
            "correccion-matizada", "!", "Ni correcto ni incorrecto",
        ),
    }

    @staticmethod
    def pantalla_resolucion(gasto, veredicto, decision: str) -> None:
        """
        Dice al alumno si acerto y por que, en una sola caja.

        La ventana se ha reducido a lo minimo por una razon de ritmo de clase:
        se abre y se cierra decenas de veces en una sesion, una por cada gasto
        que alguien revisa. Todo lo que no sea el veredicto sobre su respuesta
        y la frase que lo sostiene alarga esa operacion sin anadir nada, porque
        el gasto lo tiene delante en la fila desde la que ha pulsado y la
        politica la tiene en el cuadro de texto de la misma pagina.

        Tampoco se nombra el tipo de veredicto del agente. APROBADO, PARCIAL o
        REVISION son etiquetas internas del sistema; lo que el alumno necesita
        saber es si su decision se sostiene y con que argumento.
        """
        correccion = corregir_decision(veredicto, decision)

        # Sin decision no hay nada que corregir. No deberia ocurrir, porque la
        # pantalla se abre justo despues de pulsar, pero se contempla para que
        # una sesion en un estado raro no deje un hueco sin explicacion.
        if correccion is None:
            st.markdown(
                f'<div class="resolucion-texto">{escape(veredicto.motivo)}</div>',
                unsafe_allow_html=True,
            )
            return

        clase, icono, titulo = Componentes.TEXTOS_CORRECCION[correccion]

        st.markdown(
            f'<div class="correccion {clase}">'
            f'  <div class="correccion-icono">{icono}</div>'
            f'  <div>'
            f'    <div class="correccion-titulo">{escape(titulo)}</div>'
            f'    <div class="correccion-detalle">{escape(veredicto.motivo)}</div>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )
