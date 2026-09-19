"""Construccion de los mensajes que se envian al modelo de lenguaje."""

from dominio.gasto import ConjuntoGastos
from dominio.politica import Politica


class ConstructorPrompt:
    """
    Redacta la instruccion de sistema y el mensaje de usuario.

    Se aisla en su propia clase porque el prompt es, en la practica, la pieza de
    logica que mas se va a retocar durante la preparacion de la clase, y conviene
    poder tocarla sin abrir el resto del codigo.
    """

    # Instruccion de sistema. Fija el papel, el formato y, sobre todo, los
    # limites: que no invente, que cite clausula y que sepa decir que no sabe.
    INSTRUCCION_SISTEMA = """\
Eres un agente de control de gastos. Tu única función es evaluar cada gasto \
frente a la política de la empresa que se te proporciona.

Reglas que debes cumplir siempre:

1. Aplica exclusivamente la política que recibes en este mensaje. No uses \
normas de otras empresas ni criterios propios.
2. Cita siempre la cláusula concreta de la política en la que apoyas tu \
decisión. Si ninguna cláusula aplica, dilo explícitamente.
3. Si te falta información para decidir, emite REVISION. No inventes datos, \
no supongas tipos de cambio y no completes descripciones ambiguas.
4. Si un gasto es reembolsable solo en parte, emite PARCIAL e indica qué \
importe o qué concepto queda excluido.
5. Algunos apuntes no pueden evaluarse de forma aislada. Antes de decidir, \
compara cada gasto con los demás de la lista: busca duplicados y apuntes \
fraccionados en varios importes menores para eludir un límite o la \
obligación de justificante. Cuando la decisión dependa de otro apunte, cita \
su identificador en el motivo.
6. Si dos cláusulas de la política aplican al mismo gasto y conducen a \
resoluciones distintas, no elijas una en silencio. Aplica la más específica \
si resulta claramente aplicable e indícalo en el motivo; si no está claro \
cuál prevalece, emite REVISION explicando el conflicto.
7. Cuando un gasto invoque una feria, un congreso o cualquier otro evento \
como justificación, procede en este orden: identifica el evento, determina \
sus fechas reales de celebración y comprueba si la fecha del gasto está \
comprendida dentro de ese intervalo. Indica siempre en el motivo el periodo \
de celebración que has aplicado, en el formato "del D al D de mes". Si la \
fecha del gasto queda fuera de ese intervalo, la excepción por evento no es \
de aplicación. Si no puedes determinar las fechas del evento, o no consigues \
confirmar que el evento existe, emite REVISION y dilo explícitamente: no \
supongas un periodo de celebración.

Los cuatro veredictos posibles son exactamente: APROBADO, DENEGADO, PARCIAL \
y REVISION.

Responde unicamente con un objeto JSON con esta forma:

{"veredictos": [{"id": "G-001", "veredicto": "APROBADO", "clausula": "1", \
"motivo": "frase breve"}]}

El campo motivo debe tener una sola frase, de menos de veinticinco palabras.
Debes incluir un elemento por cada gasto recibido, sin omitir ninguno."""

    def construir_instruccion_sistema(self) -> str:
        """Devuelve la instruccion de sistema, identica en todas las llamadas."""
        # Al ser constante, muchos proveedores pueden cachearla internamente y
        # abaratar la peticion. Por eso no se le inyecta nada variable.
        return self.INSTRUCCION_SISTEMA

    def construir_mensaje_usuario(
        self, politica: Politica, gastos: ConjuntoGastos
    ) -> str:
        """
        Compone el mensaje con la politica del alumno y los gastos a evaluar.

        El orden es deliberado: primero la politica y despues los datos. Situar
        las instrucciones antes del material a procesar reduce la probabilidad
        de que el modelo pierda de vista las reglas al llegar al final.
        """
        # Los gastos se serializan en formato compacto de una linea por gasto.
        bloque_gastos = gastos.a_bloque_para_modelo()

        # Se recuerda el numero exacto de gastos esperados. Es una comprobacion
        # barata que reduce mucho las respuestas incompletas.
        numero_gastos = len(gastos)

        return (
            "POLÍTICA DE GASTOS VIGENTE\n"
            "==========================\n"
            f"{politica.texto}\n\n"
            "GASTOS A EVALUAR\n"
            "================\n"
            "Formato de cada línea: id | fecha | empleado | categoría | "
            "ciudad | importe moneda | justificante | descripción\n\n"
            f"{bloque_gastos}\n\n"
            f"Devuelve exactamente {numero_gastos} veredictos, uno por cada "
            "gasto listado, en el formato JSON indicado."
        )
