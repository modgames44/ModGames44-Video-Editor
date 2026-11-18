# Historial de cambios — ModGames44 Video Editor

## v0.6.12 — Reproducción fluida con cámara rápida y lenta

**Base:** v0.6.11.

**Problema:** al reproducir clips con la velocidad cambiada, la interfaz se
trababa, se colgaba o el programa se cerraba.

**Causa:** el monitor convertía en imagen CADA fotograma decodificado, en el
hilo de la interfaz. Esa carga crecía en proporción a la velocidad: 60
conversiones por segundo a 1×, 240 a 4× y hasta 960 a 16×. Además, el
reproductor intentaba decodificar a 16× o 100×, y su audio interno, aunque
silenciado, se seguía procesando a esa velocidad.

**Correcciones:**
- El monitor convierte **como máximo ~30 fotogramas por segundo** y descarta
  los intermedios (`services.preview_performance.frame_delay_ms`).
- **Por encima de 4×**, el reproductor no decodifica a esa velocidad: queda en
  pausa y el monitor salta a la posición correcta unas 8 veces por segundo,
  como un timelapse (`core.sequence_player`, `PLAYER_MAX_RATE`). Hasta 4×,
  y en cámara lenta, la reproducción es normal.
- En la Timeline, el audio interno del reproductor se **desconecta** en vez
  de solo silenciarse (`MediaEngine.set_internal_audio`). El sonido sigue
  saliendo del audio continuo con efectos, sin cambios.
- La exportación no cambia: siempre es exacta.
- `tests/test_frame_throttle.py` y nuevos casos en
  `tests/test_sequence_continuity_v063.py`.

## v0.6.11 — Velocidad de clip sin el tope de 4×

**Base:** v0.6.10.

- La velocidad de clip pasa de **0,25×–4×** a **0,01×–100×**: de 100 veces
  más lento a timelapse de 100×. El límite está en una sola constante
  (`effects.model.SPEED_MIN/SPEED_MAX`); antes estaba repetido en el panel,
  el modelo, el audio, la vista previa y la exportación.
- Panel de efectos: puedes escribir cualquier valor. El paso de las flechas
  se adapta (0,01 cerca de 0,1×; 1 cerca de 10×). Nuevos accesos rápidos:
  0,1×, 0,25×, 0,5×, 1×, 2×, 4×, 8×, 16× y 50×.
- El audio vinculado sigue la misma velocidad (atempo encadenado, sin
  cambiar el tono). Probado con exportaciones reales a 0,05×, 0,1×, 20× y
  100× y con la vista previa del audio a 0,05×, 16× y 100×.
- **A tener en cuenta:** a velocidades muy altas el monitor puede saltar
  fotogramas al reproducir (la exportación es exacta), y la cámara muy lenta
  repite fotogramas, así que se ve «a saltos».
- `tests/test_speed_range.py`.

## v0.6.10 — Borrar solo el audio o solo el video tras desvincular

**Base:** v0.6.9.

- **Error corregido:** el clic derecho no seleccionaba el clip bajo el
  cursor (Qt solo selecciona con el botón izquierdo). Por eso «Desvincular»
  y «Eliminar» del menú contextual actuaban sobre la selección anterior o
  sobre nada. El clip seguía vinculado y, al borrar el audio, se borraba
  también el video. Ahora el clic derecho selecciona el clip bajo el cursor
  (respetando una selección múltiple si el clip ya forma parte de ella).
- Los clips vinculados muestran 🔗 junto al nombre. Al desvincular, el
  icono desaparece de los dos.
- Mensajes claros: «Selecciona primero el clip…» y «Ese clip ya está
  desvinculado…», en vez de no hacer nada sin avisar.
- `tests/test_unlink_delete.py`: borrar cada lado tras desvincular, con y
  sin Ripple, y tras cortar.

## v0.6.9 — Exportación por GPU (NVIDIA NVENC) optimizada

**Base:** v0.6.8. No cambia la interfaz de edición; solo la exportación.

### La GPU se detecta y se usa siempre que funcione
- **Error corregido:** la prueba del codificador GPU usaba un video de
  128×128, por debajo del mínimo de NVENC en RTX 20 y posteriores (145 px en
  H.264 y 129 px en HEVC). La prueba fallaba siempre y la exportación caía
  en la CPU sin avisar. Ahora se prueba a 256×256.
- Se prueban los codificadores GPU de NVIDIA, AMD e Intel que incluya
  FFmpeg aunque Windows no informe el nombre de la tarjeta. La prueba real
  decide, y la GPU que funciona va siempre primero («Automático»).
- El diálogo de exportación indica qué se va a usar, por ejemplo: «Se usará
  la GPU: NVIDIA · h264_nvenc (calidad máxima)».
- **Reintento automático:** si NVENC falla al exportar (driver, o sesión
  ocupada por OBS u otra grabación), se reintenta con ajustes más simples
  y, solo como último recurso, con la CPU. El mensaje final indica el
  codificador usado y el motivo del cambio.

### Calidad con NVENC (`exporter/encoder_settings.py`)
- Calidad constante (`-rc vbr -cq`) con la tasa del perfil como límite
  máximo, `-preset p5 -tune hq -multipass fullres`, AQ espacial y temporal,
  `-rc-lookahead 32`, B-frames de referencia y GOP de 2 s.
- Tres niveles: calidad máxima, calidad optimizada (sin AQ temporal ni
  B-frames de referencia) y modo compatible. La prueba de cada GPU elige el
  mejor que funcione.

### 10 bits y AV1
- Nuevos perfiles: **H.265 10-bit 1440p60 y 4K60** y **AV1 10-bit 1440p60 y
  4K60**. Producen menos franjas de color en degradados y escenas oscuras.
  Si la GPU no admite 10 bits, se exporta en 8 bits con un aviso.

### Tasas más altas
- YouTube vuelve a comprimir lo que subes, así que se le envía más calidad:
  1080p30 24 Mbps, 1080p60 40, 1440p60 60 y 4K60 100 (como límite, con
  calidad constante). También se subieron las de Shorts, H.265 y AV1.

### Pruebas
- `tests/test_gpu_encoding.py` y `tests/test_export_fallback.py` (este
  último con FFmpeg real: NVENC falla y la exportación termina con la CPU).

### Qué probar en Windows con la RTX
1. Abrir Exportar: «Hardware» debe mostrar «Se usará la GPU: NVIDIA ·
   h264_nvenc (calidad máxima)».
2. Exportar con «YouTube 1080p 60» y con «MP4 AV1 10-bit 1440p 60»; el
   mensaje final indica el codificador usado.
3. Exportar con OBS grabando por NVENC, para comprobar el reintento.

## v0.6.8 — v0.6.5 + una sola onda de audio

**Base:** v0.6.5. Se descartaron los cambios de v0.6.6 y v0.6.7 (reloj de
audio maestro, Timeline incremental, análisis en segundo plano y división de
la ventana) porque hacían la interfaz más lenta. Solo se conserva esto:

- Las pistas de audio muestran por defecto **una sola onda** que usa toda
  la altura del clip. Es la envolvente de los dos canales (el pico más
  extremo de L y R en cada píxel), así que no se pierde un sonido que esté
  solo en un lado.
- **Es solo visual:** el audio, la vista previa, los efectos y la exportación
  siguen en estéreo.
- La casilla **L/R** de la barra de la Timeline vuelve a mostrar los dos
  canales por separado. La elección se guarda entre sesiones.
- `services/waveform.combined_peaks` + `tests/test_single_waveform.py`.

## v0.6.5 — Correcciones de la revisión de código

**Base:** v0.6.4. No cambia la interfaz ni el formato `.mg44`: los proyectos
anteriores se abren igual y los nuevos campos son opcionales.

### Errores corregidos

1. **Exportación mucho más rápida con muchos fragmentos.** Cada clip se
   busca con `-ss`/`-t` antes de `-i`, en vez de decodificar el archivo
   desde el principio con `trim=start=`. Con 30 fragmentos de un video de
   4 min (caso típico de «Quitar silencios»), la exportación pasó de
   127 s a 14,5 s, con un resultado idéntico fotograma a fotograma.
2. **Censura, zoom y espejo coinciden entre el monitor y la exportación**
   en videos que no son 16:9 (verticales de móvil, 4:3). Los efectos se
   aplican sobre la imagen fuente antes de añadir las barras negras. El
   compositor multipista del monitor sigue el mismo orden. La intensidad
   del desenfoque y del mosaico ya no depende de la resolución, así que el
   monitor y la exportación se ven igual.
3. **Keyframes de volumen y de títulos** se conservan al cortar un clip y
   al recortar su inicio (`timeline/local_keys.py`).
4. **«Cerrar huecos»** conserva los solapes de transición y mueve títulos,
   subtítulos e imágenes junto con el video. **Ripple Edit** también los
   desplaza, y borrar un título ya no mueve los demás. La lógica está ahora
   centralizada en `timeline.model.close_all_gaps`, compartida con la IA.
5. **Un MP3/M4A con carátula ya no se importa como video.** `probe()` ahora
   devuelve el ancho y el alto visibles (con la rotación de móvil
   aplicada) y los fps, invalida su caché si el archivo cambia y no guarda
   en caché los fallos transitorios.
6. La prueba que usaba `audioop` funciona en Python 3.13.
7. **Cerrar la aplicación cancela la generación de proxies** (antes, FFmpeg
   seguía ejecutándose en segundo plano).
8. **Registro de errores** en `%LOCALAPPDATA%/ModGames44/VideoEditor/logs/editor.log`,
   que incluye excepciones de slots de Qt e hilos, con un aviso en la barra
   de estado. El monitor ya no oculta los errores, y los registra con un
   límite de frecuencia.
9. Una operación que falla (transición imposible, recorte no válido) ya no
   borra la pila de «Rehacer».
10. `split()` hace copias profundas: las dos mitades de un corte ya no
    comparten `effects`/`audio_fx`.

### Mejoras

- **Guardar / Descartar / Cancelar** al cerrar o al abrir otro proyecto. Si
  se descarta, no se ofrece recuperar esa sesión al volver a abrir.
- **Proyectos portables:** se guardan también rutas relativas. Si faltan
  medios al abrir, se puede buscarlos por nombre en otra carpeta.
- Guardado con `fsync` (más seguro ante cortes de luz).
- «Avanzar fotograma» usa los fps reales del clip (60, 24…) en vez de 30.
- Nuevos perfiles: **Shorts/TikTok 1080×1920** a 30 y 60 fps, y H.265/AV1 a
  60 fps. Los codificadores por software usan calidad constante (CRF) con
  la tasa del perfil como límite máximo; los de GPU mantienen la tasa fija.
- Medidor de audio con numpy (~7× menos trabajo en el hilo de la interfaz).
- Versión única en `core/version.py`; se eliminaron 49 imports sin usar.
- `tests/test_fixes_v065.py`: 17 pruebas de regresión, incluidas
  exportaciones reales con FFmpeg.

### Pendiente (requiere probar la interfaz en Windows)

- Usar el reloj del dispositivo de audio como reloj maestro de la
  reproducción (evita la deriva A/V en reproducciones largas).
- `TimelinePanel.refresh()` incremental, en vez de reconstruir la escena.
- Ejecutar `probe()` fuera del hilo de la interfaz al importar.
- Dividir `main_window.py` / `timeline_panel.py` en controladores.
- El monitor sigue mostrando un lienzo 16:9 al editar para un perfil vertical.

### Qué probar en Windows

1. Abrir un proyecto v0.6.4, guardarlo, mover la carpeta y volver a abrirlo.
2. Censura/zoom sobre un video vertical: comparar el monitor con la exportación.
3. «Quitar silencios» + «Cerrar huecos» con subtítulos y transiciones; exportar.
4. Cerrar el programa mientras se genera un proxy: el proceso debe terminar.


---

<!-- CAMBIOS_v0.6.4.md -->
## ModGames44 Video Editor v0.6.4 — Fluidez del monitor

**Base:** v0.6.3. No se cambian la interfaz Cyber Studio, el modelo de proyecto ni los parámetros de exportación. Se conservan «Quitar silencios», imán, Ripple Edit, títulos, imágenes y subtítulos.

### Optimizaciones implementadas

1. **Decodificación secuencial más eficiente:** `services/video_frames.py` utiliza `VideoCapture.grab()` para saltar unos pocos fotogramas de avance en lugar de realizar búsquedas completas en cada actualización (caso frecuente con material de 60 fps). Con la misma fuente a la misma posición reutiliza un fotograma ya obtenido. La caché LRU está limitada a 14 imágenes **reducidas** y 4 decodificadores abiertos.
2. **Calidad de previsualización automática:** `services/preview_performance.py` adapta el ancho de trabajo de los efectos y la composición multipista a **960, 720 o 480 px**, y nunca supera el tamaño visible del monitor. Reduce calidad cuando la composición no puede mantener el ritmo y se recupera gradualmente. **No afecta la exportación.**
3. **Renderizado fuera del hilo gráfico:** conversión, escalado y efectos Pillow se procesan en trabajadores con una sola petición activa; la interfaz no realiza el escalado completo de los cuadros 4K antes de encolarlos. Los fotogramas solicitados durante un trabajo se fusionan en una única solicitud más reciente, en vez de acumular una cola extensa.
4. **Menos trabajo repetido:** durante la composición de varias pistas se ignoran los frames QVideoSink que no se usan. Se evitan copias profundas de efectos sin cambios, repintados duplicados de títulos estáticos y reapertura constante de sus PNG cacheados. Las imágenes sobrepuestas también se cachean respetando cambios del archivo.
5. **Reanudación más rápida:** Play después de Pause conserva el decodificador y no ejecuta `setPosition()` si el reproductor ya está donde corresponde. El seek manual mantiene precisión, aunque sea de pocos milisegundos.
6. **Sincronización de la UI:** se limitan las actualizaciones redundantes del cabezal generadas por dos fuentes de tiempo (QMediaPlayer y QTimer), manteniendo alrededor de 30 actualizaciones/s. Un salto manual invalida resultados atrasados para impedir que un efecto antiguo sustituya la imagen de la nueva posición.

### Pruebas realizadas

- `python -m unittest discover -s tests -q`: **265 pruebas superadas** en este entorno Linux (incluye las pruebas de regresión de las versiones previas).
- `python -m compileall -q .`: sin errores de sintaxis.
- FFmpeg/OpenCV: se decodificó un video de 60 fps, se comprobó la búsqueda hacia atrás y se ejecutó la composición multipista. Una medición local de **35 lecturas** de `testsrc2` (640×360, 60 fps, solicitudes cada 33 ms y salida reducida a 480px) fue aproximadamente **0,247 s en v0.6.3 frente a 0,103 s en v0.6.4**. Son datos de esta máquina y esa muestra, **no un FPS garantizado**.

### Qué debe probarse en Windows

1. Reproducir un mismo video en v0.6.3 y v0.6.4, desde el inicio y desde una posición avanzada: comprobar fluidez y sincronización de audio.
2. Pausar y pulsar Play de nuevo varias veces; probar seeks cortos y largos con el cabezal.
3. Aplicar desenfoque/zoom; comprobar que no desaparezca el efecto durante la reproducción.
4. Superponer 2–3 capas de video, un PNG y títulos animados; probar con resolución 1080p/4K y con proxies.
5. Comprobar que la exportación mantiene la resolución y los efectos originales, independientemente de la calidad variable del monitor.
6. Comprobar «Quitar silencios» + «Cerrar huecos» + reproducción continua y arrastres magnéticos para descartar regresiones.

### Limitaciones

- **No hay una nueva ruta GPU dedicada.** QMediaPlayer puede usar aceleración del sistema cuando el backend/controlador la soporta; los efectos Pillow y la composición multipista continúan en CPU. Una ruta GPU real exige un renderizador específico de Qt/RHI/OpenGL/Vulkan y pruebas de compatibilidad.
- La caché de la composición **no es una precarga ilimitada** de video: está limitada para no aumentar demasiado el consumo de memoria. En códecs pesados o medios almacenados en discos lentos pueden permanecer tirones, especialmente en cambios de fuente.
- La compilación y reproducción real de la interfaz de PySide6 sobre Windows no pueden verificarse en el entorno de pruebas actual. La prueba de usuario es necesaria antes de marcar esta versión como estable.

---

<!-- CAMBIOS_v0.6.3.md -->
## ModGames44 Video Editor v0.6.3 — Reproducción continua e imán real

**Base:** v0.6.2. Se conservan subtítulos, títulos, imágenes, IA, «Quitar silencios», proxies y la interfaz Cyber Studio.

### 1. Play sin interrupción entre clips unidos

- `timeline/playback_boundaries.py`: los bordes de edición ya no provocan una pausa si hay material de video/audio en continuidad. El programa se detiene únicamente ante huecos reales cuando esa preferencia está activada.
- `core/sequence_player.py`: al llegar a un nuevo fragmento del **mismo archivo**, se conserva la fuente cargada en QMediaPlayer para evitar el `stop()` y la recarga que interrumpían la reproducción. Se salta al nuevo `in_ms` si se ha eliminado un tramo de origen.
- El cabezal no retrocede al borde durante el cambio de clip. El seek manual continúa siendo exacto.
- La opción del menú se llama ahora **Reproducción → Detener reproducción cuando hay huecos**. Internamente conserva la clave `stop_at_cuts` para no perder las preferencias existentes.
- **Cuchilla en uso activo:** al realizar manualmente un corte mientras Play está en marcha, esa operación sigue pausando para facilitar la edición. Los futuros Play atraviesan el corte normalmente.

### 2. Imán durante el arrastre de clips

- Nuevo motor puro `timeline/snapping.py` para ajustar el **inicio al final** del vecino y el **final al inicio** del siguiente, además de bordes entre pistas, origen y cabezal.
- Tolerancia en píxeles (12 px por defecto), adaptada al zoom.
- Con el imán activado se impiden solapamientos accidentales entre clips del mismo tipo (video/video, audio/audio) y la misma pista. Se respeta el desplazamiento horizontal de los compañeros vinculados.
- El acoplamiento ya se representa **durante el arrastre** en la Timeline, no únicamente al soltar.
- Desactivar el imán permite solapamientos deliberados. Los títulos, subtítulos e imágenes siguen siendo superponibles.
- Los cambios se integran con deshacer/rehacer y no modifican archivos originales.

### Pruebas recomendadas en Windows

1. Importa un video de unos segundos con 3 silencios detectables. Aplica **Quitar silencios** y **Cerrar huecos**. Pulsa Play desde el principio: debe pasar por las uniones sin detenerse, aunque salte posiciones de origen.
2. Deja otro par de clips separados por 2 segundos en la Timeline; con la opción de detener en huecos activada, confirma que el cabezal se detiene al empezar el espacio vacío.
3. Acerca un clip arrastrándolo hasta que su **inicio** coincida con el **final** de otro. Repite en dirección inversa, acercando el **final** al **inicio** del siguiente.
4. Intenta montar un clip sobre otro en V1/A1 con imán activado: debe quedar adyacente. Con imán desactivado se puede solapar intencionalmente.
5. Repite el arrastre con mucho zoom y con un par video/audio vinculado. Usa Ctrl+Z y Ctrl+Y para comprobar los movimientos.
6. Verifica que las transiciones de solapamiento deliberadas y las imágenes/textos encima de clips siguen funcionando.

### Validación realizada

- 248 pruebas automatizadas: límites de reproducción, motor de secuencia simulado, continuidad de fuente, saltos de origen, colisiones de pista, tolerancias de zoom, vínculos, además de las regresiones anteriores.
- Sintaxis Python y archivo ZIP verificados.
- **Pendiente de verificar:** arrastre real con mouse y decodificación Qt Multimedia en Windows. Las uniones entre fuentes de video distintas pueden tener pequeños retrasos de decodificación según equipo/códec.

---

<!-- CAMBIOS_v0.6.2.md -->
## ModGames44 Video Editor v0.6.2 — Edición directa de texto e imágenes

### Nuevas funciones

- **Texto sobre el monitor:** selecciona el título o subtítulo con el botón izquierdo del mouse y arrástralo a cualquier posición del lienzo. Usa los cuatro manejadores de esquina para aumentar o reducir el tamaño sin deformarlo.
- **Tipografía:** en `Texto y subtítulos → Títulos`, selecciona la familia de fuente instalada en el sistema y pulsa **Actualizar** en un título seleccionado. La fuente seleccionada también se usa en el render de exportación; si la fuente no está instalada o Pillow no puede cargarla, se usa la fuente predeterminada de respaldo.
- **Imágenes:** `Texto y subtítulos → Imágenes → Insertar imagen…` (o `Editar → Insertar imagen…`, `Ctrl+Shift+I`). Soporta PNG/JPG/JPEG/BMP/WEBP/TIFF, conserva el alfa de PNG y la relación de aspecto.
- Las imágenes crean un clip independiente en la pista **V3**, con **5 segundos** iniciales de duración, ampliables con el extremo del clip en la Timeline.
- Al seleccionar una imagen puedes moverla, escalarla, rotarla y animarla desde el panel **Keyframes**. El mouse modifica posición y escala; las posiciones se guardan en coordenadas relativas al lienzo.
- **Deshacer** (`Ctrl+Z`) restaura las modificaciones del monitor. El proyecto `.mg44` conserva estilos, rutas y keyframes. Los archivos de imagen originales no se modifican.

### Diseño

Se conserva el diseño Cyber Studio y la distribución por pestañas sin añadir un nuevo dock. La selección y redimensionado usan únicamente el propio monitor.

### Validación

- 218 pruebas de regresión y nuevas pruebas de imágenes, geometría, tipografías, cortes y serialización de proyecto.
- Exportación real FFmpeg con imagen RGBA y posición desplazada, más muestras con animación de movimiento, escala y rotación.
- Sintaxis Python y ZIP verificados.
- **Pendiente:** prueba visual de PySide6 en Windows, con distintos tamaños de monitor y selección con mouse. No se compiló un EXE en esta entrega.

### Limitaciones

- Las fuentes necesitan estar instaladas en el equipo para aparecer en el selector, y se requiere que Pillow pueda cargarlas para que se exporten idénticas.
- Las imágenes se insertan como capas de superposición, no como clips de video con audio.
- La edición con el mouse escala proporcionalmente; posición, rotación, escala y opacidad exactas se pueden configurar desde Keyframes.
- Si una imagen referenciada se mueve o borra fuera del programa, el proyecto necesitará volver a localizarla.

---

<!-- CAMBIOS_v0.6.1.md -->
## ModGames44 Video Editor v0.6.1 — Recuperar «Quitar silencios»

**Base:** v0.6.0. Se mantienen autoguardado, Ripple, proxies, subtítulos, títulos, compositor multipista y seguimiento.

### Qué ocurrió

El motor local `ai/silence.py` ya existía desde v0.3.9 y seguía intacto en v0.6.0. El acceso a «Autoedición: quitar silencios» permaneció exclusivamente en el Asistente IA, oculto por defecto en Cyber Studio. El catálogo y Audio / Voz no mostraban la herramienta.

### Corrección

- **Efectos → Catálogo → Efectos de audio → Quitar silencios**, buscable por nombre.
- **Efectos → Audio / Voz → Detectar y quitar silencios…**, al seleccionar un clip de audio (o video con audio vinculado).
- El botón usa el mismo análisis FFmpeg de siempre y abre automáticamente el plan en **Asistente IA**. Se revisan los intervalos antes de pulsar **Aplicar cambios**.
- Los cortes afectan a clips enlazados si procede y no alteran los medios originales. Se pueden revertir con `Ctrl+Z`.
- Se conserva el acceso anterior desde **IA → Asistente IA**.
- Se corrigió una nota de interfaz obsoleta sobre el procesamiento por tramos.

### Comportamiento y límites

- La función elimina *tramos de silencio de la Timeline*, no reduce ruido de fondo ni silencia una pista: **Reducir ruido** sigue siendo un control independiente.
- El detector utiliza los valores predeterminados existentes (-34 dB, 0,75 s), conserva márgenes y **no elimina automáticamente todo un clip**.
- Los cortes propuestos inicialmente dejan huecos; el usuario puede cerrarlos posteriormente mediante «Cerrar huecos» o Ripple Edit según convenga.
- La aplicación abre el panel de IA para confirmar cambios. **No requiere la API de OpenAI:** la detección es local con FFmpeg.

### Pruebas recomendadas en Windows

1. Abre Efectos → Catálogo, busca «silencios» y haz doble clic.
2. Selecciona un clip de video con audio enlazado en la Timeline y abre Efectos → Audio / Voz. Pulsa «Detectar y quitar silencios…».
3. Confirma que Asistente IA muestra una propuesta de cortes sin cambiar todavía el montaje.
4. Aplica la propuesta y comprueba que los fragmentos de video/audio permanecen sincronizados; `Ctrl+Z` debe restaurarlos.
5. Repite la operación con una pista de audio independiente y con un clip sin audio.

**Entorno de prueba:** regresiones Python y prueba FFmpeg, sin GUI de Windows/PySide6 disponible aquí.

---

<!-- CAMBIOS_v0.6.0.md -->
## ModGames44 Video Editor v0.6.0 — Edición y textos

**Base:** v0.5.0. Se mantienen los archivos `.mg44`, los motores de previsualización y el diseño Cyber Studio / Cyber Neon.

### Interfaz compacta

- **Izquierda:** pestañas Proyecto / Efectos / Texto y subtítulos. Herramientas e IA disponibles de forma contextual desde el menú Ver.
- **Centro:** monitor amplio, sin paneles adicionales superpuestos.
- **Derecha:** Propiedades / Keyframes (Audio Meter disponible en pestaña).
- **Abajo:** Timeline, que recupera el espacio horizontal antes ocupado por Herramientas.
- Barra superior compacta con selección (V), cuchilla (✂), textos (T) y Exportar. Los paneles siguen siendo reubicables.
- Si tenías distribuciones antiguas guardadas, esta versión inicia nuevas distribuciones para evitar paneles pequeños o flotantes.

### Las ocho mejoras

1. **Autoguardado y recuperación:** guardado atómico cada 60 segundos, también sin nombre de proyecto, en la carpeta de datos del usuario; se ofrece recuperar una sesión o una copia más reciente. No sustituye a Guardar (`Ctrl+S`).
2. **Edición magnética / Ripple:** Snapping existente y opción Editar → Ripple Edit. Al eliminar segmentos enlazados, desplaza los clips posteriores en las pistas afectadas. Se puede deshacer con `Ctrl+Z`.
3. **Transiciones:** Editar → Disolución de 0,6 s / 1,0 s, Barrido y Deslizamiento. Selecciona el PRIMER clip de dos videos en la misma pista. Se mueve el inicio del segundo para crear un solape de fuentes, con fundido de audio cuando hay audio enlazado. Se conservan los medios originales.
4. **Proxies:** menú Proxies → Generar proxy del video seleccionado. Codificación H.264 a 540p en hilo trabajador. Con «Usar proxies durante la previsualización» habilitado, QMediaPlayer y el compositor prefieren el proxy si existe. La exportación siempre usa el archivo original. Los proxies quedan en caché local, no dentro del `.mg44`.
5. **Panel de Keyframes:** selecciona un título/subtítulo para animar posición X/Y, escala, rotación u opacidad, o una pista de audio para animar su volumen. Coloca el cabezal y pulsa «Guardar keyframe». Los cambios de títulos se exportan vía filtros FFmpeg; los de volumen se aplican a la reproducción y exportación. Para video siguen disponibles los keyframes de zoom y máscara del panel Efectos.
6. **Caché inteligente:** miniaturas persistentes con invalidación por fecha/tamaño del medio y mantenimiento de límite aproximado de 512 MiB. Se conserva la caché de formas de onda ya presente, para no recalcularla en cada sesión.
7. **Subtítulos automáticos:** pestaña «Texto y subtítulos» → «Subtítulos» → selecciona video → «Generar subtítulos». Usa **faster-whisper opcional** con transcripción local en hilo de trabajo. El modelo se descarga la primera vez; después se usa localmente. Los fragmentos se insertan como clips editables en V3. Es posible exportar `.srt` desde el mismo panel.
8. **Títulos y textos animados:** pestaña «Texto y subtítulos» → «Títulos»; estilos sencillos (centro, arriba, abajo; aparecer, subir, deslizar). Se insertan como clips editables en V3 y se guardan dentro del proyecto. Exportación de títulos con fondo transparente y animaciones FFmpeg para posición, escala, rotación y opacidad.

### Instalar

```powershell
python -m pip install -r requirements.txt
python main.py
```

Transcripción local opcional:

```powershell
python -m pip install -r requirements-subtitulos.txt
```

Puede requerir descargas adicionales de modelos, memoria y CPU. La compatibilidad real de `faster-whisper` en el equipo depende de sus dependencias nativas.

### Límites actuales

- Para aplicar una transición se necesitan **dos clips contiguos de video en la misma pista** y al menos 100 ms de material útil. No genera fotogramas de origen inexistentes.
- El desplazamiento Ripple es por pistas afectadas, no un «ripple de todas las pistas» al estilo de determinados NLE. Mantiene la sincronización de los clips enlazados eliminados y posteriores.
- Los proxies son opcionales, se generan en segundo plano y ocupan espacio adicional en disco. Se requiere FFmpeg con libx264. No se usan en la exportación.
- Subtítulos automáticos requieren instalar `faster-whisper` aparte; los resultados pueden necesitar corrección humana. No se ha validado la inferencia Whisper real en Windows en esta entrega.
- Render de títulos con animaciones por frame puede incrementar el tiempo de exportación (especialmente a 4K). Para una gran cantidad de subtítulos, la preparación de imágenes PNG puede tardar unos instantes.
- Algunas funciones anteriores como el seguimiento de objetos continúan siendo experimentales.

### Pruebas sugeridas en Windows

1. Guarda un `.mg44`, añade clips, espera más de 60 s y abre de nuevo: comprueba la recuperación sin sobrescribir el proyecto.
2. Usa Ripple sobre dos segmentos enlazados y verifica que audio y video mantengan su posición relativa; deshaz.
3. Aplica disolución/barrido/deslizamiento entre dos videos e inspecciona el monitor y el archivo exportado.
4. Genera un proxy de un MP4 4K y compara la reproducción; exporta y verifica que conserve la resolución de origen seleccionada.
5. Añade un título, crea dos keyframes distantes y modifica posición, rotación, escala y opacidad. Exporta.
6. Genera subtítulos con un video de voz clara y revisa la alineación y el `.srt`.
7. Vuelve a probar drag-and-drop de Proyecto a Timeline, desplazamiento con zoom máximo y «Ir al final».

**Pruebas en este entorno:** unit tests Python y render FFmpeg real. No disponemos de PySide6/Windows para comprobar visualmente los paneles, el audio QAudioSink ni el reconocimiento con modelos descargados.

---

<!-- CAMBIOS_v0.5.0.md -->
## ModGames44 Video Editor v0.5.0 — Motores avanzados (pruebas)

**Base:** v0.4.12b. Windows 10/11 x64, Python 3.14 + PySide6. Se mantiene Cyber Studio, el formato `.mg44` y los archivos fuente intactos.

### Cambios

#### 1. Audio continuo con efectos
- `core/continuous_audio_preview.py`: salida continua PCM 48 kHz/16-bit estéreo a través de `QAudioSink`.
- `services/continuous_audio.py`: FFmpeg aplica la mezcla y los mismos filtros que exportación en un único flujo; no crea archivos WAV de 30 segundos.
- Si haces Seek, cambias filtros o pausas en un corte, se reinicia el flujo en la nueva posición: **podría haber demora al comenzar**, pero no debe haber interrupción periódica de 30 segundos durante Play continuo.
- El Audio Meter recibe picos de la señal PCM procesada. Las correcciones de latencia entre la salida Qt y el video requieren pruebas en distintos equipos.

#### 2. Previsualización multipista
- `effects/compositor.py` y `services/video_frames.py`: composición no destructiva de V1/V2/V3 por prioridad de pista, con máscaras, color, zoom y opacidad (fade) por clip.
- Se activa al coincidir al menos dos capas en el mismo tiempo; el render se solicita en un trabajador, no en el hilo de interfaz.
- Utiliza OpenCV para extraer fotogramas; si no está disponible, recurre a FFmpeg, con menor rendimiento. 4K con varias capas puede requerir proxies en una versión posterior.

#### 3. Máscaras y zoom animados al exportar
- `exporter/animated_effects.py` genera expresiones FFmpeg interpolando keyframes guardados en tiempo de archivo.
- `exporter/render.py`: usa `zoompan` y máscaras animadas con `geq`/`maskedmerge`. Se incluyen los bordes suaves por interpolación espacial aproximada.
- Los keyframes siguen sincronizados cuando se cambia la velocidad del clip o se recorta un segmento.
- **Rendimiento:** los filtros `geq` sobre una imagen 4K pueden tardar considerablemente. Optimización GPU todavía pendiente.

#### 4. Seguimiento automático de censura
- `services/object_tracking.py`: seguimiento local por similitud de plantilla OpenCV.
- En Efectos → Censura encontrarás **«Seguir objeto · generar fotogramas clave»**.
- Primero configura y coloca el recuadro. Sitúa el cabezal donde comienza el seguimiento, pulsa el botón y revisa los keyframes producidos.
- Los puntos se guardan en `.mg44`, pueden corregirse con el mouse y admiten Deshacer.
- Sigue hasta 20 segundos por operación; puede perder objetos que se tapen, se deformen, giren o abandonen la pantalla. **Se requiere supervisión**; no es un modelo de IA para reconocer semánticamente objetos.

### Instalación

```powershell
python -m pip install -r requirements.txt
python main.py
```

Nueva dependencia: `opencv-python>=4.10,<5`. La capacidad de ejecutar la interfaz PySide6 y el audio `QAudioSink` **no se ha verificado en este entorno Linux**, por lo que debe ensayarse en Windows. Los tests puros de Python, procesamiento FFmpeg y OpenCV no reemplazan esa prueba.

### Plan de validación en Windows

1. Reproduce una grabación de más de 60 segundos con efecto Podcast; escucha los segundos 29–31 y 59–61 para comprobar que no haya pausas.
2. Superpone dos videos en V1 y V2, con un Fade In en V2. Comprueba que el video inferior siga visible durante el desvanecimiento.
3. Anima un zoom y una máscara con al menos dos fotogramas clave. Exporta y comprueba que sus posiciones cambien efectivamente.
4. Elige una región contrastada y en movimiento, usa «Seguir objeto» y corrige los puntos que fallen. Exporta para comprobar el seguimiento.
5. Ensaya pausa, arrastre del cabezal, cortes, exportación y guardado/carga para verificar regresiones.

**Estado:** versión de pruebas; no se declara producción estable ni equivalencia de rendimiento con Premiere.

---

<!-- CAMBIOS_v0.4.12b.md -->
## Corrección de compilación Nuitka v0.4.12b

La regla `imageio_ffmpeg` en `nuitka-package.config.yml` contenía `executable` al nivel equivocado. Nuitka 4.3.1 la rechazaba con «Additional properties are not allowed».

- Se movió `executable: 'yes'` dentro de `from_filenames`, tal como especifica Nuitka.
- `build.py` comprueba la estructura antes de compilar.
- Test de regresión para la sangría.
- El auto-test onefile tiene un límite de 180 segundos para dar tiempo a extraer el paquete.

Compilar en Windows:

```powershell
python -m pip install -r requirements.txt
python build.py
```

Salida esperada: `dist/ModGames44VideoEditor.exe`. Es necesario probar el compilado real en Windows, especialmente Qt Multimedia y FFmpeg; no se ha compilado aquí.

---

<!-- CAMBIOS_v0.4.12.md -->
## ModGames44 Video Editor v0.4.12 — Branding y Nuitka Onefile

- Logotipo suministrado por el usuario junto a «ModGames44 Video Editor» en la barra superior.
- Archivo `.ico` suministrado aplicado a la ventana y al `.exe` mediante Nuitka.
- `build.py` reemplazado por Nuitka `--mode=onefile` para Windows 10/11 x64.
- Assets (iconos, logo, QSS) incluidos en el mismo ejecutable distribuible.
- FFmpeg interno de `imageio-ffmpeg` empaquetado como ejecutable según la configuración YAML de Nuitka.
- PySide6 y Qt Multimedia incluidos mediante el plugin de Nuitka; OpenAI opcional si está instalado.
- Auto-test de recursos, FFmpeg y Qt Multimedia al terminar la compilación.

### Compilar

En Windows 10/11 de 64 bits, con Python x64 y compilador C compatible instalado:

```powershell
python -m pip install -r requirements.txt
python build.py
```

Resultado previsto: `dist/ModGames44VideoEditor.exe`.

Para incluir IA en línea (opcional): `python -m pip install -r requirements-ia.txt` antes de compilar. La API requiere clave y conexión al usarse.

`python build.py --dry-run` muestra las opciones; `python build.py --skip-self-test` permite saltar el auto-test (no recomendado).

### Importante

El ejecutable es un solo archivo para distribuir. Nuitka descomprime internamente los componentes en una carpeta temporal mientras se ejecuta; es normal. El editor continúa creando cachés, archivos temporales de procesamiento, proyectos y exportaciones fuera del exe. No es posible incluir los videos futuros ni sus resultados permanentemente dentro del ejecutable.

La compilación Windows y su ejecución gráfica deben verificarse en Windows; este paquete contiene el proyecto y el script listo, **no** un `.exe` compilado ni validado en Windows.

---

<!-- CAMBIOS_v0.4.11.md -->
## ModGames44 Video Editor v0.4.11 — Navegación y extremos de la Timeline

### Correcciones

- Se sincroniza explícitamente el `sceneRect` de `QGraphicsScene` con el de `QGraphicsView` al refrescar los clips. Qt puede mantener un rango de scroll desactualizado tras cargas, zoom y cambios de ventana.
- El botón **Final** ahora recalcula el área disponible antes de intentar desplazar el cabezal y comprueba su posición real en el viewport con `mapFromScene`. Si la barra limita el desplazamiento, amplía el área y corrige la posición.
- Se ejecuta una segunda corrección en el siguiente ciclo del evento de Qt para evitar el máximo de scroll antiguo. No cambia la velocidad, el tiempo de los medios ni el zoom.
- Se mantiene espacio de edición después del último clip, incluidos zooms grandes y ventanas pequeñas.
- Nueva opción **Ver → Copiar diagnóstico de Timeline** (`Ctrl+Alt+D`). Copia duración real, escala, ancho de escena, rango de barra y posición visible del cabezal. Para soporte, pulsar **Final**, copiar diagnóstico y compartir el texto.
- Opción de depuración por consola: iniciar con `MODGAMES_TIMELINE_DEBUG=1` para registrar la navegación a Final.

### Validación

- Pruebas geométricas para un video de 10:20.120 y zoom entre 5 y 700 px/s.
- Comprobación de corrección del desplazamiento a partir de coordenadas reales de la vista.
- Pruebas previas de edición, audio, exportación y drag/drop conservadas.

**Limitación de verificación:** aquí no se dispone de PySide6 ni de un escritorio Windows operativo para ensayar los eventos reales de QGraphicsView. El ZIP se verifica con pruebas Python y necesita la prueba visual en tu equipo.

---

<!-- CAMBIOS_v0.4.10.md -->
## v0.4.10 — Navegación extendida y drag & drop de Proyecto

- Cola de edición tras el último clip: mínimo 45 segundos a la escala actual y 1,25 anchos de viewport. Permite scroll hasta el final y más allá a cualquier zoom, incluso a 700 px/s.
- Inicio/Final: mismo motor, ahora dispone de espacio físico de scroll para encuadrar el cabezal.
- Al redimensionar la ventana o cambiar el espacio de trabajo, el margen de Timeline se recalcula sin regenerar videos.
- Arrastre desde Proyecto: inicio explícito al superar la distancia del mouse; MIME propio, URL local y texto; recepción directa en viewport de Timeline. Funciona tanto en modo Lista como Miniaturas (pendiente validación física en Windows).
- Doble clic y menú Añadir a Timeline conservados.
- Se mantienen efectos, Audio FX, cuchilla, fades y Cyber Studio.

Pruebas: ejecutar `python -m unittest discover -s tests -v` y probar el arrastre y el scroll en Windows. Estas pruebas automatizadas no garantizan la interacción física del mouse en Windows.

---

<!-- CAMBIOS_v0.4.9.md -->
## ModGames44 Video Editor v0.4.9 — Scroll y cabezal

### Correcciones

- Repintado completo del viewport de la Timeline cuando se mueve cualquiera de las barras de desplazamiento, evitando rastros y etiquetas repetidas del overlay de regla/cabeceras.
- La regla de tiempo y los encabezados V3/V2/V1/A1/A2/A3 se mantienen anclados a la ventana, no al contenido que se desplaza.
- Los botones Inicio y Final del monitor llevan también la vista de los clips a la ubicación del cabezal, sin alterar el zoom ni mover verticalmente las pistas.
- En reproducción la vista acompaña al cabezal cuando este alcanza el extremo derecho.
- Los saltos manuales desde el monitor centran el tiempo seleccionado.
- Funcionalidad de Fade, clip, ondas FX, desenfoque, audio y exportación conservada.

### Pruebas recomendadas en Windows

1. Cargar video con audio, ampliar zoom y mover horizontalmente la barra numerosas veces. No deben aparecer títulos V1, V2 o marcas temporales repetidos.
2. Cambiar altura de las pistas, desplazar verticalmente el viewport y verificar que los nombres no dejan restos.
3. Con el zoom alto y la Timeline desplazada al minuto 3, pulsar Inicio; la vista debe mostrar 00:00 y el cabezal.
4. Pulsar Final; la vista debe mostrar el último instante y el cabezal.
5. Reproducir con el cabezal cerca del límite derecho: la vista debe seguirlo.
6. Confirmar cuchilla, fades, zoom y audio vinculados.

Las pruebas unitarias de geometría no sustituyen a una ejecución real de la interfaz PySide6 en Windows.

---

<!-- CAMBIOS_v0.4.8.md -->
## ModGames44 Video Editor v0.4.8 — Corrección Proyecto / Timeline

### Cambios
- Proyecto: doble clic sobre un medio lo inserta en la Timeline (V1/A1); clic simple continúa mostrando vista previa.
- Menú contextual de Proyecto: **Añadir a la Timeline**.
- Arrastrar y soltar: recepción explícita de archivos existentes, validación del medio y mensajes de estado.
- Timeline: pintura de clips aislada de los triángulos amarillos de fades. No debería producirse la franja amarilla que ocultaba fotogramas.
- Miniaturas: mientras se generan, aparece la miniatura provisional; después se reemplaza por fotogramas correspondientes a instantes diferentes.
- No se cambian los datos `.mg44`, los tiempos, las ondas, los fades ni los filtros.

### Pruebas en Windows
1. Abre el programa, importa un MP4 de prueba.
2. Haz doble clic sobre el MP4 en Proyecto. Debe aparecer en V1 y su audio en A1.
3. Importa otro MP4 y arrástralo a V1. Comprueba que aparece donde lo sueltas.
4. Comprueba que el video muestra miniaturas y no un rectángulo amarillo.
5. En la herramienta Selección, arrastra los pequeños triángulos amarillos en las esquinas para crear Fade In y Fade Out y reproduce el video.
6. Comprueba cortes, zoom, audio y exportación.

**Limitación de validación:** no se ha ejecutado PySide6 en Windows desde este entorno. Se hicieron análisis estáticos, pruebas Python y comprobaciones sin interfaz gráfica, no una prueba audiovisual integral.

---

<!-- CAMBIOS_v0.4.7.md -->
## ModGames44 Video Editor v0.4.7 — Fades y pistas al estilo Premiere

### Organización de la Timeline

- Las pistas se ordenan como `V3, V2, V1, A1, A2, A3`: V1 queda inmediatamente encima de A1.
- Las pistas de video y audio conservan su índice de modelo 0, 1, 2; los proyectos `.mg44` previos siguen siendo compatibles.
- El audio se puede arrastrar verticalmente a A1/A2/A3 sin desplazar el video a otra pista. El movimiento **horizontal** de clips vinculados sigue sincronizado hasta utilizar «Desvincular».
- Se puede cambiar la altura de cada pista con la rueda del mouse sobre su encabezado.

### Desvanecimientos (Fade In / Fade Out)

1. Selecciona la herramienta **Seleccionar (V)**.
2. En la parte superior del extremo **izquierdo** del clip verás un pequeño triángulo amarillo. Arrástralo hacia el interior para crear un Fade In. Arrástralo hacia la izquierda para reducirlo o eliminarlo.
3. Haz lo mismo desde el extremo **derecho**, arrastrándolo a la izquierda, para un Fade Out.
4. Sirve en clips de video y en clips de audio. Los desvanecimientos de ambos clips son **independientes**, incluso cuando sus movimientos permanecen vinculados.
5. También puedes seleccionar un clip y abrir el menú contextual para aplicar un fade de 1 segundo o quitarlo.
6. `Ctrl+Z` / `Ctrl+Y` permiten deshacer y rehacer cambios de fades.

#### Comportamiento audiovisual

- En video, el Fade In/Out modifica la opacidad de 0% a 100% y viceversa, con una curva lineal. La vista previa actual funde al fondo negro; al exportar se revela la pista inferior cuando existe. La reproducción simultánea de múltiples capas de video en el monitor todavía está limitada por el motor de previsualización actual.
- En audio, el Fade In/Out modifica la ganancia progresivamente y también se dibuja sobre la forma de onda de la Timeline. **Sí se escucha al reproducir desde la Timeline**, y se exporta con FFmpeg.
- Los fades de audio no reanudan la curva desde cero cuando la previsualización cambia de ventana temporal (procesamiento por tramos).
- Las duraciones se guardan en los campos opcionales `fade_in_ms` y `fade_out_ms` de cada clip, sin alterar los archivos originales.
- Al cortar un clip, el segmento izquierdo conserva el fade de entrada y el segmento derecho conserva el fade de salida. Los cortes no introducen fades adicionales.
- El modelo limita cada fade para que ambos no superen la duración total del clip.

### Pruebas técnicas

- 149 pruebas automatizadas superadas, incluidas regresiones anteriores y 16 nuevas pruebas de fades y distribución.
- FFmpeg comprobado con archivos reales: render MP4 con transiciones de opacidad y volumen, y previsualización WAV por ventanas.
- Sintaxis Python verificada con `compileall`.
- **No se ha comprobado la GUI de PySide6 en Windows.** Falta validar visualmente el arrastre de los triángulos y la reproducción en el sistema destino.

### Ejecución

```powershell
python -m pip install -r requirements.txt
python main.py
```

El programa conserva Cyber Studio como espacio predeterminado.

---

<!-- CAMBIOS_v0.4.6.md -->
## ModGames44 Video Editor v0.4.6 — Ondas FX y voz

### Implementado
- Visualización de ondas procesadas con botón «Onda FX» en la Timeline.
- Ganancia en dB reflejada sin volver a procesar el audio.
- Regeneración asíncrona y caché por archivo + configuración de efectos.
- Tres perfiles ModGames44 revisados con EQ y compresión moderadas.
- Reducción de ruido corregida de escala casi nula a 3–20 dB con FFmpeg afftdn.
- Conservación de archivos originales y motor de previsualización de v0.4.5.

### Limitaciones
- No son presets idénticos a Adobe; sus curvas exactas no son públicas.
- Los efectos espectrales no siempre producen diferencias visuales grandes en la onda.
- Calcular toda la onda procesada de archivos largos puede tardar; no bloquea el hilo de Qt.
- La onda refleja el audio por clip, no la mezcla final del limitador del proyecto.
- No se ha ejecutado la interfaz real en Windows.

### Prueba
1. Añade un video con voz real a V1/A1.
2. Cambia ganancia A1 de 0 dB a +6 dB y pulsa Aplicar.
3. Comprueba que la onda es más alta al tener «Onda FX» activada.
4. Selecciona Voz Podcast; cuando esté procesada, la onda deberá representar el PCM filtrado.
5. Desmarca «Onda FX» para comparar con la forma de onda original.
6. Pulsa Play para escuchar y exporta una muestra para comparar.

---

<!-- CAMBIOS_v0.4.5.md -->
## ModGames44 Video Editor v0.4.5 — Efectos durante reproducción (beta)

### Qué cambia

- **Los efectos de audio ahora se escuchan al pulsar Play desde la Timeline**. La reproducción de pistas A1/A2/A3 se mezcla con FFmpeg usando **la misma función de filtros** que la exportación (`effects.audio.audio_filter_chain`). Incluye ganancia, reducción de ruido, perfiles Podcast/alto/bajo y normalización; también tiene en cuenta cortes, huecos y velocidades de los clips.
- **No se vuelve a codificar el video** para escuchar los efectos. Una segunda instancia QMediaPlayer reproduce pequeños WAV de audio procesado y el QMediaPlayer principal reproduce el video con su salida de audio silenciada. Esto evita oír dos voces a la vez.
- **Audio Meter** mide la mezcla procesada de la Timeline (cuando Qt 6.8+ permite `QAudioBufferOutput`). En la vista Proyecto mide el audio original.
- **Efectos de video** (zoom, máscara de desenfoque/mosaico, ajustes de color y espejo) se calculan sobre los fotogramas decodificados por QVideoSink. Se movió el render Pillow a un hilo secundario con descarte de imágenes antiguas para no bloquear el hilo principal a 60 fps. Los fotogramas clave de máscaras/zoom son visibles en la previsualización.
- Corregido el avance del reloj de Timeline con cámara rápida/lenta: la velocidad no debe aplicarse dos veces (la duración del clip ya la incorpora).
- Indicación `FX` en el monitor: listo, preparando audio o activo.
- Pausar y arrastrar el cabezal detiene inmediatamente el audio procesado; los cambios de efectos invalidan su caché de reproducción.
- **Cyber Studio** sigue siendo la interfaz predeterminada; no se reemplazaron paneles ni herramientas.

### Instalación

```powershell
python -m pip install -r requirements.txt
python main.py
```

Requiere FFmpeg mediante PATH o `imageio-ffmpeg` (incluido como dependencia), con los filtros `afftdn`, `loudnorm`, `acompressor`, `alimiter` y `atempo`.

### Pruebas manuales de Windows (importantes)

1. Carga MP4 con voz; arrástralo a V1/A1 y selecciona A1.
2. En Efectos → Audio/Voz, configura **Ganancia -12 dB** y presiona **Aplicar**. Pulsa Play: debe escucharse más bajo y el Audio Meter medir el resultado. Cambia a +6 dB y vuelve a probar.
3. Aplica Voz Podcast, eliminación de ruido y normalización. Pulsa Play cada vez para comparar. Estos cambios NO modifican el archivo original.
4. Selecciona V1, aplica desenfoque parcial y mueve la máscara; reproduce y verifica que solo esa región esté afectada. Comprueba zoom, color, espejo y cambios de velocidad.
5. Corta el video con C, presiona Play y verifica que el audio y el cabezal se detienen juntos en el corte.
6. Mueve el cabezal a otra parte del video, espera al mensaje de audio preparado y vuelve a reproducir. Añade una segunda pista A2 para probar la mezcla.
7. Al elegir un archivo en el panel Proyecto (no en la Timeline) se reproduce su audio **sin filtros de clip**.

### Limitaciones verificables

- **Primer Play o nuevo seek:** puede necesitar preparar ~30 segundos de audio en segundo plano. El video no se inicia hasta que el tramo WAV esté disponible. Se pueden producir pausas breves al pasar al siguiente tramo; el sistema está en beta.
- **No equivalencia píxel a píxel entre previsualización y exportación:** el monitor usa Pillow y una resolución reducida para responder rápidamente, mientras la exportación usa filtros FFmpeg. Los fotogramas clave de zoom y máscara, así como el suavizado de bordes de censura, **siguen sin exportarse como animación**, aunque puedan verse al reproducir. La función de exportación avisa de esas limitaciones.
- **Composición de video V1/V2/V3:** el reproductor actual sigue mostrando el clip superior activo, no una composición simultánea de capas de video; el exportador sí compone las pistas. No se implementaron efectos que no existían (p.ej. estabilización real o transiciones). No debe suponerse que están activos.
- **Sin prueba en Windows desde este entorno:** se probaron FFmpeg/PCM, modelo y sintaxis; pero no fue posible ejecutar PySide6 para validar la sincronización audiovisual ni el dispositivo de audio en un PC Windows. Se requiere la validación manual anterior.

---

<!-- CAMBIOS_v0.4.4.md -->
## ModGames44 Video Editor v0.4.4 · Cyber Studio

- Cyber Studio se selecciona automáticamente en el primer inicio de esta versión; después se respeta la preferencia guardada. Cyber Neon sigue disponible si se desea.
- Botón **Quitar desenfoque / mosaico** siempre visible en la cabecera de Video / Efectos, aunque se desplace el panel.
- Botón adicional en Propiedades del clip para eliminar la censura sin cambiar de pestaña.
- Al quitar el efecto se desactiva inmediatamente la edición por mouse, desaparecen el recuadro y el desenfoque.
- Se borran la máscara y los fotogramas clave asociados a la censura. **Ctrl+Z** permite recuperar el efecto completo.
- La caché de imagen se invalida y las herramientas no conservan un arrastre de máscara pendiente.
- Deshacer/Rehacer actualiza los botones y la casilla de edición según el clip seleccionado.

Prueba manual recomendada (Windows): añadir video → aplicar desenfoque → editar máscara con mouse → Quitar censura en Propiedades → verificar la imagen limpia y el cursor normal → Ctrl+Z y Ctrl+Y.

---

<!-- CAMBIOS_v0.4.3.md -->
## ModGames44 Video Editor v0.4.3 — Cyber Responsive

### Qué cambia frente a v0.4.2

- **Cyber Neon**: Proyecto a la izquierda; Program Monitor central; Efectos rápidos, Propiedades y Medidor de audio a la derecha; herramientas y Timeline abajo.
- **Cyber Studio**: Catálogo de efectos y Proyecto apilados a la izquierda; Program Monitor central; Propiedades y Medidor de audio a la derecha; herramientas y Timeline abajo.
- Ambos comparten **grafito, cian y violeta**; nuevos bordes, tipografía, estados de selección, iconos compactos y botón Exportar visible.
- `ui/responsive_rules.py` define tamaños relativos basados en píxeles **lógicos** de Qt. Se ajustan la densidad de tarjetas, controles del monitor y tamaño inicial de la Timeline. No se cambia la posición real de los clips al redimensionar.
- Medidor L/R vertical expresado en dBFS. Usa **muestras PCM reales** cuando Qt lo permite.
- Proyecto con búsqueda, eliminación, miniaturas y cambio Lista/Miniaturas; el arrastre a Timeline conserva las rutas `QMimeData`.
- Catálogo Cyber Studio y botones Cyber Neon **abren controles existentes de video y audio**. Se omiten herramientas decorativas que todavía no tienen motor.
- Tamaños de docks guardados de forma independiente para cada espacio. Versión nueva del estado `v3`, por lo que se regeneran los tamaños heredados de v0.4.2 una vez.
- Recursos gráficos y QSS en `assets/`, incluidos automáticamente mediante `build.py`.

### Instalación y uso

1. Extraer el ZIP a una nueva carpeta.
2. `python -m pip install -r requirements.txt`
3. `python main.py`
4. Menú **Ver → Espacio de trabajo** o `Ctrl+Alt+1` (Cyber Neon) / `Ctrl+Alt+2` (Cyber Studio).
5. Si un panel ha quedado mal colocado: **Ver → Restablecer distribución actual**.
6. Botón **Exportar** superior derecho o `Ctrl+M`.

La interfaz también puede reorganizarse manualmente mediante los títulos de paneles. Los estados de cada espacio de trabajo se guardan al cambiar o salir.

### Pruebas y límites

- Pruebas unitarias y de integración pura (`pytest`) ejecutadas en el entorno de desarrollo.
- Sintaxis de todos los `.py` comprobada.
- **No se ha podido ejecutar una sesión gráfica PySide6/Qt en Windows** desde este entorno, por lo tanto no se afirma que el resultado sea idéntico píxel a píxel a los mockups. Se requiere prueba de UI real a 100/125/150% de escalado.
- La exportación, el soporte GPU, las máscaras y los efectos conservan las limitaciones funcionales descritas en la v0.4.1. Este cambio es principalmente visual y de distribución.
- La Timeline mantiene zoom y desplazamiento; las miniaturas no se actualizan con cada fotograma de reproducción, sino que representan distintas posiciones fuente según el zoom.

---

<!-- CAMBIOS_v0.4.2.md -->
## ModGames44 Video Editor v0.4.2 — Cyber Workspaces

### Novedades

- Dos espacios de trabajo en **el mismo programa**, sin duplicar el motor ni las funciones:
  - **Cyber Neon** (predeterminado): Proyecto arriba a la izquierda; Herramientas debajo; Program Monitor central; Efectos rápidos arriba a la derecha; medidor de audio debajo; Timeline inferior.
  - **Cyber Studio**: Efectos rápidos arriba a la izquierda; Proyecto debajo; Program Monitor central; Propiedades arriba a la derecha; medidor de audio debajo; herramientas junto a la Timeline.
- **Misma identidad visual** en ambas vistas: negro grafito, cian eléctrico y violeta.
- **Botón Exportar** fijo arriba a la derecha, conectado al exportador real de la versión 0.4.1.
- Selector de espacio en la barra superior y en **Ver → Espacio de trabajo**.
- Atajos: **Ctrl+Alt+1** Cyber Neon / **Ctrl+Alt+2** Cyber Studio.
- Panel **Propiedades** muestra datos del clip seleccionado y ofrece enlaces reales a las herramientas de efectos y voz.
- Es posible mover, redimensionar, tabificar y cerrar paneles. Cada espacio recuerda sus propias posiciones y tamaños al cambiar de vista y al reiniciar el programa.
- Opción **Ver → Restablecer distribución actual**.
- Se conserva el panel IA (oculto por defecto, accesible desde el menú IA).

### Notas de implementación

- `core/workspaces.py`: definición independiente de Qt de ambas distribuciones.
- `ui/workspace_manager.py`: reubica los QDockWidget existentes, y guarda/restaura el estado por perfil con QSettings y saveState/restoreState versionados.
- `ui/theme_manager.py`: tema QSS compartido por ambas.
- `ui/clip_properties_panel.py`: panel de información del clip, con botones conectados a los efectos existentes.
- `ui/main_window.py`: selector, botón Exportar, menú Ver y conexión con los paneles existentes.
- `main.py`: carga el tema.

### Pruebas

- Pruebas existentes y nuevas de la lógica: **108 superadas** (más 10 subpruebas).
- Compilación de sintaxis con `compileall` superada.
- El entorno de creación no tiene PySide6 y no permite instalarlo, así que **no se ha ejecutado la ventana ni validado visualmente en Windows**.
- No se ha compilado un EXE de Windows en este entorno. Para ello usa `python build.py` desde Windows después de instalar dependencias.

### Instalación

Descomprime la carpeta en una ubicación nueva.

```powershell
python -m pip install -r requirements.txt
python main.py
```

Ajusta paneles a tu gusto. Para volver a los tamaños iniciales de un espacio, selecciona **Ver → Restablecer distribución actual**.

### Compatibilidad

Esta versión parte directamente de la **v0.4.1**, sin alterar formatos `.mg44`, controles de reproducción, Timeline, recortes, efectos, IA ni exportación. La distribución es una preferencia local de QSettings, no se guarda dentro del proyecto.

---

<!-- CAMBIOS_v0.4.1.md -->
## ModGames44 Video Editor v0.4.1 — Audio y Exportación

### Nuevas herramientas de audio

En **Efectos rápidos → Audio / Voz**, selecciona un clip de A1/A2/A3 (o el video vinculado):

- Ganancia de -36 a +24 dB, con limitador de picos al exportar.
- Reducción de ruido FFT FFmpeg (`afftdn`), intensidad de 0 a 100 %.
- Perfiles **ModGames44**: Voz podcast / Voz equilibrada tono alto / Voz equilibrada tono bajo.
- Normalización opcional a -16 LUFS (FFmpeg `loudnorm`, método dinámico de una pasada).

**No son los algoritmos privados de Adobe.** Son filtros propios de FFmpeg (ecualización, compresión y supresión espectral). La eliminación de ruido no puede garantizar voces limpias en grabaciones difíciles y puede introducir artefactos. La ganancia alta puede llevar al limitador a comprimir los picos.

**Limitación actual importante:** el monitor Qt todavía reproduce el audio *original*. Los efectos de audio se aplican al archivo exportado, no durante Play en el monitor. Se guardan en `.mg44` y pueden deshacerse con Ctrl+Z.

### Exportar video

**Archivo → Exportar video** o **Ctrl+M**. Elegir perfil, codificador, destino y pulsar Exportar. Progreso y cancelación sin bloquear la ventana.

Perfiles:
- YouTube MP4 H.264: 1080p30, 1080p60, 1440p60, 4K60
- MP4 H.265/HEVC: 1080p30
- MP4 AV1: 1080p30, si hay encoder disponible
- MOV ProRes 422: 1080p30
- WebM VP9: 1080p30

Exporta la composición de V1-V3 (capas superiores delante de inferiores), mezcla A1-A3, huecos negros/silencios, cortes, recortes, cambios de velocidad, zoom/censura/color **estáticos**, y efectos de audio. Los clips superpuestos quedan compuestos según su pista.

**Advertencia:** el seguimiento de máscaras y los keyframes de zoom/censura animados *todavía no se procesan en exportación*; se avisa y se exige confirmación. Los bordes suaves de censura tampoco se exportan todavía, solo el recuadro. No hay transiciones, textos, óptica de ralentización, HDR ni mezcla profesional de pistas. El exportador no es un equivalente completo de Premiere y los exportes de muchos clips largos pueden consumir bastante memoria.

#### GPUs y codificadores

- Obtiene nombres de GPU con PowerShell/CIM en Windows 10/11.
- Inspecciona los codificadores que **realmente** incluye cada FFmpeg disponible.
- Ejecuta una prueba mínima de codificación por hardware antes de ofrecer NVENC (NVIDIA), AMF (AMD) o QSV (Intel).
- Ofrece CPU/software (`libx264`, `libx265`, `libsvtav1`, `prores_ks`, `libvpx-vp9`) cuando está disponible.
- En automático prefiere GPU compatible y usa CPU cuando falla su prueba. En última instancia la exportación depende del driver, GPU, formato y compilación FFmpeg.

**Windows:** si tienes FFmpeg instalado en PATH con NVENC/AMF/QSV podrá usarse. El FFmpeg incluido por `imageio-ffmpeg` puede no disponer de todos los encoders de GPU. Si Windows no reconoce la GPU o el encoder no es compatible, aparecerá CPU.

Los videos originales no se modifican. El render se genera en archivo temporal dentro de la carpeta de destino y solo sustituye al fichero final cuando la operación termina correctamente.

### Estructura modular nueva

- `effects/audio.py`: validación de efectos y cadenas de filtros de voz.
- `ui/audio_effects_panel.py`: panel de audio/voz.
- `exporter/hardware.py`: detección GPU, encoders, test de capacidad.
- `exporter/render.py`: comandos FFmpeg multipista sin interfaz.
- `ui/export_dialog.py`: selección, progreso, cancelación y guardado seguro.
- `tests/test_audio_export.py`: pruebas de audio, filtros, dispositivos, formatos y exportación real.

### Pruebas

`python -m unittest discover -s tests -v`

Comprobado con FFmpeg del entorno: exportación de MP4 H.264/AAC, MP4 HEVC/AAC, MOV ProRes/PCM y WebM VP9/Opus. También se probó una secuencia multipista con huecos, audio procesado y efectos de video. La interfaz PySide6 y las GPUs NVIDIA/AMD/Intel **no se pudieron probar en Windows desde este entorno**; requiere validación en el PC del usuario.

### Referencias

- https://helpx.adobe.com/es/premiere/desktop/add-audio-effects/adjust-volume-and-levels/improve-dialogue-clarity.html
- https://helpx.adobe.com/es/premiere/desktop/add-audio-effects/adjust-volume-and-levels/enhance-speech.html
- https://helpx.adobe.com/la/premiere/desktop/render-and-export/export-files/video-encoding-settings.html
- https://helpx.adobe.com/premiere/desktop/get-started/technical-requirements/hardware-accelerated-decoding-and-encoding.html
- https://ffmpeg.org/ffmpeg-filters.html

---

<!-- CAMBIOS_v0.4.0.md -->
## ModGames44 Video Editor v0.4.0 — Efectos rápidos

### Nuevos módulos
- `effects/model.py`: efectos no destructivos, máscaras normalizadas, keyframes y velocidad enlazada.
- `effects/renderer.py`: procesamiento visual de fotogramas para la previsualización (Pillow).
- `ui/effects_panel.py`: catálogo de efectos frecuentes, ajustes rápidos y botones de aplicación.
- `ui/effect_video_view.py`: monitor con QVideoSink y recuadro editable por arrastre.
- `timeline/thumbnail_math.py`: instantes correctos de miniaturas con cortes, zoom y velocidad.

### Funciones
- Lenta: 0,25× y 0,5×; rápida: 2× y 4× (valores entre 0,25× y 4×).
- Zoom con centro X/Y, animación opcional entre fotogramas clave.
- Censura por región rectangular, con desenfoque gaussiano o mosaico y bordes suaves.
- La máscara se desplaza arrastrando dentro del cuadro y cambia de tamaño desde las esquinas.
- Fotogramas clave de máscara para acompañar el movimiento manualmente.
- Color: brillo, contraste, saturación, escala de grises y espejo horizontal.
- Un paso de Deshacer por aplicación de efecto; persistencia dentro de `.mg44`.
- Cuchilla/cortes, audio enlazado y miniaturas adaptados al nuevo factor de velocidad.

### Cómo probar
1. Instalar: `python -m pip install -r requirements.txt`.
2. Abrir `python main.py`, importar un video con audio y arrastrarlo a V1/A1.
3. Hacer clic en V1 (no en la onda A1). Abrir la pestaña **Efectos rápidos**.
4. En **Censura**, seleccionar Desenfoque gaussiano o Mosaico y **Aplicar censura**.
5. Sobre el Monitor de programa, mover el recuadro amarillo con el mouse o arrastrar sus esquinas.
6. Para acompañar un objeto: situar el cabezal en el primer instante, ajustar el recuadro, pulsar **Fotograma clave de máscara**; ir a otro instante y mover el recuadro para crear el segundo keyframe.
7. Repetir con Zoom / Cámara lenta / Cámara rápida y probar un corte con la cuchilla, Deshacer y guardado `.mg44`.
8. Para ver fotogramas de diferentes instantes, aumentar el zoom horizontal de la Timeline con la rueda; las imágenes se extraen de distintos tiempos y se almacenan en caché. Las miniaturas no son video animado.

### Limitaciones conocidas y trabajo posterior
- La exportación de los efectos a un nuevo archivo NO está implementada. Esta versión sirve para probar editor y previsualización. El MP4 original no se modifica.
- Aún no hay seguimiento automático de caras/objetos, máscaras circulares o poligonales, ni interpolación óptica avanzada de cámara lenta.
- El motor sigue siendo preliminar para secuencias con varias pistas simultáneas; no hay composición ni mezcla multipista completas.
- La velocidad usa `QMediaPlayer.setPlaybackRate`; la calidad, audio y conservación del tono varían según códec/backend. Puede haber saltos o audio con tono alterado.
- El monitor procesa fotogramas por CPU con una resolución de previsualización reducida (máximo 960 px de ancho cuando hay efectos activos) para limitar la carga.
- No fue posible ejecutar PySide6 en Windows desde el entorno de construcción. Se verificó sintaxis, pruebas de modelos matemáticos y render de Pillow, no la interfaz ni GPU de Windows.
- Si tenías la distribución de paneles guardada de versiones anteriores, el dock mantiene su identificador para recuperar la geometría.

### Fuentes consultadas (Adobe, 2026)
- Máscaras y efectos: https://helpx.adobe.com/premiere/desktop/add-video-effects/work-with-masks/create-masks-using-shapes.html
- Seguimiento de máscaras: https://helpx.adobe.com/premiere/desktop/add-video-effects/work-with-masks/mask-tracking-tools.html
- Velocidad y duración: https://helpx.adobe.com/es/premiere/desktop/edit-projects/change-clip-speed/change-clip-speed-using-the-speedduration-option.html
- Movimiento/escala: https://helpx.adobe.com/la/premiere/desktop/add-video-effects/commonly-used-effects/apply-motion-effect.html
- Catálogo de efectos: https://helpx.adobe.com/cl/premiere/desktop/add-video-effects/effects-and-transitions-library/list-of-effects-and-transitions.html

---

<!-- CAMBIOS_v0.3.9.md -->
## v0.3.9 · ModGames44 AI Assistant (primera integración)

- Añadido panel flotante/ocultable, con vista previa de operaciones, botones Aplicar y Descartar.
- Órdenes locales de corte, eliminación de intervalos, desplazamiento de clips, cierre de huecos y búsqueda temporal.
- Integración opcional con OpenAI Responses API, sin almacenar clave y sin enviar videos.
- Motor JSON autorizado, con simulación transaccional y revalidación antes de aplicar.
- Operaciones agrupadas en un solo paso de Deshacer.
- Autoedición local de silencios mediante FFmpeg, sin sobrescribir medios.
- Peticiones en hilo secundario para mantener la interfaz receptiva.
- Documentación de privacidad, API, limitaciones y pruebas.

### Pruebas

Sintaxis Python, pruebas del motor de Timeline preexistente y pruebas nuevas de
operaciones de IA y detección de silencios. Pruebas manuales en Windows y con API
real pendientes: el entorno de compilación no tiene PySide6 ni conexión API.

---

<!-- CAMBIOS_v0.3.8.md -->
## v0.3.8 — Reparación del rastro de texto en Timeline

### Causa raíz

`ClipItem.paint()` dibujaba el nombre de archivo en `option.exposedRect.left()`.
Durante la reproducción, el arrastre del cabezal o la cuchilla, Qt invalida
franjas pequeñas de pantalla en distintas posiciones; el texto se recalculaba
en cada una y terminaba repetido/superpuesto. El mismo error afectaba a las
etiquetas «L» y «R» en la onda estéreo.

### Corrección

- Texto de clips y canales anclado a la intersección entre clip y viewport,
  no al área repintada (`option.exposedRect`).
- Nombre abreviado con `QFontMetrics.elidedText` si no cabe en el clip.
- Respeta el desplazamiento horizontal, zoom y clips muy cortos.
- No cambia el motor multimedia, la cuchilla, los recortes, el audio, ni el
  ajuste de la reproducción en cortes de v0.3.7.

### Prueba manual Windows

1. Importar un MP4 con audio y arrastrarlo a V1/A1.
2. Ampliar V1 y A1 con la rueda sobre sus encabezados.
3. Reproducir varios segundos y observar que el nombre del archivo no se
   repite ni se desplaza siguiendo el cabezal.
4. Arrastrar el cabezal y hacer un corte con C; comprobar el nombre y L/R.
5. Hacer zoom horizontal, desplazarse hacia la derecha y volver al inicio.

**Validación:** sintaxis y pruebas automatizadas en Linux. Prueba Qt real en
Windows pendiente. No se garantiza compatibilidad absoluta sin dicha prueba.

---

<!-- CAMBIOS_v0.3.7.md -->
## ModGames44 Video Editor v0.3.7 — Pausa en cortes

### Cambios

1. `timeline/playback_boundaries.py`: función pura que calcula el instante de detención exacto para cada segmento cortado.
2. `core/sequence_player.py`: evita rebasar el borde del clip en el reloj y en las actualizaciones de QMediaPlayer. Pausa en el punto exacto incluso con ticks retrasados.
3. `ui/timeline_panel.py`: al cortar con la cuchilla o Ctrl+K, emite el tiempo de corte y coloca allí el cabezal.
4. `ui/main_window.py`: pausa al cortar y sincroniza el monitor con el nuevo corte; agrega `Reproducción → Detener reproducción en los cortes` (activado por defecto y guardado en QSettings).
5. `tests/test_playback_boundaries.py`: nuevos casos de regresión para cortes adyacentes, fuentes recortadas, reproducción continua y ausencia de sobrepaso temporal.

### Pruebas realizadas aquí

- 45 pruebas automatizadas superadas con `python -m unittest discover -s tests -v`.
- Sintaxis comprobada con `python -m compileall -q .`.
- Simulación del motor con temporizador y reproductor sustitutos: pausa exacta al corte y reanudación desde el siguiente segmento.
- **Pendiente**: validación gráfica en Windows con PySide6 y QMediaPlayer/FFmpeg.

### Prueba manual en Windows

1. Importar un video y llevarlo a V1/A1.
2. Con `C`, cortar a los 5 segundos. El cabezal debe saltar a `00:00:05.000` y quedar pausado.
3. Desplazar el cabezal a `00:00:00.000` y pulsar Play: debe detenerse exactamente en `00:00:05.000`.
4. Pulsar Play otra vez: debe continuar desde el segmento derecho.
5. Desactivar `Reproducción → Detener reproducción en los cortes`, volver a 00:00 y reproducir: debe cruzar el corte sin pausa.
6. Comprobar que Arrastrar cabezal, Deshacer/Rehacer, zoom, ondas de audio y audio vinculado siguen operativos.

---

<!-- CAMBIOS_v0.3.6.md -->
## ModGames44 Video Editor v0.3.6 — Cabezal amarillo y búsqueda estable

Basada **directamente en v0.3.5**, conservando iconos, cuchilla, corte,
recorte, ondas L/R y zoom de Timeline.

### Correcciones

1. El cabezal amarillo es ahora **arrastrable con el botón izquierdo** desde
   cualquier altura de la Timeline, incluso sobre clips. Se reconoce al situar
   el cursor a menos de 9 píxeles de la línea.
2. Un **clic en la regla superior**, seguido de arrastre manteniendo pulsado
   el botón, desplaza el cabezal. También se puede hacer clic en el espacio vacío.
3. Dibujado como **capa no interactiva del visor**: ya no se añade/elimina
   un elemento `QGraphicsLineItem` para cada fotograma de reproducción.
4. Durante el movimiento, el indicador y el código de tiempo reaccionan de
   inmediato; la búsqueda costosa en el decodificador se **agrupa con 130 ms
   de espera**. Al soltar, se aplica de inmediato la posición definitiva.
5. Al empezar un arrastre se pausa la reproducción y se evitan búsquedas
   masivas de FFmpeg que podían congelar la interfaz.
6. Corrigida la posición del reloj interno si se busca durante Play y el
   archivo de origen utilizado al alternar entre Proyecto y Timeline.
7. Se respetan los límites 00:00 y duración de la secuencia.

### Cómo probar en Windows 10/11

```powershell
python -m pip install -r requirements.txt
python main.py
```

- Importa un vídeo, arrástralo a V1, y empieza a reproducirlo.
- Pausa y arrastra **la propia línea amarilla** por toda la Timeline.
- Haz clic y arrastra en la **regla superior**; el cabezal debe seguir al mouse.
- Haz clic en un hueco libre de la Timeline y comprueba que no se congela.
- Cambia a herramienta C (cuchilla), corta y vuelve con V.
- Cambia a vista Proyecto, selecciona otro archivo y regresa a Timeline.
- Aumenta el zoom y comprueba que el arrastre sigue alineado con el tiempo.

### Comprobaciones

`python -m unittest discover -s tests -v` y `python -m compileall -q .`

**Limitación:** no es posible ejecutar el reproductor Qt real sobre Windows
ni comprobar la integración GUI con PySide6 en este entorno. Si aparece un
bloqueo todavía, envía el traceback o un video para identificar su origen.

---

<!-- CAMBIOS_v0.3.5.md -->
## ModGames44 Video Editor v0.3.5 — Barra de herramientas y cuchilla

Basada en la v0.3.4. Se conserva la Timeline multipista, sus formas de onda L/R y miniaturas multirresolución.

### Interfaz

Los botones de texto se reemplazan por **iconos**, originales y editables (`assets/icons/*.svg`), con sus archivos PNG para Windows. Al pasar el mouse aparece la explicación y el atajo. El botón de herramienta activa queda resaltado.

| Icono | Herramienta | Uso |
| --- | --- | --- |
| Flecha | **Seleccionar** (V) | Arrastra un clip para moverlo. Arrastra sus bordes para recortarlo. |
| Cuchilla | **Cortar** (C) | El cursor se convierte en cuchilla. Haz clic en cualquier punto interior del clip para partirlo. La herramienta permanece activa. |
| Borde izquierdo | **Recortar inicio** ([) | Arrastra horizontalmente en el clip. |
| Borde derecho | **Recortar final** (]) | Arrastra horizontalmente en el clip. |
| Papelera | **Eliminar** (Supr) | Elimina clips seleccionados y sus compañeros enlazados. |
| Dos flechas | **Cerrar huecos** | Compacta la secuencia de clips. |
| Flecha izquierda / derecha | **Deshacer/Rehacer** | También Ctrl+Z/Ctrl+Y. |
| Cadena rota | **Desvincular** | Permite editar video y audio por separado. |
| Imán | **Snapping** | Alterna el ajuste magnético en movimiento/recorte. |

**Ctrl+K** conserva la acción «Cortar clip seleccionado en la posición del cabezal» para quienes la prefieran. **Esc** regresa a Seleccionar. La cuchilla solo corta al hacer clic *sobre* un clip, no en los espacios libres. Se muestra una línea de previsualización del corte, incluyendo el audio vinculado.

### Detalles de edición

- Corta la pareja video/audio en el mismo tiempo, asignando un vínculo nuevo a los segmentos derechos. Los segmentos izquierdos mantienen su vínculo original.
- El recorte modifica los puntos In/Out del clip, jamás el medio original.
- Se respetan el límite de 00:00, la duración mínima de 1 ms y el final del medio original al alargar un clip.
- Todos los cortes, recortes, eliminaciones, desvinculaciones y cierres de huecos son reversibles con Deshacer.
- La información de la herramienta activa aparece en la Timeline y en la barra de estado.

### Instalación y ejecución

En Windows 10 u 11 de 64 bits:

```powershell
python -m pip install -r requirements.txt
python main.py
```

Si el `.exe` compilado no encuentra los iconos, compila con `python build.py`: ahora empaqueta `assets/icons` y los archivos de `imageio_ffmpeg`.

### Pruebas

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
```

**Ejemplo manual:** carga un video con audio, arrástralo a V1/A1, pulsa C, sitúa el mouse a mitad del clip y haz clic. Deben aparecer dos mitades en ambas pistas; prueba Ctrl+Z, V, y arrastra el borde izquierdo. Pulsa Esc para volver a selección.

#### Limitaciones importantes

- En el entorno de desarrollo no se dispone del runtime `PySide6` ni de Windows; los eventos reales de mouse/cursor y el empaquetado EXE **necesitan prueba en Windows**.
- No se añade aún composición/multiaudio simultáneo ni exportación final. El motor de reproducción sigue siendo preliminar.

---

<!-- CAMBIOS_v0.3.4.md -->
## Cambios 0.3.4

### Cambios de arquitectura

1. `services/waveform.py`: motor PCM estéreo real, extracción por streaming y niveles min/max multirresolución; persistencia `.npz` invalidada por tamaño, fecha y versión.
2. `services/media_visuals.py`: tareas Qt independientes para cuadros de video y onda de audio; hilos de trabajo limitados; caché LRU para fotogramas.
3. `ui/timeline_panel.py`: dibujo basado en el área visible, ondas L/R separadas, miniaturas según tiempo real, regla adaptable, cabeceras ancladas, zoom centrado y pista redimensionable.
4. `timeline/zoom_math.py`: cálculos de geometría desacoplados de PySide6 y testeables.
5. `requirements.txt`: agregado NumPy.

### Errores/limitaciones corregidas

- La onda de audio no se reduce a 1.200 valores mono ni se estira como imagen.
- Un audio estéreo se conserva como dos canales L/R distintos.
- Los picos muy breves no se descartan al reducir la escala gracias a los extremos por intervalos.
- Los videos largos no necesitan repintar todos sus fotogramas fuera de pantalla.
- Se eliminaron definiciones de wheelEvent y FrameTask duplicadas existentes en v0.3.3.
- Los clips mantienen límite izquierdo 00:00; el tiempo no es afectado por el zoom.

### Pruebas realizadas en el entorno de generación

- `python -m compileall -q .`: correcto.
- `python -m unittest discover -s tests -v`: 15 pruebas correctas.
- Audio sintético estéreo L fuerte/R débil: decodificado y comparado correctamente.
- Tres capturas FFmpeg de distintos instantes de MP4 real: válidas y con hashes diferentes.
- MP4 OBS real de 50,93 segundos: se comprobó que **sus muestras PCM son silenciosas** (aunque existe una pista AAC).

### Límite de verificación

No está instalada PySide6 y este entorno no dispone de Windows, así que la GUI, la reproducción en Qt y los eventos mouse de Windows siguen requiriendo pruebas del usuario. No se ha afirmado validación de interfaz no realizada.

---

<!-- README_CAMBIOS_v0.3.3.md -->
## ModGames44 Video Editor v0.3.3 — Timeline

### Cambios
- Rueda del ratón sobre el área de clips: zoom horizontal centrado aproximadamente bajo el cursor.
- Rueda sobre la cabecera V1–V3/A1–A3: altura de pista independiente (42–200 px).
- Límite izquierdo 00:00 al arrastrar clips; movimiento vinculado preservado.
- Fotogramas diferentes solicitados a FFmpeg según el instante de cada miniatura, con caché y trabajos asíncronos limitados.
- Forma de onda PCM más detallada (1200 puntos) y normalización visual limitada para grabaciones de volumen bajo.
- Se mantienen los controles de zoom y edición existentes.

### Pruebas
- Compilación de todos los módulos Python: correcta.
- 7 pruebas unitarias existentes: correctas.
- Interacción gráfica Qt/Windows: pendiente de validación en Windows.

### Notas
- La rueda sobre las pistas realiza zoom vertical; sobre los clips, zoom horizontal.
- Los fotogramas se extraen progresivamente; pueden tardar en aparecer al acercar el zoom.
- La normalización de la forma de onda es visual y NO altera el volumen de audio.
