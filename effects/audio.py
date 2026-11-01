"""Audio no destructivo por clip. Filtros FFmpeg explícitos y acotados.

Los perfiles son diseños propios de ModGames44; no replican algoritmos Adobe.
"""
from math import isfinite

VOICE_PRESETS = ('none', 'podcast', 'high', 'low')


def default_audio_effects():
    return {'volume_db': 0.0, 'noise': 0.0, 'voice': 'none', 'normalize': False}


def validated_audio_effects(raw=None):
    data = default_audio_effects()
    if isinstance(raw, dict):
        data.update({key: raw[key] for key in data if key in raw})
    for key, lo, hi in [('volume_db', -36., 24.), ('noise', 0., 1.)]:
        try:
            value = float(data[key])
        except (ValueError, TypeError) as exc:
            raise ValueError(f'Audio: {key} no válido') from exc
        if not isfinite(value):
            raise ValueError(f'Audio: {key} debe ser finito')
        data[key] = round(max(lo, min(hi, value)), 3)
    if data['voice'] not in VOICE_PRESETS:
        raise ValueError('Perfil de voz no reconocido')
    data['normalize'] = bool(data['normalize'])
    return data


def audio_filter_chain(raw, speed=1.0):
    """Cadena apta para -filter_complex (sin etiquetas).

    Atenuación de ruido: afftdn. La voz se realza mediante EQ y compresión.
    La limitación final de picos va sobre la mezcla completa del proyecto.
    """
    fx = validated_audio_effects(raw)
    speed = float(speed)
    if not 0.25 <= speed <= 4.0 or not isfinite(speed):
        raise ValueError('Velocidad de audio fuera de rango')
    chain = []
    remaining = speed
    while remaining > 2:
        chain.append('atempo=2.0')
        remaining /= 2
    while remaining < 0.5:
        chain.append('atempo=0.5')
        remaining /= 0.5
    if abs(remaining - 1.) > 0.00001:
        value=f'{remaining:.6f}'.rstrip('0').rstrip('.')
        if '.' not in value:value += '.0'
        chain.append(f'atempo={value}')
    if fx['noise'] > 0:
        # afftdn.nr se expresa en dB, no como proporción 0..1.
        # 3.0..20.0 dB: control conservador, 100% no equivale a eliminar voz.
        nr = 3.0 + fx['noise'] * 17.0
        chain.append(f'afftdn=nr={nr:.2f}:nf=-50:tn=1')
    preset = fx['voice']
    if preset != 'none':
        # Perfiles PROPIOS basados en EQ convencional, no ajustes secretos de Adobe.
        if preset == 'podcast':
            chain += ['highpass=f=75',
                      'equalizer=f=250:t=q:w=1:g=-2',
                      'equalizer=f=3200:t=q:w=1:g=3',
                      'lowpass=f=15000',
                      'acompressor=threshold=0.18:ratio=3:attack=12:release=180:makeup=1.4']
        elif preset == 'high':
            # Voz aguda: recuperar algo de cuerpo y contener frecuencias ásperas.
            chain += ['highpass=f=90',
                      'equalizer=f=180:t=q:w=1:g=2',
                      'equalizer=f=5500:t=q:w=1:g=-2',
                      'lowpass=f=15000',
                      'acompressor=threshold=0.22:ratio=2.5:attack=15:release=180:makeup=1.4']
        else:
            # Voz grave: evitar excesos en bajos medios y mejorar la presencia.
            chain += ['highpass=f=65',
                      'equalizer=f=220:t=q:w=1:g=-3',
                      'equalizer=f=3000:t=q:w=1:g=3',
                      'lowpass=f=15000',
                      'acompressor=threshold=0.22:ratio=2.5:attack=14:release=190:makeup=1.4']
    if fx['normalize']:
        chain.append('loudnorm=I=-16:TP=-1.5:LRA=11')
    if fx['volume_db']:
        chain.append(f'volume={fx["volume_db"]:.3f}dB')
    return chain
