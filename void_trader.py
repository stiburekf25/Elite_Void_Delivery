"""
VOID TRADER v5
Controls:
  W/UP    Thrust      TAB   Phase     E   Dock (inside station) / Refuel
  A/D     Rotate      M     Full map  F11 Fullscreen   ESC Quit
  S/DN    Brake       SPACE Respawn (death)
"""
import pygame, math, random, sys
pygame.init()

_info = pygame.display.Info()
NATIVE_W, NATIVE_H = _info.current_w, _info.current_h
fullscreen = True
W, H = NATIVE_W, NATIVE_H
screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
pygame.display.set_caption("VOID TRADER")
clock = pygame.time.Clock()
FPS = 60

def toggle_fullscreen():
    global fullscreen, screen, W, H
    fullscreen = not fullscreen
    if fullscreen:
        W, H = NATIVE_W, NATIVE_H
        screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
    else:
        W, H = 1280, 720
        screen = pygame.display.set_mode((W, H))

# ── CONSTANTS ──────────────────────────────────────────────────────────────────
CHUNK_SIZE    = 5000
CHUNKS_LOAD   = 3
DOCK_RADIUS   = 110
TRADE_HALF    = 95       # half-size of trading station outer square
TRADE_GAP     = 44       # half-width of entrance gap
TRADE_DOCK_R  = 34       # inner docking circle radius
FUEL_COLL_R   = 40
SHIP_R        = 18
SHIP_HP_MAX   = 100
SHIP_FUEL_MAX = 100.0

BG      = (246, 246, 250)
BLACK   = (12,  12,  18)
DGRAY   = (70,  70,  80)
GRAY    = (140, 140, 150)
LGRAY   = (210, 210, 218)
C_GREEN = (45,  180, 95)
C_BLUE  = (55,  115, 225)
C_RED   = (210, 65,  65)
C_YELL  = (205, 172, 35)
C_CYAN  = (50,  190, 190)
C_ORANGE= (220, 130, 50)

PHASES = [
    ("SUBLIGHT", 4.5,  0.10,  0.975, (110,110,125), C_GREEN,  0.012),
    ("CRUISE",   19.0, 0.65,  0.990, (70, 110,220), C_BLUE,   0.040),
    ("WARP",     58.0, 3.20,  0.998, (220, 75, 75), C_RED,    0.140),
]
PHASE_DAMAGE = [0, 20, 42]

GOODS = [
    ("Minerals",  48), ("Food",      27), ("Electronics",165),
    ("Fuel Cells",88), ("Arms",     245), ("Medicine",   115),
    ("Alloys",    72), ("Luxury",   310),
]
TRADE_NAMES = [
    "Kepler Station","Nova Reach","Helios Port","Cygnus Base",
    "Delta Outpost","Frontier Hub","Orion Dock","Vega Terminal",
    "Proxima Yard","Lyra Beacon","Sirius Market","Tau Ceti Port",
    "Altair Hub","Rigel Post","Deneb Base","Castor Yard",
    "Pollux Point","Antares Gate","Spica Terminal","Fomalhaut Dock",
]
FUEL_NAMES = [
    "Fuel Depot A","Gas Point B","Refinery C","Pump Station D",
    "Energy Post E","Fuel Bay F","Reactor G","Depot H",
    "Void Pump I","Plasma Bay J","Ion Depot K","Core Fuel L",
]

# ── FONTS ──────────────────────────────────────────────────────────────────────
def try_font(names, size):
    for n in names:
        try:
            f = pygame.font.SysFont(n, size)
            f.render("A", True, BLACK)
            return f
        except Exception:
            pass
    return pygame.font.Font(None, size+4)

MONO = ["consolas","couriernew","courier new","lucidaconsole","dejavusansmono","monospace"]
FSM = try_font(MONO, 13)
FMD = try_font(MONO, 17)
FLG = try_font(MONO, 27)
FXL = try_font(MONO, 42)

def txt(surf, s, font, col, x, y, anchor="tl"):
    r = font.render(str(s), True, col)
    if anchor == "tc": x -= r.get_width() // 2
    if anchor == "tr": x -= r.get_width()
    surf.blit(r, (int(x), int(y)))
    return r.get_width(), r.get_height()

# ── CHUNK WORLD ────────────────────────────────────────────────────────────────
chunks = {}

def chunk_rng(cx, cy):
    seed = (cx * 0x5DEECE66D ^ cy * 0x9B05688C) & 0xFFFFFFFF
    return random.Random(seed)

def generate_chunk(cx, cy):
    if (cx, cy) in chunks:
        return
    cr = chunk_rng(cx, cy)
    ox = cx * CHUNK_SIZE
    oy = cy * CHUNK_SIZE
    stars = [(ox+cr.randint(0,CHUNK_SIZE), oy+cr.randint(0,CHUNK_SIZE),
              cr.choice([1,1,1,2,2,3]), cr.randint(135,195)) for _ in range(55)]
    occupied = []; trading = []; fuel = []
    margin = 400
    for _ in range(cr.randint(0, 2)):
        for _ in range(40):
            x = ox + cr.randint(margin, CHUNK_SIZE-margin)
            y = oy + cr.randint(margin, CHUNK_SIZE-margin)
            if all(math.hypot(x-px, y-py) > 2200 for px,py in occupied):
                name = cr.choice(TRADE_NAMES)
                prices = {g: max(5, int(b*cr.uniform(0.60,1.55))) for g,b in GOODS}
                stock  = {g: cr.randint(0,50) for g,b in GOODS}
                trading.append({"x":x,"y":y,"name":name,"prices":prices,"stock":stock,
                                 "entrance":cr.randint(0,3)})
                occupied.append((x,y)); break
    for _ in range(cr.randint(0, 1)):
        for _ in range(40):
            x = ox + cr.randint(margin, CHUNK_SIZE-margin)
            y = oy + cr.randint(margin, CHUNK_SIZE-margin)
            if all(math.hypot(x-px, y-py) > 1500 for px,py in occupied):
                fuel.append({"x":x,"y":y,"name":cr.choice(FUEL_NAMES),
                              "fuel_price":cr.randint(6,28),
                              "rot":cr.uniform(0,360),"coll_r":FUEL_COLL_R})
                occupied.append((x,y)); break
    chunks[(cx,cy)] = {"trading":trading, "fuel":fuel, "stars":stars}

def ensure_chunks_around(wx, wy):
    cx0 = int(wx//CHUNK_SIZE); cy0 = int(wy//CHUNK_SIZE)
    for dcx in range(-CHUNKS_LOAD, CHUNKS_LOAD+1):
        for dcy in range(-CHUNKS_LOAD, CHUNKS_LOAD+1):
            generate_chunk(cx0+dcx, cy0+dcy)

def get_chunks_in_view(lx, ly, rx, ry):
    cx0=int(lx//CHUNK_SIZE)-1; cy0=int(ly//CHUNK_SIZE)-1
    cx1=int(rx//CHUNK_SIZE)+1; cy1=int(ry//CHUNK_SIZE)+1
    return [chunks[(cx,cy)] for cx in range(cx0,cx1+1)
            for cy in range(cy0,cy1+1) if (cx,cy) in chunks]

def get_stations_near(wx, wy, radius=CHUNK_SIZE):
    trading, fuel = [], []
    cx0=int((wx-radius)//CHUNK_SIZE)-1; cy0=int((wy-radius)//CHUNK_SIZE)-1
    cx1=int((wx+radius)//CHUNK_SIZE)+1; cy1=int((wy+radius)//CHUNK_SIZE)+1
    for cx in range(cx0,cx1+1):
        for cy in range(cy0,cy1+1):
            if (cx,cy) in chunks:
                trading.extend(chunks[(cx,cy)]["trading"])
                fuel.extend(chunks[(cx,cy)]["fuel"])
    return trading, fuel

# ── FOG OF WAR ─────────────────────────────────────────────────────────────────
CELL=200; EXPL_R=6
explored=set(); fog_dirty=True

def do_explore(wx, wy):
    global fog_dirty
    cx=int(wx/CELL); cy=int(wy/CELL)
    for dx in range(-EXPL_R, EXPL_R+1):
        for dy in range(-EXPL_R, EXPL_R+1):
            if dx*dx+dy*dy <= EXPL_R*EXPL_R:
                cell=(cx+dx, cy+dy)
                if cell not in explored:
                    explored.add(cell); fog_dirty=True

# ── TRADING STATION HELPERS ────────────────────────────────────────────────────
def ship_inside_station(sx, sy, st):
    return (abs(sx-st["x"]) < TRADE_HALF-SHIP_R and
            abs(sy-st["y"]) < TRADE_HALF-SHIP_R)

def ship_near_dock(sx, sy, st):
    return math.hypot(sx-st["x"], sy-st["y"]) < TRADE_DOCK_R+18

# ── TRADE WALL COLLISION ───────────────────────────────────────────────────────
def resolve_trade_walls(ship):
    tlist, _ = get_stations_near(ship.x, ship.y, TRADE_HALF*3)
    for st in tlist:
        cx2, cy2 = st["x"], st["y"]
        h = TRADE_HALF; g = TRADE_GAP; e = st["entrance"]
        if abs(ship.x-cx2) > h+SHIP_R+4 or abs(ship.y-cy2) > h+SHIP_R+4:
            continue

        def do_damage():
            if ship.phase > 0 and ship.coll_flash == 0:
                dmg = PHASE_DAMAGE[ship.phase]
                ship.phase = 0; ship.cooldown = 45
                ship.take_damage(dmg)
                notify(f"COLLISION! -{dmg} HP  (phase reset)", C_RED)

        # Horizontal wall at wy; solid_x: list of (x1,x2) solid segments
        def chk_h(wy, solid_x):
            d = ship.y - wy
            if abs(d) < SHIP_R:
                for x1, x2 in solid_x:
                    if x1 - SHIP_R < ship.x < x2 + SHIP_R:
                        if d >= 0:
                            ship.y = wy + SHIP_R
                            if ship.vy < 0:
                                ship.vy *= -0.3
                                do_damage()
                        else:
                            ship.y = wy - SHIP_R
                            if ship.vy > 0:
                                ship.vy *= -0.3
                                do_damage()
                        break

        # Vertical wall at wx; solid_y: list of (y1,y2) solid segments
        def chk_v(wx, solid_y):
            d = ship.x - wx
            if abs(d) < SHIP_R:
                for y1, y2 in solid_y:
                    if y1 - SHIP_R < ship.y < y2 + SHIP_R:
                        if d >= 0:
                            ship.x = wx + SHIP_R
                            if ship.vx < 0:
                                ship.vx *= -0.3
                                do_damage()
                        else:
                            ship.x = wx - SHIP_R
                            if ship.vx > 0:
                                ship.vx *= -0.3
                                do_damage()
                        break

        # top wall  (y = cy2-h)
        if e == 0:
            chk_h(cy2-h, [(cx2-h, cx2-g), (cx2+g, cx2+h)])
        else:
            chk_h(cy2-h, [(cx2-h, cx2+h)])
        # bottom wall (y = cy2+h)
        if e == 2:
            chk_h(cy2+h, [(cx2-h, cx2-g), (cx2+g, cx2+h)])
        else:
            chk_h(cy2+h, [(cx2-h, cx2+h)])
        # right wall (x = cx2+h)
        if e == 1:
            chk_v(cx2+h, [(cy2-h, cy2-g), (cy2+g, cy2+h)])
        else:
            chk_v(cx2+h, [(cy2-h, cy2+h)])
        # left wall  (x = cx2-h)
        if e == 3:
            chk_v(cx2-h, [(cy2-h, cy2-g), (cy2+g, cy2+h)])
        else:
            chk_v(cx2-h, [(cy2-h, cy2+h)])

# ── SHIP ───────────────────────────────────────────────────────────────────────
SHIP_PTS = [(0,-24),(13,10),(7,4),(0,14),(-7,4),(-13,10)]

class Ship:
    def __init__(self, x, y):
        self.x=float(x); self.y=float(y)
        self.angle=0.0; self.vx=0.0; self.vy=0.0
        self.phase=0; self.cooldown=0
        self.credits=5000; self.cargo={}; self.cap=24
        self.trail=[]; self.docked=None
        self.thrust_glow=0; self.hp=SHIP_HP_MAX; self.fuel=SHIP_FUEL_MAX
        self.coll_flash=0; self.dead=False; self.no_fuel_warn=0

    @property
    def cargo_used(self): return sum(self.cargo.values())

    def rotated(self, cx, cy, scale=1.0):
        a=math.radians(self.angle); ca,sa=math.cos(a),math.sin(a)
        return [(cx+(px*ca-py*sa)*scale, cy+(px*sa+py*ca)*scale) for px,py in SHIP_PTS]

    def respawn(self, st):
        self.x=st["x"]+rng.uniform(-10,10); self.y=st["y"]+rng.uniform(-10,10)
        self.vx=self.vy=0; self.angle=0; self.phase=0
        self.hp=SHIP_HP_MAX; self.fuel=SHIP_FUEL_MAX; self.cargo={}
        self.credits=max(500,self.credits); self.trail=[]
        self.dead=False; self.coll_flash=0; self.cooldown=0

    def take_damage(self, dmg):
        self.hp=max(0,self.hp-dmg); self.coll_flash=35
        if self.hp<=0: self.dead=True

    def update(self, keys):
        if self.docked or self.dead:
            self.vx*=0.8; self.vy*=0.8
            self.thrust_glow=max(0,self.thrust_glow-1); return
        if self.cooldown>0: self.cooldown-=1
        if self.coll_flash>0: self.coll_flash-=1
        if self.no_fuel_warn>0: self.no_fuel_warn-=1
        _,max_spd,accel,drag,_,_,fdrain = PHASES[self.phase]
        rot=[4.5,3.0,1.5][self.phase]
        if keys[pygame.K_LEFT]  or keys[pygame.K_a]: self.angle-=rot
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: self.angle+=rot
        thrusting=keys[pygame.K_UP] or keys[pygame.K_w]
        if thrusting and self.fuel>0:
            a=math.radians(self.angle)
            self.vx+=math.sin(a)*accel; self.vy-=math.cos(a)*accel
            self.fuel=max(0.0,self.fuel-fdrain); self.thrust_glow=rng.randint(5,10)
        elif thrusting:
            if self.no_fuel_warn==0:
                notify("OUT OF FUEL — dock at a fuel station!", C_ORANGE)
                self.no_fuel_warn=180
            self.thrust_glow=max(0,self.thrust_glow-1)
        else:
            self.thrust_glow=max(0,self.thrust_glow-1)
        if keys[pygame.K_DOWN] or keys[pygame.K_s]: self.vx*=0.92; self.vy*=0.92
        spd=math.hypot(self.vx,self.vy)
        if spd>max_spd: f=max_spd/spd; self.vx*=f; self.vy*=f
        self.vx*=drag; self.vy*=drag
        self.x+=self.vx; self.y+=self.vy
        self.trail.append((self.x,self.y,self.phase))
        ml=[35,55,110][self.phase]
        if len(self.trail)>ml: self.trail.pop(0)
        do_explore(self.x,self.y)
        ensure_chunks_around(self.x,self.y)

    def check_fuel_collisions(self):
        if self.docked or self.dead: return
        _,flist=get_stations_near(self.x,self.y,400)
        for st in flist:
            dist=math.hypot(self.x-st["x"],self.y-st["y"])
            cr=st["coll_r"]
            if dist<cr+SHIP_R:
                if dist<1: dist=1
                nx=(self.x-st["x"])/dist; ny=(self.y-st["y"])/dist
                overlap=cr+SHIP_R-dist
                self.x+=nx*overlap; self.y+=ny*overlap
                dot=self.vx*nx+self.vy*ny
                if dot<0: self.vx-=2*dot*nx; self.vy-=2*dot*ny
                self.vx*=0.35; self.vy*=0.35
                if self.phase>0 and self.coll_flash==0:
                    dmg=PHASE_DAMAGE[self.phase]
                    self.phase=0; self.cooldown=45
                    self.take_damage(dmg)
                    notify(f"COLLISION! -{dmg} HP  (phase reset)", C_RED)

    def cycle_phase(self):
        if self.cooldown>0: return
        self.phase=(self.phase+1)%3
        spd=math.hypot(self.vx,self.vy); ms=PHASES[self.phase][1]
        if spd>ms: f=ms/spd; self.vx*=f; self.vy*=f
        self.cooldown=35

# ── INIT ───────────────────────────────────────────────────────────────────────
rng=random.Random(42)
ship=Ship(0,0)
ensure_chunks_around(0,0)
do_explore(0,0)
cam_x=ship.x-W/2; cam_y=ship.y-H/2

def w2s(wx,wy): return wx-cam_x, wy-cam_y

def update_camera():
    global cam_x,cam_y
    tx=ship.x-W/2; ty=ship.y-H/2
    cam_x+=(tx-cam_x)*0.10; cam_y+=(ty-cam_y)*0.10

# ── NOTIFICATIONS ──────────────────────────────────────────────────────────────
notices=[]
def notify(msg, col=BLACK):
    notices[:] = [n for n in notices if n[0]!=msg]
    notices.append([msg,col,220])

def draw_notices():
    dead=[]
    for i,n in enumerate(notices[:5]):
        s=FMD.render(n[0],True,n[1])
        screen.blit(s,(W//2-s.get_width()//2,H//2-90+i*30))
        n[2]-=1
        if n[2]<=0: dead.append(n)
    for d in dead: notices.remove(d)

# ── FLASH ──────────────────────────────────────────────────────────────────────
phase_flash=0
def trigger_phase_flash(): global phase_flash; phase_flash=22

def draw_phase_flash():
    global phase_flash
    if phase_flash<=0: return
    col=PHASES[ship.phase][5]; alpha=int(phase_flash/22*130)
    surf=pygame.Surface((W,H),pygame.SRCALPHA); surf.fill((*col,alpha))
    screen.blit(surf,(0,0)); phase_flash=max(0,phase_flash-1)

def draw_collision_flash():
    if ship.coll_flash<=0: return
    alpha=int(ship.coll_flash/35*190)
    surf=pygame.Surface((W,H),pygame.SRCALPHA); surf.fill((215,35,35,alpha))
    screen.blit(surf,(0,0))

# ── STARS ──────────────────────────────────────────────────────────────────────
def draw_stars():
    warp=ship.phase==2; spd=math.hypot(ship.vx,ship.vy)
    stretch=min(spd/4.5,10.0) if warp else 0
    a=math.radians(ship.angle); sa,ca=math.sin(a),math.cos(a)
    for ch in get_chunks_in_view(cam_x,cam_y,cam_x+W,cam_y+H):
        for sx,sy,sr,sb in ch["stars"]:
            scx,scy=w2s(sx,sy)
            if not(-60<scx<W+60 and -60<scy<H+60): continue
            c=(sb,sb,sb)
            if stretch>0.5:
                dx=sa*sr*stretch*1.8; dy=-ca*sr*stretch*1.8
                pygame.draw.line(screen,c,(int(scx-dx),int(scy-dy)),(int(scx+dx),int(scy+dy)),max(1,sr-1))
            else:
                pygame.draw.circle(screen,c,(int(scx),int(scy)),sr)

def draw_trail():
    n=len(ship.trail)
    for i,(tx,ty,ph) in enumerate(ship.trail):
        sx,sy=w2s(tx,ty); t=i/max(1,n-1); tc=PHASES[ph][4]
        c=tuple(int(v*t) for v in tc); sz=max(1,int(t*(1+ph)))
        pygame.draw.circle(screen,c,(int(sx),int(sy)),sz)

def draw_ship():
    if ship.dead: return
    sx,sy=w2s(ship.x,ship.y); pts=ship.rotated(sx,sy)
    col=BLACK if ship.coll_flash%4<2 else C_RED
    pygame.draw.polygon(screen,col,pts)
    if ship.thrust_glow>0:
        a=math.radians(ship.angle); ex=sx-math.sin(a)*14; ey=sy+math.cos(a)*14
        gc=PHASES[ship.phase][5]
        pygame.draw.circle(screen,gc,(int(ex),int(ey)),ship.thrust_glow+rng.randint(0,3))

# ── DRAW TRADING STATIONS (big square with gap entrance) ──────────────────────
def draw_trade_station_at(sx, sy, entrance, inside=False, show_dock=False):
    h = TRADE_HALF; g = TRADE_GAP
    wall_col  = (60, 90, 165) if inside else (55, 75, 130)
    inner_col = C_CYAN if inside else (80, 120, 200)
    acol      = (90, 210, 110)   # entrance arrow colour

    tl=(sx-h, sy-h); tr=(sx+h, sy-h)
    br=(sx+h, sy+h); bl=(sx-h, sy+h)

    # inward direction per entrance: 0=top→down, 1=right→left, 2=bot→up, 3=left→right
    inward = [(0,1),(-1,0),(0,-1),(1,0)]

    def draw_wall(p1, p2, is_gap, iv):
        mx=(p1[0]+p2[0])/2; my=(p1[1]+p2[1])/2
        dx=p2[0]-p1[0]; dy=p2[1]-p1[1]; ln=math.hypot(dx,dy)
        if ln<1: return
        ndx=dx/ln; ndy=dy/ln
        ix,iy=iv
        if not is_gap:
            pygame.draw.line(screen,wall_col,(int(p1[0]),int(p1[1])),(int(p2[0]),int(p2[1])),3)
        else:
            # two solid segments flanking the gap
            pygame.draw.line(screen,wall_col,(int(p1[0]),int(p1[1])),(int(mx-ndx*g),int(my-ndy*g)),3)
            pygame.draw.line(screen,wall_col,(int(mx+ndx*g),int(my+ndy*g)),(int(p2[0]),int(p2[1])),3)
            # entrance arrows (two triangles pointing inward)
            for sign in (-1, 1):
                # tip: slightly inside the station
                tx2=int(mx + ndx*g*sign*0.45 + ix*15)
                ty2=int(my + ndy*g*sign*0.45 + iy*15)
                # base: slightly outside the station
                bx2=tx2 - ix*18; by2=ty2 - iy*18
                lp=(int(bx2-ndy*7), int(by2+ndx*7))
                rp=(int(bx2+ndy*7), int(by2-ndx*7))
                pygame.draw.polygon(screen,acol,[(tx2,ty2),lp,rp])

    draw_wall(tl, tr, entrance==0, inward[0])   # top
    draw_wall(tr, br, entrance==1, inward[1])   # right
    draw_wall(bl, br, entrance==2, inward[2])   # bottom (l→r)
    draw_wall(tl, bl, entrance==3, inward[3])   # left   (t→b)

    # corner blocks
    for cx3,cy3 in [tl,tr,br,bl]:
        pygame.draw.rect(screen,wall_col,(int(cx3)-5,int(cy3)-5,10,10))

    # inner docking circle + crosshair
    pygame.draw.circle(screen,inner_col,(int(sx),int(sy)),TRADE_DOCK_R,2)
    hw=TRADE_DOCK_R//2
    pygame.draw.line(screen,inner_col,(int(sx-hw),int(sy)),(int(sx+hw),int(sy)),1)
    pygame.draw.line(screen,inner_col,(int(sx),int(sy-hw)),(int(sx),int(sy+hw)),1)

    if show_dock:
        txt(screen,"[ E ]  DOCK",FMD,C_GREEN,sx,sy+TRADE_DOCK_R+6,anchor="tc")


def draw_trading_stations():
    margin=TRADE_HALF*2+30
    for ch in get_chunks_in_view(cam_x,cam_y,cam_x+W,cam_y+H):
        for st in ch["trading"]:
            sx,sy=w2s(st["x"],st["y"])
            if not(-margin<sx<W+margin and -margin<sy<H+margin): continue
            inside   = ship_inside_station(ship.x,ship.y,st)
            can_dock = inside and ship_near_dock(ship.x,ship.y,st)
            show_dock_ui = can_dock and ship.docked is None and dock_state is None
            draw_trade_station_at(sx,sy,st["entrance"],inside=inside,show_dock=show_dock_ui)
            txt(screen,st["name"],FSM,DGRAY,sx,sy-TRADE_HALF-16,anchor="tc")
            # hint when near but outside
            if not inside:
                dist=math.hypot(ship.x-st["x"],ship.y-st["y"])
                if dist < DOCK_RADIUS*2.8:
                    hints=["↓ ENTER FROM TOP","← ENTER FROM RIGHT",
                           "↑ ENTER FROM BOTTOM","→ ENTER FROM LEFT"]
                    txt(screen,hints[st["entrance"]],FSM,C_GREEN,sx,sy+TRADE_HALF+10,anchor="tc")


def draw_fuel_stations():
    for ch in get_chunks_in_view(cam_x,cam_y,cam_x+W,cam_y+H):
        for st in ch["fuel"]:
            sx,sy=w2s(st["x"],st["y"])
            if not(-120<sx<W+120 and -120<sy<H+120): continue
            st["rot"]=(st["rot"]+0.18)%360
            def sq(r):
                return [(sx+r*math.cos(math.radians(st["rot"])+math.pi/4*(2*i+1)),
                         sy+r*math.sin(math.radians(st["rot"])+math.pi/4*(2*i+1))) for i in range(4)]
            op=sq(36*1.414); ip=sq(18*1.414)
            pygame.draw.polygon(screen,C_ORANGE,op,2)
            pygame.draw.polygon(screen,BLACK,ip,0)
            pygame.draw.polygon(screen,C_ORANGE,ip,2)
            for j in range(4):
                pygame.draw.line(screen,(160,90,30),(int(op[j][0]),int(op[j][1])),(int(ip[j][0]),int(ip[j][1])),1)
            pygame.draw.circle(screen,C_ORANGE,(int(sx),int(sy)),4)
            txt(screen,st["name"],FSM,C_ORANGE,sx,sy-52,anchor="tc")
            txt(screen,f"{st['fuel_price']} CR/u",FSM,C_ORANGE,sx,sy+46,anchor="tc")
            dist=math.hypot(ship.x-st["x"],ship.y-st["y"])
            if dist<DOCK_RADIUS*1.5 and ship.docked is None:
                pygame.draw.circle(screen,C_ORANGE,(int(sx),int(sy)),int(DOCK_RADIUS*0.85),1)
                txt(screen,"[E] REFUEL/REPAIR",FSM,C_ORANGE,sx,sy+63,anchor="tc")


def draw_warp_overlay():
    if ship.phase!=2: return
    spd=math.hypot(ship.vx,ship.vy); ratio=min(spd/PHASES[2][1],1.0); alpha=int(ratio*72)
    if alpha<3: return
    surf=pygame.Surface((W,H),pygame.SRCALPHA); edge=60
    for i in range(edge):
        a=int(alpha*(i/edge)**2); r,g2,b=PHASES[2][4]
        for rect in [(i,0,1,H),(W-i-1,0,1,H),(0,i,W,1),(0,H-i-1,W,1)]:
            surf.fill((r,g2,b,a),rect)
    screen.blit(surf,(0,0))

# ── HUD ────────────────────────────────────────────────────────────────────────
def draw_hud():
    pname,max_spd,*_,hcol,_=PHASES[ship.phase]
    spd=math.hypot(ship.vx,ship.vy)
    pw,phh=268,190
    s=pygame.Surface((pw,phh),pygame.SRCALPHA); s.fill((246,246,250,210)); screen.blit(s,(10,10))
    pygame.draw.rect(screen,BLACK,(10,10,pw,phh),1)
    txt(screen,"VOID TRADER v5",FSM,GRAY,20,15)
    txt(screen,f">> {pname}",FMD,hcol,20,29)
    bw=pw-30
    def bar(label,val,mx,col,yo):
        fill=int(bw*max(0,min(val/mx,1.0)))
        pygame.draw.rect(screen,LGRAY,(20,yo,bw,8)); pygame.draw.rect(screen,col,(20,yo,fill,8))
        txt(screen,f"{label}  {val:{'.0f' if isinstance(val,float) else 'd'}} / {mx:.0f}",FSM,col,20,yo+10)
    bar("SPD",spd,max_spd,hcol,54)
    hp_col=C_GREEN if ship.hp>60 else(C_YELL if ship.hp>30 else C_RED)
    bar("HP ",ship.hp,SHIP_HP_MAX,hp_col,80)
    fu_col=C_CYAN if ship.fuel>30 else(C_ORANGE if ship.fuel>10 else C_RED)
    bar("FUEL",ship.fuel,SHIP_FUEL_MAX,fu_col,106)
    txt(screen,f"CR    {ship.credits:>10,}",FSM,C_YELL,20,130)
    txt(screen,f"CARGO   {ship.cargo_used:2} / {ship.cap}",FSM,DGRAY,20,147)
    for i in range(3):
        col=PHASES[i][5] if i==ship.phase else LGRAY
        bd=BLACK if i==ship.phase else GRAY
        pygame.draw.circle(screen,col,(20+i*25,180),8)
        pygame.draw.circle(screen,bd,(20+i*25,180),8,1)
    iw=pw; cargo_items=list(ship.cargo.items())
    ih=28+max(1,len(cargo_items))*18+4; iy=10+phh+8
    inv=pygame.Surface((iw,ih),pygame.SRCALPHA); inv.fill((246,246,250,210))
    screen.blit(inv,(10,iy)); pygame.draw.rect(screen,BLACK,(10,iy,iw,ih),1)
    txt(screen,"INVENTORY",FSM,GRAY,20,iy+7)
    if not cargo_items: txt(screen,"  -- empty --",FSM,LGRAY,20,iy+22)
    for j,(gn,qty) in enumerate(cargo_items): txt(screen,f"  {gn:<14} x{qty}",FSM,DGRAY,20,iy+22+j*18)
    hints=["[TAB]   Phase","[E]     Dock/Refuel","[W/UP]  Thrust","[A/D]   Turn",
           "[S/DN]  Brake","[M]     Full Map","[F11]   Fullscreen"]
    for i,h in enumerate(hints): txt(screen,h,FSM,GRAY,W-172,15+i*17)
    txt(screen,f"X:{ship.x:,.0f}  Y:{ship.y:,.0f}",FSM,GRAY,W//2,H-22,anchor="tc")

# ── MINIMAP ────────────────────────────────────────────────────────────────────
def draw_minimap():
    mw,mh=224,184; mx,my=W-mw-10,H-mh-10
    surf=pygame.Surface((mw,mh)); surf.fill((28,28,38))
    scx=int(ship.x/CELL); scy=int(ship.y/CELL); view_r=40
    cpw=mw/(view_r*2); cph=mh/(view_r*2)
    for cx2,cy2 in explored:
        dx=cx2-scx; dy=cy2-scy
        if abs(dx)>view_r or abs(dy)>view_r: continue
        rx=int((dx+view_r)*cpw); ry=int((dy+view_r)*cph)
        pygame.draw.rect(surf,(220,220,228),(rx,ry,max(1,int(cpw)+1),max(1,int(cph)+1)))
    screen.blit(surf,(mx,my))
    pygame.draw.rect(screen,BLACK,(mx,my,mw,mh),1)
    view_rw=view_r*CELL
    def mm(wx,wy):
        return (int(mx+mw//2+(wx-ship.x)/view_rw*(mw//2)),
                int(my+mh//2+(wy-ship.y)/view_rw*(mh//2)))
    for ch in chunks.values():
        for st in ch["trading"]:
            cx3,cy3=int(st["x"]/CELL),int(st["y"]/CELL)
            if any((cx3+ddx,cy3+ddy) in explored for ddx in range(-2,3) for ddy in range(-2,3)):
                px3,py3=mm(st["x"],st["y"])
                if mx<=px3<=mx+mw and my<=py3<=my+mh:
                    pygame.draw.rect(screen,DGRAY,(px3-3,py3-3,6,6),1)
        for st in ch["fuel"]:
            cx3,cy3=int(st["x"]/CELL),int(st["y"]/CELL)
            if any((cx3+ddx,cy3+ddy) in explored for ddx in range(-2,3) for ddy in range(-2,3)):
                px3,py3=mm(st["x"],st["y"])
                if mx<=px3<=mx+mw and my<=py3<=my+mh:
                    pygame.draw.circle(screen,C_ORANGE,(px3,py3),3)
    pygame.draw.circle(screen,BLACK,(mx+mw//2,my+mh//2),3)
    txt(screen,"MAP",FSM,(180,180,190),mx+6,my+5)

# ── FULL MAP (M) ───────────────────────────────────────────────────────────────
show_full_map=False
MAP_HALF=16000

def draw_full_map():
    pad=50; mw=W-pad*2; mh=H-pad*2
    scale=min(mw/(MAP_HALF*2), mh/(MAP_HALF*2))
    csx=ship.x; csy=ship.y

    def mpos(wx,wy):
        return (int(pad+mw//2+(wx-csx)*scale),
                int(pad+mh//2+(wy-csy)*scale))
    def in_map(px,py): return pad<=px<=pad+mw and pad<=py<=pad+mh

    # White BG like game world
    pygame.draw.rect(screen,BG,(pad,pad,mw,mh))
    pygame.draw.rect(screen,BLACK,(pad,pad,mw,mh),2)

    # Stars
    vl=csx-MAP_HALF; vr=csx+MAP_HALF; vt=csy-MAP_HALF; vb=csy+MAP_HALF
    for ch in get_chunks_in_view(vl,vt,vr,vb):
        for sx2,sy2,sr2,sb2 in ch["stars"]:
            px2,py2=mpos(sx2,sy2)
            if in_map(px2,py2):
                pygame.draw.circle(screen,(sb2,sb2,sb2),(px2,py2),max(1,sr2-1))

    # Fog overlay
    fog=pygame.Surface((mw,mh),pygame.SRCALPHA); fog.fill((80,80,100,200))
    cpx=max(1,int(CELL*scale))+1
    for ecx,ecy in explored:
        wx2=ecx*CELL; wy2=ecy*CELL
        dx=wx2-csx; dy=wy2-csy
        if abs(dx)>MAP_HALF+CELL*2 or abs(dy)>MAP_HALF+CELL*2: continue
        rx=int(mw//2+dx*scale); ry=int(mh//2+dy*scale)
        pygame.draw.rect(fog,(0,0,0,0),(rx,ry,cpx,cpx))
    screen.blit(fog,(pad,pad))

    # Stations
    for ch in get_chunks_in_view(vl,vt,vr,vb):
        for st in ch["trading"]:
            cx3,cy3=int(st["x"]/CELL),int(st["y"]/CELL)
            if not any((cx3+ddx,cy3+ddy) in explored for ddx in range(-2,3) for ddy in range(-2,3)):
                continue
            px2,py2=mpos(st["x"],st["y"])
            if not in_map(px2,py2): continue
            ms=max(5,int(TRADE_HALF*scale))
            # Draw scaled square station with gap
            e=st["entrance"]
            walls=[((px2-ms,py2-ms),(px2+ms,py2-ms)),  # top
                   ((px2+ms,py2-ms),(px2+ms,py2+ms)),  # right
                   ((px2-ms,py2+ms),(px2+ms,py2+ms)),  # bottom
                   ((px2-ms,py2-ms),(px2-ms,py2+ms))]  # left
            gs=max(2,int(TRADE_GAP*scale))
            for wi,(wp1,wp2) in enumerate(walls):
                if wi==e:
                    # draw gap
                    wmx=(wp1[0]+wp2[0])//2; wmy=(wp1[1]+wp2[1])//2
                    wdx=wp2[0]-wp1[0]; wdy=wp2[1]-wp1[1]
                    wln=max(1,math.hypot(wdx,wdy))
                    wndx=wdx/wln; wndy=wdy/wln
                    pygame.draw.line(screen,DGRAY,wp1,(int(wmx-wndx*gs),int(wmy-wndy*gs)),2)
                    pygame.draw.line(screen,DGRAY,(int(wmx+wndx*gs),int(wmy+wndy*gs)),wp2,2)
                    pygame.draw.circle(screen,C_GREEN,(wmx,wmy),3)
                else:
                    pygame.draw.line(screen,DGRAY,wp1,wp2,2)
            # inner dock circle
            pygame.draw.circle(screen,(80,120,200),(px2,py2),max(2,int(TRADE_DOCK_R*scale)),1)
            if in_map(px2+ms+4,py2-6):
                lbl=FSM.render(st["name"],True,DGRAY)
                if pad<=px2+ms+4<=pad+mw: screen.blit(lbl,(px2+ms+4,py2-6))
        for st in ch["fuel"]:
            cx3,cy3=int(st["x"]/CELL),int(st["y"]/CELL)
            if not any((cx3+ddx,cy3+ddy) in explored for ddx in range(-2,3) for ddy in range(-2,3)):
                continue
            px2,py2=mpos(st["x"],st["y"])
            if not in_map(px2,py2): continue
            r2=max(3,int(FUEL_COLL_R*scale))
            pygame.draw.circle(screen,C_ORANGE,(px2,py2),r2,2)
            if in_map(px2+r2+4,py2-5):
                lbl=FSM.render(st["name"],True,C_ORANGE)
                screen.blit(lbl,(px2+r2+4,py2-5))

    # ── Ship: actual black polygon, same as game ──
    spx,spy=mpos(ship.x,ship.y)
    if in_map(spx,spy):
        ship_sc=max(0.55,min(2.2,0.55))   # fixed readable size on map
        pts=ship.rotated(spx,spy,scale=ship_sc)
        pygame.draw.polygon(screen,BLACK,pts)

    txt(screen,"VOID DELIVERY MAP",FLG,BLACK,W//2,pad+12,anchor="tc")
    txt(screen,"[M] or [ESC] — Close",FSM,GRAY,W//2,pad+mh-22,anchor="tc")

    # Scale bar
    bpx=int(2000*scale)
    if bpx>8:
        bx2=pad+mw-24-bpx; by2=pad+mh-34
        pygame.draw.line(screen,BLACK,(bx2,by2),(bx2+bpx,by2),2)
        for bex in [bx2,bx2+bpx]:
            pygame.draw.line(screen,BLACK,(bex,by2-4),(bex,by2+4),2)
        txt(screen,"2000 u",FSM,BLACK,bx2+bpx//2,by2+5,anchor="tc")

    # Legend
    lx2=pad+12; ly2=pad+mh-54
    pygame.draw.rect(screen,DGRAY,(lx2,ly2,8,8),1)
    txt(screen,"Trading station",FSM,DGRAY,lx2+14,ly2-1)
    pygame.draw.circle(screen,C_ORANGE,(lx2+4,ly2+20),4,2)
    txt(screen,"Fuel / Repair",FSM,C_ORANGE,lx2+14,ly2+13)
    pts2=ship.rotated(lx2+8,ly2+36,scale=0.55)
    pygame.draw.polygon(screen,BLACK,pts2)
    txt(screen,"Your ship",FSM,BLACK,lx2+14,ly2+27)

# ── DOCKING MINIGAME ───────────────────────────────────────────────────────────
dock_state=None; dock_target_st=None; dock_target_type=None
dock_free_idx=0; dock_sel_idx=0; dock_anim=0; dock_penalty_timer=0
DOCK_PENALTY=500

def start_dock_minigame(st, stype):
    global dock_state,dock_target_st,dock_target_type,dock_free_idx,dock_sel_idx,dock_anim
    dock_target_st=st; dock_target_type=stype
    dock_state="minigame"; dock_sel_idx=0; dock_anim=0
    dock_free_idx=rng.randint(0,3)
    notify(f"DOCKING APPROACH — FREE DOCK: {dock_free_idx+1}", C_CYAN)

def finish_dock_success():
    global dock_state
    dock_state=None
    open_shop(dock_target_st,dock_target_type)
    notify(f"Docked at {dock_target_st['name']}", C_GREEN)

def finish_dock_penalty():
    global dock_state,dock_penalty_timer
    dock_state="penalty"; dock_penalty_timer=110
    ship.credits=max(0,ship.credits-DOCK_PENALTY)
    dx=ship.x-dock_target_st["x"]; dy=ship.y-dock_target_st["y"]
    dist=math.hypot(dx,dy) or 1
    ship.vx=(dx/dist)*7; ship.vy=(dy/dist)*7
    notify(f"WRONG DOCK! -{DOCK_PENALTY} CR — EJECTED!", C_RED)

def handle_dock_key(event):
    global dock_sel_idx,dock_state
    if event.key==pygame.K_ESCAPE:
        dock_state=None; notify("Docking aborted.",GRAY); return
    if event.key in (pygame.K_LEFT,pygame.K_a):  dock_sel_idx=max(0,dock_sel_idx-1)
    if event.key in (pygame.K_RIGHT,pygame.K_d): dock_sel_idx=min(3,dock_sel_idx+1)
    if event.key in (pygame.K_RETURN,pygame.K_SPACE,pygame.K_e):
        if dock_sel_idx==dock_free_idx: finish_dock_success()
        else:                           finish_dock_penalty()

def draw_dock_minigame():
    global dock_anim
    dock_anim+=1
    ov=pygame.Surface((W,H),pygame.SRCALPHA); ov.fill((8,12,28,195)); screen.blit(ov,(0,0))
    pw,ph=820,400; px=W//2-pw//2; py=H//2-ph//2
    panel=pygame.Surface((pw,ph),pygame.SRCALPHA); panel.fill((14,18,40,252))
    screen.blit(panel,(px,py)); pygame.draw.rect(screen,C_CYAN,(px,py,pw,ph),2)
    txt(screen,"── DOCKING APPROACH ──",FLG,C_CYAN,W//2,py+14,anchor="tc")
    txt(screen,f"STATION: {dock_target_st['name']}",FMD,(180,210,255),W//2,py+50,anchor="tc")
    pulse=int(math.sin(dock_anim*0.07)*20+200)
    txt(screen,f"FREE DOCK:  {dock_free_idx+1}",FXL,(pulse,255,pulse),W//2,py+82,anchor="tc")

    bw2=160; bh=150; gap2=16; total_w=bw2*4+gap2*3
    gx=W//2-total_w//2; gy=py+155

    for i in range(4):
        bx2=gx+i*(bw2+gap2)
        is_sel=i==dock_sel_idx; is_free=i==dock_free_idx
        bg_col=(30,55,100) if is_sel else (18,28,50)
        border_col=C_CYAN if is_sel else(50,70,120)
        bs=pygame.Surface((bw2,bh),pygame.SRCALPHA); bs.fill((*bg_col,240))
        screen.blit(bs,(bx2,gy))
        pygame.draw.rect(screen,border_col,(bx2,gy,bw2,bh),3 if is_sel else 1)
        if is_sel:
            sy3=gy+int((math.sin(dock_anim*0.09)*0.5+0.5)*(bh-6))
            sl=pygame.Surface((bw2,3),pygame.SRCALPHA); sl.fill((*C_CYAN,70)); screen.blit(sl,(bx2,sy3))
        dock_nc=(200,230,255) if is_sel else(80,100,150)
        txt(screen,"DOCK",FSM,dock_nc,bx2+bw2//2,gy+18,anchor="tc")
        ns=FXL.render(str(i+1),True,C_CYAN if is_sel else(80,100,150))
        screen.blit(ns,(bx2+bw2//2-ns.get_width()//2,gy+34))
        pygame.draw.line(screen,border_col,(bx2+10,gy+88),(bx2+bw2-10,gy+88),1)
        # ── FREE or OCCUPIED ──
        if is_free:
            txt(screen,"[  FREE  ]",FSM,C_GREEN,bx2+bw2//2,gy+96,anchor="tc")
        else:
            txt(screen,"[ OCCUPIED ]",FSM,(190,55,55),bx2+bw2//2,gy+96,anchor="tc")
        if is_sel and (dock_anim//10)%2==0:
            pygame.draw.polygon(screen,C_CYAN,[(bx2+bw2//2,gy+bh-8),(bx2+bw2//2-10,gy+bh-20),(bx2+bw2//2+10,gy+bh-20)])

    txt(screen,"[← →]  Select dock    [ENTER / E]  Confirm    [ESC]  Abort",
        FSM,(80,100,140),W//2,py+ph-24,anchor="tc")

def draw_dock_penalty():
    global dock_state,dock_penalty_timer
    dock_penalty_timer-=1
    ov=pygame.Surface((W,H),pygame.SRCALPHA)
    ov.fill((180,20,20,min(dock_penalty_timer*4,180))); screen.blit(ov,(0,0))
    txt(screen,"WRONG DOCK!",FXL,(255,220,220),W//2,H//2-40,anchor="tc")
    txt(screen,f"-{DOCK_PENALTY} CR  —  EJECTED FROM DOCKING ZONE",FMD,(255,180,180),W//2,H//2+20,anchor="tc")
    if dock_penalty_timer<=0: dock_state=None

# ── SHOP ───────────────────────────────────────────────────────────────────────
shop_open=False; shop_type="trade"; shop_tab=0; shop_sel=0; shop_qty=1
shop_msg=""; shop_msg_t=0
REPAIR_COST=5

def open_shop(st,stype):
    global shop_open,shop_type,shop_tab,shop_sel,shop_qty
    ship.docked=st; shop_open=True; shop_type=stype
    shop_tab=0; shop_sel=0
    shop_qty=min(20,max(1,int(SHIP_FUEL_MAX-ship.fuel))) if stype=="fuel" else 1

def close_shop():
    global shop_open; ship.docked=None; shop_open=False

def shop_status(msg):
    global shop_msg,shop_msg_t; shop_msg=msg; shop_msg_t=200

def handle_shop_key(event):
    global shop_tab,shop_sel,shop_qty
    if event.key in (pygame.K_ESCAPE,pygame.K_e): close_shop(); return
    st=ship.docked
    if shop_type=="fuel":
        max_buy=max(0,int(SHIP_FUEL_MAX-ship.fuel))
        if event.key==pygame.K_TAB: shop_tab=(shop_tab+1)%2
        elif shop_tab==0:
            if event.key==pygame.K_LEFT:  shop_qty=max(0,shop_qty-5)
            if event.key==pygame.K_RIGHT: shop_qty=min(max_buy,shop_qty+5)
            if event.key in (pygame.K_RETURN,pygame.K_SPACE):
                qty=min(shop_qty,max_buy); cost=int(qty*st["fuel_price"])
                if qty<=0: shop_status("Tank is already full!")
                elif cost>ship.credits: shop_status(f"Need {cost} CR!")
                else:
                    ship.credits-=cost; ship.fuel=min(SHIP_FUEL_MAX,ship.fuel+qty)
                    shop_status(f"Loaded {qty}u fuel  (-{cost} CR)")
        else:
            hm=SHIP_HP_MAX-ship.hp
            if event.key==pygame.K_LEFT:  shop_qty=max(0,shop_qty-10)
            if event.key==pygame.K_RIGHT: shop_qty=min(hm,shop_qty+10)
            if event.key in (pygame.K_RETURN,pygame.K_SPACE):
                qty=min(shop_qty,hm); cost=qty*REPAIR_COST
                if qty<=0: shop_status("Hull fully intact!")
                elif cost>ship.credits: shop_status(f"Need {cost} CR!")
                else:
                    ship.credits-=cost; ship.hp=min(SHIP_HP_MAX,ship.hp+qty)
                    shop_status(f"Repaired {qty} HP  (-{cost} CR)")
        return
    cargo_list=list(ship.cargo.keys()); n=len(GOODS) if shop_tab==0 else len(cargo_list)
    if event.key==pygame.K_TAB:   shop_tab=1-shop_tab; shop_sel=0; shop_qty=1; return
    if event.key==pygame.K_UP:    shop_sel=max(0,shop_sel-1)
    if event.key==pygame.K_DOWN:  shop_sel=min(max(0,n-1),shop_sel+1)
    if event.key==pygame.K_LEFT:  shop_qty=max(1,shop_qty-1)
    if event.key==pygame.K_RIGHT: shop_qty=min(20,shop_qty+1)
    if event.key in (pygame.K_RETURN,pygame.K_SPACE):
        if shop_tab==0:
            if shop_sel<len(GOODS):
                gn,gb=GOODS[shop_sel]; price=st["prices"][gn]
                qty=min(shop_qty,st["stock"][gn],ship.cap-ship.cargo_used); cost=price*qty
                if qty==0: shop_status("No stock or cargo full!")
                elif cost>ship.credits: shop_status("Not enough credits!")
                else:
                    ship.credits-=cost; ship.cargo[gn]=ship.cargo.get(gn,0)+qty
                    st["stock"][gn]-=qty; shop_status(f"Bought {qty}x {gn}  -{cost} CR")
        else:
            if shop_sel<len(cargo_list):
                gn=cargo_list[shop_sel]; qty=min(shop_qty,ship.cargo.get(gn,0))
                price=st["prices"][gn]; earn=price*qty
                if qty==0: shop_status("Nothing to sell!")
                else:
                    ship.credits+=earn; ship.cargo[gn]-=qty
                    st["stock"][gn]=st["stock"].get(gn,0)+qty
                    if ship.cargo[gn]<=0:
                        del ship.cargo[gn]; shop_sel=min(shop_sel,max(0,len(ship.cargo)-1))
                    shop_status(f"Sold {qty}x {gn}  +{earn} CR")

def draw_shop():
    global shop_msg_t
    st=ship.docked; pw,phh=740,550; px=W//2-pw//2; py=H//2-phh//2
    panel=pygame.Surface((pw,phh),pygame.SRCALPHA); panel.fill((244,244,249,248))
    screen.blit(panel,(px,py)); pygame.draw.rect(screen,BLACK,(px,py,pw,phh),2)
    if shop_type=="fuel":
        txt(screen,f"DEPOT  |  {st['name']}",FLG,C_ORANGE,px+18,py+14)
        txt(screen,f"{ship.credits:,} CR",FMD,C_YELL,px+pw-200,py+22)
        for i,label in enumerate(["  FUEL  ","  REPAIR  "]):
            bx3=px+18+i*140; bg=LGRAY if i==shop_tab else(244,244,249); bd=BLACK if i==shop_tab else GRAY
            pygame.draw.rect(screen,bg,(bx3,py+58,130,28)); pygame.draw.rect(screen,bd,(bx3,py+58,130,28),1)
            txt(screen,label,FMD,bd,bx3+65,py+63,anchor="tc")
        cy2=py+105
        if shop_tab==0:
            txt(screen,"Current fuel:",FMD,BLACK,px+30,cy2); cy2+=28
            bw3=pw-60; ff=int(bw3*ship.fuel/SHIP_FUEL_MAX); fc=C_CYAN if ship.fuel>30 else C_ORANGE
            pygame.draw.rect(screen,LGRAY,(px+30,cy2,bw3,20)); pygame.draw.rect(screen,fc,(px+30,cy2,ff,20))
            txt(screen,f" {ship.fuel:.1f} / {SHIP_FUEL_MAX:.0f}",FSM,BLACK,px+30,cy2+22); cy2+=52
            txt(screen,f"Price:  {st['fuel_price']} CR/u",FMD,BLACK,px+30,cy2); cy2+=36
            dq=min(shop_qty,max(0,int(SHIP_FUEL_MAX-ship.fuel)))
            txt(screen,f"Buy:    < {dq:3} units >  [LEFT/RIGHT]",FMD,BLACK,px+30,cy2); cy2+=30
            cost2=int(dq*st["fuel_price"])
            txt(screen,f"Cost:   {cost2:,} CR",FMD,C_YELL if cost2<=ship.credits else C_RED,px+30,cy2)
        else:
            hm=SHIP_HP_MAX-ship.hp
            txt(screen,"Hull integrity:",FMD,BLACK,px+30,cy2); cy2+=28
            bw3=pw-60; hf=int(bw3*ship.hp/SHIP_HP_MAX)
            hpc=C_GREEN if ship.hp>60 else(C_YELL if ship.hp>30 else C_RED)
            pygame.draw.rect(screen,LGRAY,(px+30,cy2,bw3,20)); pygame.draw.rect(screen,hpc,(px+30,cy2,hf,20))
            txt(screen,f" {ship.hp} / {SHIP_HP_MAX}",FSM,BLACK,px+30,cy2+22); cy2+=52
            txt(screen,f"Repair:  {REPAIR_COST} CR / HP",FMD,BLACK,px+30,cy2); cy2+=36
            rh=min(shop_qty,hm)
            txt(screen,f"Repair:  < {rh:3} HP >  [LEFT/RIGHT]",FMD,BLACK,px+30,cy2); cy2+=30
            txt(screen,f"Cost:    {rh*REPAIR_COST:,} CR",FMD,C_YELL if rh*REPAIR_COST<=ship.credits else C_RED,px+30,cy2)
            if hm==0: txt(screen,"Hull fully repaired!",FMD,C_GREEN,px+30,cy2+36)
        cy3=py+phh-60
        pygame.draw.line(screen,LGRAY,(px+14,cy3),(px+pw-14,cy3),1)
        txt(screen,"[TAB] Switch   [ENTER] Confirm   [E/ESC] Leave",FSM,DGRAY,px+pw//2,cy3+10,anchor="tc")
        if shop_msg_t>0:
            col=C_GREEN if any(w in shop_msg for w in ["Loaded","Repaired","intact"]) else C_RED
            txt(screen,shop_msg,FMD,col,px+pw//2,py+phh-28,anchor="tc"); shop_msg_t-=1
        return
    txt(screen,f"  {st['name']}",FLG,BLACK,px+18,py+14)
    txt(screen,f"{ship.credits:,} CR",FMD,C_YELL,px+pw-200,py+22)
    ty=py+60
    for i,label in enumerate(["  BUY  ","  SELL  "]):
        bx3=px+18+i*130; bg=LGRAY if i==shop_tab else(244,244,249); bd=BLACK if i==shop_tab else GRAY
        pygame.draw.rect(screen,bg,(bx3,ty,120,28)); pygame.draw.rect(screen,bd,(bx3,ty,120,28),1)
        txt(screen,label,FMD,bd,bx3+60,ty+5,anchor="tc")
    hy=ty+38
    txt(screen,"COMMODITY",FSM,GRAY,px+22,hy); txt(screen,"UNIT PRICE",FSM,GRAY,px+290,hy)
    txt(screen,"STOCK",FSM,GRAY,px+445,hy)
    if shop_tab==1: txt(screen,"OWNED",FSM,GRAY,px+560,hy)
    pygame.draw.line(screen,LGRAY,(px+14,hy+17),(px+pw-14,hy+17),1)
    row_h=32; iy=hy+23; cargo_list=list(ship.cargo.items())
    if shop_tab==0:
        for i,(gn,gb) in enumerate(GOODS):
            ry=iy+i*row_h; price=st["prices"][gn]; stock=st["stock"][gn]; sel=i==shop_sel
            if sel: pygame.draw.rect(screen,(200,212,245),(px+14,ry-2,pw-28,row_h-2))
            col=BLACK if stock>0 else GRAY
            pcol=C_GREEN if price<gb else(C_RED if price>gb*1.2 else col)
            txt(screen,gn,FSM,col,px+24,ry+7); txt(screen,f"{price:>5} CR",FSM,pcol,px+285,ry+7)
            txt(screen,f"{stock:>5}",FSM,col,px+450,ry+7)
    else:
        if not cargo_list: txt(screen,"-- Cargo hold is empty --",FMD,GRAY,px+pw//2,iy+40,anchor="tc")
        for i,(gn,qty) in enumerate(cargo_list):
            ry=iy+i*row_h; price=st["prices"][gn]; sel=i==shop_sel
            if sel: pygame.draw.rect(screen,(200,245,210),(px+14,ry-2,pw-28,row_h-2))
            txt(screen,gn,FSM,BLACK,px+24,ry+7); txt(screen,f"{price:>5} CR",FSM,C_GREEN,px+285,ry+7)
            txt(screen,f"x{qty}",FSM,BLACK,px+450,ry+7)
    if shop_msg_t>0:
        col=C_GREEN if any(w in shop_msg for w in ["Bought","Sold"]) else C_RED
        txt(screen,shop_msg,FSM,col,px+pw//2,py+phh-65,anchor="tc"); shop_msg_t-=1
    by3=py+phh-52
    pygame.draw.line(screen,LGRAY,(px+14,by3),(px+pw-14,by3),1)
    txt(screen,f"QTY: < {shop_qty} >  [LEFT / RIGHT]",FSM,BLACK,px+22,by3+10)
    txt(screen,f"Cargo: {ship.cargo_used}/{ship.cap}",FSM,DGRAY,px+22,by3+28)
    txt(screen,"[ENTER] Confirm   [TAB] Switch   [E/ESC] Undock",FSM,DGRAY,px+pw//2,by3+10,anchor="tc")

# ── DEATH ──────────────────────────────────────────────────────────────────────
death_timer=0
def draw_death_screen():
    global death_timer
    alpha=min(death_timer*5,155)
    surf=pygame.Surface((W,H),pygame.SRCALPHA); surf.fill((180,20,20,alpha)); screen.blit(surf,(0,0))
    if death_timer>18:
        txt(screen,"SHIP DESTROYED",FXL,(255,255,255),W//2,H//2-55,anchor="tc")
        txt(screen,f"HP: 0 / {SHIP_HP_MAX}  —  Credits kept: {ship.credits:,} CR",FMD,(220,180,180),W//2,H//2+5,anchor="tc")
        txt(screen,"Press [SPACE] to respawn at nearest station",FMD,(220,180,180),W//2,H//2+36,anchor="tc")
    death_timer=min(death_timer+1,80)

# ── MAIN LOOP ──────────────────────────────────────────────────────────────────
notify("VOID TRADER v5  |  TAB=phase  E=dock  M=map  F11=fullscreen", C_BLUE)

while True:
    clock.tick(FPS)
    for event in pygame.event.get():
        if event.type==pygame.QUIT: pygame.quit(); sys.exit()
        if event.type==pygame.KEYDOWN:
            if event.key==pygame.K_F11: toggle_fullscreen()
            elif ship.dead:
                if event.key==pygame.K_SPACE:
                    best=None; best_d=1e18
                    for ch in chunks.values():
                        for st in ch["trading"]:
                            d=math.hypot(ship.x-st["x"],ship.y-st["y"])
                            if d<best_d: best_d=d; best=st
                    if best: ship.respawn(best); death_timer=0; notify("Ship restored.",C_GREEN)
            elif dock_state=="minigame":
                handle_dock_key(event)
            elif dock_state=="penalty":
                pass
            elif shop_open:
                handle_shop_key(event)
            else:
                if event.key==pygame.K_ESCAPE:
                    if show_full_map: show_full_map=False
                    else: pygame.quit(); sys.exit()
                elif event.key==pygame.K_m:
                    show_full_map=not show_full_map
                elif event.key==pygame.K_TAB:
                    ship.cycle_phase(); trigger_phase_flash()
                    notify(f">> {PHASES[ship.phase][0]} MODE",PHASES[ship.phase][5])
                elif event.key==pygame.K_e:
                    if ship.docked is None and dock_state is None:
                        docked=False
                        tlist,flist=get_stations_near(ship.x,ship.y,TRADE_HALF*3)
                        # Trading: must be inside + near dock circle
                        for st in tlist:
                            if ship_inside_station(ship.x,ship.y,st) and ship_near_dock(ship.x,ship.y,st):
                                start_dock_minigame(st,"trade"); docked=True; break
                        if not docked:
                            for st in flist:
                                if math.hypot(ship.x-st["x"],ship.y-st["y"])<DOCK_RADIUS*1.2:
                                    start_dock_minigame(st,"fuel"); docked=True; break
                        if not docked:
                            # Hint if near a trade station but outside
                            for st in tlist:
                                if math.hypot(ship.x-st["x"],ship.y-st["y"])<DOCK_RADIUS*3:
                                    hints=["fly in from TOP","fly in from RIGHT",
                                           "fly in from BOTTOM","fly in from LEFT"]
                                    notify(f"Must enter station first — {hints[st['entrance']]}",C_YELL)
                                    docked=True; break
                        if not docked: notify("No station in range",C_RED)

    keys=pygame.key.get_pressed()
    if not shop_open and not ship.dead and dock_state is None and not show_full_map:
        ship.update(keys)
        ship.check_fuel_collisions()
        resolve_trade_walls(ship)
        if ship.dead: death_timer=0
        update_camera()
    elif dock_state=="penalty":
        ship.x+=ship.vx; ship.y+=ship.vy; ship.vx*=0.97; ship.vy*=0.97; update_camera()
    elif ship.dead:
        update_camera()

    screen.fill(BG)
    draw_stars(); draw_trail()
    draw_trading_stations(); draw_fuel_stations()
    if not ship.dead: draw_ship()
    draw_warp_overlay(); draw_phase_flash(); draw_collision_flash()
    draw_hud(); draw_minimap(); draw_notices()
    if dock_state=="minigame":  draw_dock_minigame()
    elif dock_state=="penalty": draw_dock_penalty()
    elif shop_open:             draw_shop()
    if show_full_map:           draw_full_map()
    if ship.dead:               draw_death_screen()
    pygame.display.flip()