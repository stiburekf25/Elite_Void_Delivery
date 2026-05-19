"""
VOID TRADER v2
Controls:
  W/UP       Thrust          TAB        Cycle phase
  A/D ←/→   Rotate          E          Dock / Refuel
  S/DN       Brake           F11        Toggle fullscreen
  SPACE      Respawn (death) ESC        Quit
"""

import pygame, math, random, sys

pygame.init()

# ── DISPLAY ───────────────────────────────────────────────────────────────────
_info = pygame.display.Info()
NATIVE_W, NATIVE_H = _info.current_w, _info.current_h
fullscreen = True
W, H = NATIVE_W, NATIVE_H
screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
pygame.display.set_caption("VOID TRADER")
clock = pygame.time.Clock()
FPS   = 60

def toggle_fullscreen():
    global fullscreen, screen, W, H, cam_x, cam_y
    fullscreen = not fullscreen
    if fullscreen:
        W, H = NATIVE_W, NATIVE_H
        screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
    else:
        W, H = 1280, 720
        screen = pygame.display.set_mode((W, H))
    cam_x = max(0, min(WORLD_W - W, cam_x))
    cam_y = max(0, min(WORLD_H - H, cam_y))

# ── WORLD ─────────────────────────────────────────────────────────────────────
WORLD_W      = 22000
WORLD_H      = 22000
NUM_STARS    = 1400
DOCK_RADIUS  = 90
TRADE_COLL_R = 46
FUEL_COLL_R  = 34
SHIP_R       = 18      # approximate ship collision radius (world units)
SHIP_HP_MAX  = 100
SHIP_FUEL_MAX= 100.0

# ── COLOURS ───────────────────────────────────────────────────────────────────
BG       = (246, 246, 250)
BLACK    = (12,  12,  18)
DGRAY    = (70,  70,  80)
GRAY     = (140, 140, 150)
LGRAY    = (210, 210, 218)
C_GREEN  = (45,  180, 95)
C_BLUE   = (55,  115, 225)
C_RED    = (210, 65,  65)
C_YELL   = (205, 172, 35)
C_CYAN   = (50,  190, 190)
C_ORANGE = (220, 130, 50)

# ── FLIGHT PHASES ─────────────────────────────────────────────────────────────
# (name, max_spd, accel, drag, trail_rgb, hud_rgb, fuel_drain_per_frame)
PHASES = [
    ("SUBLIGHT", 4.5,  0.10,  0.975, (110,110,125), C_GREEN,  0.012),
    ("CRUISE",   19.0, 0.65,  0.990, (70, 110,220), C_BLUE,   0.040),
    ("WARP",     58.0, 3.20,  0.998, (220, 75, 75), C_RED,    0.140),
]
PHASE_DAMAGE = [0, 20, 42]   # HP lost on collision per phase

# ── GOODS ─────────────────────────────────────────────────────────────────────
GOODS = [
    ("Minerals",    48), ("Food",     27), ("Electronics", 165),
    ("Fuel Cells",  88), ("Arms",    245), ("Medicine",    115),
    ("Alloys",      72), ("Luxury",  310),
]

TRADE_NAMES = [
    "Kepler Station","Nova Reach","Helios Port","Cygnus Base",
    "Delta Outpost","Frontier Hub","Orion Dock","Vega Terminal",
    "Proxima Yard","Lyra Beacon","Sirius Market","Tau Ceti Port",
]
FUEL_NAMES = [
    "Fuel Depot A","Gas Point B","Refinery C","Pump Station D",
    "Energy Post E","Fuel Bay F","Reactor G","Depot H",
]

# ── FONTS ─────────────────────────────────────────────────────────────────────
def try_font(names, size):
    for n in names:
        try:
            f = pygame.font.SysFont(n, size)
            f.render("A", True, BLACK)
            return f
        except Exception:
            pass
    return pygame.font.Font(None, size + 4)

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

# ── WORLD GENERATION ──────────────────────────────────────────────────────────
rng = random.Random(2025)

stars = [
    (rng.randint(0, WORLD_W), rng.randint(0, WORLD_H),
     rng.choice([1,1,1,2,2,3]), rng.randint(135, 195))
    for _ in range(NUM_STARS)
]

def gen_world():
    trade_st, fuel_st = [], []
    occupied = []
    margin = 1500

    for name in TRADE_NAMES:
        for _ in range(600):
            x = rng.randint(margin, WORLD_W - margin)
            y = rng.randint(margin, WORLD_H - margin)
            if all(math.hypot(x-p[0], y-p[1]) > 2200 for p in occupied):
                prices = {g: max(5, int(b * rng.uniform(0.60, 1.55))) for g,b in GOODS}
                stock  = {g: rng.randint(0, 50)                        for g,b in GOODS}
                trade_st.append({"x":x,"y":y,"name":name,"prices":prices,"stock":stock,
                                  "rot":rng.uniform(0,360),"coll_r":TRADE_COLL_R})
                occupied.append((x, y))
                break

    for name in FUEL_NAMES:
        for _ in range(600):
            x = rng.randint(margin, WORLD_W - margin)
            y = rng.randint(margin, WORLD_H - margin)
            if all(math.hypot(x-p[0], y-p[1]) > 1600 for p in occupied):
                fp = rng.randint(6, 28)
                fuel_st.append({"x":x,"y":y,"name":name,"fuel_price":fp,
                                 "rot":rng.uniform(0,360),"coll_r":FUEL_COLL_R})
                occupied.append((x, y))
                break

    return trade_st, fuel_st

trading_st, fuel_st = gen_world()
ALL_STATIONS = trading_st + fuel_st

# ── FOG OF WAR ────────────────────────────────────────────────────────────────
CELL   = 180                          # world units per fog cell
GRID_W = WORLD_W // CELL + 2
GRID_H = WORLD_H // CELL + 2
EXPL_R = 7                            # reveal radius in cells
explored   = set()
fog_dirty  = True

def do_explore(wx, wy):
    global fog_dirty
    cx = int(wx / CELL)
    cy = int(wy / CELL)
    for dx in range(-EXPL_R, EXPL_R + 1):
        for dy in range(-EXPL_R, EXPL_R + 1):
            if dx*dx + dy*dy <= EXPL_R*EXPL_R:
                cell = (cx + dx, cy + dy)
                if cell not in explored:
                    explored.add(cell)
                    fog_dirty = True

# ── SHIP ──────────────────────────────────────────────────────────────────────
SHIP_PTS = [(0,-24),(13,10),(7,4),(0,14),(-7,4),(-13,10)]

class Ship:
    def __init__(self, x, y):
        self.x      = float(x)
        self.y      = float(y)
        self.angle  = 0.0
        self.vx     = 0.0
        self.vy     = 0.0
        self.phase  = 0
        self.cooldown = 0
        self.credits  = 5000
        self.cargo    = {}
        self.cap      = 24
        self.trail    = []
        self.docked   = None
        self.thrust_glow   = 0
        self.hp            = SHIP_HP_MAX
        self.fuel          = SHIP_FUEL_MAX
        self.coll_flash    = 0
        self.dead          = False
        self.no_fuel_warn  = 0

    @property
    def cargo_used(self): return sum(self.cargo.values())

    def rotated(self, cx, cy, scale=1.0):
        a  = math.radians(self.angle)
        ca, sa = math.cos(a), math.sin(a)
        return [(cx + (px*ca - py*sa)*scale, cy + (px*sa + py*ca)*scale)
                for px, py in SHIP_PTS]

    def respawn(self, st):
        self.x      = st["x"] + rng.uniform(-10, 10)
        self.y      = st["y"] + rng.uniform(-10, 10)
        self.vx = self.vy = 0
        self.angle  = 0
        self.phase  = 0
        self.hp     = SHIP_HP_MAX
        self.fuel   = SHIP_FUEL_MAX
        self.cargo  = {}
        self.credits= max(500, self.credits)
        self.trail  = []
        self.dead   = False
        self.coll_flash = 0
        self.cooldown   = 0

    def take_damage(self, dmg):
        self.hp = max(0, self.hp - dmg)
        self.coll_flash = 35
        if self.hp <= 0:
            self.dead = True

    def update(self, keys):
        if self.docked or self.dead:
            self.vx *= 0.8; self.vy *= 0.8
            self.thrust_glow = max(0, self.thrust_glow - 1)
            return
        if self.cooldown > 0:     self.cooldown -= 1
        if self.coll_flash > 0:   self.coll_flash -= 1
        if self.no_fuel_warn > 0: self.no_fuel_warn -= 1

        _, max_spd, accel, drag, _, _, fdrain = PHASES[self.phase]

        rot = [4.5, 3.0, 1.5][self.phase]
        if keys[pygame.K_LEFT]  or keys[pygame.K_a]: self.angle -= rot
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: self.angle += rot

        thrusting = keys[pygame.K_UP] or keys[pygame.K_w]
        if thrusting and self.fuel > 0:
            a = math.radians(self.angle)
            self.vx += math.sin(a) * accel
            self.vy -= math.cos(a) * accel
            self.fuel = max(0.0, self.fuel - fdrain)
            self.thrust_glow = rng.randint(5, 10)
        elif thrusting and self.fuel <= 0:
            if self.no_fuel_warn == 0:
                notify("OUT OF FUEL — dock at a fuel station!", C_ORANGE)
                self.no_fuel_warn = 180
            self.thrust_glow = max(0, self.thrust_glow - 1)
        else:
            self.thrust_glow = max(0, self.thrust_glow - 1)

        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.vx *= 0.92; self.vy *= 0.92

        spd = math.hypot(self.vx, self.vy)
        if spd > max_spd:
            f = max_spd / spd; self.vx *= f; self.vy *= f

        self.vx *= drag; self.vy *= drag
        self.x = max(50, min(WORLD_W - 50, self.x + self.vx))
        self.y = max(50, min(WORLD_H - 50, self.y + self.vy))

        self.trail.append((self.x, self.y, self.phase))
        ml = [35, 55, 110][self.phase]
        if len(self.trail) > ml: self.trail.pop(0)

        do_explore(self.x, self.y)

    def check_collisions(self):
        if self.docked or self.dead: return
        for st in ALL_STATIONS:
            cr   = st["coll_r"]
            dist = math.hypot(self.x - st["x"], self.y - st["y"])
            if dist < cr + SHIP_R:
                if dist < 1: dist = 1
                nx = (self.x - st["x"]) / dist
                ny = (self.y - st["y"]) / dist
                overlap = cr + SHIP_R - dist
                self.x += nx * overlap
                self.y += ny * overlap
                # Bounce
                dot = self.vx * nx + self.vy * ny
                if dot < 0:
                    self.vx -= 2 * dot * nx
                    self.vy -= 2 * dot * ny
                self.vx *= 0.35; self.vy *= 0.35
                # Damage in CRUISE / WARP
                if self.phase > 0 and self.coll_flash == 0:
                    dmg = PHASE_DAMAGE[self.phase]
                    old_phase = self.phase
                    self.phase = 0
                    self.cooldown = 45
                    self.take_damage(dmg)
                    notify(f"COLLISION! -{dmg} HP  (phase reset)", C_RED)

    def cycle_phase(self):
        if self.cooldown > 0: return
        self.phase = (self.phase + 1) % 3
        spd = math.hypot(self.vx, self.vy)
        ms  = PHASES[self.phase][1]
        if spd > ms:
            f = ms / spd; self.vx *= f; self.vy *= f
        self.cooldown = 35

# ── INIT SHIP + CAMERA ────────────────────────────────────────────────────────
ship  = Ship(WORLD_W / 2, WORLD_H / 2)
do_explore(ship.x, ship.y)
cam_x = ship.x - W / 2
cam_y = ship.y - H / 2

def w2s(wx, wy): return wx - cam_x, wy - cam_y

def update_camera():
    global cam_x, cam_y
    tx = ship.x - W / 2; ty = ship.y - H / 2
    cam_x += (tx - cam_x) * 0.10
    cam_y += (ty - cam_y) * 0.10
    cam_x = max(0, min(WORLD_W - W, cam_x))
    cam_y = max(0, min(WORLD_H - H, cam_y))

# ── NOTIFICATIONS ─────────────────────────────────────────────────────────────
notices = []
def notify(msg, col=BLACK):
    # Remove duplicate
    notices[:] = [n for n in notices if n[0] != msg]
    notices.append([msg, col, 220])

def draw_notices():
    dead = []
    for i, n in enumerate(notices[:5]):
        s = FMD.render(n[0], True, n[1])
        screen.blit(s, (W//2 - s.get_width()//2, H//2 - 90 + i*30))
        n[2] -= 1
        if n[2] <= 0: dead.append(n)
    for d in dead: notices.remove(d)

# ── FLASH EFFECTS ─────────────────────────────────────────────────────────────
phase_flash = 0
def trigger_phase_flash(): global phase_flash; phase_flash = 22

def draw_phase_flash():
    global phase_flash
    if phase_flash <= 0: return
    col   = PHASES[ship.phase][5]
    alpha = int(phase_flash / 22 * 130)
    surf  = pygame.Surface((W, H), pygame.SRCALPHA)
    surf.fill((*col, alpha))
    screen.blit(surf, (0, 0))
    phase_flash = max(0, phase_flash - 1)

def draw_collision_flash():
    if ship.coll_flash <= 0: return
    alpha = int(ship.coll_flash / 35 * 190)
    surf  = pygame.Surface((W, H), pygame.SRCALPHA)
    surf.fill((215, 35, 35, alpha))
    screen.blit(surf, (0, 0))

# ── DRAW STARS ────────────────────────────────────────────────────────────────
def draw_stars():
    warp    = ship.phase == 2
    spd     = math.hypot(ship.vx, ship.vy)
    stretch = min(spd / 4.5, 10.0) if warp else 0
    a = math.radians(ship.angle); sa, ca = math.sin(a), math.cos(a)
    for sx, sy, sr, sb in stars:
        scx, scy = w2s(sx, sy)
        if not (-60 < scx < W + 60 and -60 < scy < H + 60): continue
        c = (sb, sb, sb)
        if stretch > 0.5:
            dx = sa * sr * stretch * 1.8; dy = -ca * sr * stretch * 1.8
            pygame.draw.line(screen, c,
                             (int(scx-dx), int(scy-dy)), (int(scx+dx), int(scy+dy)),
                             max(1, sr-1))
        else:
            pygame.draw.circle(screen, c, (int(scx), int(scy)), sr)

# ── DRAW TRAIL ────────────────────────────────────────────────────────────────
def draw_trail():
    n = len(ship.trail)
    for i, (tx, ty, ph) in enumerate(ship.trail):
        sx, sy = w2s(tx, ty)
        t  = i / max(1, n - 1)
        tc = PHASES[ph][4]
        c  = tuple(int(v * t) for v in tc)
        sz = max(1, int(t * (1 + ph)))
        pygame.draw.circle(screen, c, (int(sx), int(sy)), sz)

# ── DRAW SHIP ─────────────────────────────────────────────────────────────────
def draw_ship():
    if ship.dead: return
    sx, sy = w2s(ship.x, ship.y)
    pts = ship.rotated(sx, sy)
    col = BLACK if ship.coll_flash % 4 < 2 else C_RED
    pygame.draw.polygon(screen, col, pts)
    if ship.thrust_glow > 0:
        a  = math.radians(ship.angle)
        ex = sx - math.sin(a) * 14; ey = sy + math.cos(a) * 14
        gc = PHASES[ship.phase][5]
        pygame.draw.circle(screen, gc, (int(ex), int(ey)),
                           ship.thrust_glow + rng.randint(0, 3))

# ── DRAW TRADING STATIONS ─────────────────────────────────────────────────────
def draw_trading_stations():
    for st in trading_st:
        sx, sy = w2s(st["x"], st["y"])
        if not (-130 < sx < W+130 and -130 < sy < H+130): continue
        st["rot"] = (st["rot"] + 0.12) % 360
        for n_sides, radius, col, width in [(6, 40, BLACK, 2), (6, 24, DGRAY, 1)]:
            pts = [(sx + math.cos(math.radians(st["rot"]+i*(360/n_sides)))*radius,
                    sy + math.sin(math.radians(st["rot"]+i*(360/n_sides)))*radius)
                   for i in range(n_sides)]
            pygame.draw.polygon(screen, col, pts, width)
        pygame.draw.circle(screen, DGRAY, (int(sx), int(sy)), 7)
        pygame.draw.circle(screen, BLACK, (int(sx), int(sy)), 7, 1)
        txt(screen, st["name"], FSM, DGRAY, sx, sy - 58, anchor="tc")
        dist = math.hypot(ship.x - st["x"], ship.y - st["y"])
        if dist < DOCK_RADIUS * 2.2 and ship.docked is None:
            pygame.draw.circle(screen, C_GREEN, (int(sx), int(sy)), DOCK_RADIUS, 1)
            txt(screen, "[E] DOCK", FSM, C_GREEN, sx, sy + 56, anchor="tc")

# ── DRAW FUEL STATIONS ────────────────────────────────────────────────────────
def draw_fuel_stations():
    for st in fuel_st:
        sx, sy = w2s(st["x"], st["y"])
        if not (-90 < sx < W+90 and -90 < sy < H+90): continue
        st["rot"] = (st["rot"] + 0.22) % 360
        r  = 28
        a  = math.radians(st["rot"])
        ca, sa = math.cos(a), math.sin(a)
        base_pts = [(sx, sy-r), (sx+r, sy), (sx, sy+r), (sx-r, sy)]
        rpts = [(sx + (px-sx)*ca - (py-sy)*sa,
                 sy + (px-sx)*sa + (py-sy)*ca) for px,py in base_pts]
        pygame.draw.polygon(screen, C_ORANGE, rpts, 2)
        pygame.draw.circle(screen, C_ORANGE, (int(sx), int(sy)), 5)
        txt(screen, st["name"],              FSM, C_ORANGE, sx, sy - 42, anchor="tc")
        txt(screen, f"{st['fuel_price']} CR/u", FSM, C_ORANGE, sx, sy + 38, anchor="tc")
        dist = math.hypot(ship.x - st["x"], ship.y - st["y"])
        if dist < DOCK_RADIUS * 1.5 and ship.docked is None:
            pygame.draw.circle(screen, C_ORANGE, (int(sx), int(sy)), int(DOCK_RADIUS*0.75), 1)
            txt(screen, "[E] REFUEL", FSM, C_ORANGE, sx, sy + 54, anchor="tc")

# ── WARP OVERLAY ──────────────────────────────────────────────────────────────
def draw_warp_overlay():
    if ship.phase != 2: return
    spd   = math.hypot(ship.vx, ship.vy)
    ratio = min(spd / PHASES[2][1], 1.0)
    alpha = int(ratio * 72)
    if alpha < 3: return
    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    edge = 60
    for i in range(edge):
        a = int(alpha * (i/edge)**2)
        r, g, b = PHASES[2][4]
        for rect in [(i,0,1,H),(W-i-1,0,1,H),(0,i,W,1),(0,H-i-1,W,1)]:
            surf.fill((r,g,b,a), rect)
    screen.blit(surf, (0,0))

# ── HUD ───────────────────────────────────────────────────────────────────────
def draw_hud():
    pname, max_spd, *_, hcol, fdrain = PHASES[ship.phase]
    spd = math.hypot(ship.vx, ship.vy)

    # ─ Status panel (top-left) ─
    pw, ph_h = 268, 190
    s = pygame.Surface((pw, ph_h), pygame.SRCALPHA)
    s.fill((246, 246, 250, 210))
    screen.blit(s, (10, 10))
    pygame.draw.rect(screen, BLACK, (10, 10, pw, ph_h), 1)

    txt(screen, "VOID TRADER", FSM, GRAY, 20, 15)
    txt(screen, f">> {pname}", FMD, hcol, 20, 29)

    bw = pw - 30
    def bar(label, val, mx, col, y_off):
        fill = int(bw * max(0, min(val/mx, 1.0)))
        pygame.draw.rect(screen, LGRAY, (20, y_off, bw, 8))
        pygame.draw.rect(screen, col,   (20, y_off, fill, 8))
        txt(screen, f"{label}  {val:{'.0f' if isinstance(val,float) else 'd'}} / {mx:.0f}",
            FSM, col, 20, y_off + 10)

    bar("SPD",  spd,          max_spd,     hcol, 54)
    # HP bar
    hp_col = C_GREEN if ship.hp > 60 else (C_YELL if ship.hp > 30 else C_RED)
    bar("HP ",  ship.hp,      SHIP_HP_MAX, hp_col, 80)
    # Fuel bar
    fu_col = C_CYAN if ship.fuel > 30 else (C_ORANGE if ship.fuel > 10 else C_RED)
    bar("FUEL", ship.fuel,    SHIP_FUEL_MAX, fu_col, 106)

    txt(screen, f"CR    {ship.credits:>10,}", FSM, C_YELL, 20, 130)
    txt(screen, f"CARGO   {ship.cargo_used:2} / {ship.cap}", FSM, DGRAY, 20, 147)

    # Phase dots
    for i in range(3):
        col = PHASES[i][5] if i == ship.phase else LGRAY
        bd  = BLACK if i == ship.phase else GRAY
        pygame.draw.circle(screen, col, (20 + i*25, 180), 8)
        pygame.draw.circle(screen, bd,  (20 + i*25, 180), 8, 1)

    # ─ Inventory panel (below status) ─
    iw = pw
    cargo_items = list(ship.cargo.items())
    ih = 28 + max(1, len(cargo_items)) * 18 + 4
    iy = 10 + ph_h + 8
    inv = pygame.Surface((iw, ih), pygame.SRCALPHA)
    inv.fill((246, 246, 250, 210))
    screen.blit(inv, (10, iy))
    pygame.draw.rect(screen, BLACK, (10, iy, iw, ih), 1)
    txt(screen, "INVENTORY", FSM, GRAY, 20, iy + 7)
    if not cargo_items:
        txt(screen, "  -- empty --", FSM, LGRAY, 20, iy + 22)
    for j, (gname, qty) in enumerate(cargo_items):
        txt(screen, f"  {gname:<14} x{qty}", FSM, DGRAY, 20, iy + 22 + j*18)

    # ─ Hints (top-right) ─
    hints = ["[TAB]   Phase", "[E]     Dock/Refuel",
             "[W/UP]  Thrust","[A/D]   Turn",
             "[S/DN]  Brake", "[F11]   Fullscreen"]
    for i, h in enumerate(hints):
        txt(screen, h, FSM, GRAY, W - 172, 15 + i*17)

# ── MINIMAP ───────────────────────────────────────────────────────────────────
_fog_surf  = None
_fog_dirty = True

def _rebuild_fog(mw, mh):
    global _fog_surf, _fog_dirty
    surf = pygame.Surface((mw, mh))
    surf.fill((28, 28, 38))
    cpw = mw / GRID_W; cph = mh / GRID_H
    for cx, cy in explored:
        if 0 <= cx < GRID_W and 0 <= cy < GRID_H:
            pygame.draw.rect(surf, (220, 220, 228),
                             (int(cx*cpw), int(cy*cph),
                              max(1, int(cpw)+1), max(1, int(cph)+1)))
    _fog_surf  = surf
    _fog_dirty = False

def draw_minimap():
    global _fog_dirty
    mw, mh = 224, 184
    mx, my = W - mw - 10, H - mh - 10

    if fog_dirty or _fog_surf is None:
        _rebuild_fog(mw, mh)

    screen.blit(_fog_surf, (mx, my))
    pygame.draw.rect(screen, BLACK, (mx, my, mw, mh), 1)

    def m(wx, wy):
        return mx + int(wx/WORLD_W*mw), my + int(wy/WORLD_H*mh)

    # Stations — only show if explored
    for st in trading_st:
        scx, scy = int(st["x"]/CELL), int(st["y"]/CELL)
        if any((scx+dx, scy+dy) in explored for dx in range(-2,3) for dy in range(-2,3)):
            smx, smy = m(st["x"], st["y"])
            pygame.draw.circle(screen, DGRAY, (smx, smy), 3)

    for st in fuel_st:
        scx, scy = int(st["x"]/CELL), int(st["y"]/CELL)
        if any((scx+dx, scy+dy) in explored for dx in range(-2,3) for dy in range(-2,3)):
            smx, smy = m(st["x"], st["y"])
            pygame.draw.circle(screen, C_ORANGE, (smx, smy), 3)

    # Viewport rect
    vx1, vy1 = m(cam_x, cam_y)
    vw = max(1, int(W/WORLD_W*mw)); vh = max(1, int(H/WORLD_H*mh))
    pygame.draw.rect(screen, GRAY, (vx1, vy1, vw, vh), 1)

    # Ship
    sx, sy = m(ship.x, ship.y)
    pygame.draw.circle(screen, BLACK, (sx, sy), 3)

    txt(screen, "MAP",  FSM, (180,180,190), mx+6, my+5)

# ── DEATH SCREEN ──────────────────────────────────────────────────────────────
death_timer = 0

def draw_death_screen():
    global death_timer
    alpha = min(death_timer * 5, 155)
    surf  = pygame.Surface((W, H), pygame.SRCALPHA)
    surf.fill((180, 20, 20, alpha))
    screen.blit(surf, (0,0))
    if death_timer > 18:
        txt(screen, "SHIP DESTROYED", FXL, (255,255,255), W//2, H//2 - 55, anchor="tc")
        txt(screen, f"HP: 0 / {SHIP_HP_MAX}  —  Credits kept: {ship.credits:,} CR",
            FMD, (220,180,180), W//2, H//2 + 5, anchor="tc")
        txt(screen, "Press [SPACE] to respawn at nearest station",
            FMD, (220,180,180), W//2, H//2 + 36, anchor="tc")
    death_timer = min(death_timer + 1, 80)

# ── SHOP ──────────────────────────────────────────────────────────────────────
shop_open  = False
shop_type  = "trade"
shop_tab   = 0
shop_sel   = 0
shop_qty   = 1
shop_msg   = ""
shop_msg_t = 0

def open_shop(st, stype):
    global shop_open, shop_type, shop_tab, shop_sel, shop_qty
    ship.docked = st; shop_open = True; shop_type = stype
    shop_tab = 0;     shop_sel  = 0
    shop_qty = min(20, max(1, int(SHIP_FUEL_MAX - ship.fuel))) if stype == "fuel" else 1

def close_shop():
    global shop_open
    ship.docked = None; shop_open = False

def shop_status(msg):
    global shop_msg, shop_msg_t
    shop_msg = msg; shop_msg_t = 200

def handle_shop_key(event):
    global shop_tab, shop_sel, shop_qty
    if event.key in (pygame.K_ESCAPE, pygame.K_e):
        close_shop(); return

    st = ship.docked

    # ─ Fuel shop ─
    if shop_type == "fuel":
        max_buy = max(0, int(SHIP_FUEL_MAX - ship.fuel))
        if event.key == pygame.K_LEFT:  shop_qty = max(0,       shop_qty - 5)
        if event.key == pygame.K_RIGHT: shop_qty = min(max_buy, shop_qty + 5)
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            qty  = min(shop_qty, max_buy)
            cost = int(qty * st["fuel_price"])
            if qty <= 0:
                shop_status("Tank is already full!")
            elif cost > ship.credits:
                shop_status(f"Need {cost} CR, have {ship.credits} CR!")
            else:
                ship.credits -= cost
                ship.fuel = min(SHIP_FUEL_MAX, ship.fuel + qty)
                shop_status(f"Loaded {qty}u fuel  (-{cost} CR)")
        return

    # ─ Trade shop ─
    cargo_list = list(ship.cargo.keys())
    n = len(GOODS) if shop_tab == 0 else len(cargo_list)

    if event.key == pygame.K_TAB:
        shop_tab = 1 - shop_tab; shop_sel = 0; shop_qty = 1; return
    if event.key == pygame.K_UP:   shop_sel = max(0,      shop_sel - 1)
    if event.key == pygame.K_DOWN: shop_sel = min(max(0,n-1), shop_sel + 1)
    if event.key == pygame.K_LEFT:  shop_qty = max(1,  shop_qty - 1)
    if event.key == pygame.K_RIGHT: shop_qty = min(20, shop_qty + 1)

    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
        if shop_tab == 0:   # BUY
            if shop_sel < len(GOODS):
                gname, gbase = GOODS[shop_sel]
                price = st["prices"][gname]
                qty   = min(shop_qty, st["stock"][gname], ship.cap - ship.cargo_used)
                cost  = price * qty
                if qty == 0:   shop_status("No stock or cargo full!")
                elif cost > ship.credits: shop_status("Not enough credits!")
                else:
                    ship.credits -= cost
                    ship.cargo[gname] = ship.cargo.get(gname, 0) + qty
                    st["stock"][gname] -= qty
                    shop_status(f"Bought {qty}x {gname}  -{cost} CR")
        else:               # SELL
            if shop_sel < len(cargo_list):
                gname = cargo_list[shop_sel]
                qty   = min(shop_qty, ship.cargo.get(gname, 0))
                price = st["prices"][gname]
                earn  = price * qty
                if qty == 0: shop_status("Nothing to sell!")
                else:
                    ship.credits += earn
                    ship.cargo[gname] -= qty
                    st["stock"][gname] = st["stock"].get(gname, 0) + qty
                    if ship.cargo[gname] <= 0:
                        del ship.cargo[gname]
                        shop_sel = min(shop_sel, max(0, len(ship.cargo)-1))
                    shop_status(f"Sold {qty}x {gname}  +{earn} CR")

def draw_shop():
    global shop_msg_t
    st = ship.docked
    pw, ph_h = 740, 530
    px = W//2 - pw//2; py = H//2 - ph_h//2

    panel = pygame.Surface((pw, ph_h), pygame.SRCALPHA)
    panel.fill((244, 244, 249, 248))
    screen.blit(panel, (px, py))
    pygame.draw.rect(screen, BLACK, (px, py, pw, ph_h), 2)

    # ─ Fuel shop ─
    if shop_type == "fuel":
        txt(screen, f"FUEL DEPOT  |  {st['name']}", FLG, C_ORANGE, px+18, py+14)
        txt(screen, f"{ship.credits:,} CR", FMD, C_YELL, px+pw-200, py+22)

        cy = py + 75
        txt(screen, f"Current fuel:", FMD, BLACK, px+30, cy)
        cy += 28
        bw = pw - 60
        ff = int(bw * ship.fuel/SHIP_FUEL_MAX)
        fc = C_CYAN if ship.fuel > 30 else C_ORANGE
        pygame.draw.rect(screen, LGRAY, (px+30, cy, bw, 20))
        pygame.draw.rect(screen, fc,    (px+30, cy, ff, 20))
        txt(screen, f" {ship.fuel:.1f} / {SHIP_FUEL_MAX:.0f}", FSM, BLACK, px+30, cy+22)
        cy += 52
        txt(screen, f"Price:  {st['fuel_price']} CR per unit", FMD, BLACK, px+30, cy)
        cy += 36
        display_qty = min(shop_qty, max(0, int(SHIP_FUEL_MAX - ship.fuel)))
        txt(screen, f"Buy:    < {display_qty:3} units >  [LEFT/RIGHT to change]",
            FMD, BLACK, px+30, cy)
        cy += 30
        cost = int(display_qty * st["fuel_price"])
        txt(screen, f"Cost:   {cost:,} CR", FMD, C_YELL if cost <= ship.credits else C_RED,
            px+30, cy)
        cy += 55
        txt(screen, "[ENTER] Buy   [E / ESC] Leave depot", FSM, DGRAY, px+30, cy)
        if shop_msg_t > 0:
            good = any(w in shop_msg for w in ["Loaded","full"])
            col  = C_GREEN if good else C_RED
            txt(screen, shop_msg, FMD, col, px+pw//2, py+ph_h-55, anchor="tc")
            shop_msg_t -= 1
        return

    # ─ Trade shop ─
    txt(screen, f"  {st['name']}", FLG, BLACK, px+18, py+14)
    txt(screen, f"{ship.credits:,} CR", FMD, C_YELL, px+pw-200, py+22)

    ty = py + 60
    for i, label in enumerate(["  BUY  ", "  SELL  "]):
        bx = px + 18 + i*130
        bg = LGRAY if i == shop_tab else (244,244,249)
        bd = BLACK if i == shop_tab else GRAY
        pygame.draw.rect(screen, bg, (bx, ty, 120, 28))
        pygame.draw.rect(screen, bd, (bx, ty, 120, 28), 1)
        txt(screen, label, FMD, bd, bx+60, ty+5, anchor="tc")

    hy = ty + 38
    txt(screen, "COMMODITY",  FSM, GRAY, px+22, hy)
    txt(screen, "UNIT PRICE", FSM, GRAY, px+290, hy)
    txt(screen, "STOCK",      FSM, GRAY, px+445, hy)
    if shop_tab == 1:
        txt(screen, "OWNED", FSM, GRAY, px+560, hy)
    pygame.draw.line(screen, LGRAY, (px+14, hy+17), (px+pw-14, hy+17), 1)

    row_h = 32; iy = hy + 23
    cargo_list = list(ship.cargo.items())

    if shop_tab == 0:
        for i, (gname, gbase) in enumerate(GOODS):
            ry    = iy + i*row_h
            price = st["prices"][gname]
            stock = st["stock"][gname]
            sel   = i == shop_sel
            if sel: pygame.draw.rect(screen,(200,212,245),(px+14,ry-2,pw-28,row_h-2))
            col  = BLACK if stock > 0 else GRAY
            pcol = C_GREEN if price < gbase else (C_RED if price > gbase*1.2 else col)
            txt(screen, gname,            FSM, col,  px+24, ry+7)
            txt(screen, f"{price:>5} CR", FSM, pcol, px+285, ry+7)
            txt(screen, f"{stock:>5}",    FSM, col,  px+450, ry+7)
    else:
        if not cargo_list:
            txt(screen,"-- Cargo hold is empty --",FMD,GRAY,px+pw//2,iy+40,anchor="tc")
        for i, (gname, qty) in enumerate(cargo_list):
            ry    = iy + i*row_h
            price = st["prices"][gname]
            sel   = i == shop_sel
            if sel: pygame.draw.rect(screen,(200,245,210),(px+14,ry-2,pw-28,row_h-2))
            txt(screen, gname,            FSM, BLACK,   px+24, ry+7)
            txt(screen, f"{price:>5} CR", FSM, C_GREEN, px+285, ry+7)
            txt(screen, f"x{qty}",        FSM, BLACK,   px+450, ry+7)

    if shop_msg_t > 0:
        good = any(w in shop_msg for w in ["Bought","Sold"])
        col  = C_GREEN if good else C_RED
        txt(screen, shop_msg, FSM, col, px+pw//2, py+ph_h-65, anchor="tc")
        shop_msg_t -= 1

    by = py + ph_h - 52
    pygame.draw.line(screen, LGRAY, (px+14, by), (px+pw-14, by), 1)
    txt(screen, f"QTY: < {shop_qty} >  [LEFT / RIGHT]", FSM, BLACK, px+22, by+10)
    txt(screen, f"Cargo: {ship.cargo_used}/{ship.cap}", FSM, DGRAY, px+22, by+28)
    txt(screen,"[ENTER] Confirm   [TAB] Switch   [E/ESC] Undock",
        FSM, DGRAY, px+pw//2, by+10, anchor="tc")

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
notify("VOID TRADER v2  |  TAB=phase  E=dock/refuel  F11=fullscreen", C_BLUE)

while True:
    clock.tick(FPS)

    # Sync fog_dirty flag
    if fog_dirty:
        _fog_dirty = True

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit(); sys.exit()

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                toggle_fullscreen()

            elif ship.dead:
                if event.key == pygame.K_SPACE:
                    near = min(trading_st,
                               key=lambda s: math.hypot(s["x"]-ship.x, s["y"]-ship.y))
                    ship.respawn(near)
                    death_timer = 0
                    notify("Ship restored. Keep your speed in check.", C_GREEN)

            elif shop_open:
                handle_shop_key(event)

            else:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                elif event.key == pygame.K_TAB:
                    ship.cycle_phase()
                    trigger_phase_flash()
                    notify(f">> {PHASES[ship.phase][0]} MODE", PHASES[ship.phase][5])
                elif event.key == pygame.K_e:
                    if ship.docked is None:
                        docked = False
                        for st in trading_st:
                            if math.hypot(ship.x-st["x"], ship.y-st["y"]) < DOCK_RADIUS:
                                open_shop(st, "trade")
                                notify(f"Docked at {st['name']}", C_GREEN)
                                docked = True; break
                        if not docked:
                            for st in fuel_st:
                                if math.hypot(ship.x-st["x"],ship.y-st["y"]) < DOCK_RADIUS*1.2:
                                    open_shop(st, "fuel")
                                    notify(f"Refueling at {st['name']}", C_ORANGE)
                                    docked = True; break
                        if not docked:
                            notify("No station in range", C_RED)

    keys = pygame.key.get_pressed()
    if not shop_open and not ship.dead:
        ship.update(keys)
        ship.check_collisions()
        if ship.dead: death_timer = 0
        update_camera()
    elif ship.dead:
        update_camera()

    # ── Draw ──────────────────────────────────────────────────────────────────
    screen.fill(BG)
    draw_stars()
    draw_trail()
    draw_trading_stations()
    draw_fuel_stations()
    if not ship.dead:
        draw_ship()
    draw_warp_overlay()
    draw_phase_flash()
    draw_collision_flash()
    draw_hud()
    draw_minimap()
    draw_notices()
    if shop_open:   draw_shop()
    if ship.dead:   draw_death_screen()

    pygame.display.flip()