"""Exportación de subtítulos SRT desde clips de la Timeline."""
from pathlib import Path


def _stamp(ms):
    ms=max(0,int(ms));h,rest=divmod(ms,3600000);m,rest=divmod(rest,60000);s,millis=divmod(rest,1000)
    return f'{h:02}:{m:02}:{s:02},{millis:03}'


def srt_text(clips):
    items=sorted((c for c in clips if c.get('kind')=='subtitle' and c.get('text','').strip()),
                 key=lambda c:(c['start_ms'],c['id']))
    return '\n\n'.join(f"{i}\n{_stamp(c['start_ms'])} --> {_stamp(c['start_ms']+c['duration_ms'])}\n{c['text'].strip()}"
                      for i,c in enumerate(items,1))+'\n' if items else ''


def export_srt(path,clips):
    text=srt_text(clips)
    if not text:raise ValueError('No hay subtítulos en la Timeline')
    Path(path).write_text(text,encoding='utf-8-sig')
