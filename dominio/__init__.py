"""
Capa de dominio.

Contiene las entidades del problema -gastos, politica y veredictos- expresadas
sin ninguna dependencia de Streamlit ni de ningun proveedor de IA.

Mantener esta capa aislada tiene una consecuencia practica: el dia que se
sustituya la interfaz o el modelo de lenguaje, este paquete no se toca.
"""
