"""Transiciones por solapamiento: no destructivas y compatibles con fade alfa."""
from timeline.model import end


def crossfade_adjacent(clips, first_id, requested_ms=600, style='dissolve'):
    """Acerca el clip siguiente y aplica fades al solape, también al audio enlazado.

    No alarga los archivos: usa únicamente material ya presente en ambos clips.
    Evita alterar otros clips de la misma pista que solapen la zona de transición.
    """
    if style not in ('dissolve','wipe','slide'):
        raise ValueError('Transición desconocida')
    first=next((c for c in clips if c['id']==first_id),None)
    if first is None or first.get('kind')!='video':return False
    later=sorted((c for c in clips if c['id'] != first_id and c.get('kind')=='video'
                  and c.get('track',0)==first.get('track',0)
                  and c['start_ms']>=first['start_ms']),key=lambda c:c['start_ms'])
    if not later:return False
    second=later[0]
    max_len=min(int(first['duration_ms'])//2,int(second['duration_ms'])//2)
    length=min(max(0,int(requested_ms)),max_len)
    if length<100:return False
    desired=end(first)-length
    if desired<0:return False
    old_second_start=second['start_ms']
    delta=desired-old_second_start
    # Desplazar también la cola de la misma pista para no dejar un hueco nuevo.
    subsequent=[c for c in clips if c.get('kind')=='video'
                and c.get('track',0)==second.get('track',0)
                and c['id'] not in (first['id'],second['id'])
                and c['start_ms']>=old_second_start]
    for clip in subsequent:
        clip['start_ms']=max(0,clip['start_ms']+delta)
        if clip.get('link'):
            for audio in clips:
                if audio.get('kind')=='audio' and audio.get('link')==clip['link']:
                    audio['start_ms']=clip['start_ms']
    second['start_ms']=desired
    # Conservar opacidad total de la capa inferior durante el solape.
    # El segundo clip aparece gradualmente: disolución real sin oscurecer.
    first['fade_out_ms']=0
    second['fade_in_ms']=length if style=='dissolve' else 0
    second['transition_in']=dict(kind=style,duration_ms=length)
    first['fade_in_ms']=min(first.get('fade_in_ms',0),first['duration_ms']-length)
    second['fade_out_ms']=min(second.get('fade_out_ms',0),second['duration_ms']-length)
    for video,fade_field in ((first,'fade_out_ms'),(second,'fade_in_ms')):
        if video.get('link'):
            for c in clips:
                if c.get('kind')=='audio' and c.get('link')==video['link']:
                    c['start_ms']=video['start_ms']
                    c[fade_field]=length
    return True
