# ModGames44 Video Editor v0.6.12 — Reproducción fluida con cámara rápida y lenta

**Nuevo en v0.6.12:** la interfaz ya no se cuelga al reproducir clips con la velocidad cambiada (el monitor convierte como máximo ~30 fotogramas/s; por encima de 4× la vista previa es tipo timelapse).

**Nuevo en v0.6.11:** la velocidad de clip va de 0,01× a 100× (antes 0,25×–4×), con accesos rápidos hasta 50×.

**Nuevo en v0.6.10:** tras desvincular, puedes borrar solo el audio o solo el video. El clic derecho ahora selecciona el clip bajo el cursor, y los clips vinculados muestran 🔗.

**Nuevo en v0.6.9:** la GPU (NVIDIA NVENC, AMD, Intel) se detecta y se usa siempre que funcione, con ajustes de máxima calidad, perfiles AV1/HEVC de 10 bits, tasas más altas para YouTube y reintento automático si el codificador falla.

**Nuevo en v0.6.8:** las pistas de audio muestran una sola onda (el audio sigue siendo estéreo); la casilla **L/R** vuelve a mostrar ambos canales.

**Nuevo en v0.6.5:** exportación hasta ~9× más rápida con muchos fragmentos,
censura y zoom idénticos entre monitor y exportación en videos verticales,
keyframes que se conservan al cortar, «Cerrar huecos» que respeta las
transiciones y los subtítulos, proyectos portables con nuevo enlace de
medios, perfiles Shorts/TikTok y registro de errores. Detalles en
[CHANGELOG.md](CHANGELOG.md).

Para instalar: `python -m pip install -r requirements.txt` y `python main.py`
(Python 3.11–3.13). Pruebas: `python -m pytest -q`.

---

## Historial

# ModGames44 Video Editor v0.6.2 — Texto e imágenes editables en el monitor

**Nuevo en v0.6.2:** ahora puedes seleccionar un título o subtítulo en el monitor, moverlo arrastrando con el mouse, y cambiar su tamaño desde las esquinas. El panel `Texto y subtítulos → Títulos` permite elegir la familia de fuente instalada en Windows. La nueva pestaña **Imágenes** inserta PNG/JPG/WEBP/BMP/TIFF superpuestos (V3), con posición, escala, transparencia y keyframes. También puedes ir a `Editar → Insertar imagen…` (`Ctrl+Shift+I`). Los cambios se guardan en el archivo de proyecto y se exportan con FFmpeg. Consulta [CHANGELOG.md](CHANGELOG.md).

**Comportamiento:** selecciona el texto o imagen con clic izquierdo y arrástralo; las cuatro esquinas modifican proporcionalmente el tamaño. Los originales no se alteran. El selector de fuentes utiliza las instaladas en el equipo; si una no está disponible para Pillow, el render usa una fuente de respaldo. Las imágenes insertadas duran cinco segundos inicialmente; cambia su duración desde el borde del clip en la Timeline. La interfaz sigue en pruebas visuales en Windows.

---

## Historial

# ModGames44 Video Editor v0.6.1 — Edición, títulos y subtítulos

**Proyecto de código fuente disponible para Windows 10/11.** La v0.6.1 recupera el acceso visible a «Quitar silencios» desde Audio / Voz; la v0.6.0 amplió el motor de la v0.5.0 con autoguardado recuperable, Ripple, transiciones de disolución/barrido/deslizamiento, proxies, caché de miniaturas, keyframes, títulos animados y subtítulos locales opcionales. Mantiene Cyber Studio y el formato `.mg44`. La aplicación continúa en desarrollo.

Para instalar: `python -m pip install -r requirements.txt` y `python main.py`.

Consulta [CHANGELOG.md](CHANGELOG.md) para las ocho mejoras y la validación pendiente en Windows. El seguimiento de objetos de v0.5.0 sigue disponible.

---

## Historial anterior

# ModGames44 Video Editor v0.4.12 — Identidad visual

**Novedades de icono y logotipo:** consulta `CHANGELOG.md`.

# ModGames44 Video Editor v0.4.10 — Timeline y arrastre

**Nuevo:** zoom con desplazamiento completo, área libre más allá del último clip, botón Final con vista sincronizada, arrastre desde Proyecto en Miniaturas/Lista. Consulta [CHANGELOG.md](CHANGELOG.md).

# ModGames44 Video Editor v0.4.7 — Fade In/Out en Timeline

**Novedad:** V1 junto a A1, pistas de audio movibles de forma independiente en vertical y triángulos de Fade In/Out arrastrables sobre cada clip de video y audio. Los fades se escuchan en la previsualización y se aplican al exportar. Consulta `CHANGELOG.md` para instrucciones y limitaciones.

# ModGames44 Video Editor v0.4.5 — Previsualización de efectos

**Ahora puedes escuchar la ganancia, los filtros de voz y la reducción de ruido
antes de exportar**, al reproducir clips de la Timeline. Los efectos de video
se procesan durante Play en el Program Monitor sin bloquear la interfaz.
El Audio Meter usa la mezcla procesada, y Cyber Studio sigue siendo el espacio
predeterminado.

**Nota histórica (v0.4.5):** esta versión anterior preparaba WAV por ventanas; tenía limitaciones para keyframes y capas. La versión v0.5.0 reemplaza esos componentes. La ejecución de la interfaz en Windows sigue pendiente de verificación.

Ver [CHANGELOG.md](CHANGELOG.md) para instalación, límites y pruebas.

---

# ModGames44 Video Editor v0.4.4 — Cyber Studio

**Mejora:** puedes quitar el desenfoque o mosaico en cualquier momento desde el botón superior del panel Video o desde Propiedades del clip, aunque esté activado «Editar recuadro con el mouse». Deshacer (Ctrl+Z) recupera la censura anterior.

Consulta [CHANGELOG.md](CHANGELOG.md).

# ModGames44 Video Editor v0.4.3

**Cyber Responsive Edition:** dos espacios de trabajo personalizables (Cyber Neon / Cyber Studio), con tema grafito, cian y violeta, más un diseño que se adapta al tamaño de la ventana.

Consulta [CHANGELOG.md](CHANGELOG.md) para las mejoras, instalación, controles y limitaciones.

# ModGames44 Video Editor v0.4.2 — Cyber Workspaces

**Dos espacios de trabajo en un solo programa:** Cyber Neon y Cyber Studio. Ambos usan la misma paleta cian/violeta y las mismas herramientas. Selección en la barra superior o en Ver → Espacio de trabajo. Botón Exportar arriba a la derecha.

Para ver todos los detalles y las pruebas: [CHANGELOG.md](CHANGELOG.md).

---

# ModGames44 Video Editor — v0.4.1 Audio y Exportación

**Proyecto modular de pruebas para Windows 10/11 x64.** La aplicación aún no es un editor de producción.

Para instalar:

```powershell
python -m pip install -r requirements.txt
python main.py
```

La compilación del ejecutable es privada y no forma parte de la distribución del código fuente.

**v0.3.8:** corregidas las etiquetas repetidas en V1/A1 durante reproducción,
arrastre del cabezal y corte con cuchilla. Véase `CHANGELOG.md`.


## Nuevo en v0.4.1

- **Efectos rápidos → Audio / Voz:** subir/bajar ganancia, reducir ruido, tres perfiles propios de voz (podcast, tono alto, tono bajo) y normalización. Selecciona un clip A1/A2/A3 o su video vinculado y pulsa **Aplicar ajustes al clip**.
- **Archivo → Exportar video / Ctrl+M:** perfiles MP4 H.264/H.265/AV1, MOV ProRes y WebM VP9, detector de NVIDIA/AMD/Intel o CPU y verificación del encoder, progreso/cancelación, exportación multipista.
- **Desde v0.4.5** los efectos de audio se escuchan también en la Timeline mediante WAV de previsualización (ver arriba).
- Exportación de máscaras y zoom animados **no soportada**: avisa antes de exportar. Sí exporta la posición estática, color, velocidad, etc.
- Para GPUs es recomendable instalar una versión FFmpeg de Windows con NVENC/AMF/QSV en PATH. Siempre se valida el encoder antes de ofrecerlo.

**Lee `CHANGELOG.md` para detalles, pruebas, funcionamiento y limitaciones.**

## Efectos rápidos (v0.4.0)

Selecciona un clip **de video** en V1/V2/V3. Abre la pestaña **Efectos rápidos**
arriba a la izquierda (junto al Asistente IA). Puedes aplicar velocidad,
zoom, desenfoque/mosaico **solo en una región rectangular**, ajustes de color,
blanco y negro y espejo horizontal. Para censurar una zona, aplica el efecto
y mueve el **recuadro amarillo** en el Program Monitor con el mouse; cambia
su tamaño desde las esquinas. Si la persona se mueve, crea al menos dos
fotogramas clave de máscara en momentos distintos para interpolar el movimiento
manualmente.

Las miniaturas de V1 son **fotogramas estáticos muestreados en instantes
diferentes**; el cabezal muestra el instante actual, no cambia todas las
miniaturas con cada tick de reproducción. El zoom modifica qué instantes se
muestrean; el cálculo incluye cortes e incremento de velocidad.

**Actualización v0.4.1:** ya existe exportación de clips con efectos de video estáticos y mezcla de audio; no se exportan aún máscaras ni zoom animados, bordes suaves de censura ni transiciones. Ver `CHANGELOG.md`.

## Herramientas

La barra **Herramientas** muestra iconos (en vez de botones con texto). El botón elegido queda resaltado y muestra descripción al pasar el mouse.

- **V** — seleccionar/mover clips; al arrastrar el borde, recortas el inicio/final.
- **C** — cuchilla persistente: al pasar sobre un clip aparece la línea de corte y el cursor cambia a cuchilla. Haz clic para cortar clip y audio vinculado. **Esc** vuelve a seleccionar.
- **[ / ]** — herramientas persistentes para recortar inicio/final arrastrando.
- **Supr** — eliminar clip seleccionado y audio enlazado.
- **Ctrl+Z/Ctrl+Y** — deshacer/rehacer.
- **Ctrl+K** — cortar clip seleccionado en el cabezal, sin cambiar de herramienta.
- **Desvincular** — separa video/audio de la edición vinculada.
- **Cerrar huecos** — acerca clips consecutivos al origen de cada pista.
- **Imán** — ajusta ambos bordes al acercarlos a otros clips o al cabezal; con el imán activado, los clips de video/audio no se montan accidentalmente sobre otros de su misma pista. Desactívalo cuando necesites un solapamiento intencional (por ejemplo, una transición manual).

## Cuchilla, quitar silencios, reproducción e imán (actualizado en v0.6.3)

- Con **C** puedes dividir un clip (y su audio vinculado) exactamente donde hagas clic.
- Si haces un corte **mientras reproduces**, la acción de corte pausa el motor para poder editar con precisión. Esto **no** significa que Play tenga que detenerse posteriormente al cruzar ese corte.
- Al pulsar **Play**, dos fragmentos pegados se reproducen **continuamente**, incluso después de usar **Quitar silencios → Cerrar huecos**. Si se han eliminado segundos del archivo original, el reproductor salta a la siguiente posición de origen.
- Con **Reproducción → Detener reproducción cuando hay huecos** activado, el cabezal se detiene al terminar el material audiovisual si comienza un hueco real. Si hay material audiovisual continuo en otra pista, la reproducción sigue. Desactiva esa opción si quieres avanzar también por los espacios vacíos. La preferencia se conserva entre sesiones.
- Al mover un clip con el **Imán activado**, tanto su comienzo como su final se acoplan a otros límites próximos; la tolerancia depende del zoom. El movimiento respeta el audio/video vinculado y evita que clips AV se solapen en la misma pista. Para superposiciones intencionales, desactiva el imán.
- Todas estas operaciones de edición siguen siendo no destructivas y pueden revertirse con **Ctrl+Z**.

## Zoom y ondas

- Rueda sobre clips o regla: zoom horizontal centrado alrededor del cursor.
- Rueda sobre encabezado de pista: aumenta/disminuye altura de esa pista.
- Ondas PCM reales por canal izquierdo/derecho, con detalle variable según el zoom (pueden tardar en analizarse inicialmente).
- Miniaturas extraídas de diferentes momentos del video.
- Los clips se detienen en el borde inicial de la Timeline, 00:00.

## Pruebas y dependencias

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
```

Usa `imageio-ffmpeg` para FFmpeg y `numpy` para formas de onda. Ver `CHANGELOG.md` para pruebas manuales, funcionamiento y limitaciones.

## Nuevo en v0.3.9: ModGames44 AI Assistant (beta)

El editor agrega el panel **Asistente IA**, ocultable desde **IA → Abrir asistente de edición**
(`Ctrl+Shift+A`). No usa esta conversación ni inicia sesión con tu cuenta ChatGPT.

**Modo local gratuito (sin conexión):** escribe instrucciones como:

- `corta en 00:05`
- `elimina desde 00:05 hasta 00:10` (deja un hueco)
- `mueve el clip a 00:20` (selecciona previamente el clip)
- `cierra huecos`
- `ve a 00:15`

Pulsa **Analizar instrucción**, revisa la lista y luego **Aplicar cambios**.
Confirma en la ventana emergente. Las operaciones son atómicas: un solo **Ctrl+Z**
revierte todo el plan aplicado. Nunca se sobrescriben archivos multimedia.

**Autoedición: quitar silencios:** selecciona un video con audio en la Timeline,
abre el panel IA y pulsa **Autoedición: quitar silencios**. FFmpeg detecta pausas de
al menos 0,75 s inferiores a -34 dB y ofrece eliminarlas, conservando un margen
aproximado de 120 ms a cada lado. Revisa el plan antes de confirmarlo.
Esta función NO identifica palabras ni evalúa qué escenas son interesantes.
Si casi todo es silencio, se abstiene de cortar el video completo. Inicialmente
deja huecos para no modificar los demás clips: puedes aplicar `cierra huecos`
posteriormente.

**Modo en línea (opcional):** el editor usa la **API Responses** de OpenAI para
interpretar instrucciones más flexibles, pero únicamente en operaciones
soportadas. Instala el paquete adicional:

```powershell
python -m pip install -r requirements-ia.txt
$env:OPENAI_API_KEY = 'TU_CLAVE_DE_API'  # Solo en esta sesión de PowerShell
python main.py
```

En el panel, activa **Usar API de OpenAI**. Modelo predeterminado:
`gpt-4.1-mini` (cámbialo si tu cuenta no tiene acceso). La API tiene facturación
independiente de ChatGPT. El programa **no almacena la clave en el proyecto ni
en archivos de configuración**. A la API se envían la instrucción y metadatos
(limitados a 60 clips: IDs, nombres base, tiempos y pistas), **no** el video,
audio, archivos locales ni rutas completas. El parámetro `store=False` evita
el almacenamiento de la respuesta cuando es admitido por la API, pero sigue
aplicando la política del proveedor a los datos enviados.

**Seguridad e integridad:** las propuestas son JSON validados mediante una lista
cerrada de operaciones; nunca se ejecuta código que el modelo haya generado.
Si cambia la Timeline durante el análisis, el plan se invalida. Antes de aplicar
se verifica otra vez y se solicita confirmación. Las peticiones remotas se
procesan fuera del hilo de Qt para no congelar la interfaz. Sin clave o sin red,
las instrucciones locales y el análisis de silencios siguen funcionando.

**Limitaciones actuales:** no hay análisis semántico del contenido, transcripción,
subtítulos, efectos, exportación ni edición automática narrativa completa.
El modo en línea no procesa el video por sí solo; planifica acciones compatibles.
Para ello habrá que integrar transcripción, análisis de escenas y exportación.

**Pruebas:** `python -m pytest -q` o `python -m unittest discover -s tests -v`.
La ejecución real del panel requiere un sistema con PySide6, por ejemplo Windows
10/11. Las pruebas de API en vivo requieren una clave propia y no están incluidas.


## v0.4.6 — Ondas dinámicas y perfiles de voz revisados

- La Timeline permite alternar **Onda FX**: activada muestra la onda procesada, desactivada la original.
- La ganancia del clip actualiza la amplitud instantáneamente sin volver a decodificar.
- EQ, compresión, reducción de ruido y normalización generan en un hilo de trabajo una
  onda de audio PCM L/R procesada, con caché independiente para cada combinación.
- La reducción de ruido (`afftdn`) usa ahora un rango real de **3–20 dB** en vez
  de valores de 0,01–0,08 dB. Los ajustes extremos pueden deteriorar la voz.
- Perfiles ModGames44: podcast (HP 75 Hz; -2 dB/250 Hz; +3 dB/3,2 kHz; 3:1),
  tono alto (HP 90 Hz; +2 dB/180 Hz; -2 dB/5,5 kHz; 2,5:1),
  tono bajo (HP 65 Hz; -3 dB/220 Hz; +3 dB/3 kHz; 2,5:1).
- Los parámetros son propios y **no** representan curvas oficiales de Adobe.
- La escucha previa y la exportación siguen compartiendo `effects/audio.py`.

La primera generación de la onda procesada puede requerir tiempo en videos largos;
se realiza en segundo plano y no debe bloquear la interfaz. Mientras tanto se
ve una aproximación de la onda original; cuando el cálculo termina se sustituye.

Referencias de investigación:
- https://helpx.adobe.com/premiere/desktop/add-audio-effects/adjust-volume-and-levels/dynamic-audio-waveforms.html
- https://helpx.adobe.com/uk/premiere/desktop/add-audio-effects/adjust-volume-and-levels/improve-dialogue-clarity.html
- https://ffmpeg.org/ffmpeg-filters.html

## Actualización v0.4.9
Ver `CHANGELOG.md` para las correcciones de Proyecto y miniaturas de Timeline.

## v0.4.11 — Diagnóstico de navegación

El salto **Ir al final** debe mostrar el cabezal cerca del extremo derecho de la Timeline incluso con zoom máximo. Para investigar un fallo persistente en Windows, pulsa **Ir al final**, luego **Ver → Copiar diagnóstico de Timeline** (`Ctrl+Alt+D`) y comparte el texto copiado. El diagnóstico no contiene el video ni datos privados del proyecto: solo parámetros de geometría y tiempo.

## v0.6.0 — Montaje, subtítulos y títulos animados

La interfaz organiza las herramientas en pestañas laterales para dejar libres el monitor y la Timeline. Se incorporan recuperación por autoguardado, Ripple Edit, disoluciones/barridos/deslizamientos, proxies H.264 opcionales a 540p, keyframes de títulos y volumen, caché persistente de miniaturas, subtítulos automáticos locales y títulos animados.

**Uso rápido:** en «Ver» puedes abrir el panel «Texto y subtítulos». Selecciona «Títulos» y pulsa «Añadir título» para colocarlo en el cabezal; usa «Keyframes» para animarlo. En «Subtítulos», selecciona antes un clip de video. Para la función automática, instala `python -m pip install -r requirements-subtitulos.txt` (opcional). Los subtítulos se pueden guardar como `.srt`. Los originales nunca se modifican.

**Compilación privada:** los archivos `build.py` y `nuitka-package.config.yml` están excluidos del repositorio público mediante `.gitignore`; no son necesarios para ejecutar el código fuente.

Lee `CHANGELOG.md` para limitaciones y pruebas de regresión.


### Quitar silencios (restaurado en v0.6.1)

Selecciona un clip de audio en la Timeline (o un video con audio vinculado) y abre **Efectos → Audio / Voz → Detectar y quitar silencios…**. También está disponible desde **Efectos → Catálogo → Efectos de audio → Quitar silencios** y desde **Asistente IA**. FFmpeg detecta pausas, presenta un plan de cortes y requiere tu confirmación antes de aplicar los cambios. La operación es reversible (`Ctrl+Z`) y no modifica el archivo fuente. El detector local no requiere una cuenta ni una API de IA.

## v0.6.4 — Optimización de vista previa

El monitor utiliza ahora una caché de fotogramas limitada, decodificación secuencial mejorada para videos de alta frecuencia, calidad de trabajo adaptable (960/720/480 píxeles) y descarte de resultados antiguos después de un salto manual. Se reducen las conversiones de imagen redundantes en composiciones multipista y se evitan búsquedas innecesarias al reanudar Play después de Pause.

**La calidad variable afecta solo al monitor:** los archivos exportados siempre siguen utilizando las fuentes y opciones originales. La aceleración GPU dedicada de composición no está implementada; consulta las advertencias y pruebas de Windows en `CHANGELOG.md`.
