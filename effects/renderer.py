"""Render de efectos sobre Pillow. Sin Qt: comprobable con fotogramas sintéticos.

El motor usa imágenes de previsualización reducidas para evitar bloquear Qt.
No altera nunca el archivo original. Exportación de efectos aún no implementada.
"""
from PIL import Image, ImageFilter, ImageEnhance, ImageOps, ImageDraw
from effects.model import merged_effects, censor_mask, zoom_state, valid_mask


def _zoom(image, state):
    scale=state['scale']
    if scale <= 1.0001:
        return image
    w,h=image.size
    crop_w=max(1,round(w/scale)); crop_h=max(1,round(h/scale))
    left=min(w-crop_w,max(0,round(state['cx']*w-crop_w/2)))
    top=min(h-crop_h,max(0,round(state['cy']*h-crop_h/2)))
    return image.crop((left,top,left+crop_w,top+crop_h)).resize((w,h),Image.Resampling.BICUBIC)


def _censor(image, effect, mask):
    w,h=image.size
    x=max(0,int(mask['x']*w));y=max(0,int(mask['y']*h))
    right=min(w,max(x+1,round((mask['x']+mask['w'])*w)))
    bottom=min(h,max(y+1,round((mask['y']+mask['h'])*h)))
    if x>=right or y>=bottom:
        return image
    region=image.crop((x,y,right,bottom))
    strength=max(1,int(effect.get('strength',18)))
    if effect.get('mode')=='mosaic':
        size=max(2,min(min(region.size),round(strength*.8)))
        blurred=region.resize((max(1,region.width//size),max(1,region.height//size)),
                              Image.Resampling.BOX).resize(region.size,Image.Resampling.NEAREST)
    else:
        blurred=region.filter(ImageFilter.GaussianBlur(radius=min(80,strength)))
    edge=max(0,round(float(effect.get('feather',0))*min(w,h)))
    if edge:
        # feather con imagen procesada en el ROI extendido, sin halos negros.
        edge=min(edge, max(1,min(region.size)//3))
        alpha=Image.new('L',region.size,0)
        ImageDraw.Draw(alpha).rectangle((edge,edge,region.width-edge-1,region.height-edge-1),fill=255)
        alpha=alpha.filter(ImageFilter.GaussianBlur(max(1,edge)))
        region=Image.composite(blurred,region,alpha)
    else:
        region=blurred
    result=image.copy();result.paste(region,(x,y))
    return result


def render_frame(frame, effects, source_ms=0, max_width=1280):
    """Devuelve nueva imagen RGB procesada; acepta PIL.Image.Image."""
    if frame is None:
        raise ValueError('Fotograma inexistente')
    img=frame.convert('RGB')
    if img.width>max_width:
        img=img.resize((max_width,max(1,round(img.height*max_width/img.width))),
                       Image.Resampling.BILINEAR)
    fx=merged_effects(effects)
    color=fx['color']
    if color['enabled']:
        if color.get('mirror'):img=ImageOps.mirror(img)
        brightness=float(color.get('brightness',0))
        if brightness:img=ImageEnhance.Brightness(img).enhance(max(.01,1+brightness/100))
        contrast=float(color.get('contrast',1))
        if contrast!=1:img=ImageEnhance.Contrast(img).enhance(max(0,contrast))
        saturation=float(color.get('saturation',1))
        if saturation!=1:img=ImageEnhance.Color(img).enhance(max(0,saturation))
        if color.get('grayscale'):img=ImageOps.grayscale(img).convert('RGB')
    if fx['zoom']['enabled']:
        img=_zoom(img,zoom_state(fx,source_ms))
    if fx['censor']['enabled']:
        img=_censor(img,fx['censor'],censor_mask(fx,source_ms))
    return img
