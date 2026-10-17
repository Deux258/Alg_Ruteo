# Evolución del esquema

`crear_bd.sql` es la versión inicial 1. El orquestador guarda su SHA-256 y no
permite modificar una versión ya aplicada. Nuevos cambios deben ir en archivos
`002_descripcion.sql`, `003_descripcion.sql`, etc., sin BEGIN/COMMIT/ROLLBACK:
el ejecutor ya los aplica en una transacción y guarda el checksum junto al número.

No cambiar migraciones que ya se ejecutaron. No usar DROP CASCADE sobre el esquema
para actualizar una instalación. Los cambios de geometría/contrato requieren una
versión nueva de datos y una migración compatible con los snapshots conservados.

Para una creación manual desde cero, ejecutar primero `crear_bd.sql` y luego las
migraciones en orden. `main` realiza este proceso en cada arranque y omite las ya
aplicadas. La entrega inicial no necesita una migración 002 ficticia.
