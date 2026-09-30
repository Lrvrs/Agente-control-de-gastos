"""Precalcula la evaluacion de la demo y la guarda en precalculado/demo.json.

Se ejecuta con `python3 generar_demo.py` DESPUES de cualquier cambio de codigo
y ANTES de subirlo. La demo guarda la huella del codigo con el que se hizo, y
cualquier cambio en un .py o en datos/ la deja caducada: la aplicacion la
ignora y el primer alumno vuelve a pagar la evaluacion completa.

Es la unica pieza del proyecto que llama de verdad al modelo y al buscador
fuera de la aplicacion, asi que lee las mismas credenciales por variables de
entorno: LLM_CLAVE_API y BUSQUEDA_CLAVE_API.
"""

import sys

from aplicacion.redactor_cuerpo_correo import GeneradorCuerpoCorreo
from aplicacion.servicio_evaluacion import ServicioEvaluacion
from dominio.correo import RedactorCorreo
from infraestructura.buscador_web import FabricaBuscadores
from infraestructura.cache_evaluaciones import CacheEvaluaciones
from infraestructura.configuracion import Configuracion
from infraestructura.demo_precalculada import (
    DemoPrecalculada,
    RepositorioDemoPrecalculada,
)
from infraestructura.proveedor_llm import FabricaProveedores
from infraestructura.repositorio_datos import RepositorioDatos
from version import huella


def main() -> int:
    """Evalua, redacta los correos y guarda el conjunto. Devuelve el codigo de salida."""
    configuracion = Configuracion()

    # Sin buscador la demo saldria con todo lo externo en REVISION, y eso
    # precalculado enganaria: parecera que el agente no sabe verificar. Es
    # preferible no generar nada.
    if not configuracion.busqueda.esta_configurado:
        print("Falta BUSQUEDA_CLAVE_API: la demo no puede verificar hechos.")
        return 1

    proveedor = FabricaProveedores.crear(configuracion.llm)
    buscador = FabricaBuscadores.crear(configuracion.busqueda.clave_api)
    repositorio = RepositorioDatos()
    politica = repositorio.cargar_politica()
    gastos = repositorio.cargar_gastos()

    servicio = ServicioEvaluacion(
        proveedor=proveedor, cache=CacheEvaluaciones(), buscador=buscador
    )
    print(f"Evaluando {len(gastos)} gastos con {proveedor.nombre_modelo}...")
    resultado = servicio.evaluar(politica, gastos, usar_cache=False)

    # Una demo sin verificar se descarta por la misma razon que una sin
    # buscador: presentaria como verdad del agente algo que no comprobo.
    if resultado.verificacion_fallida:
        print("La fase de verificacion fallo. No se guarda nada; repite.")
        return 1

    # Una demo con huecos se descarta: el aula la veria como la verdad del
    # agente, y un hueco es un fallo puntual del modelo que se arregla
    # repitiendo la ejecucion.
    huecos = [
        g.identificador for g in gastos if resultado.obtener(g.identificador) is None
    ]
    if huecos:
        print(f"Sin veredicto para {huecos}. No se guarda nada; repite.")
        return 1

    # Los correos se redactan aqui, con el mismo generador que usa la
    # aplicacion, para que la clave de cada cuerpo sea exactamente la de ella.
    generador = GeneradorCuerpoCorreo(proveedor)
    redactor = RedactorCorreo()
    sin_cuerpo = []
    for gasto in gastos:
        veredicto = resultado.obtener(gasto.identificador)
        destinatario = redactor.nombre_destinatario(gasto, veredicto)
        if not generador.generar(gasto, veredicto, destinatario):
            sin_cuerpo.append(gasto.identificador)

    # Un correo sin cuerpo no invalida la demo: la aplicacion recurre a la
    # plantilla fija. Se avisa para que se sepa, no se aborta.
    if sin_cuerpo:
        print(f"Aviso: sin cuerpo de correo para {sin_cuerpo}.")

    RepositorioDemoPrecalculada().guardar(
        DemoPrecalculada(
            huella_codigo=huella(),
            huella_politica=politica.huella,
            huella_gastos=servicio.calcular_huella_gastos(gastos),
            resultado=resultado,
            traza=servicio.traza_verificacion,
            cuerpos_correo=generador.exportar_cuerpos(),
        )
    )
    print(f"Guardado precalculado/demo.json con la huella {huella()}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
