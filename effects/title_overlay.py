"""Títulos, subtítulos y keyframes simples con render PNG de fondo transparente.

El PNG se crea en caché; nunca se modifica el archivo fuente del usuario.
"""
import hashlib
import json
import os
import re
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

VALID_PRESETS=('estatico','aparecer','subir','deslizar')

def title_clip(text,start_ms,duration_ms=3000,*,subtitle=False):
    import uuid
    return dict(id=uuid.uuid4().hex,kind='subtitle' if subtitle else 'title',path='',
                start_ms=max(0,int(start_ms)),in_ms=0,duration_ms=max(100,int(duration_ms)),
                track=2,link=None,text=str(text)[:800],title_style=dict(
                    size=58 if not subtitle else 44,color='#ffffff',
                    position='bottom' if subtitle else 'center',
                    animation='aparecer' if subtitle else 'subir',bold=True),
                transform_keys=[],fade_in_ms=0,fade_out_ms=0)


def default_style(clip):
    style=dict(size=58,color='#ffffff',position='center',animation='estatico',bold=True,font_family='Arial')
    style.update(clip.get('title_style') or {})
    style['animation']=style['animation'] if style['animation'] in VALID_PRESETS else 'estatico'
    style['size']=max(12,min(180,int(style['size'])))
    return style


def interpolation(keys,time_ms,field,default):
    seq=sorted((int(k.get('time_ms',0)),float(k.get(field,default)))
               for k in keys if field in k)
    if not seq:return float(default)
    if time_ms <= seq[0][0]:return seq[0][1]
    for (a,x),(b,y) in zip(seq,seq[1:]):
        if time_ms <= b:
            return y if b==a else x+(y-x)*(time_ms-a)/(b-a)
    return seq[-1][1]


def transform_at(clip,timeline_ms):
    local=max(0,float(timeline_ms)-float(clip['start_ms']))
    keys=clip.get('transform_keys') or []
    sty=default_style(clip)
    y_default=.87 if sty['position']=='bottom' else (.12 if sty['position']=='top' else .5)
    return {name: interpolation(keys,local,name,default) for name,default in
            [('x',0.5),('y',y_default),('scale',1),('rotation',0),('opacity',1)]}


def _font(size,bold,family='Arial'):
    """Resuelve la fuente seleccionada usando el registro de Windows y rutas comunes."""
    wanted = re.sub(r'[^a-z0-9]', '', str(family).casefold())
    paths = []
    try:
        import winreg
        fonts_dir = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
        registry = r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts'
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, registry) as key:
                    for i in range(winreg.QueryInfoKey(key)[1]):
                        name, value, _ = winreg.EnumValue(key, i)
                        normalized = re.sub(r'[^a-z0-9]', '', name.casefold())
                        if wanted and (wanted in normalized or normalized.startswith(wanted)):
                            path = Path(str(value))
                            if not path.is_absolute(): path = fonts_dir / path
                            rank = int(bool(bold) != ('bold' in name.casefold()))
                            paths.append((rank, str(path)))
            except OSError: pass
    except ImportError: pass
    defaults = ([r'C:\Windows\Fonts\arialbd.ttf','DejaVuSans-Bold.ttf'] if bold else
                [r'C:\Windows\Fonts\arial.ttf','DejaVuSans.ttf'])
    for name in [p for _,p in sorted(paths)] + [family] + defaults:
        try:return ImageFont.truetype(name,size)
        except (OSError, ValueError):pass
    return ImageFont.load_default()


def render_title_png(clip,width=960,height=540,*,cache_root=None):
    """Retorna ruta PNG transparente reproducible y dimensiones reales."""
    style=default_style(clip)
    fingerprint=hashlib.sha256(json.dumps([clip.get('text',''),style,width,height],
                                  sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:32]
    root=Path(cache_root) if cache_root else Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.cache')/'ModGames44'/'VideoEditor'/'titles'
    target=root/(fingerprint+'.png')
    if target.is_file():
        with Image.open(target) as im:return target,im.size
    font=_font(max(10,int(style['size']*height/540)),bool(style['bold']),style.get('font_family','Arial'))
    text=' '.join(str(clip.get('text','')).split())
    lines=[];word_line=''
    measure=ImageDraw.Draw(Image.new('RGBA',(1,1)))
    for word in text.split():
        candidate=(word_line+' '+word).strip()
        if measure.textbbox((0,0),candidate,font=font)[2] > width*.85 and word_line:
            lines.append(word_line);word_line=word
        else:word_line=candidate
    if word_line:lines.append(word_line)
    lines=lines[:8]
    spacing=max(4,int(style['size']*height/540*.2))
    boxes=[measure.textbbox((0,0),line,font=font,stroke_width=2) for line in lines]
    iw=max([box[2]-box[0] for box in boxes]+[2])+32
    ih=sum(box[3]-box[1] for box in boxes)+spacing*max(0,len(boxes)-1)+28
    im=Image.new('RGBA',(min(iw,width),max(2,ih)),(0,0,0,0))
    draw=ImageDraw.Draw(im)
    y=12
    for line,box in zip(lines,boxes):
        lw=box[2]-box[0]
        color=style['color']
        draw.text(((im.width-lw)/2-box[0],y-box[1]),line,font=font,
                  fill=color,stroke_width=2,stroke_fill='#111111')
        y+=box[3]-box[1]+spacing
    root.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix('.tmp.png')
    im.save(temp)
    temp.replace(target)
    return target,im.size


def title_position(clip,canvas_width,canvas_height,title_width,title_height):
    style=default_style(clip)
    x=(canvas_width-title_width)/2
    y=(canvas_height-title_height)/2
    if style['position']=='bottom':y=canvas_height-title_height-max(18,canvas_height//22)
    elif style['position']=='top':y=max(18,canvas_height//20)
    return x,y


def active_titles(clips,position_ms):
    return sorted((c for c in clips if c.get('kind') in ('title','subtitle','image')
                   and c['start_ms']<=position_ms<c['start_ms']+c['duration_ms']),
                  key=lambda c:(int(c.get('track',2)),c['start_ms']))
