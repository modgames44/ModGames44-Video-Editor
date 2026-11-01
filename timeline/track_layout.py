"""Orden visual tipo Premiere: V3,V2,V1,A1,A2,A3.

El índice de pista del modelo sigue igual (video 0=V1, audio 0=A1).
Separar coordenadas UI y modelo evita que los cambios rompan los proyectos .mg44.
"""
TRACK_LABELS=('V3','V2','V1','A1','A2','A3')


def row_for_clip(clip):
    track=max(0,min(2,int(clip.get('track',0))))
    return 3+track if clip.get('kind','video') == 'audio' else 2-track


def track_for_row(kind,row,current=0):
    if row is None:
        return max(0,min(2,int(current)))
    row=int(row)
    if kind=='audio':
        return max(0,min(2,row-3)) if row>=3 else max(0,min(2,int(current)))
    return max(0,min(2,2-row)) if row<3 else max(0,min(2,int(current)))
