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
    s+=f'<rect x="{cx-23:.1f}" y="{cy-19:.1f}" width="46" height="38" rx="13" fill="url(#g)" transform="rotate({rot:.1f} {cx:.1f} {cy:.1f})"/>'
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
EYE='M-6.5,0 Q0,-6.5 6.5,0 Q0,6.5 -6.5,0 Z'
names=[]
for dark in (False,True):
    k='c9-almond-gradient'+('-dark' if dark else '')
    svg=logo(38,False,dark,-52); open(k+'.svg','w').write(svg)
    open(k+'-zoom.svg','w').write(svg.replace('viewBox="0 0 240 240"','viewBox="140 38 70 50"'))
    names.append(k)
card=lambda k,w: f"<div style='background:#fff;border-radius:16px;padding:12px;text-align:center'><img src='{k}.svg' width={w}><div style='font-size:13px'>{k}</div></div>"
cards=''.join(card(k,240) for k in names)+''.join(card(k+'-zoom',240) for k in names)
cards+="<div style='grid-column:span 4;background:#fff;border-radius:16px;padding:16px;display:flex;gap:24px;align-items:end;justify-content:center'>"+''.join(f"<img src='{k}.svg' width={w}>" for k in names for w in (32,64,128))+"</div>"
open('sheet6.html','w').write(f"""<html><body style="margin:0;background:{L};font-family:DejaVu Sans,sans-serif;color:{D}">
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:20px;padding:32px;width:1136px">{cards}</div></body></html>""")
