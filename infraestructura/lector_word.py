"""Lectura de una politica escrita en Word (.docx)."""

import io
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

# Espacio de nombres de los elementos de texto de Word.
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ErrorFicheroPolitica(Exception):
    """El fichero de politica no se puede leer como un Word."""


@dataclass(frozen=True)
class TextoWord:
    """
    Las dos lecturas posibles de un mismo documento.

    No son lo mismo y la diferencia es el motivo de existir de esta clase.
    Word permite marcar un texto como oculto: no se ve al abrir el documento ni
    al imprimirlo, pero sigue dentro del fichero, y un extractor que recorre el
    texto sin mirar el formato lo recoge igual que el resto.
    """

    # Todo lo que contiene el documento, oculto incluido. Es lo que lee un
    # extractor sin criterio y, por tanto, lo que recibe el modelo.
    completo: str

    # Lo que ve una persona al abrir el documento en Word.
    visible: str


class LectorWord:
    """
    Extrae el texto de un .docx con la biblioteca estandar.

    Un .docx es un zip con un XML dentro, y para leer parrafos y formato basta
    con zipfile y ElementTree. No se anade python-docx: cuatro dependencias son
    las que hay, y esta no justifica una quinta.
    """

    def leer(self, contenido: bytes) -> TextoWord:
        """Devuelve el texto completo y el visible, o lanza ErrorFicheroPolitica."""
        try:
            with zipfile.ZipFile(io.BytesIO(contenido)) as paquete:
                raiz = ET.fromstring(paquete.read("word/document.xml"))
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as error:
            raise ErrorFicheroPolitica(
                "El fichero no es un documento de Word (.docx) válido."
            ) from error

        completo, visible = [], []

        for parrafo in raiz.iter(f"{_W}p"):
            texto_completo, texto_visible = "", ""

            for tramo in parrafo.iter(f"{_W}r"):
                texto = self._texto_del_tramo(tramo)
                texto_completo += texto
                if not self._esta_oculto(tramo):
                    texto_visible += texto

            # Los parrafos vacios se descartan: un parrafo cuyo contenido era
            # todo texto oculto no debe dejar un hueco que delate que faltaba
            # algo en la lectura visible.
            if texto_completo.strip():
                completo.append(texto_completo.strip())
            if texto_visible.strip():
                visible.append(texto_visible.strip())

        return TextoWord(completo="\n\n".join(completo), visible="\n\n".join(visible))

    @staticmethod
    def _esta_oculto(tramo: ET.Element) -> bool:
        """Indica si el tramo lleva la marca de texto oculto de Word."""
        propiedades = tramo.find(f"{_W}rPr")
        if propiedades is None:
            return False

        marca = propiedades.find(f"{_W}vanish")
        if marca is None:
            return False

        # La marca puede estar presente y desactivada (w:val="0" o "false").
        return marca.get(f"{_W}val", "true").lower() not in ("0", "false", "off")

    @staticmethod
    def _texto_del_tramo(tramo: ET.Element) -> str:
        """Concatena el texto de un tramo, respetando tabulaciones y saltos."""
        partes = []
        for hijo in tramo:
            if hijo.tag == f"{_W}t":
                partes.append(hijo.text or "")
            elif hijo.tag == f"{_W}tab":
                partes.append("\t")
            elif hijo.tag in (f"{_W}br", f"{_W}cr"):
                partes.append("\n")
        return "".join(partes)
