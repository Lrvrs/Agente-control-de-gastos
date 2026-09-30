"""Evaluacion de la demo guardada en disco, para servirla sin llamar al modelo."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List

from dominio.veredicto import ResultadoEvaluacion, TipoVeredicto, Veredicto
from infraestructura.buscador_web import ResultadoBusqueda


@dataclass
class DemoPrecalculada:
    """
    Una evaluacion real hecha antes de clase, con todo lo que la acompana.

    Reune el resultado, la traza de verificacion y los cuerpos de los correos
    porque los tres son la misma cosa vista desde sitios distintos de la
    pantalla: separarlos dejaba el panel de consultas o el correo vacios al
    servir la demo, que es el fallo que ya se dio con la cache en memoria.
    """

    # Huella del codigo con el que se genero. Si no coincide con la del codigo
    # que arranca, la demo se obtuvo con otro prompt y no debe servirse.
    huella_codigo: str

    # Claves de la cache en memoria a las que corresponde esta evaluacion.
    huella_politica: str
    huella_gastos: str

    resultado: ResultadoEvaluacion
    traza: List[ResultadoBusqueda] = field(default_factory=list)

    # Cuerpos de correo ya redactados, con la misma clave que usa el redactor.
    cuerpos_correo: Dict[str, str] = field(default_factory=dict)


class RepositorioDemoPrecalculada:
    """
    Lee y escribe la demo precalculada.

    El fichero NO vive en `datos/`. La huella del codigo incluye todo lo que
    hay en esa carpeta, de modo que guardar ahi la demo cambiaria la huella en
    el mismo acto de guardarla y la invalidaria a si misma, siempre.
    """

    RUTA_POR_DEFECTO = (
        Path(__file__).resolve().parent.parent / "precalculado" / "demo.json"
    )

    def __init__(self, ruta: Path | None = None) -> None:
        """Fija el fichero; en las pruebas se sustituye por uno temporal."""
        self._ruta = ruta or self.RUTA_POR_DEFECTO

    def guardar(self, demo: DemoPrecalculada) -> None:
        """Escribe la demo en disco, creando la carpeta si hace falta."""
        self._ruta.parent.mkdir(parents=True, exist_ok=True)

        contenido = {
            "huella_codigo": demo.huella_codigo,
            "huella_politica": demo.huella_politica,
            "huella_gastos": demo.huella_gastos,
            "modelo_utilizado": demo.resultado.modelo_utilizado,
            "veredictos": [
                {**asdict(v), "tipo": v.tipo.value}
                for v in demo.resultado.veredictos.values()
            ],
            "traza": [asdict(b) for b in demo.traza],
            "cuerpos_correo": demo.cuerpos_correo,
        }

        # ensure_ascii a falso y sangrado: el fichero se versiona en git y una
        # diferencia legible vale mas que ahorrar unos bytes.
        self._ruta.write_text(
            json.dumps(contenido, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def cargar(self, huella_codigo: str) -> DemoPrecalculada | None:
        """
        Devuelve la demo si existe y se genero con este mismo codigo.

        Cualquier problema -fichero ausente, JSON roto, campos que ya no
        existen- devuelve None en lugar de lanzar. La demo es un atajo: si
        falla, la aplicacion debe arrancar igual y evaluar de la forma normal.
        """
        try:
            bruto = json.loads(self._ruta.read_text(encoding="utf-8"))

            if bruto["huella_codigo"] != huella_codigo:
                return None

            resultado = ResultadoEvaluacion(
                huella_politica=bruto["huella_politica"],
                modelo_utilizado=bruto["modelo_utilizado"],
                # Se marca como precalculado para que la pantalla no lo
                # presente como una evaluacion que acaba de hacer el modelo.
                precalculado=True,
            )
            for dato in bruto["veredictos"]:
                resultado.anadir(
                    Veredicto(**{**dato, "tipo": TipoVeredicto(dato["tipo"])})
                )

            return DemoPrecalculada(
                huella_codigo=bruto["huella_codigo"],
                huella_politica=bruto["huella_politica"],
                huella_gastos=bruto["huella_gastos"],
                resultado=resultado,
                traza=[ResultadoBusqueda(**b) for b in bruto["traza"]],
                cuerpos_correo=dict(bruto["cuerpos_correo"]),
            )
        except Exception:
            return None
