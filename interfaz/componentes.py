"""Componentes visuales reutilizables de la aplicacion."""

from html import escape
from pathlib import Path
from typing import List

import streamlit as st

from dominio.correo import CorreoSimulado
from dominio.gasto import ConjuntoGastos
from dominio.veredicto import ResultadoEvaluacion, TipoVeredicto
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

    # Color asociado a cada veredicto, para el distintivo de la tabla.
    COLOR_POR_VEREDICTO = {
        TipoVeredicto.APROBADO: Paleta.VERDE,
        TipoVeredicto.DENEGADO: Paleta.ROJO,
        TipoVeredicto.PARCIAL: Paleta.AMBAR,
        TipoVeredicto.REVISION: Paleta.MORADO,
    }

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
            st.sidebar.image(str(ruta_logotipo), use_container_width=True)
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
    def tabla_veredictos(
        gastos: ConjuntoGastos,
        resultado: ResultadoEvaluacion,
        identificadores_cambiados: List[str],
    ) -> None:
        """
        Pinta la tabla de gastos con el veredicto de cada uno.

        Se genera HTML propio en lugar de usar el componente de tabla de
        Streamlit porque hacen falta tres cosas que este no ofrece: distintivos
        de color por veredicto, resaltado de filas completas y control fino de
        la tipografia monoespaciada en las cifras.
        """
        # Conjunto para consulta rapida al decidir si una fila va resaltada.
        cambiados = set(identificadores_cambiados)

        filas: List[str] = []
        for gasto in gastos:
            veredicto = resultado.obtener(gasto.identificador)

            # Un gasto sin veredicto no deberia ocurrir porque el analizador
            # rellena los ausentes, pero se contempla por seguridad.
            if veredicto is None:
                continue

            color = Componentes.COLOR_POR_VEREDICTO[veredicto.tipo]
            resaltada = gasto.identificador in cambiados
            clase_fila = "fila-cambiada" if resaltada else ""

            # Marca textual que acompana al distintivo en las filas que cambian.
            marca = '<span class="marca-cambio">CAMBIA</span>' if resaltada else ""

            filas.append(
                f'<tr class="{clase_fila}">'
                f'  <td class="mono">{escape(gasto.identificador)}</td>'
                f'  <td>{escape(gasto.descripcion)}<br>'
                f'      <span class="mono" style="color:{Paleta.TEXTO_SUAVE}">'
                f'      {escape(gasto.categoria)} · {escape(gasto.ciudad)} · '
                f'      {escape(gasto.fecha)}</span></td>'
                f'  <td class="mono">{gasto.importe:.2f} {escape(gasto.moneda)}</td>'
                f'  <td><span class="distintivo" '
                f'      style="background:{color}1A;color:{color}">'
                f'      {escape(veredicto.tipo.value)}</span>{marca}</td>'
                f'  <td class="mono">{escape(veredicto.clausula)}</td>'
                f'  <td style="color:{Paleta.TEXTO_SUAVE}">'
                f'      {escape(veredicto.motivo)}</td>'
                f'</tr>'
            )

        # Cabecera de la tabla, con los nombres de columna en versalitas.
        encabezado = (
            "<tr><th>Id</th><th>Gasto</th><th>Importe</th>"
            "<th>Veredicto</th><th>Cláusula</th><th>Motivo</th></tr>"
        )

        st.markdown(
            f'<table class="tabla">{encabezado}{"".join(filas)}</table>',
            unsafe_allow_html=True,
        )

    @staticmethod
    def ventana_correo(correo: CorreoSimulado) -> None:
        """
        Pinta el correo simulado con el aspecto de una ventana de redaccion.

        Se reproduce la disposicion de un cliente de correo -De, Para, CC,
        Asunto y cuerpo- porque el reconocimiento visual es la mitad del
        efecto: el alumno entiende de un vistazo que esto es lo que llegaria
        a la bandeja de entrada de una persona.
        """
        # El aviso de simulacion va primero y no se puede cerrar. Es una
        # decision de honestidad: en ningun momento debe caber duda de que no
        # se esta enviando nada.
        st.markdown(
            '<div class="correo-aviso">SIMULACIÓN · Este mensaje no se envía. '
            'Es la acción que el agente ejecutaría si estuviera autorizado.</div>',
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
