"""Operaciones ripple conservadoras para clips unidos y pistas independientes."""
from timeline.model import end, OVERLAY_KINDS, map_time_after_gaps


def ripple_remove(clips, selected_ids):
    """Elimina selección/enlaces y desplaza clips posteriores de pistas afectadas.

    Solo desplaza cuando los clips comparten una pista con el segmento eliminado.
    El desplazamiento de varios intervalos disjuntos es acumulativo. Clips que
    comienzan dentro del intervalo eliminado no se desplazan hacia tiempo negativo.
    """
    selected = set(selected_ids)
    links = {c.get('link') for c in clips if c['id'] in selected and c.get('link')}
    deleted = [c for c in clips if c['id'] in selected or (c.get('link') and c['link'] in links)]
    if not deleted:
        return 0
    gaps = {}
    for c in deleted:
        key=(c.get('kind','video'),int(c.get('track',0)))
        gaps.setdefault(key,[]).append((int(c['start_ms']),int(end(c))))
    # Los clips asociados V/A deben permanecer perfectamente sincronizados.
    for key, intervals in gaps.items():
        intervals.sort()
        merged=[]
        for a,b in intervals:
            if merged and a <= merged[-1][1]:
                merged[-1]=(merged[-1][0],max(merged[-1][1],b))
            else:merged.append((a,b))
        gaps[key]=merged
    removed_ids={c['id'] for c in deleted}
    clips[:]=[c for c in clips if c['id'] not in removed_ids]
    # Títulos, subtítulos e imágenes acompañan al video eliminado de la pista
    # más baja; nunca hacen ripple entre ellos (borrar un título no debe
    # desplazar los demás títulos).
    video_tracks=sorted(track for kind,track in gaps if kind=='video')
    reference=gaps[('video',video_tracks[0])] if video_tracks else []
    for c in clips:
        if c.get('kind') in OVERLAY_KINDS:
            if reference:
                c['start_ms']=map_time_after_gaps(int(c['start_ms']),reference)
            continue
        key=(c.get('kind','video'),int(c.get('track',0)))
        original=int(c['start_ms'])
        shift=sum(b-a for a,b in gaps.get(key,()) if b <= original)
        c['start_ms']=max(0,original-shift)
    return len(deleted)
