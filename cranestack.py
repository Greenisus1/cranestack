#!/usr/bin/env python3
"""cranestack - a 3D block-stacking tower game for the terminal.

Slide, drop, slice. A block sweeps side to side over the tower; drop it so it
lands on the block below. Whatever hangs past the edge gets sliced off and
falls away, and your next block is that much smaller. Miss the tower outright
and the run ends. How tall can you build before the crane wins?

An original game. Built with AI assistance from my design.
MIT License - Copyright (c) 2026 Greenisus1
"""
import argparse, json, math, os, random, select, shutil, sys, termios, time, tty

VERSION = "1.0.0"
RECORD = os.path.expanduser("~/.cranestack-best.json")

START_SIZE = 2.6      # block footprint (x and z) on level 1
BLOCK_H = 0.5
BASE_SPEED = 1.6      # sweep speed, grows per level
SWEEP_RANGE = 3.2     # blocks sweep between -RANGE..+RANGE on their axis
PERFECT_EPS = 0.09    # |offset| under this snaps perfect
GRAV = 9.8

# ---------- mechanics (pure, unit-testable) ----------

class Stack:
    """The tower. blocks: list of dicts {cx, cz, sx, sz, y} (y = base height)."""
    def __init__(self):
        self.blocks = [dict(cx=0.0, cz=0.0, sx=START_SIZE, sz=START_SIZE, y=0.0)]
        self.level = 1
        self.score = 0
        self.combo = 0
        self.over = False

    def top(self): return self.blocks[-1]
    def top_y(self): return self.top()["y"] + BLOCK_H
    def speed(self): return BASE_SPEED + 0.08 * (self.level - 1)
    def sweep_axis(self): return "x" if self.level % 2 == 1 else "z"

    def drop(self, pos):
        """Drop the sweeping block centered at `pos` on the sweep axis.
        Returns (result, overlap_size, offset) - result: 'perfect'|'ok'|'miss'."""
        t = self.top()
        ax = self.sweep_axis()
        size = t["sx"] if ax == "x" else t["sz"]
        center = t["cx"] if ax == "x" else t["cz"]
        lo = max(pos - size / 2, center - size / 2)
        hi = min(pos + size / 2, center + size / 2)
        overlap = hi - lo
        offset = pos - center
        if overlap <= 0:
            self.over = True
            return "miss", 0.0, offset
        if abs(offset) <= PERFECT_EPS:
            self.combo += 1
            ncx, ncz, nsx, nsz = t["cx"], t["cz"], t["sx"], t["sz"]
            result = "perfect"
        else:
            self.combo = 0
            mid = (lo + hi) / 2
            if ax == "x": ncx, ncz, nsx, nsz = mid, t["cz"], overlap, t["sz"]
            else:         ncx, ncz, nsx, nsz = t["cx"], mid, t["sx"], overlap
            result = "ok"
        self.blocks.append(dict(cx=ncx, cz=ncz, sx=nsx, sz=nsz, y=self.top_y()))
        self.level += 1
        self.score += 1 + (self.combo if result == "perfect" else 0)
        return result, overlap, offset

def best():
    try: return int(json.load(open(RECORD)).get("best", 0))
    except Exception: return 0

def save(score):
    try:
        b = best()
        if score > b: json.dump({"best": score}, open(RECORD, "w"))
        return True
    except Exception: return False

# ---------- renderer ----------

def mix(a, b, t):
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))

def hue(i):
    # slow rainbow up the tower
    h = (i * 0.045) % 1.0
    r, g, b = abs(h * 6 - 3) - 1, 2 - abs(h * 6 - 2), 2 - abs(h * 6 - 4)
    cl = lambda v: max(0.0, min(1.0, v))
    return (int(cl(r) * 200 + 40), int(cl(g) * 200 + 40), int(cl(b) * 200 + 40))

FOG = (16, 18, 30)
SKY_TOP = (24, 26, 48); SKY_BOT = (54, 46, 66)

class Scene:
    """Perspective camera orbiting slightly; axis-aligned box tower."""
    def __init__(self, fov=58.0):
        self.set_fov(fov)
    def set_fov(self, fov):
        self.fov = fov; self.scale = math.tan(math.radians(fov) / 2)

    def render(self, st, W, PH, moving, debris, t_now):
        """rows[PH][W] packed RGB ints. moving=(cx,cz,sx,sz,y,axis,pos) or None.
        debris: list of (cx,cz,sx,sz,y,vy)."""
        top_y = st.top_y()
        # camera height follows tower; gentle idle sway
        cy = top_y + 2.6
        sway = math.sin(t_now * 0.35) * 0.35
        cd = 6.8
        cx0, cz0 = math.sin(sway) * 0.8, -cd + math.cos(sway) * 0.0
        tx, ty, tz = 0.0 - cx0, top_y - 0.6 - cy, 0.0 - cz0
        tl = math.sqrt(tx * tx + ty * ty + tz * tz) or 1.0
        fx, fy, fz = tx / tl, ty / tl, tz / tl
        rx, ry, rz = -fz, 0.0, fx
        ux, uy, uz = ry * fz - rz * fy, rz * fx - rx * fz, rx * fy - ry * fx
        aspect = W / max(1, PH)
        boxes = [(0.0, 0.0, 90.0, 90.0, -1.2, 1.2, (46, 48, 68))]  # ground slab (past fog)
        n = len(st.blocks)
        for i, b in enumerate(st.blocks):
            col = hue(i)
            boxes.append((b["cx"], b["cz"], b["sx"], b["sz"], b["y"], BLOCK_H, col))
        if moving:
            cx, cz, sx, sz, y = moving
            boxes.append((cx, cz, sx, sz, y, BLOCK_H, hue(n)))
        for (dx, dz, dsx, dsz, dy, dvy) in debris:
            boxes.append((dx, dz, dsx, dsz, dy, BLOCK_H, (150, 150, 160)))
        LX, LY, LZ = 0.35, 0.85, -0.4
        ll = math.sqrt(LX * LX + LY * LY + LZ * LZ); LX, LY, LZ = LX / ll, LY / ll, LZ / ll
        rows = []
        invph = 2.0 / PH
        for py in range(PH):
            ny = (1.0 - (py + 0.5) * invph) * self.scale
            dy = fy + ny * uy
            row = []
            for px in range(W):
                nx = ((px + 0.5) * 2.0 / W - 1.0) * self.scale * aspect
                dx = fx + nx * rx; dz = fz + nx * rz
                dl = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
                dx, dyy, dz = dx / dl, dy / dl, dz / dl
                # sky gradient
                g = py / max(1, PH - 1)
                shade = mix(SKY_TOP, SKY_BOT, g)
                bt, bcol = 1e9, None
                for (bx, bz, bsx, bsz, by0, bh, col) in boxes:
                    # slab test on AABB centered (bx,bz), y in [by0, by0+bh]
                    t0, t1, nrm = 0.0, 1e9, None
                    ok = True
                    for o, d, s in ((cx0 - bx, dx, bsx), (cy - (by0 + bh / 2), dyy, bh), (cz0 - bz, dz, bsz)):
                        if abs(d) < 1e-9:
                            if abs(o) > s / 2: ok = False; break
                            continue
                        ta = (-s / 2 - o) / d; tb = (s / 2 - o) / d
                        if ta > tb: ta, tb = tb, ta
                        if ta > t0: t0 = ta; nrm = (o, d, s)
                        t1 = min(t1, tb)
                        if t0 > t1: ok = False; break
                    if not ok or t0 <= 0 or t0 >= bt: continue
                    bt = t0; bcol = (col, nrm)
                if bcol is not None:
                    col, (o, d, s) = bcol
                    # face normal from which slab set the entry
                    posv = -o / s  # -1/+1 on entry face
                    if abs(d) < 1e-9: diff = 1.0
                    else:
                        nx2 = 0.0
                        # determine axis by which coordinate saturates at hit
                        hx = cx0 + dx * bt; hy = cy + dyy * bt; hz = cz0 + dz * bt
                        if abs(hy - (by0 + bh)) < 0.02: n2 = (0, 1, 0)
                        elif abs(hy - by0) < 0.02: n2 = (0, -1, 0)
                        elif abs(hx - (bx + bsx / 2)) < 0.02: n2 = (1, 0, 0)
                        elif abs(hx - (bx - bsx / 2)) < 0.02: n2 = (-1, 0, 0)
                        elif abs(hz - (bz + bsz / 2)) < 0.02: n2 = (0, 0, 1)
                        else: n2 = (0, 0, -1)
                        diff = max(0.15, n2[0] * LX + n2[1] * LY + n2[2] * LZ)
                    shade = mix((col[0] // 4, col[1] // 4, col[2] // 4), col, 0.25 + 0.75 * diff)
                    fk = min(1.0, bt / 22.0)
                    shade = mix(shade, FOG, fk * fk * 0.7)
                row.append((shade[0] << 16) | (shade[1] << 8) | shade[2])
            rows.append(row)
        return rows

# ---------- terminal ----------

class Term:
    def __init__(self, mode):
        self.mode = mode; self.prev = None
    def seq(self, c, bg):
        if self.mode == "true":
            r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
            return ("\x1b[48;2;%d;%d;%dm" % (r, g, b)) if bg else ("\x1b[38;2;%d;%d;%dm" % (r, g, b))
        r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
        i = 16 + 36 * round(r / 255 * 5) + 6 * round(g / 255 * 5) + round(b / 255 * 5)
        return ("\x1b[48;5;%dm" % i) if bg else ("\x1b[38;5;%dm" % i)
    def draw(self, rows, hud, fd, fast=False):
        PH = len(rows); W = len(rows[0])
        mag = 2 if fast else 1
        out = ["\x1b[H"]
        if self.prev is None or len(self.prev) != PH or len(self.prev[0]) != W or getattr(self, "_mag", 1) != mag:
            self.prev = None
        self._mag = mag
        for py in range(PH):
            line = []
            for px in range(W):
                top = rows[py][px]
                bot = rows[py + 1][px] if py + 1 < PH else (10 << 16)
                if self.prev is not None and self.prev[py][px] == (top, bot):
                    continue
                line.append("\x1b[%d;%dH" % (py + 1, px * mag + 1) + self.seq(top, False) + self.seq(bot, True) + "\u2580" * mag)
            out.append("".join(line))
        self.prev = [[(rows[py][px], rows[py + 1][px] if py + 1 < PH else (10 << 16)) for px in range(W)] for py in range(PH)]
        out.append("\x1b[0m\x1b[%d;1H\x1b[46;5;17m\x1b[38;5;255m %s \x1b[0m" % (PH + 1, hud))
        os.write(fd, "".join(out).encode())

def detect_colors():
    if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit"): return "true"
    return "256"

# ---------- game loop ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--colors", choices=["auto", "true", "256"], default="auto")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--fast", dest="fast", action="store_true", default=None, help="half horizontal resolution for wide/slow terminals")
    ap.add_argument("--no-fast", dest="fast", action="store_false")
    args = ap.parse_args()
    random.seed(args.seed)
    mode = detect_colors() if args.colors == "auto" else args.colors
    fd = sys.stdout.fileno()
    old = termios.tcgetattr(fd)
    st = Stack(); sc = Scene(); tm = Term(mode)
    fps_modes = [8, 12, 24, 30, 60]; fi = fps_modes.index(args.fps) if args.fps in fps_modes else 2
    pos, dirn = -SWEEP_RANGE, 1
    debris = []; flash = ""; flash_t = 0.0
    paused = False; done = False
    try:
        tty.setcbreak(fd)
        os.write(fd, b"\x1b[?1049h\x1b[?25l\x1b[2J")
        last = time.time(); acc = 0.0
        while not done:
            now = time.time(); dt = min(0.05, now - last); last = now
            while select.select([sys.stdin], [], [], 0)[0]:
                ch = os.read(sys.stdin.fileno(), 8)
                if ch in (b"q", b"Q"): done = True; break
                if ch in (b"p", b"P"): paused = not paused
                if ch in (b"f", b"F"): fi = (fi + 1) % len(fps_modes)
                if ch in (b"[",): sc.set_fov(max(30.0, sc.fov - 4))
                if ch in (b"]",): sc.set_fov(min(110.0, sc.fov + 4))
                if ch in (b" ", b"\r", b"\n") and not paused:
                    if st.over:
                        st = Stack(); debris = []; pos, dirn = -SWEEP_RANGE, 1; flash = ""
                    else:
                        res, overlap, offset = st.drop(pos)
                        if res == "miss":
                            save(st.score)
                            t = st.blocks[-1]; ax = st.sweep_axis()
                            size = t["sx"] if ax == "x" else t["sz"]
                            debris.append([pos, t["cz"] if ax == "x" else t["cx"],
                                           t["sx"] if ax == "x" else size,
                                           t["sz"] if ax == "z" else size, st.top_y(), 0.0])
                            flash = "MISSED! Space to retry"; flash_t = now
                        elif res == "ok":
                            t = st.blocks[-2]; ax = "x" if (st.level - 1) % 2 == 1 else "z"
                            size0 = t["sx"] if ax == "x" else t["sz"]
                            cen0 = t["cx"] if ax == "x" else t["cz"]
                            off_lo = min(pos - size0 / 2, cen0 - size0 / 2)
                            off_hi = max(pos + size0 / 2, cen0 + size0 / 2)
                            if pos > cen0:
                                dcx, dsx = (pos + size0 / 2 + cen0 + size0 / 2) / 2 + overlap / 2, size0 - overlap
                            else:
                                dcx, dsx = (pos - size0 / 2 + cen0 - size0 / 2) / 2 - overlap / 2, size0 - overlap
                            if dsx > 0.01:
                                if ax == "x": debris.append([dcx, t["cz"], dsx, t["sz"], st.top_y() - BLOCK_H, 0.0])
                                else: debris.append([t["cx"], dcx, t["sx"], dsx, st.top_y() - BLOCK_H, 0.0])
                            flash = "sliced"; flash_t = now
                        else:
                            flash = "PERFECT x%d" % st.combo if st.combo > 1 else "PERFECT!"; flash_t = now
                        pos, dirn = -SWEEP_RANGE, 1
            if paused:
                time.sleep(0.05); continue
            if not st.over:
                pos += dirn * st.speed() * dt
                if pos > SWEEP_RANGE: pos, dirn = SWEEP_RANGE, -1
                if pos < -SWEEP_RANGE: pos, dirn = -SWEEP_RANGE, 1
            for d in debris:
                d[5] += GRAV * dt; d[4] -= d[5] * dt
            debris = [d for d in debris if d[4] > st.top_y() - 14]
            ax = st.sweep_axis()
            t = st.top()
            if not st.over:
                if ax == "x": moving = (pos, t["cz"], t["sx"], t["sz"], st.top_y())
                else: moving = (t["cx"], pos, t["sx"], t["sz"], st.top_y())
            else: moving = None
            W, Ht = shutil.get_terminal_size((100, 32))
            fast = args.fast if args.fast is not None else W > 130
            PH = min(Ht - 2, 60); W = min(W, 160)
            rw = W // 2 if fast else W
            rows = sc.render(st, rw, PH, moving, [tuple(d) for d in debris], now)
            hud = "CRANESTACK  SCORE %d  BEST %d  L%d  space drop  [] fov  f fps  p pause  q quit   %s" % (
                st.score, max(best(), st.score), st.level, flash if now - flash_t < 2.5 else "")
            hud += "  [half-res]" if fast else ""
            tm.draw(rows, hud, fd, fast)
            fps = fps_modes[fi]
            time.sleep(max(0.0, 1.0 / fps - (time.time() - now)))
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        os.write(fd, b"\x1b[0m\x1b[?25h\x1b[?1049l")
    save(st.score)

if __name__ == "__main__":
    main()
