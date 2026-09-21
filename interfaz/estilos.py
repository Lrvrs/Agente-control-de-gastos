"""Hoja de estilos de la aplicacion y paleta corporativa."""

import streamlit as st


class Paleta:
    """
    Colores de la aplicacion, declarados en un unico lugar.

    Tenerlos como constantes con nombre, en vez de repartir codigos hexadecimales
    por las plantillas, permite ajustar el acabado a la identidad visual de la
    institucion cambiando solo esta clase.
    """

    # Azul marino profundo de la barra lateral.
    MARINO = "#141F52"

    # Azul de acento: enlaces, boton principal y elemento de navegacion activo.
    AZUL = "#1B45D7"

    # Azul mas claro para fondos suaves y estados de foco.
    AZUL_SUAVE = "#E8EDFD"

    # Fondo general de la zona de contenido.
    FONDO = "#F5F7FB"

    # Fondo de las tarjetas y de la tabla.
    BLANCO = "#FFFFFF"

    # Linea de separacion y bordes de tarjeta.
    BORDE = "#E4E9F2"

    # Texto principal.
    TEXTO = "#0F1B3D"

    # Texto secundario y descripciones.
    TEXTO_SUAVE = "#6B7794"

    # Texto de las etiquetas de seccion en mayusculas.
    ETIQUETA = "#8A94AD"

    # Colores semanticos de los cuatro veredictos posibles.
    VERDE = "#0E9F6E"
    AMBAR = "#C2760B"
    ROJO = "#D92D20"
    MORADO = "#7C3AED"


class GestorEstilos:
    """
    Inyecta la hoja de estilos en la pagina.

    Streamlit no permite enlazar un fichero CSS externo, asi que el unico camino
    es insertar una etiqueta de estilo en el documento. Se concentra aqui para
    que ningun otro modulo tenga que insertar CSS suelto.
    """

    @staticmethod
    def aplicar() -> None:
        """Escribe la hoja de estilos completa en la pagina."""
        # La cadena se construye con formato para poder referenciar la paleta
        # por nombre y mantener un unico origen de verdad para los colores.
        hoja = f"""
        <style>
        /* ---------- Tipografia y lienzo general ---------- */

        html, body, [class*="css"] {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                         "Inter", "Helvetica Neue", Arial, sans-serif;
        }}

        /* Fondo de la zona de contenido, ligeramente azulado como la
           referencia visual, para que las tarjetas blancas destaquen. */
        .stApp {{
            background-color: {Paleta.FONDO};
        }}

        /* Se reduce el espacio superior que Streamlit reserva por defecto:
           la pantalla debe empezar en el banner, no con un hueco vacio. */
        .block-container {{
            padding-top: 2rem;
            padding-bottom: 4rem;
            max-width: 1180px;
        }}

        /* Oculta el menu y el pie de Streamlit, que no aportan nada al alumno
           y delatan la herramienta con la que esta construida la pagina. */
        #MainMenu, footer, header {{ visibility: hidden; }}

        /* ---------- Barra lateral ---------- */

        section[data-testid="stSidebar"] {{
            background-color: {Paleta.MARINO};
        }}

        /* Todo el texto de la barra lateral va en claro sobre el azul marino. */
        section[data-testid="stSidebar"] * {{
            color: #FFFFFF;
        }}

        /* Bloque de identidad en la cabecera de la barra lateral. */
        .marca {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 4px 0 22px 0;
            border-bottom: 1px solid rgba(255,255,255,0.12);
            margin-bottom: 18px;
        }}

        /* Cuadro con las iniciales, usado cuando no hay logotipo disponible. */
        .marca-sigla {{
            width: 40px; height: 40px;
            border-radius: 10px;
            background: {Paleta.AZUL};
            display: flex; align-items: center; justify-content: center;
            font-weight: 700; font-size: 15px; letter-spacing: 0.02em;
        }}

        .marca-nombre {{ font-weight: 700; font-size: 15px; line-height: 1.2; }}

        .marca-sub {{
            font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase;
            color: rgba(255,255,255,0.55); margin-top: 3px;
        }}

        /* Elemento de navegacion. El estado activo se resuelve con una clase
           adicional en lugar de con JavaScript, que Streamlit no permite. */
        .nav-item {{
            padding: 11px 14px; border-radius: 10px; margin-bottom: 4px;
        }}

        .nav-item-activo {{ background: {Paleta.AZUL}; }}

        .nav-titulo {{ font-size: 14px; font-weight: 600; }}

        .nav-desc {{
            font-size: 11.5px; color: rgba(255,255,255,0.55); margin-top: 2px;
        }}

        /* Pie de la barra lateral, con el dato tecnico del modelo en uso. */
        .lateral-pie {{
            position: relative; margin-top: 28px; padding-top: 14px;
            border-top: 1px solid rgba(255,255,255,0.12);
            font-size: 11px; color: rgba(255,255,255,0.45);
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        }}

        /* ---------- Banner superior reservado ---------- */

        /* Espacio reservado para el banner que se disenara mas adelante.
           Se deja como marcador visible para que no se olvide, y se sustituye
           por una imagen cambiando unicamente el componente que lo pinta. */
        .banner-hueco {{
            height: 104px; border-radius: 14px; margin-bottom: 26px;
            border: 1.5px dashed {Paleta.BORDE};
            background: repeating-linear-gradient(
                -45deg, {Paleta.BLANCO}, {Paleta.BLANCO} 12px,
                #FAFBFE 12px, #FAFBFE 24px);
            display: flex; align-items: center; justify-content: center;
            color: {Paleta.ETIQUETA}; font-size: 11px;
            letter-spacing: 0.16em; text-transform: uppercase; font-weight: 600;
        }}

        /* ---------- Cabecera de la pagina ---------- */

        .etiqueta-seccion {{
            font-size: 11px; font-weight: 700; letter-spacing: 0.16em;
            text-transform: uppercase; color: {Paleta.ETIQUETA};
            margin-bottom: 10px;
        }}

        .titulo-pagina {{
            font-size: 40px; font-weight: 800; color: {Paleta.AZUL};
            letter-spacing: -0.02em; margin: 0 0 14px 0; line-height: 1.1;
        }}

        .entradilla {{
            font-size: 15px; color: {Paleta.TEXTO}; line-height: 1.65;
            max-width: 860px; margin-bottom: 30px;
        }}

        .entradilla strong {{ color: {Paleta.TEXTO}; font-weight: 700; }}

        /* ---------- Tarjetas ---------- */

        /* Tarjeta con filete de color a la izquierda, como en la referencia.
           El color del filete lo fija cada uso mediante un estilo en linea. */
        .tarjeta {{
            background: {Paleta.BLANCO}; border: 1px solid {Paleta.BORDE};
            border-radius: 12px; padding: 18px 20px; margin-bottom: 14px;
        }}

        .tarjeta-titulo {{
            font-size: 10.5px; font-weight: 700; letter-spacing: 0.14em;
            text-transform: uppercase; margin-bottom: 8px;
        }}

        .tarjeta-dato {{
            font-size: 19px; font-weight: 700; color: {Paleta.TEXTO};
            line-height: 1.25;
        }}

        .tarjeta-nota {{
            font-size: 12.5px; color: {Paleta.TEXTO_SUAVE};
            margin-top: 6px; line-height: 1.55;
        }}

        /* ---------- Tabla de veredictos ---------- */

        .tabla {{
            width: 100%; border-collapse: separate; border-spacing: 0;
            background: {Paleta.BLANCO}; border: 1px solid {Paleta.BORDE};
            border-radius: 12px; overflow: hidden; font-size: 13px;
        }}

        .tabla th {{
            text-align: left; padding: 12px 14px;
            font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase;
            color: {Paleta.ETIQUETA}; font-weight: 700;
            border-bottom: 1px solid {Paleta.BORDE}; background: #FBFCFE;
        }}

        .tabla td {{
            padding: 13px 14px; border-bottom: 1px solid #F0F3F8;
            color: {Paleta.TEXTO}; vertical-align: top;
        }}

        .tabla tr:last-child td {{ border-bottom: none; }}

        /* Fila resaltada: marca los gastos cuyo veredicto ha cambiado respecto
           a la ejecucion anterior. Es el elemento central del ejercicio. */
        .fila-cambiada {{ background: {Paleta.AZUL_SUAVE}; }}

        /* Los identificadores e importes van en monoespaciada para que las
           cifras queden alineadas y se comparen de un vistazo. */
        .mono {{
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 12px;
        }}

        /* Distintivo de veredicto. El color concreto lo aporta cada fila. */
        .distintivo {{
            display: inline-block; padding: 3px 9px; border-radius: 6px;
            font-size: 10.5px; font-weight: 700; letter-spacing: 0.06em;
            white-space: nowrap;
        }}

        /* Marca discreta que senala una fila modificada. */
        .marca-cambio {{
            display: inline-block; margin-left: 7px; font-size: 10px;
            font-weight: 700; color: {Paleta.AZUL}; letter-spacing: 0.06em;
        }}

        /* ---------- Ventana de correo simulado ---------- */

        /* Aviso de simulacion. Va arriba del todo y en color de alerta a
           proposito: el alumno debe tener claro en todo momento que ningun
           mensaje sale de la aplicacion. */
        .correo-aviso {{
            background: #FFF4E5; border: 1px solid #F0C98A;
            color: #8A5200; border-radius: 8px; padding: 9px 12px;
            font-size: 11.5px; font-weight: 600; margin-bottom: 14px;
        }}

        /* Cabecera del mensaje, imitando la ventana de redaccion de un
           cliente de correo: etiqueta a la izquierda y valor subrayado. */
        .correo-campo {{
            display: flex; align-items: baseline; gap: 14px;
            padding: 9px 2px; border-bottom: 1px solid {Paleta.BORDE};
            font-size: 13px;
        }}

        .correo-etiqueta {{
            width: 68px; flex: 0 0 68px; color: {Paleta.TEXTO_SUAVE};
            font-size: 12px;
        }}

        .correo-valor {{ color: {Paleta.TEXTO}; font-weight: 500; }}

        .correo-valor small {{
            color: {Paleta.TEXTO_SUAVE}; font-weight: 400;
        }}

        /* Cuerpo del mensaje. Monoespaciada porque el detalle del gasto va
           tabulado y la alineacion es parte de la informacion. */
        .correo-cuerpo {{
            margin-top: 18px; padding: 16px 18px;
            background: #FBFCFE; border: 1px solid {Paleta.BORDE};
            border-radius: 10px;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 12px; line-height: 1.7; color: {Paleta.TEXTO};
            white-space: pre-wrap;
        }}

        /* Acuse de envio. Sustituye al aviso de simulacion una vez el
           alumno ha pulsado Enviar: el mensaje ya no es un borrador, es un
           hecho consumado dentro de la simulacion. */
        .correo-enviado {{
            background: #E7F6EF; border: 1px solid #A7DCC4;
            color: #076B47; border-radius: 8px; padding: 9px 12px;
            font-size: 11.5px; font-weight: 600; margin-bottom: 14px;
        }}

        /* ---------- Filas interactivas de veredicto ---------- */

        /* Cabecera de la lista de gastos. Replica el aspecto de la cabecera
           de tabla anterior, pero sobre una rejilla de columnas de Streamlit,
           que es lo que permite intercalar botones en cada fila. */
        .fila-cabecera {{
            font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase;
            color: {Paleta.ETIQUETA}; font-weight: 700; padding-bottom: 2px;
        }}

        /* Celda de concepto: descripcion en primera linea y metadatos debajo. */
        .celda-concepto {{ font-size: 13px; line-height: 1.45; }}

        .celda-meta {{
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 11px; color: {Paleta.TEXTO_SUAVE};
        }}

        /* Marca de discrepancia entre el alumno y el agente. Es el dato mas
           valioso del ejercicio, asi que se destaca en rojo y en versalitas. */
        .discrepa {{
            display: inline-block; margin-left: 6px; font-size: 9.5px;
            font-weight: 800; letter-spacing: 0.08em; color: {Paleta.ROJO};
        }}

        /* Celda aun sin decidir por el alumno. */
        .sin-decidir {{
            font-size: 11.5px; color: {Paleta.ETIQUETA}; font-style: italic;
        }}

        /* Separador entre filas, para que la lista se lea como una tabla. */
        .separador-fila {{
            height: 1px; background: #EDF1F7; margin: 2px 0 6px 0;
        }}

        /* ---------- Pantalla de resolucion ---------- */

        /* Franja superior con el resultado de la correccion. Ocupa todo el
           ancho y es lo primero que se ve al abrir la pantalla: el alumno
           acaba de pronunciarse y lo que espera es saber si acerto. */
        .correccion {{
            border-radius: 12px; padding: 16px 20px; margin-bottom: 18px;
            display: flex; align-items: center; gap: 14px;
        }}

        .correccion-icono {{
            font-size: 26px; line-height: 1; flex: 0 0 auto;
        }}

        .correccion-titulo {{
            font-size: 17px; font-weight: 800; letter-spacing: -0.01em;
        }}

        .correccion-detalle {{
            font-size: 12.5px; margin-top: 3px; opacity: 0.85;
        }}

        /* Los tres desenlaces, con sus colores. */
        .correccion-acertada {{
            background: #E7F6EF; border: 1px solid #A7DCC4; color: #076B47;
        }}

        .correccion-fallada {{
            background: #FDECEA; border: 1px solid #F3B7B0; color: #8C1D13;
        }}


        /* Bloque principal con el razonamiento. Tipografia de lectura y
           tamano algo mayor de lo habitual: es el texto que el alumno debe
           leer con atencion y compara con su propia decision. */
        /* Cita literal de la clausula de la politica. Se compone con tipo
           ligeramente menor y en cursiva para que se lea como texto traido de
           otro documento y no como una frase escrita por el agente. */
        .clausula-cita {{
            background: {Paleta.AZUL_SUAVE}; border-radius: 10px;
            padding: 13px 16px; margin: 2px 0 16px 0;
            font-size: 13px; line-height: 1.6; font-style: italic;
            color: {Paleta.MARINO};
        }}

        .resolucion-texto {{
            background: #FBFCFE; border: 1px solid {Paleta.BORDE};
            border-left: 3px solid {Paleta.AZUL};
            border-radius: 10px; padding: 18px 20px; margin: 4px 0 16px 0;
            font-size: 14.5px; line-height: 1.75; color: {Paleta.TEXTO};
        }}

        /* Frase del contraste de fechas, destacada dentro del razonamiento
           porque suele ser el dato que decide la resolucion. */
        .resolucion-fechas {{
            display: block; margin-top: 12px; padding-top: 12px;
            border-top: 1px dashed {Paleta.BORDE};
            font-weight: 600;
        }}

        /* Fila con el veredicto del agente y la decision del alumno,
           enfrentados para que la comparacion sea inmediata. */
        .resolucion-cara {{
            display: flex; gap: 10px; align-items: center;
            font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase;
            color: {Paleta.ETIQUETA}; font-weight: 700; margin-bottom: 4px;
        }}

        /* ---------- Animaciones de entrada ---------- */

        /* Entrada de la ventana emergente: aparece desde abajo, con un ligero
           aumento de escala. La duracion es corta a proposito; una animacion
           larga se percibe como lentitud en cuanto se ha visto dos veces. */
        @keyframes aparecer {{
            from {{ opacity: 0; transform: translateY(22px) scale(0.97); }}
            to   {{ opacity: 1; transform: translateY(0)    scale(1);    }}
        }}

        /* Entrada de la ilustracion, un punto mas tardia que la del marco,
           para que se lea como una secuencia y no como un salto. */
        @keyframes revelar {{
            from {{ opacity: 0; transform: scale(1.04); }}
            to   {{ opacity: 1; transform: scale(1);    }}
        }}

        /* Se aplica a la ventana modal de Streamlit. Se seleccionan varios
           atributos porque la biblioteca ha cambiado el nombre del suyo entre
           versiones y conviene que la animacion sobreviva a una actualizacion. */
        div[role="dialog"],
        div[data-testid="stDialog"] > div,
        div[data-modal-container] > div {{
            animation: aparecer 340ms cubic-bezier(0.16, 0.84, 0.44, 1) both;
        }}

        /* La ilustracion de bienvenida, con su pequeno retardo. */
        div[role="dialog"] img {{
            animation: revelar 520ms cubic-bezier(0.16, 0.84, 0.44, 1) 120ms both;
            border-radius: 10px;
        }}

        /* Entrada del contenido principal la primera vez que se pinta. Es un
           matiz discreto: basta con que la pagina no aparezca de golpe. */
        .block-container {{
            animation: aparecer 420ms ease-out both;
        }}

        /* Pie de la ventana de bienvenida. */
        .bienvenida-pie {{
            text-align: center; color: {Paleta.TEXTO_SUAVE};
            font-size: 12.5px; margin: 14px 0 4px 0; line-height: 1.6;
        }}

        /* ---------- Controles ---------- */

        /* Boton principal, en el azul de acento y con el texto en negrita. */
        .stButton > button[kind="primary"] {{
            background: {Paleta.AZUL}; border: none; border-radius: 9px;
            font-weight: 700; padding: 10px 22px; font-size: 14px;
        }}

        .stButton > button[kind="primary"]:hover {{ background: #1639B8; }}

        /* Area de texto de la politica: monoespaciada, porque se edita como un
           documento normativo y la alineacion ayuda a leer las clausulas. */
        .stTextArea textarea {{
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 12.5px; line-height: 1.6;
            border-radius: 10px; border: 1px solid {Paleta.BORDE};
        }}
        </style>
        """
        st.markdown(hoja, unsafe_allow_html=True)
