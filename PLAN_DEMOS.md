# Plan: aguantar demos de clase (15-20 alumnos) gratis

Decidido el 2026-09-30. Análisis ya hecho: NO volver a analizar el proyecto entero.
Leer solo los ficheros citados. Sin subagentes, sin capturas de navegador. Respuestas cortas.

## Contexto común (Gastos + Chatpdf comparten la cuenta de Groq)
- Groq gratis, límites POR MODELO y por organización: gpt-oss-120b / gpt-oss-20b / qwen3.8-27b
  = 30 RPM, 8K TPM, 200K TPD cada uno; llama-3.1-8b-instant = 6K TPM, 500K TPD.
  Total ≈ 1,1 M tokens/día para todas las apps. Una demo grande al día.
- Reparto: modelo principal fijo por app + lista de respaldo ante 429.
  Gastos → gpt-oss-120b, qwen3.8-27b, gpt-oss-20b. Chatpdf → gpt-oss-20b primero.
- Tavily gratis ≈ 1.000 créditos/mes.
- Streamlit = UN proceso: `st.cache_resource` es memoria común de todos los alumnos
  (sirve para cola y cuota globales). Se pierde al reiniciar o dormir la app.

## Paso 1 (este proyecto) — tareas
1. Demo precalculada. Script que evalúa `datos/gastos_demo` con la política por defecto y guarda
   veredictos + traza del agente + correos en `datos/demo_precalculada.json`. Al arrancar,
   cargarlo en la caché (`vista_principal.py:90-105`). Respetar la huella del código: si no
   coincide, ignorar el fichero. Opcional: normalizar espacios en la huella de la política.
2. Cola global: semáforo en `st.cache_resource`, máx. 3-4 llamadas a Groq simultáneas;
   el resto espera con `st.status("En cola…")`.
3. Lista de modelos en `infraestructura/proveedor_llm.py`: secreto `[llm] modelos = [...]`
   (mantener compatibilidad con `modelo`). Ante 429: si «try again in» ≤ pocos s, esperar;
   si no, siguiente modelo. Portar el parser de «try again in» de
   Chatpdf `services/netlify-functions/lib/rag/llm.js` (`duracionEnSegundos`).
4. Reintentos: `servicio_evaluacion.py:30-34,286-313` usa 3 s fijos → backoff exponencial + jitter.
5. Planificación: `planificador_verificacion.py:84-87` traga el error → reintentar igual que la
   evaluación y, si falla, avisar en pantalla «no se pudo verificar en la web».
6. Correos: `redactor_cuerpo_correo.py:83` pide json_object sin la palabra «json» → probable
   400 + segunda llamada. Añadir `pedir_json=False` a `completar()` para el redactor.
7. Tavily: búsquedas en serie (`servicio_evaluacion.py:156-159`) → ThreadPoolExecutor(3).
   En clase, `MAXIMO_CONSULTAS` (hoy 8) configurable, bajar a 4.
8. Cuota diaria GLOBAL en `st.cache_resource` (evaluaciones reales/día), además de la de sesión
   (`aplicacion/control_uso.py`, que se reinicia al recargar).
9. Antes de clase: abrir la app ~10 min antes.

Verificar con las pruebas existentes; no hacer llamadas reales a Groq salvo para generar la demo.

## Pasos siguientes (en `Agente RAG Chatpdf/Chatpdf/PLAN_DEMOS.md`)
2. Chatpdf: lista de modelos, topes y fragmentos. 3. Prueba de calidad e5-small.
4. Chatpdf: embeddings en el navegador. 5. Proveedor de reserva (ambas apps).

## Control de gasto de Claude
- 2026-10-01: hechas las tareas 1 y 2 (commits 0688352 y 223f7a0). Uso semanal 43 % (+2 puntos desde el 41 %).
  Falta generar `precalculado/demo.json` con las claves, y el 403 de Groq en Streamlit sigue sin resolver.
- Uso semanal al empezar el paso 1: 41 % (reinicio sábado 9:00). Anotar % al terminar.
- Usar Sonnet para implementar. Si el paso 1 cuesta > 8 %, dejar el paso 4 para después del sábado.
