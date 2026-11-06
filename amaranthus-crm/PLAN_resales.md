# Resales → CRM, orden de trabajo

La clave de la API todavía no conecta. Resales solo acepta llamadas desde la IP fija del servidor. Una prueba hecha desde otro sitio fue rechazada: la IP no coincide con la de la clave. Hasta que la llamada salga de ese servidor, la conexión no está activa.

Cuando Resales responda, el orden es este:

1. Configurar el enlace y auditarlo entero.
2. Volcar las propiedades de la web original del propietario a su CRM. El catálogo ya se sincroniza desde `https://www.amaranthus-realestate.com`: 40 fichas, última sync correcta el 4 de noviembre de 2026 a las 19:11 (hora de Madrid). Hay que comprobar que sigue al día antes de dar este paso por bueno.
3. Cuando ese volcado esté correcto, hacer el volcado completo de todo lo que hay en su web.
