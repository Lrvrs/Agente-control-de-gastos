"""Lectura de una politica escrita en PDF."""

import io
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError



class ErrorFicheroPolitica(Exception):
    """El fichero de politica no se puede leer como un PDF."""


@dataclass(frozen=True)
class TextoPdf:
    """Lo que la biblioteca extrae de un PDF."""

    # Todo el texto de todas las paginas, tal y como lo devuelve la biblioteca.
    # No hay una lectura "visible" aparte, y es el punto de la demostracion: un
    # PDF no tiene marca de texto oculto como Word. El color y la posicion son
    # solo atributos de dibujo, y el extractor devuelve el texto sin mirarlos.
    # Ese texto, tal cual, es la politica que recibe el modelo.
    texto: str

    paginas: int


class LectorPdf:
    """
    Extrae el texto de un PDF con pypdf.

    Se usa una biblioteca y no una lectura a mano porque un PDF no es texto
    plano: el contenido esta partido en operadores de dibujo con fuentes y
    codificaciones propias, y reconstruirlo es un trabajo que ya esta hecho.
    pypdf es Python puro y no arrastra dependencias, que importa: Pillow y
    pandas ya rompieron el despliegue por exigir compilacion.
    """

    # Tope de paginas. Una politica no pasa de unas pocas, y un PDF enorme
    # agotaria la memoria compartida del contenedor gratuito.
    MAXIMO_PAGINAS = 30

    def leer(self, contenido: bytes) -> TextoPdf:
        """Devuelve el texto del PDF, o lanza ErrorFicheroPolitica."""
        try:
            lector = PdfReader(io.BytesIO(contenido))

            if lector.is_encrypted:
                raise ErrorFicheroPolitica(
                    "El PDF está protegido con contraseña y no se puede leer."
                )

            paginas = lector.pages
            if len(paginas) > self.MAXIMO_PAGINAS:
                raise ErrorFicheroPolitica(
                    f"El PDF tiene más de {self.MAXIMO_PAGINAS} páginas."
                )

            partes = [pagina.extract_text() or "" for pagina in paginas]
        except ErrorFicheroPolitica:
            raise
        except (PdfReadError, ValueError, KeyError, OSError) as error:
            raise ErrorFicheroPolitica("El fichero no es un PDF válido.") from error

        texto = "\n\n".join(p.strip() for p in partes if p.strip())

        # Un PDF escaneado es una imagen: no tiene texto que extraer, y pasarle
        # al modelo una politica vacia le haria inventarse las reglas.
        if not texto:
            raise ErrorFicheroPolitica(
                "El PDF no contiene texto (¿es un escaneo?)."
            )

        return TextoPdf(texto=texto, paginas=len(paginas))
