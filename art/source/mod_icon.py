import sys, math, numpy as np
sys.path.insert(0, "art/source")
import displays as d, xc_jumps as xc, show_jumps as sj
from PIL import Image, ImageDraw, ImageFilter
"""The mod icon: a red tractor on the turntable, 512x512 with no mips (GIANTS TestRunner).
Run from the repo root: python3 art/source/mod_icon.py"""
import os
from eqdds import save_bc7
yaws=[-155]
def flip(m):
    o=xc.Mesh(); o.verts=[(p,n,(uv[0],1-uv[1])) for p,n,uv in m.verts]; o.tris=list(m.tris); return o
TOP=0.7
def wheel(m, hub, x0, x1, cy, cz, r, sides=28):
    for i in range(sides):
        a0=2*math.pi*i/sides; a1=2*math.pi*(i+1)/sides
        p=lambda a,x:(x,cy+r*math.sin(a),cz+r*math.cos(a))
        n=lambda a:(0,math.sin(a),math.cos(a))
        ids=[m.vertex(p(a0,x0),n(a0),(0,0)),m.vertex(p(a1,x0),n(a1),(0,0)),m.vertex(p(a1,x1),n(a1),(0,0)),m.vertex(p(a0,x1),n(a0),(0,0))]
        m.tri(ids[0],ids[1],ids[2]); m.tri(ids[0],ids[2],ids[3])
        for x,s in ((x0,-1),(x1,1)):
            c=m.vertex((x,cy,cz),(s,0,0),(0,0))
            q=m.vertex(p(a0,x),(s,0,0),(0,0)); w=m.vertex(p(a1,x),(s,0,0),(0,0))
            m.tri(c,q,w)
            xr=x+s*0.01; pr=lambda a:(xr,cy+0.6*r*math.sin(a),cz+0.6*r*math.cos(a))
            c=hub.vertex((xr,cy,cz),(s,0,0),(0,0)); q=hub.vertex(pr(a0),(s,0,0),(0,0)); w=hub.vertex(pr(a1),(s,0,0),(0,0))
            hub.tri(c,q,w)
body=xc.Mesh(); tyres=xc.Mesh(); hubs=xc.Mesh(); glass=xc.Mesh(); black=xc.Mesh()
# tractor along z, centred on disc; front at -z
R=0.85; r=0.52
body.box(-0.45,0.45,TOP+0.75,TOP+1.45,-1.9,0.4,(0,0))     # hood/chassis
body.box(-0.55,0.55,TOP+0.55,TOP+1.35,0.4,1.2,(0,0))      # under cab
body.box(-0.6,0.6,TOP+2.45,TOP+2.6,0.15,1.55,(0,0))       # roof
for x in (-0.58,0.5):
    for z in (0.2,1.45): black.box(x,x+0.08,TOP+1.35,TOP+2.45,z-0.05,z+0.05,(0,0))
glass.box(-0.52,0.52,TOP+1.35,TOP+2.45,0.25,1.45,(0,0))
black.box(-0.47,0.47,TOP+0.6,TOP+0.78,-2.0,-1.85,(0,0)) # grille base
black.box(-0.06,0.06,TOP+1.45,TOP+2.2,-1.3,-1.18,(0,0))  # exhaust
for s in (-1,1):
    wheel(tyres,hubs, s*0.62 if s>0 else -0.62-0.45, s*0.62+0.45 if s>0 else -0.62, TOP+R, 0.8, R)
    wheel(tyres,hubs, s*0.5 if s>0 else -0.5-0.3, s*0.5+0.3 if s>0 else -0.5, TOP+r, -1.35, r)
    body.box(s*0.62-(0.5 if s<0 else 0)+(0 if s<0 else -0.02), s*0.62+(0.5 if s>0 else 0), TOP+1.72, TOP+1.78, 0.1, 1.5,(0,0))  # mudguards
logo=sj.flat(sj.WHITE)
stone=np.asarray(Image.open("placeables/displays/plinthStone_diffuse.dds").convert("RGB"),dtype=float)
s, logos, col = d.turntable()
green=sj.flat(sj.COLOUR["green"])
meshes=[(s["stone"], stone),(s["paint"],green),(s["white"],sj.flat(sj.WHITE)),(s["disc"], sj.flat((0.25,0.25,0.27))),
        (body,sj.flat((0.72,0.12,0.1))),(tyres,sj.flat((0.1,0.1,0.1))),(hubs,sj.flat((0.78,0.78,0.76))),(glass,sj.flat((0.45,0.6,0.7))),(black,sj.flat((0.12,0.12,0.12)))]
meshes += [(flip(m), logo) for m in logos.values()]
BOLD = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
MEDIUM = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
SIG_FONT = "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"
from PIL import ImageFont

def spaced(d, cx, y, text, font, fill, tracking):
    widths = [d.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        d.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += w + tracking
    return total

def logotype(can):
    """SHOWROOM over a green rule and DISPLAYS, at the top, with a soft shadow."""
    layer = Image.new("RGBA", can.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    w = spaced(d, 256, 92, "SHOWROOM", ImageFont.truetype(BOLD, 66), (248, 248, 246, 255), 5)
    green = (62, 158, 78, 255)
    d.rectangle([256 - w / 2, 108, 256 + w / 2, 113], fill=green)
    spaced(d, 256, 150, "DISPLAYS", ImageFont.truetype(MEDIUM, 34), (226, 232, 238, 255), 15)
    shadow = Image.new("RGBA", can.size, (0, 0, 0, 0)); shadow.putalpha(layer.getchannel("A").point(lambda v: v * 0.6))
    shadow = shadow.filter(ImageFilter.GaussianBlur(4))
    can.alpha_composite(shadow, (0, 3)); can.alpha_composite(layer)
    return can

def sign(can):
    """The maker's signature, small, bottom right like a painter's."""
    layer = Image.new("RGBA", can.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    d.text((488, 494), "Jasta007", font=ImageFont.truetype(SIG_FONT, 19), fill=(150, 165, 180, 150), anchor="rs")
    can.alpha_composite(layer.filter(ImageFilter.GaussianBlur(0.3)))
    return can

for yaw in yaws:
    img = xc.render(meshes, size=512, yaw=yaw, pitch=22)
    y,x=np.mgrid[0:512,0:512]
    rr=np.hypot((x-256)/320,(y-190)/300)
    t=np.clip(rr,0,1)[...,None]
    bg=np.array([70,90,110])*(1-t)+np.array([18,24,32])*t
    can=Image.fromarray(bg.astype(np.uint8)).convert("RGBA")
    M=450; mx, my = (512-M)//2, 96
    sm=img.resize((M,M),Image.LANCZOS)
    a=np.asarray(sm)[...,3]
    sh=Image.fromarray((a*0.7).astype(np.uint8)).filter(ImageFilter.GaussianBlur(12))
    shadow=Image.new("RGBA",(M,M),(0,0,0,255)); shadow.putalpha(sh)
    can.alpha_composite(shadow,(mx,my+8)); can.alpha_composite(sm,(mx,my))
    can=logotype(can)
    can=sign(can)
    can=can.convert("RGB")
    save_bc7(can, "icon_ShowroomDisplays.dds")
    os.makedirs("art/previews", exist_ok=True)
    can.save("art/previews/icon_ShowroomDisplays.png")
