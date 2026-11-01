"""Modelo de secuencia no destructiva. Tiempo en milisegundos."""
import uuid


def make_clip(path, duration_ms, start_ms=0, track=0, in_ms=0, kind='video', link=None):
    return dict(id=uuid.uuid4().hex, path=str(path), start_ms=max(0,int(start_ms)),
                in_ms=max(0,int(in_ms)), duration_ms=max(1,int(duration_ms)),
                track=int(track), kind=kind, link=link,
                fade_in_ms=0, fade_out_ms=0)


def end(clip):
    return clip['start_ms'] + clip['duration_ms']


def source_position(clip, timeline_ms):
    return clip['in_ms'] + (timeline_ms - clip['start_ms']) * float(clip.get('speed', 1.0))


def active(clips, time_ms, kind='video'):
    matches = [c for c in clips if c.get('kind','video') == kind and c['start_ms'] <= time_ms < end(c)]
    return max(matches, key=lambda c: c.get('track', 0), default=None)


def split(clips, clip_id, time_ms):
    for index, c in enumerate(clips):
        if c['id'] == clip_id and c['start_ms'] < time_ms < end(c):
            left = dict(c)
            right = dict(c, id=uuid.uuid4().hex, start_ms=time_ms,
                         in_ms=c['in_ms'] + (time_ms - c['start_ms']) * float(c.get('speed', 1.0)),
                         duration_ms=end(c) - time_ms)
            left['duration_ms'] = time_ms - c['start_ms']
            from timeline.fades import split_fade
            split_fade(left, right, c)
            clips[index:index+1] = [left, right]
            return right['id']
    return None


def close_gap(clips, track, kind):
    items = sorted((c for c in clips if c['track']==track and c.get('kind','video')==kind), key=lambda c:c['start_ms'])
    cursor = 0
    for c in items:
        c['start_ms'] = cursor
        cursor += c['duration_ms']
