# Agente de control de gastos · ESIC University

Demo de aula. Un agente evalúa apuntes de viaje contra una política escrita en
castellano que el alumno puede editar en pantalla, y el alumno supervisa cada
resolución. Audiencia mayoritariamente no técnica.

La idea que sostiene todo el proyecto: **el texto de la política es el programa
y el modelo es el intérprete.** Cualquier cambio que reste poder a ese texto —
por ejemplo, fijar en código qué se verifica — contradice lo que la aplicación
enseña, aunque funcione.

## Cómo trabajar en este repositorio

- Castellano en identificadores, comentarios, mensajes de commit y textos de
  pantalla. Sin acentos en el código y en los mensajes de commit; con acentos
  en todo lo que ve el usuario.
- Programación orientada a objetos y estructurada. Ratio de comentarios
  aproximadamente 1:1, y el comentario explica **por qué**, no qué hace la
  línea siguiente.
- Cuatro capas, con las dependencias siempre hacia adentro:
  `dominio` (no importa nada externo) ← `aplicacion` ← `infraestructura` /
  `interfaz`. El dominio no conoce ni Streamlit ni el cliente del modelo.
- Nada de dependencias nuevas sin motivo fuerte. Ahora son cuatro:
  streamlit, openai, httpx y openpyxl. Pandas se retiró porque no se usaba y
  rompía el despliegue.

## Commits

Se commitea cuando hay un cambio relevante, y el mensaje va sin escatimar, con
esta estructura:

```
Titulo en una linea, en imperativo

PROBLEMA
Que se observaba, con el sintoma concreto.

DIAGNOSTICO
Por que ocurria. Incluye lo que se descarto y por que.

SOLUCION
Que se hizo, y las decisiones de diseño que no son obvias.

VERIFICACION
Que se probo y con que resultado, con los datos reales de la prueba.
```

La sección de verificación no es adorno: **no se commitea nada sin haberlo
probado**, y el resultado de esa prueba va escrito en el mensaje. Si una prueba
dio un falso positivo o negativo antes de acertar, se deja anotado.

## Verificación

- Lógica de dominio y aplicación: proveedores simulados, sin consumir cuota.
- Interfaz: `streamlit.testing.v1.AppTest`.
- Estado de widgets, parámetros de URL y cualquier cosa visual: **navegador
  real**. AppTest no reproduce el borrado de estado de los widgets que
  Streamlit hace al no dibujarlos, ni refleja la escritura de parámetros de
  URL. Las dos cosas ya han dado un falso resultado en este proyecto.

## Despliegue

GitHub → Streamlit Community Cloud, con Python 3.11 fijado en los ajustes
avanzados (no lee `runtime.txt`). El pie de la barra lateral muestra una huella
del código; `python3 version.py` imprime la misma. Si no coinciden, lo
desplegado no es lo último: Manage app → Reboot.

Secretos en el panel de Streamlit: `[llm] clave_api` (Groq), `[busqueda]
clave_api` (Tavily), `[aula] contrasena` y `limite_evaluaciones`.

## Trampas ya pisadas

- Streamlit borra el estado de los widgets que no se dibujan en una ejecución.
  Por eso la política se guarda en una clave propia que no es la del widget, y
  por eso las modales se abren **al final** del renderizado.
- Una modal puede cerrarse con su aspa o pulsando fuera, sin ejecutar su botón.
  Toda selección que abra una modal se consume **al abrirla**, nunca al
  cerrarla.
- La caché de evaluaciones se indexa por política, gastos y **huella del
  código**. Cambiar el prompt sin la huella en la clave dejaba la caché
  sirviendo respuestas de la versión anterior.
- El resultado y su traza de verificación viajan juntos en la caché. Separarlos
  dejaba el panel de consultas vacío al servir de caché.
- `TipoVeredicto.desde_texto` tolera formas matizadas ("APROBADO CON
  EXCEPCIÓN"). Con coincidencia exacta, todo eso caía en REVISION y la pantalla
  se contradecía a sí misma.
- Ninguna cláusula de la política puede depender de la fecha de hoy ni de un
  dato que el fichero de gastos no contenga. La cláusula de antigüedad denegaba
  los ocho gastos por eso, sin que saltara ningún error.

## Datos de la demo

`datos/gastos_demo.csv` son ocho apuntes que alternan correcto e incorrecto.
Cada fila incorrecta falla **por una sola causa**, y los importes por comensal
se fijaron por debajo del límite a propósito para que ninguna pueda resolverse
con una comparación aritmética: la única vía es verificar un hecho externo.

Regla dura del proyecto: **un caso que se resuelve con un IF de Excel no vale**.
Si un cambio introduce uno, sobra.

Los hechos del lado real (establecimientos, ubicaciones, festivos, ferias) se
comprueban buscándolos antes de escribirlos en los datos, nunca de memoria: si
el dato es falso, el agente dirá lo contrario y el ejemplo se cae en clase.
