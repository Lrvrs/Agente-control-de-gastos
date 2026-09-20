"""Entidad que representa la politica de gastos que el alumno puede editar."""

from dataclasses import dataclass
import hashlib
import re


@dataclass(frozen=True)
class Politica:
    """
    La politica de viajes, tal y como esta escrita en lenguaje natural.

    Es la pieza central del ejercicio: el alumno la modifica en un cuadro de
    texto y observa como cambian los veredictos sin que nadie toque el codigo.
    Por eso se guarda como texto libre y no como una estructura de reglas: en
    cuanto se formaliza en campos, se pierde justamente lo que se quiere ensenar.
    """

    # Texto integro de la politica, en Markdown.
    texto: str

    def __post_init__(self) -> None:
        """Valida que la politica no llegue vacia."""
        # Una politica vacia haria que el modelo se inventase las reglas enteras,
        # que es un fallo silencioso y dificil de detectar en clase.
        if not self.texto or not self.texto.strip():
            raise ValueError("La política no puede estar vacía.")

    @property
    def huella(self) -> str:
        """
        Huella digital corta y estable del texto de la politica.

        Sirve como clave de cache: dos alumnos que no hayan tocado la politica
        por defecto comparten huella y comparten resultado, de modo que la
        segunda evaluacion no consume ninguna llamada al modelo.
        """
        # Se normalizan espacios y saltos para que un retorno de carro de mas no
        # invalide la cache. SHA-256 truncado a 16 caracteres: colision
        # practicamente imposible en el ambito de una clase y clave manejable.
        normalizado = " ".join(self.texto.split())
        return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()[:16]

    @property
    def numero_de_lineas(self) -> int:
        """Cuenta las lineas no vacias, para mostrarlo como dato en la interfaz."""
        return len([linea for linea in self.texto.splitlines() if linea.strip()])

    def difiere_de(self, otra: "Politica") -> bool:
        """Indica si esta politica es distinta de otra, ignorando el formato."""
        # Se compara por huella y no por texto crudo para que un cambio de
        # sangrado o una linea en blanco no cuenten como modificacion real.
        return self.huella != otra.huella

    # Reconoce el arranque de una clausula numerada: posibles espacios de
    # sangrado, un numero, un punto y el resto de la linea. Es el unico formato
    # que la politica por defecto utiliza, y el que se pide respetar al alumno
    # que la edite.
    _PATRON_CLAUSULA = re.compile(r"^\s*(\d+)\.\s+(.*)$")

    def texto_de_clausula(self, referencia: str) -> str:
        """
        Devuelve el texto literal de la clausula que cita un veredicto.

        El agente cita la clausula en lenguaje libre ("cláusula 12", "12.
        Excepción por evento", "punto 5"), de modo que lo unico fiable que se
        puede extraer de esa cita es el numero. Con el numero se recorta del
        texto de la politica el parrafo correspondiente.

        Se cita la politica viva, la que el alumno tiene en el cuadro de texto,
        y no una copia guardada en el codigo. Asi, si la ha modificado, la
        pantalla le muestra su propia redaccion y no la original, que es
        precisamente lo que hace visible el efecto de haberla cambiado.

        Devuelve cadena vacia cuando no hay numero en la cita o cuando ese
        numero no existe en la politica. Es un adorno del razonamiento, no una
        pieza de la que dependa la resolucion, asi que ante la duda se calla en
        lugar de mostrar un parrafo equivocado.
        """
        if not referencia:
            return ""

        # Primer numero que aparezca en la cita. Un numero dentro de un importe
        # ("120 EUR") no llega hasta aqui porque la cita es una referencia, no
        # el motivo; aun asi, si no existe como clausula, el recorte falla y se
        # devuelve cadena vacia, que es el comportamiento deseado.
        encontrado = re.search(r"\d+", referencia)
        if encontrado is None:
            return ""
        numero = encontrado.group(0)

        # Se recorre la politica linea a linea acumulando el parrafo desde que
        # arranca la clausula buscada hasta que empieza otra o hasta que
        # aparece un encabezado de seccion.
        recogiendo = False
        partes: list[str] = []
        for linea in self.texto.splitlines():
            arranque = self._PATRON_CLAUSULA.match(linea)

            if arranque is not None:
                # Otra clausula distinta cierra la que se estaba recogiendo.
                if recogiendo:
                    break
                if arranque.group(1) == numero:
                    recogiendo = True
                    partes.append(arranque.group(2))
                continue

            if recogiendo:
                # Un encabezado o una linea en blanco cierran el parrafo.
                if not linea.strip() or linea.lstrip().startswith("#"):
                    break
                partes.append(linea.strip())

        if not partes:
            return ""

        # Se limpia el enfasis de Markdown y se colapsan los espacios, porque el
        # parrafo va a pintarse dentro de una caja estrecha.
        texto = " ".join(" ".join(partes).split())
        return texto.replace("**", "").replace("*", "")
