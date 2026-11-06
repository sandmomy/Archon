# Importación automática a Resales

Primer módulo del CRM: las ventas de la web del cliente entran en Resales solas.
Nadie las da de alta ni las quita a mano. Este documento no cambia ninguna
configuración y no envía nada a Resales.

## Qué se publica y qué no

La fuente es `site/data.json`, solo las fichas con operación Venta. Hay 36 en
la web. `sync/resales_import_xml.py` escribe 35 en `site/resales-import.xml`
(esquema Resales 1.5). Deja fuera `lasboas-top`: ya está en Resales como
`R5442232`, con referencia de agencia `LasBoas-7.1`. El alquiler se queda fuera.

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
catastro: la API de búsqueda no los devuelve. La web no trae una calle postal.
`address1` es la zona del catálogo cuando nombra un lugar. Si esa zona es
solo el municipio (Sant Josep, Sant Antoni, Santa Eulària, Formentera) y el
título nombra un lugar más fino, se usa el del título: Cala Tarida, Benimussa,
Sa Caleta, San Augustin, Vista Alegre, Sa Serra y Es Pujols. La ficha
`vedella-27` usa `Cala Vedella`. Si la descripción nombra una calle, se junta
con la zona. En esa ficha queda `Calle Calvià 27, Cala Vedella`. Si no hay
calle, queda solo la zona. Si el campo está vacío o solo dice Ibiza, se toma
el primer lugar de la descripción en inglés y, si ahí no hay ninguno, el del
título (Figueretes, Playa d'en Bossa). Bossa Nova queda en Playa d'en Bossa.
No hay calle por defecto. Marina Botafoch solo se escribe cuando el texto de
esa ficha dice que la propiedad está ahí. No se copia al resto.

| Campo Resales 1.5 | Kyero 3 | De dónde sale | Estado |
| --- | --- | --- | --- |
| `referenceId` | `id` y `ref` | `slug` de la web | Listo en las 35. `lasboas-top` no entra. Si entrara, la referencia sería `LasBoas-7.1` |
| `type`, `subType` | `type` | `type` de la web, con la tabla del script | El subtipo se deduce. El volcado trae el subtipo real solo de las 84, no de las 35 que faltan |
| `currency`, precio | `currency`, `price`, `price_freq=sale` | `currency` y `price` | Listo |
| `status` | no existe | `off_market` | Listo: Available u Off Market |
| `town` | `town` | `zone` | Listo |
| provincia y país | `province`, `country` | isla Ibiza o Formentera | Deducido, no viene escrito en el JSON |
| dormitorios, baños, superficies, planta, año | `beds`, `baths`, `surface_area` | en una vivienda, `facts`; si no hay hecho, un solo número en el título o la descripción. Si el sync se dejó una lista de la ficha pública, esa línea entra con la misma regla. En comercial y parcela el número del catálogo no se copia | 24 fichas escriben `bedrooms` y 28 escriben `bathrooms`. Hotel, Restaurant, Commercial space y Building land (en Resales, Commercial y Plot) omiten los dos nodos aunque el catálogo traiga un número: el esquema 1.5 los define como Numeric y no documenta N/A, así que omitir el nodo es la marca de no aplicable. No se escribe 0 ni «N/A». `Rooms` no se copia. Un rango no se convierte en un número. Siguen pendientes, sin dormitorios, `anahata-ibz`, `saserra`, `thenr` y `vistalegre`. No se rellena un 1 por defecto en plantas |
| características | `pool`, `new_build` | `features`, y si la lista está vacía, una etiqueta del apéndice 2 que el texto de esa ficha sí dice | Las seis que estaban vacías llevan al menos una. No se escribe "Not specified" |
| `descriptions/en` | `desc/en` | `description` | Las 35 tienen texto. Las cuatro que el catálogo dejaba vacías salen de la ficha pública |
| `descriptions/es` | `desc/es` | `sync/descriptions_es.json`, traducción del inglés del catálogo | Las 35 lo tienen. Traducido del texto en inglés. Hay que revisarlo con el cliente. Hace falta para compartir en la red |
| `propertyImages` | `images` | `image` y `gallery` | Las fotos ampliadas salen como URL `https://` del repositorio público. La web no publica `/photos/` |
| `address1` | primera línea de `location_detail` | zona del catálogo; si es un municipio y el título nombra un lugar, ese lugar; si la zona es solo Ibiza, el lugar de la descripción | No hay valor por defecto. Si no hay lugar, el nodo no se escribe |
| `address2`, `postCode` | resto de `location_detail` | no está | Sigue faltando en las 35 |
| `cadastralRef` | `catastral` | no está | Falta en las 35. Hace falta para compartir en la red |
| `saleType` | `leasehold` | valor provisional | `Freehold` en las 35. No viene en el catálogo. Es el valor habitual en Ibiza y hay que revisarlo ficha por ficha con el cliente |
| `shared` | no existe | valor provisional | `0` en las 35. Las Boas no está marcada como Compartida. Hay que confirmarlo ficha por ficha |
| `type` villa | `type` | apéndice 1 | Las villas van como `House` / `Villa`. `Villa` / `Detached` no está en el apéndice |
| `commissionPct` | no existe en Kyero | no se escribe | Se deja en el alta del feed. En Las Boas el panel muestra 4,52 % y un reparto del 50 % |
| captador (`lister`) | no existe | no está | Falta en los datos. En el alta se elige un usuario por defecto |
| agencia | no existe | no es un campo de la ficha | La cuenta ya es la de Amaranthus |

Kyero 3 es el formato alternativo que Resales acepta. Cubre la misma ficha
pública y tampoco trae comisión ni captador. El script actual genera 1.5.

## Qué falta en las 35

El tipo de venta se escribe como `Freehold` en las 35. Es el valor habitual
en Ibiza y es provisional: el catálogo no lo trae y no se leyó en la ficha
de Las Boas. Hay que confirmarlo ficha por ficha con el cliente antes de
dar el XML a Resales.

La comisión no se escribe en el XML. En el alta del feed se puede usar lo que Las Boas ya tiene en el panel: 4,52 % y un reparto del 50 %. Es el dato de esa ficha, no una confirmación de las otras 35.

Las 35 fichas llevan texto en español (`descriptions/es`). Está en `sync/descriptions_es.json` y es una traducción del texto en inglés del catálogo. `sync_catalog.py` reescribe `data.json` desde la web en inglés y no toca ese archivo, así que el siguiente sync no lo borra. Hay que revisarlo con el cliente. El español hace falta para compartir la ficha en la red. En `casmut-plot` y `plot-benimussa` el inglés cierra con una nota de redacción que no describe la finca; esa frase no se ha traducido. En `atzeca-2hab` el texto de la web se corta a mitad de palabra («potential f»); el español termina en la última palabra completa.

El catálogo no trae estos datos. El XML los deja vacíos:

- Referencia catastral (`cadastralRef`)
- Código postal (`postCode`)
- Segunda línea de dirección (`address2`)
- El lado largo de las fotos ampliadas mide 800 px, que es el mínimo del XML. La pantalla de subida del panel pide 1600 px. No se han vuelto a ampliar
- `levels` no se rellena con un 1. La planta y las plantas del edificio solo se escriben cuando el catálogo las trae
- La parcela de `casmut-plot` y la superficie de `restaurant-marina` y `restaurant-varaderey` no están en la ficha

`bedrooms` y `bathrooms` son Numeric en el esquema 1.5. Esa definición no documenta un valor N/A. `add()` ya omite el nodo cuando el texto está vacío, y esa omisión es la marca de no aplicable. No se escribe 0 y no se escribe «N/A».

No aplican en comercial ni en parcela, aunque el catálogo traiga un número. En la web son Hotel, Restaurant, Commercial space y Building land. En Resales son Commercial y Plot. Entran el hotel, los restaurantes, el café y las parcelas. En estas 35 no hay un bar con otro tipo; si la web lo clasificara como Restaurant o Commercial space, también se omitirían los dos nodos. Son 7 fichas, y el informe las llama no aplicables, no datos que faltan: `boutiquehotel`, `cafe-bistro`, `casmut-plot`, `plazaparque`, `plot-benimussa`, `restaurant-marina`, `restaurant-varaderey`.

`plot-benimussa` trae Bedrooms 2 y Bathrooms 3. `boutiquehotel` trae Bathrooms 26 (habitaciones de hotel, no dormitorios de una vivienda). `cafe-bistro` trae Bathrooms 3. `plazaparque` trae Bathrooms 2. Esos números no se copian. `casmut-plot`, `restaurant-marina` y `restaurant-varaderey` tampoco escriben baños: no aplica, no es un dato pendiente.

Las viviendas (Apartment, y House/Villa para las villas) conservan el número que ya salía de `bedrooms()` y `bathrooms()`.

`vedella-27` dice un número único en la descripción del catálogo: «The apartment offers 2 comfortable bedrooms and 2 bathrooms». El XML escribe 2.

`patioblanco` tampoco trae el hecho. Los párrafos del catálogo no dan número, porque el sync guarda las etiquetas `<p>` y se deja la lista. En la ficha pública, antes de «More properties», la distribución de este apartamento dice «2 bedrooms». Es un solo número. El XML escribe 2. La frase está en `PUBLIC_PAGE_TEXT`, con la URL de la ficha. El hecho Rooms también vale 2 y no se usa. El hecho Bathrooms ya es 2. La misma lista dice «1 full bathroom with bathtub and shower» y «1 separate guest toilet»; eso no se suma ni sustituye al hecho.

`whiteangel` lista Bathrooms 2. Una frase de la descripción dice «3-bathroom». El XML escribe 2, el hecho. No se cambia a 3.

Sobre las 35 ventas, 24 escriben el nodo `bedrooms` y 28 escriben el nodo `bathrooms`. Las 7 de comercial y parcela omiten los dos. Cuatro viviendas siguen pendientes, sin un solo número de dormitorios. El nodo no se escribe y el informe las marca como pendiente:

- `anahata-ibz`: «2- and 3-bedroom layouts». Es un rango. Rooms es 2 y no se copia.
- `saserra`: «30 apartments with 1 and 2 bedrooms». Es un rango. Rooms es 1 y no se copia.
- `thenr`: «one- and two-bedroom» y, en la lista, 18 viviendas de un dormitorio y 27 de dos. Es un rango. Rooms es 1 y no se copia.
- `vistalegre`: «24 exceptional suites», sin número de dormitorios. Rooms es 2 y no se copia.

Ninguna vivienda deja `bathrooms` vacío. Esas cuatro escriben 1.

`restaurant-varaderey` nombra Passeig de Vara de Rey en el texto que ahora
sí entra en el XML. La calle de esa ficha sale de ese texto.

## Cómo se automatiza

1. El sync de la web (`sync_catalog.py`) sigue siendo la fuente. Ya copia el
   catálogo público a `data.json`.
2. Después de cada sync, ejecutar `resales_import_xml.py`. El XML queda con
   las ventas de ese momento y con ninguna más. El español se lee de
   `sync/descriptions_es.json` y no se pierde al sincronizar el catálogo.
3. Publicar ese archivo en una URL HTTPS fija del sitio. No dar esa URL a
   Resales hasta completar o aceptar los campos que faltan.
4. Un solo alta, con el formulario de importación de Resales. La cuenta tiene
   que ser de red. En el formulario se indican la URL, el usuario captador por
   defecto y la comisión por defecto. Resales hace una simulación y hay que
   aprobarla. El alta puede tardar unos días laborables.
5. `lasboas-top` no va en el XML. Así el primer pase no crea una segunda ficha
   junto a `LasBoas-7.1`. En la simulación hay que comprobar que Resales deja
   esa ficha como está.
6. A partir de ahí Resales descarga el XML solo, una vez al día a las 06:00,
   y manda un resumen por email. La documentación no ofrece un disparo manual.
   Una venta nueva en la web entra al día siguiente. Una venta que desaparece
   de la web sale del XML y Resales la pasa a Off Market.

No hace falta el botón de feed nuevo del panel: eso crea un feed de salida.
Tampoco hace falta la API de búsqueda para escribir fichas: esa API solo lee.
