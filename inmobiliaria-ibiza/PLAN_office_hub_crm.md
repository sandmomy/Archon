# Office Hub y el CRM · auditoría y plan

Fecha: 5 nov 2026 (Europe/Madrid).

El Office Hub (https://ibiza-office-hub.pages.dev) es la oficina en 3D. El CRM ya existe, en el zip `inmobiliaria-ibiza-app`: Worker de Cloudflare en `cloud/` (D1, `cloud/schema.sql`), interfaz en `static/` (Chat, Catálogo, Nueva casa, Contactos, WhatsApp, Por aprobar, Avisos) y servidor local en `app/`. Esta pasada deja el hub usable con las funciones reales del CRM en datos de demostración. No llama al Worker, no lleva secretos y no despliega el CRM.

## Auditoría

| | Office Hub | CRM |
|---|---|---|
| Dónde vive | Pages, proyecto `ibiza-office-hub` | Worker, solo con `cloud/deploy.sh` y `CLOUDFLARE_API_TOKEN` |
| Datos | Seis módulos, filas de demostración en el navegador | D1: propiedades, documentos, clientes, contactos, revisión (bandeja), biblioteca, agenda en R2, WhatsApp |
| Qué se puede pulsar | Cada fila del monitor (importar, ficha, WhatsApp, aprobar, confirmar…) escribe en el registro de ese bot | Las mismas acciones ya tienen ruta en el Worker |
| Qué no está | Ninguna llamada de red al CRM. Los nombres (Ana R., Villa Porroig, facturas 2026-014) son ficticios, del estilo de los tests | El zip no trae secretos, base de datos, fotos ni datos de clientes |

La app del CRM responde bajo una ruta secreta (sin ella, 404) y está pensada para ir detrás de Cloudflare Access. El hub es público. Por eso no se conectan todavía.

Los borradores de `legal/` (nota de encargo, arras, hoja de visita, colaboración, protección de datos) siguen pendientes de abogado. El hub solo los nombra; no los genera.

## Mapa: módulo del hub → función del CRM

| Módulo del hub | Pestaña / código del CRM | Qué hace la fila del monitor |
|---|---|---|
| Búsqueda de portales | `cloud/src/portales.js`, `escaner.js`, `buscar.js` | Idealista, Fotocasa, Habitaclia, Facebook. Lo nuevo entra en Por aprobar |
| Catálogo de casas | Catálogo, Nueva casa · `propiedades`, `documentos`, `pdfcasa.js` | Ficha, PDF ES/EN/IT, avisar si falta un idioma |
| Leads y captación | Contactos · `contactos`, `clientes` | Seguimiento, ficha, WhatsApp |
| Facturación | Biblioteca · `biblioteca.js`, borradores de `legal/` | Abrir nota de encargo o arras, marcar factura cobrada, PDF |
| Agenda y visitas | `cloud/src/agenda.js`, `visita.js` · Hoy / Mañana / Semana | Confirmar visita, reservar hueco, checklist de notaría |
| IA y automatización | Por aprobar · tabla `revision`. Avisos. Borradores de `waia.js` | Aprobar precio o fotos, ver aviso, enviar borrador de WhatsApp |

Chat (inicio del CRM) no tiene módulo propio: es la puerta de las mismas casas, PDFs y citas. Cuando haya datos reales, el registro del bot puede mostrar la última respuesta del chat, no un séptimo puesto.

## Esta pasada (fase 0, hecha en el hub)

- El monitor es más ancho y casi plano. La ventana cubre el cristal, no un recuadro en el centro.
- La ventana es una cola (Cola / Registro), sin tarjetas. Arriba lo que te toca aprobar, luego lo que la IA puede hacer sola, y al final lo que ya está listo. La acción va en la misma fila.
- Móvil: menos píxeles y sin sombras por debajo de 740 px; la oficina se pausa si la pestaña está oculta. En horizontal la barra baja a una pastilla y la ventana cabe en la pantalla. En vertical la ventana crece para que la lista se pueda usar, porque el cristal es muy apaisado.

## Cuaderno local (esta noche)

Las seis mesas leen y escriben el mismo cuaderno en el navegador, con la forma del CRM y sin red:

- Importar un portal crea una fila en Por aprobar.
- Aprobar un cambio de precio actualiza la ficha. Rechazar la quita de la bandeja.
- Avisar un PDF que falta abre un aviso en la bandeja, sin duplicarlo.
- WhatsApp marca el contacto como enviado. Confirmar, reservar o la checklist mueven la agenda. Cobrada cierra la factura.
- Abrir una nota de encargo o unas arras solo enseña el borrador y recuerda que falta el abogado.

La burbuja del bot se queda con el último resultado. Si se recarga la página, vuelve la demostración. El paso siguiente sigue siendo el de abajo: lectura real, luego una escritura.

## Cómo se integra, poco a poco

1. **Lectura.** Un endpoint de solo lectura en el Worker (conteos y listas: casas, contactos, citas de hoy, pendientes de la bandeja, avisos). El hub lo pide con la ruta acordada, nunca con un token dentro del repo de Pages. Si falla, se quedan las filas de demostración.
2. **Una escritura cada vez**, por el endpoint que ya existe y con su control de origen: aprobar o rechazar una fila de la bandeja, confirmar una visita, marcar una factura. El botón del monitor llama a esa ruta y el registro del bot enseña lo que respondió el Worker.
3. **Quitar la demostración** cuando esa función ya lee y escribe de verdad. El resto de módulos sigue en demostración hasta que le toque.

El despliegue del hub (`wrangler pages deploy`) y el del CRM (`cloud/deploy.sh`) siguen siendo dos cosas distintas. Ninguna fase mete secretos, fotos ni teléfonos reales en este repositorio.
