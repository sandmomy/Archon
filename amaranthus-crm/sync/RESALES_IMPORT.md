# Importación automática a Resales

Primer módulo del CRM: las ventas de la web del cliente entran en Resales solas.
Nadie las da de alta ni las quita a mano. Este documento no cambia ninguna
configuración y no envía nada a Resales.

## Qué se publica y qué no

La fuente es `site/data.json`, solo las fichas con operación Venta. Hoy son 36.
`sync/resales_import_xml.py` las escribe en `site/resales-import.xml` (esquema
Resales 1.5). El alquiler se queda fuera.

El volcado de la API (`resales_dump.py`, filtro de ventas de Baleares) devolvió
84 fichas. No es el catálogo del cliente y no debe convertirse en el feed:

| Grupo | Número | Qué es |
| --- | --- | --- |
| Coinciden | 1 | `lasboas-top` en la web y `R5442232` en Resales (referencia de agencia `LasBoas-7.1`, 995.000 euros) |
| Sobran en el volcado | 83 | 82 en Mallorca y un hotel de Ibiza, `R5245483`, 25.000.000 euros. No están en la web |
| Sobran en la web | 35 | Ventas del cliente que Resales todavía no tiene. Ejemplos: `anahata-ibz`, `royalbeach-attico`, `whiteangel`, `canfurnet`, `escubells` |

`royalbeach-attico` también vale 995.000 euros y es otra ficha. El volcado sirve
solo para saber qué venta ya existe en Resales antes del primer enlace.

## Qué campo rellena el XML

La web cubre la ficha pública. El volcado no añade comisión, captador, calle ni
catastro: la API de búsqueda no los devuelve.

| Campo Resales 1.5 | Kyero 3 | De dónde sale | Estado |
| --- | --- | --- | --- |
| `referenceId` | `id` y `ref` | `slug` de la web | Listo. En Las Boas tiene que coincidir con la referencia de agencia ya creada |
| `type`, `subType` | `type` | `type` de la web, con la tabla del script | El subtipo se deduce. El volcado trae el subtipo real solo de las 84, no de las 35 que faltan |
| `currency`, precio | `currency`, `price`, `price_freq=sale` | `currency` y `price` | Listo |
| `status` | no existe | `off_market` | Listo: Available u Off Market |
| `town` | `town` | `zone` | Listo |
| provincia y país | `province`, `country` | isla Ibiza o Formentera | Deducido, no viene escrito en el JSON |
| dormitorios, baños, superficies, planta, año | `beds`, `baths`, `surface_area` | `facts` | Listo cuando el hecho existe. Algunas fichas no traen baños o superficie |
| características | `pool`, `new_build` | `features` | Parcial. El vocabulario de Resales es más cerrado que el de la web |
| `descriptions/en` | `desc/en` | `description` | Listo, en inglés |
| `propertyImages` | `images` | `image` y `gallery` | Hay URL. No se sabe si el lado largo mide 800 px |
| `address1`, `address2`, `postCode` | `location_detail` | no está | Falta en las 36 |
| `cadastralRef` | `catastral` | no está | Falta en las 36. Hace falta para compartir en la red |
| `descriptions/es` | `desc/es` | no está | Falta en las 36. Hace falta para compartir |
| `saleType` | `leasehold` | no está | Falta. Valores: Freehold o Leasehold |
| `commissionPct` | no existe en Kyero | no está | Falta. En el alta se puede dejar un porcentaje por defecto |
| captador (`lister`) | no existe | no está | Falta en los datos. En el alta se elige un usuario por defecto |
| agencia | no existe | no es un campo de la ficha | La cuenta ya es la de Amaranthus |

Kyero 3 es el formato alternativo que Resales acepta. Cubre la misma ficha
pública y tampoco trae comisión ni captador. El script actual genera 1.5.

## Cómo se automatiza

1. El sync de la web (`sync_catalog.py`) sigue siendo la fuente. Ya copia el
   catálogo público a `data.json`.
2. Después de cada sync, ejecutar `resales_import_xml.py`. El XML queda con
   las ventas de ese momento y con ninguna más.
3. Publicar ese archivo en una URL HTTPS fija del sitio. No dar esa URL a
   Resales hasta completar o aceptar los campos que faltan.
4. Un solo alta, con el formulario de importación de Resales. La cuenta tiene
   que ser de red. En el formulario se indican la URL, el usuario captador por
   defecto y la comisión por defecto. Resales hace una simulación y hay que
   aprobarla. El alta puede tardar unos días laborables.
5. Antes de esa primera ejecución, la referencia de Las Boas en Resales y el
   `referenceId` del XML tienen que ser el mismo texto. Si no, el primer pase
   crea un duplicado. Ese enlace solo se hace una vez.
6. A partir de ahí Resales descarga el XML solo, una vez al día a las 06:00,
   y manda un resumen por email. La documentación no ofrece un disparo manual.
   Una venta nueva en la web entra al día siguiente. Una venta que desaparece
   de la web sale del XML y Resales la pasa a Off Market.

No hace falta el botón de feed nuevo del panel: eso crea un feed de salida.
Tampoco hace falta la API de búsqueda para escribir fichas: esa API solo lee.
