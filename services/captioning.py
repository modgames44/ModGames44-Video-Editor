"""Transcripción local opcional (faster-whisper). No utiliza servicios de pago."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Caption:
    start_ms: int
    end_ms: int
    text: str


def normalize_segments(segments, duration_ms=None):
    result=[]
    for seg in segments:
        start=max(0,int(round(float(seg.start)*1000)))
        stop=max(start+100,int(round(float(seg.end)*1000)))
        if duration_ms is not None:
            stop=min(stop,int(duration_ms))
        text=' '.join(str(seg.text).split())
        if text and stop>start:result.append(Caption(start,stop,text))
    return result


def transcribe_file(path, *, language='es', model='small', device='cpu'):
    """Se ejecuta únicamente en hilo de trabajo; import tardío por ser opcional."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError('Instala la dependencia opcional: python -m pip install faster-whisper') from exc
    engine=WhisperModel(model,device=device,compute_type='int8' if device=='cpu' else 'float16')
    segments,_=engine.transcribe(str(path),language=None if language=='auto' else language,
                                 vad_filter=True,beam_size=3)
    return normalize_segments(segments)
