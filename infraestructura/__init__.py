"""
Capa de infraestructura.

Agrupa todo lo que habla con el mundo exterior: el sistema de ficheros, el
proveedor del modelo de lenguaje y la cache en memoria.

Es la capa que se espera que cambie con mas frecuencia -un proveedor nuevo, un
formato de datos distinto- y por eso se mantiene detras de interfaces estables.
"""
