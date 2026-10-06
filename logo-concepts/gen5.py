import math, sys
B,Y,D,R,L='#3776AB','#FFD43B','#1E2A38','#D9443B','#F6F3EA'
def pt(a,r=76): a=math.radians(a); return 120+r*math.cos(a),120+r*math.sin(a)
def head(theta, lift, tongue):
    # head sits where the arc ends (theta), pointing along the clockwise tangent, rotated outward by `lift` degrees
    x,y=pt(theta); d=math.radians(theta+90-lift); t=(math.cos(d),math.sin(d)); n=(t[1],-t[0])  # n = outer side
    cx,cy=x+t[0]*12,y+t[1]*12; rot=math.degrees(d)
    ex,ey=cx+t[0]*8+n[0]*7,cy+t[1]*8+n[1]*7
    fx,fy=cx+t[0]*23,cy+t[1]*23
    s=''
    if tongue:
        tip=lambda k:(fx+t[0]*12+n[0]*k, fy+t[1]*12+n[1]*k)
        a,b=tip(4),tip(-4); m=(fx+t[0]*6,fy+t[1]*6)
        s+=f'<path d="M{fx:.1f},{fy:.1f} L{m[0]:.1f},{m[1]:.1f} L{a[0]:.1f},{a[1]:.1f} M{m[0]:.1f},{m[1]:.1f} L{b[0]:.1f},{b[1]:.1f}" fill="none" stroke="{R}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
    s+=f'<rect x="{cx-23:.1f}" y="{cy-19:.1f}" width="46" height="38" rx="13" fill="{B}" transform="rotate({rot:.1f} {cx:.1f} {cy:.1f})"/>'
    s+=f'<path d="{EYE}" fill="#fff" transform="translate({ex+1:.1f} {ey+1:.1f}) rotate({rot:.1f}) scale(1.35)"/>'
    return s
def logo(lift, tongue, dark, theta=-52):
    sx,sy=pt(theta)
    s=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240">'
    if dark: s+=f'<rect width="240" height="240" rx="44" fill="{D}"/>'
    s+=f'<defs><linearGradient id="g" gradientUnits="userSpaceOnUse" x1="0" y1="44" x2="0" y2="196"><stop offset="0" stop-color="{B}"/><stop offset="1" stop-color="{Y}"/></linearGradient></defs>'
    s+=f'<path d="M{sx:.1f},{sy:.1f} A76,76 0 1,0 163.6,182.3" fill="none" stroke="url(#g)" stroke-width="28"/>'
    s+='<path d="M167.7,196.3 Q184,187 181,165 Q165,166 152.9,172.6 Z" fill="url(#g)"/>'
    s+=head(theta,lift,tongue)
    c=L if dark else D
    s+=f'<rect x="88" y="94" width="20" height="20" fill="{c}"/><rect x="88" y="128" width="20" height="20" fill="{c}"/><rect x="122" y="113" width="42" height="16" fill="{c}"/>'
    return s+'</svg>'
EYES={'almond':'M-6.5,0 Q0,-6.5 6.5,0 Q0,6.5 -6.5,0 Z',
      'hooded':'M-6.5,-3.5 L6.5,-0.5 Q4,5 -1,4.5 Q-6.5,4 -6.5,-3.5 Z',
      'teardrop':'M7.5,0 Q1.5,-5 -2.5,-4.5 Q-6,-4 -6,0 Q-6,4 -2.5,4.5 Q1.5,5 7.5,0 Z',
      'slant':'M-6.5,1.5 Q-1,-6 6.5,-2 Q1,5 -6.5,1.5 Z'}
names=[]
for e,p in EYES.items():
    EYE=p
    for dark in (False,True):
        k=f'c8-eye-{e}'+('-dark' if dark else '')
        svg=logo(38,False,dark,-52); open(k+'.svg','w').write(svg)
        open(k+'-zoom.svg','w').write(svg.replace('viewBox="0 0 240 240"','viewBox="140 38 70 50"'))
        names.append(k)
card=lambda k,w: f"<div style='background:#fff;border-radius:16px;padding:12px;text-align:center'><img src='{k}.svg' width={w}><div style='font-size:13px'>{k}</div></div>"
cards=''.join(card(k,230) for k in names[0::2])+''.join(card(k,230) for k in names[1::2])+''.join(card(k+'-zoom',230) for k in names[0::2])
open('sheet5.html','w').write(f"""<html><body style="margin:0;background:{L};font-family:DejaVu Sans,sans-serif;color:{D}">
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:20px;padding:32px;width:1136px">{cards}</div></body></html>""")
