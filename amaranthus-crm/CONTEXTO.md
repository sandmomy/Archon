# Contexto del CRM de Amaranthus

Resumen del 6 de noviembre de 2026, hora de Madrid. Sirve para retomar el
trabajo sin repetir lo ya cerrado. No se ha dado de alta ningún feed en
Resales ni se ha llamado a ningún endpoint de escritura.

## Qué es el proyecto

CRM de Amaranthus Ibiza Real Estate conectado a Resales Online. La idea es
que las ventas de la web del cliente entren en Resales solas: nadie las da
de alta ni las quita a mano. Resales descarga un archivo una vez al día, a
las 06:00, publica los anuncios y, si una casa sale de la web, al día
siguiente la pasa a Off Market.

## Lo que ya estaba

- La web principal es https://www.amaranthus-realestate.com. El catálogo
  público se sincroniza a `amaranthus-crm/site/data.json`. Hay 36 ventas.
  El alquiler no entra en el XML de importación.
- El mockup del hub de oficina está en la rama
  `cursor/ibiza-office-hub-mockup-eff5`, dentro de `inmobiliaria-ibiza`,
  y en el pull request 2.
- El volcado de lectura de Resales vive en el droplet `134.122.57.174`.
  El cron es `/etc/cron.d/amaranthus-resales` y lanza
  `amaranthus-crm/sync/resales_dump.py` a las 07:00, hora de Madrid. La
  clave de la API no está en el repositorio: en el droplet está en
  `/root/.resales_key`. El volcado escribe `site/resales.json`. La última
  lectura útil trajo 84 fichas de venta de Baleares. Esa API solo lee. No
  sirve para crear ni borrar anuncios.
- El código del droplet está en `/root/Archon`.

## Lo que se ha hecho hoy

El generador es `amaranthus-crm/sync/resales_import_xml.py`. Lee las ventas
de `site/data.json` y escribe un XML Resales 1.5. De las 36 ventas deja
fuera `lasboas-top`, así que el archivo lleva 35. Las Boas ya está en
Resales como `R5442232`. Si algún día entrara en el XML, la referencia de
agencia tendría que ser `LasBoas-7.1`, no el slug de la web.

El cruce de las 84 fichas del volcado contra las 36 de la web dio una sola
coincidencia: Las Boas. Las otras 83 del volcado no están en la web (82 de
Mallorca y un hotel de Ibiza, `R5245483`). Las 35 restantes de la web son
las que Resales todavía no tiene.

Correcciones ya aplicadas en el generador:

- Las villas van como tipo `House` y subtipo `Villa`. La pareja `Villa` /
  `Detached` no está en el apéndice 1.
- `saleType` es `Freehold` en las 35. Es provisional. Hay que confirmarlo
  casa por casa.
- `shared` es `0` en las 35. También es provisional. Las Boas no está
  marcada como compartida.
- 73 fotos que se quedaban por debajo de 800 px se ampliaron a un lado
  largo de 800 px, el mínimo del XML. Están en `site/photos/` y el XML las
  publica como URL `https://` del repositorio. La web responde 404 en
  `/photos/`. El panel de Resales pide 1600 px en la subida manual; no se
  han vuelto a ampliar.
- Las 35 fichas tienen texto en inglés y en español. El español está en
  `sync/descriptions_es.json` para que el sync de la web no lo borre.
- Dormitorios y baños se contrastaron con la ficha pública. 24 viviendas
  escriben dormitorios y las 28 viviendas escriben baños. Siguen sin un
  solo número de dormitorios cuatro viviendas: Anahata (`anahata-ibz`),
  Sa Serra (`saserra`), The N (`thenr`) y Vistalegre (`vistalegre`). Esas
  cuatro sí tienen baños. Hotel, restaurantes, local y parcelas no llevan
  dormitorios ni baños: el esquema no tiene un valor de «no aplica», así
  que el nodo se omite. Son `boutiquehotel`, `cafe-bistro`, `plazaparque`,
  `restaurant-marina`, `restaurant-varaderey`, `casmut-plot` y
  `plot-benimussa`.
- `vedella-27` queda en `Calle Calvià 27, Cala Vedella`.
- No hay calle por defecto. Marina Botafoch solo se escribe en las fichas
  cuyo propio texto sitúa ahí la propiedad. No se copia al resto.
- La comisión no va en el XML. Se deja como porcentaje por defecto en el
  alta del feed. En el panel de Las Boas se vio 4,52 % con un reparto del
  50 %. Ese dato es de esa ficha, no una confirmación de las otras 35.

El XML regenerado está publicado, sin login, en:

https://134.122.57.174/import.xml

En el droplet el archivo es `/var/www/resales/import.xml`. Nginx solo sirve
esa ruta. El certificado es de Let's Encrypt para la IP, caduca a los pocos
días y el renovador del droplet lo vuelve a pedir solo.

El detalle de campos, los huecos y los pasos del alta están en
`amaranthus-crm/sync/RESALES_IMPORT.md`. El pull request 5 recoge el
generador y esa documentación:

https://github.com/sandmomy/Archon/pull/5

Nada de esto se ha registrado en Resales. El archivo está publicado para
poder mandar la URL. El alta del feed sigue sin hacerse.

### Mensaje para Francesco

En italiano y en primera persona. No se ha enviado desde aquí.

```
Francesco, ce l'ho fatta. Ora sono collegato a Resales e sto mandando tutte le informazioni.

Funziona così: ogni mattina alle sei Resales scarica un file che preparo io e pubblica gli annunci da solo. Se una casa si vende, il giorno dopo sparisce.

Le 35 case del sito sono pronte. Las Boas è già dentro e quella non la tocco.

Si può caricare già. Per adesso ho messo la piena proprietà come tipo di vendita: se qualche casa è diversa, mi basta saperlo.

Per fare la scheda perfetta mi mancherebbero il catasto e il codice postale. Non bloccano né l'invio di adesso né quelli di dopo: servono solo perché resti tutto a posto.

Se la commissione di solito è una sola, o se cambia da casa a casa, mi serve saperlo. È necessaria, ma non blocca il file. La configuro io quando attivo il collegamento.

Il pacchetto con l'indirizzo è già pronto, e quello va mandato a Resales.

Non ho accesso a quei dati. Mi chiedo se ci sia già un modo per collegarsi e compilare tutto in automatico quando entra una casa, oppure se me li possono passare.

Grazie, Francesco. Da qui si continua.
```

### Mensaje para el soporte de Resales

En español. El marcador `[URL_DEL_XML]` se sustituye por
https://134.122.57.174/import.xml cuando se envíe. No se ha enviado desde aquí.

```
Hola,

Amaranthus Ibiza Real Estate tiene listo el XML de importación. Lleva las 35 ventas de nuestra web. Las Boas ya está en vuestro sistema y no va en el archivo.

El archivo estará en esta dirección:

[URL_DEL_XML]

Por favor, configurad el alta del feed de importación para que Resales lo descargue cada día. El archivo no trae la comisión. Fijad el porcentaje por defecto en el alta, y usadlo cuando el archivo no la traiga.

Gracias.
```

Mario Bautista, de Resales, escribió el mismo día sobre otra cosa: una clave
de API de salida y las pasarelas RESALES, OWN PROPERTIES y RENTALS. El feed
de salida se llama `OWNPROPERTIES`. El P1 que indicó es `1175569`. Eso no es
el XML de importación. El alta de la importación sigue pendiente.

## Lo que falta

De Francesco, casa por casa:

- El tipo de venta real. Ahora todas llevan `Freehold` (plena propiedad).
  Si alguna es derecho de superficie, hay que cambiarla.
- La referencia catastral.
- El código postal.
- La comisión, si la sabe y si cambia de una casa a otra. No bloquea el
  archivo. En el alta se pone un porcentaje por defecto.

De Resales: la confirmación después de recibir el correo con la URL. Hasta
entonces el feed no está dado de alta y Resales no descarga el archivo.

Huecos que el catálogo no trae y que ya están anotados en
`RESALES_IMPORT.md`: segunda línea de dirección, planta de
`belisla-penthouse` y `vedella-27`, plantas del edificio en `atzeca-2hab`,
`patioblanco`, `vedella-27` y `white-penthouse`, `levels` en las viviendas
que no lo dicen, superficie de los dos restaurantes y parcela de
`casmut-plot`. No se inventan.

## Dónde está cada cosa

| Qué | Dónde |
| --- | --- |
| Generador del XML | `amaranthus-crm/sync/resales_import_xml.py` |
| Notas de campos y alta | `amaranthus-crm/sync/RESALES_IMPORT.md` |
| Textos en español | `amaranthus-crm/sync/descriptions_es.json` |
| Catálogo de la web | `amaranthus-crm/site/data.json` |
| Sync de la web | `amaranthus-crm/sync/sync_catalog.py` |
| Volcado de lectura | `amaranthus-crm/sync/resales_dump.py` |
| Fotos a 800 px | `amaranthus-crm/site/photos/` (73 archivos) |
| Pull request | https://github.com/sandmomy/Archon/pull/5 |
| XML público | https://134.122.57.174/import.xml |
| Archivo en el droplet | `/var/www/resales/import.xml` |
| Cron del volcado | `/etc/cron.d/amaranthus-resales` en `134.122.57.174` |
| Hub de oficina | rama `cursor/ibiza-office-hub-mockup-eff5`, pull request 2 |
