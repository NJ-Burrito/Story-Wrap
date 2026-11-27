"""Story-Wrap media: banner.png (1280x640), hero.gif + hero.mp4 (README hero), and the
site link cards og-card.jpg / og-card-ar.jpg (1200x630).

Draws everything itself (HTML/SVG rendered by headless Chromium), no network, no voice.
Fonts: Thmanyah only, read from the folder in NJ_FONTS (default: the user's Windows font folder).

  uv run --with pillow --with playwright python media/make_media.py --og-dir <portfolio story-wrap/media>
  uv run --with pillow --with playwright python media/make_media.py --og-dir <dir> --sheet <sheet.png>
Renders and scratch go to NJ_RENDERS (default: sw-renders/media in the system temp folder).
"""
import argparse, json, os, re, subprocess, shutil, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRAND = HERE / "brand"
FONTS = Path(os.environ.get("NJ_FONTS") or Path.home() / "AppData/Local/Microsoft/Windows/Fonts")
WORK = Path(os.environ.get("NJ_RENDERS") or Path(tempfile.gettempdir()) / "sw-renders" / "media")

PAPER, INK, BURG, AMBER, CREAM, NIGHT = "#F6F1E8", "#17120F", "#7A1F3D", "#E39A4D", "#F1DDB5", "#130D0A"

EN = dict(
    lang="en", dir="ltr",
    head="Make Arabic story reels with Claude Code.",
    sub="Free, open-source toolkit. MIT licence.",
    stages=["Script", "Voice", "Animate", "Sound", "Compose", "Publish"],
)
AR = dict(
    lang="ar", dir="rtl",
    head="اصنع ريلز قصصية متحركة بالعربية مع Claude Code",
    sub="أداة مجانية ومفتوحة المصدر برخصة MIT",
    stages=["النص", "الصوت", "الحركة", "المؤثرات", "المونتاج", "النشر"],
)
FILES = ["script.json", "voice/line.wav", "shot.json", "sfx.json", "episode.mp4", "post.json"]


def font_css():
    def ff(fam, file, w):
        return "@font-face{font-family:'%s';src:url('%s');font-weight:%d}" % (fam, (FONTS / file).as_uri(), w)
    return "".join([
        ff("TSD", "thmanyahserifdisplay-Bold.otf", 700), ff("TSD", "thmanyahserifdisplay-Black.otf", 900),
        ff("TSD", "thmanyahserifdisplay-Medium.otf", 500),
        ff("TSN", "thmanyahsans-Medium.otf", 500), ff("TSN", "thmanyahsans-Bold.otf", 700),
        ff("TSN", "thmanyahsans-Black.otf", 900), ff("TSN", "thmanyahsans-Regular.otf", 400),
    ])


def logo_inline(h):
    """The dark wordmark logo, background rect removed, scaled to height h."""
    s = (BRAND / "story-wrap-logo-dark.svg").read_text(encoding="utf-8")
    s = re.sub(r'<rect width="1600" height="512" fill="#130D0A"/>', "", s, count=1)
    s = s.replace('width="1600" height="512"', 'width="%d" height="%d"' % (1600 * h // 512, h), 1)
    return s


# stage glyphs, drawn in a 40x40 box
ICONS = [
    '<path d="M11 6h14l6 6v22H11z M25 6v6h6 M16 18h10 M16 23h10 M16 28h6"/>',
    '<rect x="15" y="6" width="10" height="17" rx="5"/><path d="M10 20c0 7 4 10 10 10s10-3 10-10 M20 30v5"/>',
    '<rect x="6" y="8" width="28" height="24" rx="4"/><path d="M16 14l10 6-10 6z"/>',
    '<path d="M8 16h6l8-7v22l-8-7H8z M27 14c3 3 3 9 0 12 M31 10c5 5 5 15 0 20"/>',
    '<path d="M6 14l14-7 14 7-14 7z M6 21l14 7 14-7 M6 28l14 7 14-7"/>',
    '<path d="M6 20L34 6 26 34 19 23z M19 23l15-17"/>',
]


def tag_html(i, label, x, y, rot, w=164, h=170):
    fill = AMBER if i == 5 else CREAM
    return (
        '<div class="tag" style="left:%spx;top:%spx;width:%spx;height:%spx;transform:rotate(%sdeg)">'
        '<svg class="string" viewBox="0 0 10 60" style="left:50%%;margin-left:-5px"><path d="M5 0 L5 60" stroke="#8a6a48" stroke-width="2"/></svg>'
        '<div class="body" style="background:%s">'
        '<i class="hole"></i><b class="num">%02d</b>'
        '<svg class="ic" viewBox="0 0 40 40" fill="none" stroke="%s" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">%s</svg>'
        '<span class="lab">%s</span></div></div>'
    ) % (x, y, w, h, rot, fill, i + 1, INK, ICONS[i], label)


TAG_CSS = """
.tag{position:absolute;transform-origin:50% -52px}
.tag .string{position:absolute;top:-52px;width:10px;height:60px}
.tag .body{position:absolute;inset:0;clip-path:polygon(15% 0,85% 0,100% 11%,100% 100%,0 100%,0 11%);
  display:flex;flex-direction:column;align-items:center;justify-content:flex-end;padding-bottom:16%;gap:8%}
.tag .hole{position:absolute;top:7%;left:50%;width:14px;height:14px;margin-left:-7px;border-radius:50%;background:#130D0A}
.tag .num{position:absolute;top:8%;left:15%;font:700 13px TSN;color:#7A1F3D;letter-spacing:.04em}
.tag .ic{width:44px;height:44px}
.tag .lab{font:700 23px/1.1 TSN;color:#17120F}
"""


def lamp_html(cx, top_h):
    return (
        '<div class="cone" style="left:%dpx"></div>'
        '<div style="position:absolute;left:%dpx;top:0;width:3px;height:%dpx;background:#8a6a48"></div>'
        '<svg style="position:absolute;left:%dpx;top:%dpx" width="108" height="46" viewBox="0 0 108 46">'
        '<path d="M36 0h36l26 36H10z" fill="%s"/><rect x="8" y="34" width="92" height="7" rx="3.5" fill="%s"/>'
        '<path d="M14 30h80" stroke="#A2315A" stroke-width="2" opacity=".7"/></svg>'
    ) % (cx - 330, cx - 1, top_h, cx - 54, top_h - 4, BURG, "#F0C77D")


def card_html(L, w=1280, h=640):
    rtl = L["dir"] == "rtl"
    sc = min(w / 1280, h / 640)
    gx0 = 60 if rtl else 700
    tw, th, gap = 164, 196, 24
    tags = ""
    for i in range(6):
        r, c = divmod(i, 3)
        c = (2 - c) if rtl else c
        tags += tag_html(i, L["stages"][i], gx0 + c * (tw + gap), 126 + r * 236, [-2.2, 1.6, -1.2, 1.8, -1.9, 1.3][i])
    ropes = "".join('<div class="rope" style="left:%dpx;top:%dpx;width:%dpx"></div>' % (gx0 - 14, 70 + r * 236, 3 * tw + 2 * gap + 28) for r in range(2))
    lamp_cx = gx0 + (3 * tw + 2 * gap) // 2
    tpl = """<!doctype html><html lang="@LANG@"><meta charset="utf-8"><style>@FONTS@@TAGCSS@
*{box-sizing:border-box;margin:0}
html,body{width:@W@px;height:@H@px;overflow:hidden;background:@NIGHT@}
body{position:relative}
.bg{position:absolute;inset:0;background:radial-gradient(900px 520px at @LAMPX@px 360px,#3a2314 0%,#1f130c 45%,@NIGHT@ 80%)}
.stage{position:absolute;left:@OX@px;top:@OY@px;width:1280px;height:640px;transform:scale(@SC@);transform-origin:0 0}
.cone{position:absolute;top:34px;width:660px;height:560px;background:linear-gradient(180deg,rgba(240,199,125,.30),rgba(240,199,125,0));clip-path:polygon(40% 0,60% 0,100% 100%,0 100%)}
.rope{position:absolute;height:3px;background:#8a6a48;border-radius:2px}
.copy{position:absolute;top:0;bottom:0;@SIDE@:76px;width:560px;display:flex;flex-direction:column;justify-content:center;direction:@DIR@}
.copy .logo{margin-bottom:34px;@LOGOM@}
.copy h1{font:700 @HS@px/@HL@ TSD;color:@CREAM@;letter-spacing:-.01em;text-wrap:balance}
.copy p{margin-top:26px;font:500 25px/1.4 TSN;color:#C9B28A}
.floor{position:absolute;left:0;right:0;bottom:0;height:30px;background:#2a1b12;border-top:3px solid #5a3f2a}
</style><body><div class="bg"></div>
<div class="stage">@LAMP@@ROPES@@TAGS@
<div class="copy"><div class="logo">@LOGO@</div><h1>@HEAD@</h1><p>@SUB@</p></div>
<div class="floor"></div></div></body></html>"""
    rep = dict(LANG=L["lang"], FONTS=font_css(), TAGCSS=TAG_CSS, W=w, H=h, NIGHT=NIGHT, LAMPX=int(lamp_cx * sc),
               OX=(w - 1280 * sc) / 2, OY=(h - 640 * sc) / 2, SC=sc, SIDE="right" if rtl else "left", DIR=L["dir"],
               LOGOM="align-self:flex-end;" if rtl else "", HS=62 if rtl else 58, HL=1.32 if rtl else 1.14, CREAM=CREAM,
               LAMP=lamp_html(lamp_cx, 56), ROPES=ropes, TAGS=tags, LOGO=logo_inline(112), HEAD=L["head"], SUB=L["sub"])
    tpl = re.sub(r"@([A-Z]+)@", lambda m: str(rep[m.group(1)]), tpl)
    return tpl


# ---------------------------------------------------------------- hero (720x405, 8 s)
HERO_JS = r"""
const STAGES=@STAGES@, FILES=@FILES@, ICONS=@ICONS@;
const AMB='@AMBER@',CRM='@CREAM@',BUR='@BURG@',INK='@INK@',NIGHTC='@NIGHT@';
const DUR=[1.2,1.2,1.2,1.2,1.2,2.0];
const START=DUR.map((_,i)=>DUR.slice(0,i).reduce((a,b)=>a+b,0));
const $=id=>document.getElementById(id);
const clamp=(x,a=0,b=1)=>Math.min(b,Math.max(a,x));
const ease=x=>x<.5?2*x*x:1-Math.pow(-2*x+2,2)/2;
let tagsEl=[];
function buildTags(){
  const host=$('tags');
  STAGES.forEach((s,i)=>{
    const d=document.createElement('div');d.className='t';
    d.innerHTML='<div class="tb"><i class="h"></i><b class="n">0'+(i+1)+'</b><svg class="ic" viewBox="0 0 40 40" fill="none" stroke="'+INK+'" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'+ICONS[i]+'</svg><span>'+s+'</span><svg class="ck" viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="'+BUR+'"/><path d="M7 12.5l3.5 3.5L17 9" stroke="'+CRM+'" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></div>';
    d.style.left=(28+i*113)+'px';host.appendChild(d);tagsEl.push(d);
  });
}
function scene(i,p,t){
  if(i===0){
    let s='<rect x="95" y="6" width="190" height="128" rx="10" fill="'+CRM+'"/><rect x="95" y="6" width="190" height="24" rx="10" fill="'+BUR+'"/><rect x="95" y="20" width="190" height="10" fill="'+BUR+'"/>';
    s+='<circle cx="111" cy="18" r="3.5" fill="'+CRM+'"/><circle cx="123" cy="18" r="3.5" fill="'+CRM+'" opacity=".6"/>';
    const L=[150,120,160,90,140,70];
    L.forEach((w,k)=>{const q=clamp(p*7.5-k);s+='<rect x="112" y="'+(44+k*14)+'" width="'+(w*q)+'" height="7" rx="3.5" fill="'+(k%3==0?BUR:'#3a2a22')+'" opacity="'+(k%3==0?1:.75)+'"/>';});
    const kk=Math.min(5,Math.floor(p*7.5));
    if(Math.floor(t*6)%2==0)s+='<rect x="'+(112+L[kk]*clamp(p*7.5-kk)+4)+'" y="'+(44+kk*14-2)+'" width="3" height="11" fill="'+AMB+'"/>';
    return s;}
  if(i===1){
    const ph=p*364;let s='';
    for(let k=0;k<27;k++){const env=.45+.55*Math.abs(Math.sin(k*.52+.4));const h=14+(Math.sin(t*11+k*.9)*.5+.5)*80*env;
      const x=k*14;s+='<rect x="'+x+'" y="'+(70-h/2)+'" width="8" height="'+h+'" rx="4" fill="'+(x<ph?AMB:CRM)+'" opacity="'+(x<ph?1:.8)+'"/>';}
    s+='<rect x="'+ph+'" y="4" width="3" height="132" rx="1.5" fill="'+AMB+'"/>';return s;}
  if(i===2){
    let s='<rect x="40" y="4" width="300" height="132" rx="12" fill="#241830"/><clipPath id="cl"><rect x="40" y="4" width="300" height="132" rx="12"/></clipPath><g clip-path="url(#cl)">';
    [[70,24],[120,40],[210,18],[260,50],[310,28],[170,60],[90,70]].forEach((q,k)=>{s+='<circle cx="'+q[0]+'" cy="'+q[1]+'" r="1.8" fill="'+CRM+'" opacity="'+(.4+.6*Math.abs(Math.sin(t*3+k)))+'"/>';});
    const ma=ease(p);s+='<circle cx="'+(90+ma*180)+'" cy="'+(70-Math.sin(ma*Math.PI)*42)+'" r="17" fill="'+CRM+'"/><circle cx="'+(96+ma*180)+'" cy="'+(66-Math.sin(ma*Math.PI)*42)+'" r="4" fill="#d6bf8f"/>';
    s+='<path d="M40 112 Q140 98 220 108 T340 104 V136 H40Z" fill="#3a2540"/><path d="M40 122 Q160 112 340 120 V136 H40Z" fill="#1d1226"/>';
    s+='<path d="M232 90 l22-18 22 18 v26 h-44z" fill="'+BUR+'"/><rect x="246" y="96" width="12" height="12" fill="'+AMB+'" opacity="'+(.35+.65*clamp(p*2-.4))+'"/>';
    const wx=60+ease(p)*140,bob=Math.abs(Math.sin(p*18))*3;
    s+='<g transform="translate('+wx+' '+(-bob)+')"><circle cx="0" cy="88" r="7.5" fill="#E8B07F"/><path d="M-6 82 Q0 74 6 82z" fill="#2a1a14"/><rect x="-8" y="96" width="16" height="22" rx="6" fill="'+BUR+'"/>';
    s+='<rect x="-6" y="116" width="5" height="8" fill="#2a1a14" transform="rotate('+(Math.sin(p*18)*14)+' -3 116)"/><rect x="1" y="116" width="5" height="8" fill="#2a1a14" transform="rotate('+(-Math.sin(p*18)*14)+' 3 116)"/></g>';
    return s+'</g>';}
  if(i===3){
    let s='<path d="M120 52h28l36-30v96l-36-30h-28z" fill="'+CRM+'"/>';
    for(let k=0;k<3;k++){const q=((p*2+k/3)%1);const r=22+q*70;s+='<path d="M196 '+(70-r*.62)+' A'+r+' '+r+' 0 0 1 196 '+(70+r*.62)+'" fill="none" stroke="'+AMB+'" stroke-width="5" stroke-linecap="round" opacity="'+(1-q)+'" transform="translate('+(q*6)+' 0)"/>';}
    for(let k=0;k<9;k++){const h=8+Math.abs(Math.sin(t*9+k*1.3))*30;s+='<rect x="'+(270+k*12)+'" y="'+(70-h/2)+'" width="6" height="'+h+'" rx="3" fill="'+CRM+'" opacity=".85"/>';}
    return s;}
  if(i===4){
    const q=ease(clamp(p*1.6));let s='';
    [[BUR,-120,-30],[AMB,0,60],[CRM,120,-30]].forEach((l,k)=>{s+='<rect x="'+(100+k*18+(1-q)*l[1])+'" y="'+(20+k*14+(1-q)*l[2])+'" width="170" height="86" rx="10" fill="'+l[0]+'" stroke="'+NIGHTC+'" stroke-width="2"/>';});
    const tx=290;s+='<rect x="'+tx+'" y="20" width="76" height="100" rx="8" fill="#241a14"/>';
    for(let k=0;k<3;k++)s+='<rect x="'+(tx+8)+'" y="'+(32+k*26)+'" width="'+(18+clamp(p*1.4)*40*(1-k*.2))+'" height="14" rx="4" fill="'+[BUR,AMB,CRM][k]+'"/>';
    s+='<rect x="'+(tx+8+clamp(p)*58)+'" y="26" width="3" height="88" fill="#fff"/>';return s;}
  let s='<rect x="140" y="6" width="84" height="128" rx="14" fill="#241a14" stroke="'+CRM+'" stroke-width="4"/><rect x="170" y="12" width="24" height="5" rx="2.5" fill="'+CRM+'"/>';
  s+='<circle cx="182" cy="76" r="27" fill="'+AMB+'" opacity="'+clamp(p*3)+'"/><path d="M169 77l9 9 18-20" stroke="'+INK+'" stroke-width="6" fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="60" stroke-dashoffset="'+(60*(1-clamp(p*2-.3)))+'"/>';
  const ay=130-clamp(p*1.3)*130;s+='<g transform="translate(300 '+ay+')" opacity="'+(1-clamp(p*1.3-.8)*5)+'"><path d="M0 -26l14 20h-9v26h-10v-26h-9z" fill="'+CRM+'"/></g>';
  for(let k=0;k<5;k++){const w=clamp(p*1.4-k*.1);s+='<circle cx="'+(262+k*18)+'" cy="'+(112-w*70-k*6)+'" r="'+(4-w*2.5)+'" fill="'+AMB+'" opacity="'+(w>0?1-w:0)+'"/>';}
  return s;
}
function render(t){
  let idx=5;for(let i=0;i<6;i++){if(t<START[i]+DUR[i]){idx=i;break;}}
  const p=clamp((t-START[idx])/DUR[idx]);
  tagsEl.forEach((d,i)=>{
    const done=i<idx||(i===5&&t>=START[5]+1.0);const active=i===idx&&!done;
    const lift=active?-10*Math.sin(clamp(p*6)*Math.PI/2):0;
    const sway=Math.sin(t*2.2+i*1.1)*(active?1.2:.8)+[-1.8,1.4,-1,1.6,-1.5,1.1][i];
    d.style.transform='translateY('+lift+'px) rotate('+sway+'deg)';
    d.querySelector('.tb').style.background=active?AMB:CRM;
    d.style.opacity=(active||done)?1:.5;
    d.classList.toggle('done',done);
  });
  $('num').textContent='0'+(idx+1);$('lab').textContent=STAGES[idx];$('file').textContent=FILES[idx];
  $('scene').innerHTML=scene(idx,p,t);
  $('prog').style.width=(clamp(t/8)*100)+'%';
  
  $('lampglow').style.opacity=.85+.1*Math.sin(t*1.3);
}
"""

HERO_CSS = """
*{box-sizing:border-box;margin:0}
html,body{width:720px;height:405px;overflow:hidden;background:#130D0A}
#page{position:absolute;inset:0;background:radial-gradient(520px 300px at 520px 180px,#35200f 0%,#1c110b 55%,#130D0A 90%)}
#lampglow{position:absolute;left:150px;top:-40px;width:430px;height:360px;background:linear-gradient(180deg,rgba(240,199,125,.16),rgba(240,199,125,0));clip-path:polygon(38% 0,62% 0,100% 100%,0 100%)}
.rope{position:absolute;left:14px;right:14px;top:84px;height:3px;background:#8a6a48;border-radius:2px}
#tags{position:absolute;inset:0}
.t{position:absolute;top:92px;width:104px;height:84px;transform-origin:50% -8px}
.t::before{content:"";position:absolute;left:50%;top:-8px;width:2px;height:12px;background:#8a6a48;margin-left:-1px}
.tb{position:absolute;inset:0;clip-path:polygon(15% 0,85% 0,100% 12%,100% 100%,0 100%,0 12%);background:#F1DDB5;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;padding-bottom:7px;gap:2px}
.tb .h{position:absolute;top:6px;left:50%;margin-left:-4px;width:8px;height:8px;border-radius:50%;background:#130D0A}
.tb .n{position:absolute;top:5px;left:10px;font:700 9px TSN;color:#7A1F3D}
.tb .ic{width:26px;height:26px}
.tb span{font:700 14px/1.1 TSN;color:#17120F}
.tb .ck{position:absolute;top:2px;right:9px;width:15px;height:15px;display:none}
.t.done .ck{display:block}
.logo{position:absolute;left:24px;top:16px}
.tagline{position:absolute;right:26px;top:30px;font:500 14px TSN;color:#C9B28A}
#panel{position:absolute;left:28px;right:28px;top:206px;height:170px;border-radius:18px;background:#1f1510;border:2px solid #3a281b}
#left{position:absolute;left:26px;top:14px;width:230px}
#num{font:900 46px/1 TSN;color:#E39A4D}
#lab{font:700 30px/1.1 TSD;color:#F1DDB5;margin-top:4px}
#file{margin-top:10px;display:inline-block;font:500 14px TSN;color:#C9B28A;background:#2a1c14;border:1.5px solid #5a3f2a;border-radius:8px;padding:4px 10px}
#scene{position:absolute;left:272px;top:12px;width:380px;height:140px}
#progwrap{position:absolute;left:26px;right:26px;bottom:12px;height:4px;border-radius:2px;background:#3a281b}
#prog{height:4px;border-radius:2px;background:#E39A4D;width:0}
"""


def hero_html():
    js = HERO_JS
    for k, v in dict(STAGES=json.dumps(EN["stages"]), FILES=json.dumps(FILES), ICONS=json.dumps(ICONS), AMBER=AMBER,
                     CREAM=CREAM, BURG=BURG, INK=INK, NIGHT=NIGHT).items():
        js = js.replace("@%s@" % k, v)
    return ("<!doctype html><html><meta charset='utf-8'><style>" + font_css() + HERO_CSS + "</style><body><div id='page'><div id='lampglow'></div>"
            "<div class='logo'>" + logo_inline(48) + "</div><div class='tagline'>Idea to reel, in six steps</div>"
            "<div class='rope'></div><div id='tags'></div>"
            "<div id='panel'><div id='left'><div id='num'></div><div id='lab'></div><div id='file'></div></div>"
            "<svg id='scene' viewBox='0 0 380 140'></svg><div id='progwrap'><div id='prog'></div></div></div></div>"
            "<script>" + js + " buildTags();render(0);</script></body></html>")


# ---------------------------------------------------------------- rendering
def write(name, html):
    WORK.mkdir(parents=True, exist_ok=True)
    p = WORK / name
    p.write_text(html, encoding="utf-8")
    return p


def open_page(pg, name, html, w, h):
    p = write(name, html)
    pg.set_viewport_size({"width": w, "height": h})
    pg.goto(p.as_uri())
    pg.wait_for_function("document.fonts.status==='loaded'")


def shoot_static(pg, name, html, w, h, out):
    open_page(pg, name, html, w, h)
    pg.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": w, "height": h})


def render_hero_frames(pg, fps):
    d = WORK / "frames"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    open_page(pg, "hero.html", hero_html(), 720, 405)
    n = int(8 * fps)
    for k in range(n):
        pg.evaluate("render(%f)" % (k / fps))
        pg.screenshot(path=str(d / ("f%03d.png" % k)), clip={"x": 0, "y": 0, "width": 720, "height": 405})
    return d, n


def png_budget(src, dst, limit):
    from PIL import Image
    im = Image.open(src).convert("RGB")
    im.save(dst, optimize=True)
    if Path(dst).stat().st_size > limit:
        im.quantize(256, dither=Image.Dither.FLOYDSTEINBERG).save(dst, optimize=True)


def build(args):
    from playwright.sync_api import sync_playwright
    from PIL import Image
    WORK.mkdir(parents=True, exist_ok=True)
    og_dir = Path(args.og_dir) if args.og_dir else WORK / "og"
    og_dir.mkdir(parents=True, exist_ok=True)
    profile = WORK / "chrome-swmedia"
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(str(profile), viewport={"width": 1280, "height": 640})
        try:
            pg = ctx.new_page()
            shoot_static(pg, "banner.html", card_html(EN), 1280, 640, WORK / "banner_raw.png")
            png_budget(WORK / "banner_raw.png", HERE / "banner.png", 900_000)
            for L, name in ((EN, "og-card.jpg"), (AR, "og-card-ar.jpg")):
                raw = WORK / ("og_%s.png" % L["lang"])
                shoot_static(pg, "og-%s.html" % L["lang"], card_html(L, 1200, 630), 1200, 630, raw)
                Image.open(raw).convert("RGB").save(og_dir / name, quality=90, optimize=True)
            fps = 25
            d, n = render_hero_frames(pg, fps)
        finally:
            ctx.close()
    frames = [Image.open(d / ("f%03d.png" % k)).convert("RGB") for k in range(n)]
    gif = [f.quantize(48, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames[::2]]
    gif[0].save(HERE / "hero.gif", save_all=True, append_images=gif[1:], duration=80, loop=0, optimize=True, disposal=1)
    ff = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(d / "f%03d.png"),
                    "-vf", "pad=720:406:0:0:0x130D0A", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", str(HERE / "hero.mp4")], check=True)
    shutil.rmtree(profile, ignore_errors=True)
    return og_dir


def sheet(path, og_dir):
    from PIL import Image
    gif = Image.open(HERE / "hero.gif")
    hero = []
    for k in range(9):
        gif.seek(int(gif.n_frames * k / 9))
        hero.append(gif.convert("RGB").resize((480, 270)))
    canvas = Image.new("RGB", (2520, 640 + 20 + 630 + 20 + 3 * 280 + 20), "#444")
    canvas.paste(Image.open(HERE / "banner.png"), (10, 10))
    canvas.paste(Image.open(og_dir / "og-card.jpg"), (10, 670))
    canvas.paste(Image.open(og_dir / "og-card-ar.jpg"), (1230, 670))
    for k, f in enumerate(hero):
        canvas.paste(f, (10 + (k % 3) * 490, 1330 + (k // 3) * 280))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--og-dir", default=None, help="folder for og-card.jpg / og-card-ar.jpg")
    ap.add_argument("--sheet", default=None, help="write a contact sheet here")
    a = ap.parse_args()
    og = build(a)
    if a.sheet:
        sheet(a.sheet, og)


if __name__ == "__main__":
    main()
