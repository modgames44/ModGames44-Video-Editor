<p align="center">
  <img src="assets/icons/modgames44_logo.png" alt="Logo de ModGames44" width="150">
</p>

<h1 align="center">ModGames44 Video Editor</h1>

<p align="center">
  <strong>Un editor de video para Windows, modular, en español y con una interfaz pensada para editar sin complicaciones.</strong>
</p>

<p align="center">
  <strong>Versión de desarrollo: v0.4.12b</strong> · Windows 10/11 (64 bits) · Python · PySide6 · FFmpeg · Nuitka
</p>

> [!IMPORTANT]
> **Proyecto en desarrollo (beta técnica).** La aplicación incorpora edición multipista, efectos, previsualización y exportación, pero todavía presenta limitaciones y necesita pruebas de integración en equipos Windows. No se recomienda utilizarla como único sistema para proyectos de producción sin verificar previamente el resultado exportado.

## Contenido

- [¿Qué es ModGames44 Video Editor?](#qué-es-modgames44-video-editor)
- [Características principales](#características-principales)
- [Espacios de trabajo](#espacios-de-trabajo)
- [Edición en la Timeline](#edición-en-la-timeline)
- [Efectos de video](#efectos-de-video)
- [Audio y tratamiento de voz](#audio-y-tratamiento-de-voz)
- [Asistente IA opcional](#asistente-ia-opcional)
- [Exportación y aceleración por hardware](#exportación-y-aceleración-por-hardware)
- [Requisitos](#requisitos)
- [Instalación y ejecución](#instalación-y-ejecución)
- [Compilar un único EXE con Nuitka](#compilar-un-único-exe-con-nuitka)
- [Guía rápida de uso](#guía-rápida-de-uso)
- [Atajos de teclado](#atajos-de-teclado)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Pruebas y diagnóstico](#pruebas-y-diagnóstico)
- [Limitaciones conocidas](#limitaciones-conocidas)
- [Preguntas frecuentes](#preguntas-frecuentes)
- [Licencia y créditos](#licencia-y-créditos)

## ¿Qué es ModGames44 Video Editor?

**ModGames44 Video Editor** es un proyecto de edición de video no lineal (NLE) desarrollado en **Python y PySide6**, con procesamiento multimedia mediante **FFmpeg**. Su objetivo es ofrecer las herramientas habituales de un editor avanzado —clips, pistas, cortes, audio, efectos y exportación— mediante una interfaz más directa.

El trabajo es **no destructivo**: las operaciones de edición se registran en el proyecto y no modifican los archivos originales. Las secuencias pueden guardarse en archivos **`.mg44`** para continuar trabajando posteriormente.

La aplicación está orientada a **Windows 10 y Windows 11 de 64 bits** y utiliza módulos `.py` independientes para facilitar ampliaciones, correcciones y mantenimiento.

## Características principales

| Área | Funcionalidades disponibles |
| --- | --- |
| Biblioteca de medios | Importación de videos, audio e imágenes; búsqueda; vista de miniaturas o lista; eliminación del proyecto sin borrar los originales |
| Monitor de programa | Reproducción controlada por el usuario, pausa, avance/retroceso, búsqueda temporal y visualización de efectos |
| Timeline | Varias pistas V1–V3 y A1–A3, movimiento libre de clips, zoom, desplazamiento, miniaturas y ondas estéreo |
| Herramientas | Selección, cuchilla, recorte de bordes, eliminar, cerrar huecos, vincular/desvincular, imán y Deshacer/Rehacer |
| Audio | Ganancia, reducción de ruido, perfiles de voz, normalización, ondas procesadas y medidor estéreo |
| Video | Velocidad, zoom, color, espejo, desenfoque y mosaico mediante región rectangular |
| Edición por IA | Órdenes locales, propuesta de eliminación de silencios y planificación opcional mediante la API de OpenAI |
| Exportación | MP4, MOV y WebM; selección de codificador CPU/GPU cuando está disponible; progreso y cancelación |
| Personalización | Tema gaming oscuro y dos espacios de trabajo configurables |

## Espacios de trabajo

La interfaz utiliza una paleta de **grafito oscuro, cian y violeta**, con paneles redimensionables y una disposición adaptable al tamaño de la ventana.

**Cyber Studio** es el espacio predeterminado. Presenta los efectos arriba a la izquierda, el Proyecto debajo, el Monitor de programa en el centro, Propiedades a la derecha y la Timeline en la parte inferior.

**Cyber Neon** coloca el panel de Proyecto en la zona izquierda y prioriza el acceso rápido a los efectos en el lateral derecho.

Puedes cambiar entre ambos desde **Ver → Espacio de trabajo** o con `Ctrl+Alt+1` (Cyber Neon) y `Ctrl+Alt+2` (Cyber Studio). La distribución de cada espacio se conserva independientemente y puede restablecerse desde el menú **Ver**.

> La adaptación a distintas resoluciones es parte del diseño, pero las combinaciones de DPI, escalado de Windows y tamaños pequeños deben comprobarse en cada equipo.

## Edición en la Timeline

### Organización de pistas

- **V1, V2 y V3:** pistas de video, organizadas por capas.
- **A1, A2 y A3:** pistas de audio con representación de los canales izquierdo y derecho.
- Al insertar un video con audio, el editor puede crear clips de video y audio vinculados para mantener su sincronía horizontal.
- Es posible mover el audio a otra pista, trabajar con espacios vacíos e insertar clips adicionales después del último video.

### Controles de edición

- **Cuchilla (`C`):** coloca el cursor de corte sobre un clip y haz clic para dividirlo. El corte de audio/video vinculado se mantiene sincronizado.
- **Selección (`V`):** selecciona y mueve clips. Con `Esc` se vuelve a selección.
- **Recorte (`[` y `]`):** modifica los puntos de entrada y salida del clip.
- **Snapping:** alineación magnética para situar clips en límites y puntos próximos.
- **Deshacer/Rehacer:** historial de operaciones con `Ctrl+Z` y `Ctrl+Y`.
- **Fade In / Fade Out:** controles en las esquinas superiores del clip para aplicar desvanecimiento de opacidad al video o de volumen al audio; pueden ajustarse por separado.

### Zoom, fotogramas y ondas

El zoom horizontal permite acercarse o alejarse de los clips; el zoom vertical modifica la altura de las pistas. Las miniaturas muestran fotogramas extraídos de diferentes posiciones de la fuente, mientras que las ondas se dibujan con distintos niveles de detalle según la escala.

El cabezal se puede desplazar con el mouse y los controles **Inicio/Final** buscan el comienzo o el final de la secuencia. Desde **Ver → Copiar diagnóstico de Timeline** (`Ctrl+Alt+D`) se pueden obtener parámetros para investigar problemas de navegación.

**Reproducción y cortes:** existe una opción **Reproducción → Detener reproducción en los cortes**. Cuando está activada, el cabezal se detiene al alcanzar el final de un segmento; puedes desactivarla para continuar al siguiente.

## Efectos de video

Los efectos se aplican al **clip seleccionado**, sin modificar la fuente original.

| Efecto | Descripción |
| --- | --- |
| Velocidad | Cámara lenta y rápida, aproximadamente de `0,25×` a `4×` |
| Zoom | Ajuste de escala y centro de la imagen |
| Desenfoque | Censura mediante una máscara rectangular ajustable |
| Mosaico | Pixelación de una región seleccionada |
| Color | Brillo, contraste, saturación y blanco y negro |
| Espejo | Inversión horizontal |
| Fundidos | Fade In y Fade Out de opacidad en los bordes de clips |

**Censura por región:** activa el desenfoque o mosaico, mueve el recuadro en el Monitor con el mouse y cambia sus dimensiones desde las esquinas. También puedes **quitar el efecto**, eliminar su máscara y recuperar la edición anterior mediante `Ctrl+Z`.

La previsualización aplica efectos implementados mientras se reproduce. **Los fotogramas clave de animación de máscaras y zoom no se exportan completamente** en esta versión; el exportador debe mostrar una advertencia antes de continuar.

## Audio y tratamiento de voz

El editor permite ajustar y comprobar el sonido **antes de exportar**, mediante procesamiento de FFmpeg en fragmentos temporales de previsualización.

### Controles disponibles

- **Ganancia:** de `−36 dB` a `+24 dB`.
- **Reducción de ruido:** filtrado espectral mediante `afftdn`, con intensidad ajustable.
- **Normalización:** objetivo aproximado de `−16 LUFS` mediante `loudnorm`.
- **Tres perfiles de voz:** Podcast, Equilibrada tono alto y Equilibrada tono bajo.
- **Onda FX:** alterna entre la onda original y la representación del audio procesado.
- **Audio Meter:** medidor estéreo con nivel del audio procesado en la reproducción desde la secuencia.
- **Fade In/Out:** fundidos de volumen independientes de los fundidos de video.

### Perfiles de voz ModGames44

| Perfil | Ajustes de referencia |
| --- | --- |
| **Voz Podcast** | Pasa-altos de 75 Hz, −2 dB a 250 Hz, +3 dB a 3,2 kHz, compresión aproximada 3:1 |
| **Voz equilibrada · tono alto** | Pasa-altos de 90 Hz, +2 dB a 180 Hz, −2 dB a 5,5 kHz, compresión aproximada 2,5:1 |
| **Voz equilibrada · tono bajo** | Pasa-altos de 65 Hz, −3 dB a 220 Hz, +3 dB a 3 kHz, compresión aproximada 2,5:1 |

Estos filtros son **configuraciones propias de ModGames44 basadas en FFmpeg**. No son los algoritmos ni las curvas oficiales de Adobe Premiere. Los resultados dependen de la grabación: una reducción de ruido excesiva puede introducir artefactos y aumentar demasiado la ganancia puede provocar limitación de picos.

> **Previsualización:** el audio procesado se prepara por tramos de alrededor de 30 segundos. El primer Play puede tardar y pueden producirse pausas al cambiar de tramo. La visualización de Onda FX también puede demorarse mientras se analiza el archivo.

## Asistente IA opcional

**ModGames44 AI Assistant** ofrece dos modalidades:

**Modo local, sin API:** interpreta órdenes sencillas sobre la Timeline, por ejemplo:

```text
corta en 00:05
elimina desde 00:05 hasta 00:10
mueve el clip a 00:20
cierra huecos
ve a 00:15
```

También puede **detectar silencios** con FFmpeg y proponer tramos que eliminar. Antes de efectuar las operaciones muestra un plan que el usuario debe revisar y confirmar; los cambios se pueden deshacer.

**Modo con API de OpenAI:** permite interpretar instrucciones de edición más flexibles dentro de un conjunto de operaciones admitidas. Es opcional y requiere conexión y una clave de API propia.

```powershell
python -m pip install -r requirements-ia.txt
$env:OPENAI_API_KEY = 'TU_CLAVE_DE_API'
python main.py
```

Abre el panel con `Ctrl+Shift+A` y activa **Usar API de OpenAI**. La facturación de la API es **independiente de las suscripciones a ChatGPT**. No publiques tu clave, ni la subas al repositorio.

El asistente no envía los archivos completos de video/audio en el flujo actual: utiliza la instrucción y metadatos de los clips para proponer acciones. **No realiza por sí solo una edición narrativa completa ni un análisis semántico de todas las escenas.**

## Exportación y aceleración por hardware

Abre **Archivo → Exportar video**, pulsa el botón superior **Exportar** o utiliza `Ctrl+M`.

### Perfiles de exportación

| Perfil | Formato | Video |
| --- | --- | --- |
| YouTube 1080p 30 | MP4 | H.264, 1920 × 1080, 30 FPS |
| YouTube 1080p 60 | MP4 | H.264, 1920 × 1080, 60 FPS |
| YouTube 1440p 60 | MP4 | H.264, 2560 × 1440, 60 FPS |
| YouTube 4K 60 | MP4 | H.264, 3840 × 2160, 60 FPS |
| MP4 H.265 1080p | MP4 | HEVC, 1920 × 1080, 30 FPS |
| MP4 AV1 1080p | MP4 | AV1, 1920 × 1080, 30 FPS |
| MOV ProRes 422 | MOV | ProRes, 1920 × 1080, 30 FPS |
| WebM VP9 | WebM | VP9, 1920 × 1080, 30 FPS |

### Detección de codificadores

| Hardware detectado | Codificador posible (si FFmpeg y el driver lo permiten) |
| --- | --- |
| NVIDIA | NVENC |
| AMD | AMF |
| Intel | Quick Sync Video (QSV) |
| Solo CPU / alternativa | `libx264`, `libx265`, `libsvtav1`, `prores_ks`, `libvpx-vp9` |

El programa **detecta la GPU, enumera codificadores y realiza pruebas de disponibilidad**. No basta con tener una tarjeta NVIDIA/AMD/Intel: es necesario que su encoder sea compatible y que FFmpeg lo incluya. En modo automático se intenta preferir la GPU compatible y, cuando corresponde, usar CPU como alternativa.

El exportador admite clips superpuestos, huecos, mezcla de audio y varios efectos estáticos. Incluye progreso, cancelación y escritura a un **archivo temporal** que solo sustituye el destino cuando termina correctamente.

**Advertencia:** la previsualización de capas de video y la exportación no tienen aún una equivalencia funcional completa. Revisa siempre el resultado final, especialmente si utilizas superposiciones, máscaras, keyframes o efectos avanzados.

## Requisitos

- **Sistema operativo:** Windows 10 o Windows 11 de 64 bits.
- **Python:** CPython de 64 bits; el proyecto se ha trabajado con Python 3.14.
- **Dependencias Python:** PySide6 6.8+, `imageio-ffmpeg`, NumPy, Pillow, Nuitka y herramientas de compilación indicadas en `requirements.txt`.
- **Compilación del EXE:** Nuitka y un compilador C compatible con la versión de Python instalada.
- **Aceleración de video:** opcional; depende de la GPU, sus controladores y los codificadores FFmpeg disponibles.
- **Almacenamiento:** espacio para medios, cachés, audio de previsualización y archivos exportados.

> El rendimiento con 4K, proyectos largos o varios efectos depende de la CPU, GPU, RAM y del codec de los archivos. No hay todavía un mínimo de hardware validado mediante benchmarks.

## Instalación y ejecución

1. Descarga o clona este repositorio.
2. Abre **PowerShell** dentro de la carpeta que contiene `main.py`.
3. Crea un entorno virtual (recomendado):

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Instala las dependencias:

   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

5. Ejecuta el editor:

   ```powershell
   python main.py
   ```

La integración de OpenAI es opcional: utiliza `requirements-ia.txt` únicamente si deseas activar ese modo.

## Compilar un único EXE con Nuitka

El proyecto contiene un `build.py` que configura **Nuitka Onefile** para Windows, incorpora el logo y el icono, los recursos de `assets/`, los componentes de PySide6 y el FFmpeg distribuido mediante `imageio-ffmpeg`.

En PowerShell, desde la raíz del proyecto:

```powershell
python -m pip install -r requirements.txt
python build.py --dry-run
python build.py
```

Si deseas incluir el cliente de OpenAI en el ejecutable, instala antes sus dependencias opcionales:

```powershell
python -m pip install -r requirements-ia.txt
python build.py
```

**Ruta de salida prevista:**

```text
dist/
└── ModGames44VideoEditor.exe
```

Al finalizar, `build.py` ejecuta una **autocomprobación** que busca los recursos empaquetados, prueba FFmpeg y comprueba la creación de objetos de Qt Multimedia. No sustituye una prueba manual de importación, reproducción y exportación.

> [!NOTE]
> **Onefile no significa ejecutar sin extracción temporal.** Nuitka empaqueta las dependencias en un solo EXE distribuible, pero las extrae a una ubicación temporal durante el arranque. Los proyectos, cachés, videos importados y exportaciones permanecen fuera del ejecutable.

**Estado de la compilación:** el script y el archivo `nuitka-package.config.yml` fueron ajustados para resolver el error de `executable` de Nuitka 4.3.1. La generación final y la ejecución del EXE **deben validarse en Windows**. El repositorio no debe presentar el binario como verificado hasta superar esas pruebas.

## Guía rápida de uso

1. Inicia el programa y selecciona **Cyber Studio**.
2. Pulsa **Importar** en el panel Proyecto y selecciona los archivos.
3. Inserta el medio con doble clic, desde su menú contextual o arrastrándolo a una pista.
4. Selecciona **V** para mover clips o **C** para dividirlos.
5. Ajusta zoom, recortes, fades y efectos en el clip seleccionado.
6. Utiliza **Play** para revisar imagen y audio procesados.
7. Guarda tu trabajo como proyecto `.mg44`.
8. Pulsa **Exportar**, elige perfil, codificador y destino, y revisa el archivo generado.

**Nota:** la reproducción no comienza automáticamente al importar o seleccionar un video; se inicia mediante los controles del usuario.

## Atajos de teclado

| Atajo | Acción |
| --- | --- |
| `Ctrl+N` | Nuevo proyecto |
| `Ctrl+O` | Abrir proyecto |
| `Ctrl+I` | Importar archivos |
| `Ctrl+S` | Guardar |
| `Ctrl+Shift+S` | Guardar como |
| `Ctrl+M` | Exportar video |
| `Ctrl+Enter` | Insertar selección de Proyecto en la Timeline |
| `Espacio` | Reproducir/Pausar |
| `V` | Selección |
| `C` | Cuchilla |
| `[` / `]` | Recortar inicio/final |
| `Ctrl+K` | Cortar en el cabezal |
| `Supr` | Eliminar clip |
| `Ctrl+Z` / `Ctrl+Y` | Deshacer/Rehacer |
| `Ctrl+Shift+A` | Abrir asistente IA |
| `Ctrl+Alt+1` / `Ctrl+Alt+2` | Cyber Neon / Cyber Studio |
| `Ctrl+Alt+D` | Copiar diagnóstico de Timeline |

## Estructura del proyecto

```text
ModGames44_Video_Editor/
├── main.py                       # Entrada y comprobación de paquete
├── build.py                      # Compilación Nuitka onefile
├── nuitka-package.config.yml     # Inclusión del FFmpeg de Windows
├── requirements.txt
├── requirements-ia.txt
├── assets/
│   ├── icons/                    # Logo, icono .ico e iconos de herramientas
│   └── styles/                   # Tema Cyber
├── ai/                           # Órdenes, planificación y silencios
├── core/                         # Proyectos y reproducción
├── effects/                      # Procesamiento de video y audio
├── exporter/                     # Render, formatos y selección CPU/GPU
├── services/                     # Metadatos, miniaturas y ondas
├── timeline/                     # Modelo, fades, zoom y operaciones
├── ui/                           # Paneles PySide6 y espacios de trabajo
├── tests/                        # Pruebas automatizadas
└── CAMBIOS_v*.md                 # Historial técnico de versiones
```

La separación entre los modelos, el procesamiento multimedia y la interfaz permite cambiar una función sin tener que rehacer todo el editor.

## Pruebas y diagnóstico

Para ejecutar las pruebas automatizadas:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
```

Para comprobar la configuración de compilación antes del proceso completo:

```powershell
python build.py --dry-run
```

Si el EXE ya está compilado, puedes invocar su autocomprobación:

```powershell
.\dist\ModGames44VideoEditor.exe --package-self-test
```

Para informar un fallo de Timeline, indica la versión exacta, Windows, Python/PySide6 si ejecutas el código fuente, pasos para reproducirlo y registro del error. También puedes usar **Ver → Copiar diagnóstico de Timeline** y adjuntar el resultado.

**Nota:** superar pruebas unitarias no equivale a verificar todas las interacciones con mouse, aceleración GPU, audio en tiempo real o un ejecutable final en Windows.

## Limitaciones conocidas

- El proyecto está en desarrollo: pueden aparecer fallos en navegación de Timeline, arrastre o escalado de interfaz que requieran pruebas específicas en Windows.
- El audio procesado se prepara por fragmentos; pueden existir demoras o interrupciones en la escucha previa.
- La previsualización visual de varias capas superpuestas todavía no reproduce todas las composiciones posibles.
- Las animaciones de máscara y zoom mediante keyframes no están completamente implementadas en la exportación.
- No se incluye seguimiento automático de objetos para censura.
- Las transiciones avanzadas, estabilización y otros efectos listados como futuras funciones no deben considerarse completos.
- La disponibilidad de NVENC, AMF y QSV depende de la instalación de FFmpeg y los controladores, y no está garantizada.
- La compatibilidad y el rendimiento con todos los formatos, resoluciones y proyectos largos no han sido exhaustivamente validados.

## Preguntas frecuentes

**¿Se modifican los videos originales?**  
No. Los cortes, fades, filtros y cambios de posición se guardan como decisiones de edición; la exportación crea un archivo nuevo.

**¿Necesito una GPU NVIDIA?**  
No. El exportador puede usar codificadores de CPU si están disponibles. La aceleración es opcional.

**¿Necesito ChatGPT o una cuenta OpenAI?**  
No. El editor y las órdenes locales del asistente pueden utilizarse sin la API. El modo en línea es opcional.

**¿Puedo distribuir un solo `.exe`?**  
Ese es el objetivo de `build.py` mediante Nuitka Onefile. Debe comprobarse que el ejecutable final funcione correctamente en una máquina Windows limpia.

**¿El programa tiene todas las herramientas de Adobe Premiere?**  
No. Su objetivo es simplificar tareas de edición frecuentes; no pretende ser una réplica completa ni incluye todas las funciones profesionales de Premiere.

## Licencia y créditos

**Desarrollado bajo el nombre ModGames44.** Proyecto de código Python con interfaces PySide6 y procesamiento multimedia mediante FFmpeg.

Dependencias principales y documentación:

- [Python](https://www.python.org/)
- [Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/)
- [FFmpeg](https://ffmpeg.org/)
- [Nuitka](https://nuitka.net/)
- [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg)
- [OpenAI API](https://platform.openai.com/docs/overview) — integración opcional

> **Licencia del repositorio:** todavía no se ha definido una licencia propia en este README. Antes de publicar o aceptar contribuciones, añade un archivo `LICENSE` con los términos que quieras aplicar al código y revisa las licencias de las dependencias y de los binarios redistribuidos (especialmente FFmpeg y Qt/PySide6). No se debe asumir una licencia open source únicamente porque el código esté disponible en GitHub.

---

<p align="center"><strong>ModGames44 Video Editor</strong><br>Edición sencilla, arquitectura modular y control total de tus proyectos.</p>
