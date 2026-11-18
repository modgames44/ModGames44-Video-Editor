"""Ajustes de codificación por encoder (sin Qt, sin ejecutar FFmpeg).

NVIDIA NVENC (RTX 20/30/40/50) se configura para máxima calidad por bit:

- Calidad constante (`-rc vbr -cq N -b:v 0`) con la tasa del perfil como
  techo (`-maxrate`): las escenas simples ocupan poco, las de mucha acción
  reciben bits hasta el límite.
- `-preset p5 -tune hq -multipass fullres`: análisis en dos pasadas por
  fotograma a resolución completa.
- `-spatial-aq/-temporal-aq`: más bits en zonas oscuras y detalle en
  movimiento (típico del gameplay), menos en fondos estáticos.
- `-rc-lookahead 32`, B-frames como referencia, GOP de 2 s (lo que pide
  YouTube).

`tuned` elige el nivel (ver NVENC_LEVELS); False es el modo de compatibilidad: NVENC sólo con tasa fija, para
drivers antiguos que rechacen alguna opción. Lo decide la prueba real del
encoder (exporter.hardware) o el reintento automático de la exportación.
"""

NVENC = ('h264_nvenc', 'hevc_nvenc', 'av1_nvenc')

# Calidad objetivo de NVENC (menor = mejor). Las escalas difieren por códec.
NVENC_CQ = {'h264_nvenc': 19, 'hevc_nvenc': 21, 'av1_nvenc': 27}

# Calidad constante para codificadores por software (CPU).
SOFTWARE_CRF = {'libx264': 20, 'libx265': 23, 'libsvtav1': 32, 'libvpx-vp9': 31}

# Encoders capaces de 10 bits y el formato de píxel que esperan.
TEN_BIT_PIX_FMT = {
    'hevc_nvenc': 'p010le', 'av1_nvenc': 'p010le',
    'libx265': 'yuv420p10le', 'libsvtav1': 'yuv420p10le',
    'hevc_amf': 'p010le', 'av1_amf': 'p010le',
    'hevc_qsv': 'p010le', 'av1_qsv': 'p010le',
}


def is_gpu_encoder(encoder):
    return encoder.endswith(('_nvenc', '_amf', '_qsv'))


def _split_rate(bitrate):
    unit = bitrate[-1] if bitrate[-1] in 'Mk' else ''
    number = float(bitrate.rstrip('Mk'))
    return number, unit


def _double(bitrate):
    number, unit = _split_rate(bitrate)
    value = number * 2
    return f'{int(value) if value.is_integer() else value}{unit}'


# Niveles de ajuste de NVENC, del mejor al más compatible. La prueba real
# del encoder elige el primero que funciona en esa GPU y driver.
#  'full'  : todo lo anterior.
#  'safe'  : sin AQ temporal ni B-frames de referencia (no todas las
#            generaciones/drivers los admiten en todos los códecs).
#  False   : sólo tasa fija (modo compatible).
NVENC_LEVELS = ('full', 'safe', False)


def nvenc_args(encoder, profile, tuned='full'):
    if tuned is True:
        tuned = 'full'
    gop = str(max(1, int(profile.fps) * 2))
    if not tuned or profile.bitrate == '0':
        return ['-preset', 'p5', '-b:v', profile.bitrate if profile.bitrate != '0' else '20M', '-g', gop]
    args = ['-preset', 'p5', '-tune', 'hq', '-multipass', 'fullres',
            '-rc', 'vbr', '-cq', str(NVENC_CQ[encoder]), '-b:v', '0',
            '-maxrate', profile.bitrate, '-bufsize', _double(profile.bitrate),
            '-spatial-aq', '1', '-aq-strength', '8', '-rc-lookahead', '32', '-bf', '3']
    if tuned == 'full':
        args += ['-temporal-aq', '1', '-b_ref_mode', 'middle']
    return args + ['-g', gop]


def software_args(encoder, profile):
    if profile.bitrate == '0':
        return []
    crf = SOFTWARE_CRF.get(encoder)
    if crf is None:
        return ['-b:v', profile.bitrate]
    if encoder == 'libvpx-vp9':
        return ['-crf', str(crf), '-b:v', '0', '-row-mt', '1']
    if encoder == 'libsvtav1':
        return ['-crf', str(crf)]
    return ['-crf', str(crf), '-maxrate', profile.bitrate, '-bufsize', _double(profile.bitrate)]


def pixel_format(encoder, profile):
    if encoder == 'prores_ks':
        return 'yuv422p10le'
    if getattr(profile, 'ten_bit', False) and encoder in TEN_BIT_PIX_FMT:
        return TEN_BIT_PIX_FMT[encoder]
    return 'yuv420p'


def video_codec_args(encoder, profile, tuned='full'):
    """Todo lo que va después de `-c:v encoder` (excepto el audio)."""
    args = []
    if encoder in ('libx264', 'libx265'):
        args += ['-preset', 'medium']
    if encoder == 'prores_ks':
        args += ['-profile:v', '3']
    args += ['-pix_fmt', pixel_format(encoder, profile)]
    if encoder == 'hevc_nvenc' and args[-1] == 'p010le':
        args += ['-profile:v', 'main10']
    if encoder in NVENC:
        args += nvenc_args(encoder, profile, tuned)
    elif is_gpu_encoder(encoder):
        args += ['-b:v', profile.bitrate] if profile.bitrate != '0' else []
    else:
        args += software_args(encoder, profile)
    return args
