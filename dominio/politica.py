"""Entidad que representa la politica de gastos que el alumno puede editar."""

from dataclasses import dataclass
import hashlib


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
