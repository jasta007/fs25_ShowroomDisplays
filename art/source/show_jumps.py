"""
Builds the show jumps in placeables/showJumps/: uprights, oxers, fans and more whose poles fall
when the horse hits them and go back up afterwards (EqPoles).

Each jump is jumped along z, with its stands at either end along x. The stands, their wings and
the cups stay put: one static collision box each. Every pole is its own transform group named
"eqPole<n>" holding the visible pole, a static collision box of its own and an "eqEnd" marker at
its +x end (EqPoles reads the pole's length from it), so the horse's leg rays
(EqTrainingHooks.legClearance) say which pole it clipped. EqPoles moves that group: it takes the
box's collision off, drops the pole off its cups with a scripted fall (no physics, so no spinning
beam of death), and later puts it back where the i3d has it and the collision back on. A pole may
be tilted (a crossrail) or turned (a fan) in its group's rotation.

Painted parts use the base game's vehicle shader, whose colorScale EqJumpColours sets from the
shop's colour options: shapes named "eqPaint" take the pole colour (the coloured bands, stand tops
and trim) and "eqWingPaint" the wing colour. The rest is white paint, dark metal cups, peeled or
planked wood (the cross country textures) or liverpool water.

Six jumps have a Sponsor boards choice in the shop (James, 2026-10-31), dearer: their wings get
boards whose faces, shapes named "eqSponsor_<n>" (and "eqSponsor_<n>b" for the same board's back),
show the farm's sponsor (EqSponsors). Pillars get a small sign on top, fan panels a board in place
of the fan, picket wings a flattened oval on the front, and the liverpool's water the logo too.
Those parts sit under a transform group "eqSponsorOn" (hidden in the i3d), and the fan slats they
replace under "eqSponsorOff"; EqSponsors shows one or the other from the choice bought. The
crossrail and cavaletti are training jumps and stay plain; the ladder wings have no board yet.

Like the cross country fences the geometry is inline (<IndexedTriangleSet>); the i3ds need a
GIANTS Editor re-save (art/source/ge-resave.ps1) before their collision works in game. The flags
come from the cross country fences' texture: "eqFlagsRed" (+x) and "eqFlagsWhite" (-x) at their
feet are what the course recorder reads as the jump's two ends.

Run from the repository root: python3 art/source/show_jumps.py [names...] (names: only those jumps,
so the others' GIANTS Editor re-saved i3ds are left alone)

Part of Realistic Equestrian by Jasta007.
"""

import math
import os

import numpy as np

from xc_jumps import (COLLISION_GROUP, COLLISION_MASK, FLAG_CELLS, Mesh, cross, dot, flag, fmt, norm,
                      round_rail, shape_lines, store_image, sub, tube)

OUT = "placeables/showJumps"
CLIP = 300

POLE_R = 0.05           # a 10 cm pole
BAND = 0.25             # each colour band along a pole, about
STAND_X = 1.81          # the stands' middles: just past a 3.5 m pole's ends
STAND_W = 0.10          # square stand posts
STAND_H = 1.60
FOOT_L = 0.80           # the crossed feet under each stand
FOOT_W = 0.08
FOOT_H = 0.06
CUP_W = 0.07            # a cup's width along the pole
CUP_H = 0.05            # its height below the pole's underside
CUP_D = 0.12            # how far it sticks out of the stand
CUP_REACH = 0.08        # a pole's end sits this far in from the stand's inner face
FLAG_OUT = 0.10         # the flag poles stand this far outside the wing's end
COL_PAD = 0.01

# The shop's colour options (EqJumpColours.LIST in scripts/facilities/EqJumpColours.lua holds the
# same list in the same order: keep them together). Linear colours, as the shader takes them.
COLOURS = [
    ("white", (0.80, 0.80, 0.78)),
    ("cream", (0.72, 0.62, 0.42)),
    ("red", (0.55, 0.02, 0.02)),
    ("burgundy", (0.22, 0.01, 0.02)),
    ("orange", (0.80, 0.22, 0.02)),
    ("yellow", (0.85, 0.60, 0.03)),
    ("lime", (0.30, 0.55, 0.04)),
    ("green", (0.04, 0.30, 0.06)),
    ("darkGreen", (0.01, 0.09, 0.03)),
    ("skyBlue", (0.15, 0.42, 0.75)),
    ("blue", (0.02, 0.10, 0.50)),
    ("navy", (0.005, 0.02, 0.10)),
    ("purple", (0.18, 0.04, 0.42)),
    ("pink", (0.80, 0.22, 0.38)),
    ("grey", (0.20, 0.20, 0.20)),
    ("black", (0.015, 0.015, 0.015)),
]
COLOUR = dict(COLOURS)

# Sponsor boards (James, 2026-10-31): the shop choice's extra price, the logos' shape (as on the
# bleachers' boards, whose texture they show until a brand's logo is put on) and margin.
SPONSOR_PRICE = 350
SPONSOR_TEXTURE = "../bleachers/bleacherSponsor_diffuse.dds"
LOGO_ASPECT = 2.7
LOGO_MARGIN = 0.03
WHITE = COLOUR["white"]
METAL = (0.06, 0.06, 0.065)
WATER = (0.01, 0.10, 0.28)


def row(z, *tops):
    """Straight poles across a row: (a, b) end points, +x end first."""
    half = STAND_X - STAND_W / 2 - CUP_REACH
    return [((half, top - POLE_R, z), (-half, top - POLE_R, z)) for top in tops]


def crossrail():
    """Two poles crossing, each low in one stand and high in the other: the front pole's +x end
    up, the back one's down."""
    half = STAND_X - STAND_W / 2 - CUP_REACH
    low, high = 0.30, 0.78
    return [((half, high - POLE_R, -0.06), (-half, low - POLE_R, -0.06)),
            ((half, low - POLE_R, 0.06), (-half, high - POLE_R, 0.06))]


FAN_STEP = 0.11         # poles side by side on a fan's single stand


def fan(spread, tops):
    """Poles fanning out from one wide stand at -x to stands spread along z at +x."""
    half = STAND_X - STAND_W / 2 - CUP_REACH
    n = len(spread)
    poles = []
    for i, (z, top) in enumerate(zip(spread, tops)):
        zc = (i - (n - 1) / 2) * FAN_STEP
        poles.append(((half, top - POLE_R, z), (-half, top - POLE_R, zc)))
    return poles


def cavaletti():
    half = 1.75
    return [((half, CAVALETTI_POLE_Y, 0.0), (-half, CAVALETTI_POLE_Y, 0.0))]


# The X ends of a cavaletti: planks crossing in the y-z plane, the pole resting in the V on top.
CAVALETTI_X = 1.66
CAVALETTI_FOOT = 0.25   # each plank's foot this far either side
CAVALETTI_TOP = 0.45    # and its top this high
CAVALETTI_LEAN = 0.13   # past the middle at the top
CAVALETTI_PLANK = (0.08, 0.05)
CAVALETTI_POLE_Y = 0.42  # the pole's middle

# name, price, default pole and wing colours, wing style, poles as (a, b) end points. Rows are
# written front first at -z, as read on the page; approach() turns them round below, because the
# horse comes from +z: facing the jump that way the red flag (+x) is on the rider's right.
JUMPS = [
    {"name": "showJumpUpright", "sponsor": True, "price": 450, "colour": "red", "wingColour": "white", "wing": "picket",
     "poles": row(0.0, 0.40, 0.72, 1.00)},
    {"name": "showJumpOxer", "sponsor": True, "price": 700, "colour": "blue", "wingColour": "white", "wing": "fanPanel",
     "poles": row(-0.55, 0.45, 0.95) + row(0.55, 1.00)},
    {"name": "showJumpCrossrail", "price": 300, "colour": "green", "wingColour": "white", "wing": "rustic",
     "poles": crossrail(), "wide": (1, -1)},
    {"name": "showJumpAscendingOxer", "price": 750, "colour": "orange", "wingColour": "white", "wing": "ladder",
     "poles": row(-0.6, 0.45, 0.85) + row(0.6, 0.55, 1.05)},
    {"name": "showJumpTripleBar", "sponsor": True, "price": 900, "colour": "yellow", "wingColour": "darkGreen", "wing": "pillar",
     "poles": row(-0.9, 0.55) + row(0.0, 0.85) + row(0.9, 1.10)},
    {"name": "showJumpHogsback", "sponsor": True, "price": 900, "colour": "purple", "wingColour": "white", "wing": "fanPanel",
     "poles": row(-0.8, 0.75) + row(0.0, 1.10) + row(0.8, 0.85)},
    {"name": "showJumpFan2", "price": 650, "colour": "skyBlue", "wingColour": "white", "wing": "ladder",
     "poles": fan([-0.7, 0.7], [1.00, 1.00]), "fan": True, "wide": (-1,)},
    {"name": "showJumpFan3", "sponsor": True, "price": 850, "colour": "pink", "wingColour": "navy", "wing": "pillar",
     "poles": fan([-0.9, 0.0, 0.9], [1.00, 1.00, 1.00]), "fan": True, "wide": (-1,)},
    {"name": "showJumpLiverpool", "sponsor": True, "price": 800, "colour": "navy", "wingColour": "white", "wing": "picket",
     "poles": row(0.0, 0.55, 1.00), "liverpool": True},
    {"name": "showJumpCavaletti", "price": 150, "colour": "red", "wingColour": "white", "wing": None,
     "poles": cavaletti(), "cavaletti": True},
]


def approach(poles):
    """Mirror along z: the front row (written at -z) ends up facing a horse coming from +z (James
    2026-10-29: the ascending oxer was descending)."""
    return [((a[0], a[1], -a[2]), (b[0], b[1], -b[2])) for a, b in poles]


for _jump in JUMPS:
    _jump["poles"] = approach(_jump["poles"])


# ---------------------------------------------------------------------------------------------
# Geometry helpers

def prism(mesh, outline, origin, ua, ub, n, depth, tile=1.0):
    """A flat convex outline [(a, b), ...] in the plane origin + a*ua + b*ub, extruded depth along
    n (n = ua x ub or its opposite, either way). UVs in metres / tile: the paint's detail maps."""
    def at(a, b, c):
        return tuple(origin[k] + a * ua[k] + b * ub[k] + c * n[k] for k in range(3))
    # wind the outline counter-clockwise about n
    area = sum(outline[i][0] * outline[(i + 1) % len(outline)][1] - outline[(i + 1) % len(outline)][0] * outline[i][1]
               for i in range(len(outline)))
    if dot(cross(ua, ub), n) * area < 0:
        outline = outline[::-1]
    nn = norm(n)
    back = (-nn[0], -nn[1], -nn[2])
    for c, normal in ((depth, nn), (0.0, back)):
        ids = [mesh.vertex(at(a, b, c), normal, (a / tile, b / tile)) for a, b in outline]
        for k in range(1, len(ids) - 1):
            mesh.tri(ids[0], ids[k], ids[k + 1])
    ca = sum(a for a, _ in outline) / len(outline)
    cb = sum(b for _, b in outline) / len(outline)
    for k in range(len(outline)):
        (a0, b0), (a1, b1) = outline[k], outline[(k + 1) % len(outline)]
        p0, p1, q0, q1 = at(a0, b0, 0.0), at(a1, b1, 0.0), at(a0, b0, depth), at(a1, b1, depth)
        out = norm(sub(at((a0 + a1) / 2, (b0 + b1) / 2, 0.0), at(ca, cb, 0.0)))
        length = math.dist(p0, p1)
        mesh.quad([p0, p1, q1, q0], out, [(0, 0), (length / tile, 0), (length / tile, depth / tile), (0, depth / tile)])


def box(mesh, x0, x1, y0, y1, z0, z1):
    prism(mesh, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], (0.0, 0.0, z0), (1, 0, 0), (0, 1, 0), (0, 0, 1), z1 - z0)


def beam_outline(a, b, width):
    """A rectangle round the line a-b in a plane."""
    d = (b[0] - a[0], b[1] - a[1])
    length = math.hypot(*d) or 1.0
    p = (-d[1] / length * width / 2, d[0] / length * width / 2)
    return [(a[0] + p[0], a[1] + p[1]), (b[0] + p[0], b[1] + p[1]), (b[0] - p[0], b[1] - p[1]), (a[0] - p[0], a[1] - p[1])]


def upright_log(mesh, x, z, y0, y1, r, sides=12):
    """A standing round log with a flat top, its texture's v running up it."""
    rings = []
    for y in (y0, y1):
        ring = []
        for k in range(sides + 1):
            a = 2 * math.pi * k / sides
            n = (math.cos(a), 0.0, math.sin(a))
            ring.append(mesh.vertex((x + n[0] * r, y, z + n[2] * r), n, (k / sides * 0.5, y / 1.5)))
        rings.append(ring)
    tube(mesh, rings, None)
    middle = mesh.vertex((x, y1, z), (0.0, 1.0, 0.0), (0.25, 0.5))
    rim = [mesh.vertex((x + math.cos(2 * math.pi * k / sides) * r, y1, z + math.sin(2 * math.pi * k / sides) * r),
                       (0.0, 1.0, 0.0), (0.25 + 0.1 * math.cos(2 * math.pi * k / sides), 0.5)) for k in range(sides)]
    for k in range(sides):
        mesh.tri(middle, rim[k], rim[(k + 1) % sides])


class Parts:
    """A jump's static meshes by material, its collision boxes. With sponsor boards: what only the
    Sponsor boards choice shows (boards in white, trim in the pole colour, the logos by shape
    name) and the wing parts it hides."""

    def __init__(self, sponsor=False):
        self.white, self.paint, self.wing, self.metal, self.water = Mesh(), Mesh(), Mesh(), Mesh(), Mesh()
        self.peeled, self.planks = Mesh(), Mesh()
        self.cols = []
        self.sponsor = sponsor
        self.board, self.board_paint, self.unsponsored_wing = Mesh(), Mesh(), Mesh()
        self.logos = {}     # shape name ("eqSponsor_1", "eqSponsor_1b") -> Mesh


def logo_size(width, height):
    """The biggest logo of LOGO_ASPECT inside a board of width x height."""
    width, height = width - 2 * LOGO_MARGIN, height - 2 * LOGO_MARGIN
    return (width, width / LOGO_ASPECT) if width / height < LOGO_ASPECT else (height * LOGO_ASPECT, height)


def upright_logo(parts, name, xc, yc, z, facing, lw, lh):
    """A logo standing in the x-y plane at z, facing +z (facing 1) or -z (-1); its u runs to the
    right seen from the way it faces."""
    mesh = Mesh()
    left, right = xc - facing * lw / 2, xc + facing * lw / 2
    mesh.quad([(left, yc - lh / 2, z), (right, yc - lh / 2, z), (right, yc + lh / 2, z), (left, yc + lh / 2, z)],
              (0, 0, facing), [(0, 0), (1, 0), (1, 1), (0, 1)])
    parts.logos[name] = mesh


def merge(target, mesh):
    base = len(target.verts)
    target.verts += mesh.verts
    target.tris += [(a + base, b + base, c + base) for a, b, c in mesh.tris]


# ---------------------------------------------------------------------------------------------
# Stands and wings

def stand(parts, x, z, depth=STAND_W):
    """A stand: a square post (deeper along z for a fan's single stand) with a painted top, on
    crossed feet."""
    s, d = STAND_W / 2, depth / 2
    box(parts.white, x - s, x + s, 0.0, STAND_H - 0.25, z - d, z + d)
    box(parts.paint, x - s, x + s, STAND_H - 0.25, STAND_H, z - d, z + d)
    box(parts.paint, x - s - 0.01, x + s + 0.01, STAND_H, STAND_H + 0.02, z - d - 0.01, z + d + 0.01)
    box(parts.white, x - FOOT_L / 2, x + FOOT_L / 2, 0.0, FOOT_H, z - FOOT_W / 2, z + FOOT_W / 2)
    box(parts.white, x - FOOT_W / 2, x + FOOT_W / 2, 0.0, FOOT_H, z - d - FOOT_L / 2 + s, z + d + FOOT_L / 2 - s)
    parts.cols.append((x - s, x + s, 0.0, STAND_H, z - d, z + d))


class Wing:
    """Draws in the wing's own plane: u out from the stand's outer face, y up, z along the jump."""

    def __init__(self, parts, x, side, z):
        self.parts, self.x0, self.side, self.z = parts, x + side * STAND_W / 2, side, z
        # each wing's sponsor board is one board, its back (if it has one) the same number
        self.board = "eqSponsor_1" if side > 0 else "eqSponsor_2"

    def x(self, u):
        return self.x0 + self.side * u

    def flat(self, mesh, outline, z0, z1):
        """outline in (u, y), from z0 to z1 (relative to the wing's row)."""
        prism(mesh, outline, (self.x0, 0.0, self.z + z0), (self.side, 0, 0), (0, 1, 0), (0, 0, 1), z1 - z0)

    def block(self, mesh, u0, u1, y0, y1, z0, z1):
        self.flat(mesh, [(u0, y0), (u1, y0), (u1, y1), (u0, y1)], z0, z1)

    def beam(self, mesh, a, b, width, z0, z1):
        self.flat(mesh, beam_outline(a, b, width), z0, z1)

    def foot(self, u0, u1, reach=0.32):
        self.block(self.parts.white, u0, u1, 0.0, 0.06, -reach, reach)

    def collide(self, u0, u1, y1, z0, z1):
        xa, xb = sorted((self.x(u0), self.x(u1)))
        self.parts.cols.append((xa, xb, 0.0, y1, self.z + z0, self.z + z1))


def wing_picket(w):
    """Picket fence: an end post, two rails behind, pointed pickets dipping to the middle."""
    p, width = w.parts, 0.95
    w.block(p.wing, width - 0.09, width, 0.0, 1.50, -0.045, 0.045)
    w.block(p.paint, width - 0.10, width + 0.01, 1.50, 1.54, -0.055, 0.055)
    for y in (0.30, 0.98):
        w.block(p.wing, 0.0, width - 0.09, y, y + 0.08, -0.045, -0.0125)
    count = 6
    for i in range(count):
        u = 0.07 + i * (width - 0.09 - 0.12) / (count - 1)
        t = (u - 0.07) / (width - 0.09 - 0.12)
        top = 1.12 + 0.36 * (2 * t - 1) ** 2
        half = 0.0425
        outline = [(u - half, 0.10), (u + half, 0.10), (u + half, top), (u, top + 0.07), (u - half, top)]
        w.flat(p.wing, outline, -0.0125, 0.0125)
    w.foot(width - 0.20, width + 0.06)
    w.collide(0.0, width, 1.54, -0.06, 0.06)
    if p.sponsor:
        # a flattened oval board nailed on the front (+z, the way the horse comes), clear of the
        # stand and the end post and standing proud of both (James, 2026-10-31: the pickets stay
        # as they are behind it), a rim in the pole colour round a white face, the logo in it
        uc, yc, a, b = (width - 0.09) / 2, 0.70, 0.33, 0.20
        front = 0.055   # just in front of the end post's face (0.045) and the stand's (0.05)
        steps = 40
        for mesh, grow, z0, z1 in ((p.board_paint, 0.025, front, front + 0.022), (p.board, 0.0, front, front + 0.028)):
            outline = [(uc + (a + grow) * math.cos(2 * math.pi * k / steps), yc + (b + grow) * math.sin(2 * math.pi * k / steps))
                       for k in range(steps)]
            w.flat(mesh, outline, z0, z1)
        # two cleats behind it, nailed to the pickets
        for u in (uc - a * 0.55, uc + a * 0.55):
            w.block(p.board_paint, u - 0.03, u + 0.03, yc - b * 0.7, yc + b * 0.7, 0.0125, front)
        # the biggest logo inside the ellipse: its corners on the ellipse
        t = math.atan(a / (LOGO_ASPECT * b))
        lw, lh = 2 * a * math.cos(t) * 0.92, 2 * b * math.sin(t) * 0.92
        upright_logo(p, w.board, w.x(uc), yc, w.z + front + 0.0295, 1, lw, lh)
    return width


def wing_fan_panel(w):
    """A framed panel below and a fan of slats above, like a sunrise gate."""
    p, width = w.parts, 0.86
    for u0, u1 in ((0.0, 0.08), (width - 0.08, width)):
        w.block(p.wing, u0, u1, 0.0, 1.50, -0.04, 0.04)
    for y0, y1 in ((0.10, 0.18), (0.80, 0.88), (1.42, 1.50)):
        w.block(p.wing, 0.08, width - 0.08, y0, y1, -0.035, 0.035)
    w.block(p.wing, 0.08, width - 0.08, 0.18, 0.80, -0.015, 0.015)
    # raised panel mouldings, both faces
    for z0, z1 in ((0.015, 0.03), (-0.03, -0.015)):
        for u0, u1, y0, y1 in ((0.14, width - 0.14, 0.24, 0.27), (0.14, width - 0.14, 0.71, 0.74),
                               (0.14, 0.17, 0.27, 0.71), (width - 0.17, width - 0.14, 0.27, 0.71)):
            w.block(p.paint, u0, u1, y0, y1, z0, z1)
    pivot = (width / 2, 0.88)
    slats = 7
    # with sponsor boards a board fills the fan's frame instead (James, 2026-10-31), its logo
    # on both faces
    fan = p.unsponsored_wing if p.sponsor else p.wing
    for i in range(slats):
        u = 0.13 + i * (width - 0.26) / (slats - 1)
        w.beam(fan, pivot, (u, 1.42), 0.03, -0.012, 0.012)
    if p.sponsor:
        w.block(p.board, 0.08, width - 0.08, 0.88, 1.42, -0.015, 0.015)
        lw, lh = logo_size(width - 0.16, 0.54)
        for facing, name in ((1, w.board), (-1, w.board + "b")):
            upright_logo(p, name, w.x(width / 2), 1.15, w.z + facing * 0.0165, facing, lw, lh)
    w.block(p.paint, -0.01, width + 0.01, 1.50, 1.55, -0.055, 0.055)
    w.foot(width - 0.18, width + 0.06)
    w.collide(0.0, width, 1.55, -0.06, 0.06)
    return width


def wing_ladder(w):
    """A sloping wing: tall at the stand, low at its end, with upright slats under a sloping rail."""
    p, width = w.parts, 1.10
    high, low = 1.45, 0.55
    w.block(p.wing, 0.0, 0.08, 0.0, high, -0.04, 0.04)
    w.block(p.wing, width - 0.08, width, 0.0, low, -0.04, 0.04)
    w.block(p.paint, width - 0.09, width + 0.01, low, low + 0.04, -0.05, 0.05)
    w.beam(p.wing, (0.04, high - 0.04), (width - 0.04, low - 0.04), 0.09, -0.035, 0.035)
    w.block(p.wing, 0.08, width - 0.08, 0.12, 0.20, -0.035, 0.035)
    slope = (low - high) / (width - 0.08)
    u = 0.08 + 0.15
    while u < width - 0.12:
        top = high - 0.04 + slope * (u - 0.04)
        w.block(p.wing, u - 0.025, u + 0.025, 0.20, top, -0.02, 0.02)
        u += 0.16
    w.foot(width - 0.18, width + 0.06)
    w.collide(0.0, width, high, -0.05, 0.05)
    return width


def wing_pillar(w):
    """A square tower: plinth, a shaft in the wing colour with painted panels inset on its faces,
    a moulded cap."""
    p, width = w.parts, 0.62
    w.block(p.white, 0.02, width - 0.02, 0.0, 0.14, -0.28, 0.28)
    w.block(p.wing, 0.06, width - 0.06, 0.14, 1.56, -0.24, 0.24)
    for z0, z1 in ((0.24, 0.255), (-0.255, -0.24)):
        w.block(p.paint, 0.12, width - 0.12, 0.32, 1.38, z0, z1)
    for u0, u1 in ((0.06 - 0.015, 0.06), (width - 0.06, width - 0.06 + 0.015)):
        w.block(p.paint, u0, u1, 0.32, 1.38, -0.18, 0.18)
    w.block(p.white, 0.03, width - 0.03, 1.56, 1.63, -0.27, 0.27)
    w.block(p.paint, 0.0, width, 1.63, 1.69, -0.29, 0.29)
    w.block(p.white, 0.04, width - 0.04, 1.69, 1.72, -0.25, 0.25)
    w.collide(0.0, width, 1.72, -0.29, 0.29)
    if p.sponsor:
        # a small sign on top of the column, on two short legs, its logo on both faces
        y0, y1 = 1.79, 2.03
        w.block(p.board, 0.03, width - 0.03, y0, y1, -0.02, 0.02)
        w.block(p.board_paint, 0.02, width - 0.02, y1, y1 + 0.02, -0.025, 0.025)
        for u in (0.14, width - 0.14):
            w.block(p.board_paint, u - 0.02, u + 0.02, 1.72, y0, -0.015, 0.015)
        lw, lh = logo_size(width - 0.06, y1 - y0)
        for facing, name in ((1, w.board), (-1, w.board + "b")):
            upright_logo(p, name, w.x(width / 2), (y0 + y1) / 2, w.z + facing * 0.0215, facing, lw, lh)
    return width


def wing_rustic(w):
    """Peeled log posts with sloping and crossed log rails."""
    p, width = w.parts, 1.10
    inner, outer = 0.07, width - 0.07
    upright_log(p.peeled, w.x(inner), w.z, 0.0, 1.40, 0.065)
    upright_log(p.peeled, w.x(outer), w.z, 0.0, 1.00, 0.065)
    ends = Mesh()
    for (u0, y0), (u1, y1), dz in (((inner, 1.28), (outer, 0.88), -0.10), ((inner, 0.30), (outer, 0.80), 0.10),
                                    ((inner, 0.85), (outer, 0.30), 0.10)):
        round_rail(p.peeled, ends, (w.x(u0), y0, w.z + dz), (w.x(u1), y1, w.z + dz), 0.045, sides=10)
    merge(p.peeled, ends)
    w.collide(0.0, width, 1.40, -0.16, 0.16)
    return width


WINGS = {"picket": wing_picket, "fanPanel": wing_fan_panel, "ladder": wing_ladder, "pillar": wing_pillar,
         "rustic": wing_rustic}


def cup(parts, x_end, side, y_top, z):
    """A cup under a pole's end, sticking out of the stand's inner face."""
    inner = side * (STAND_X - STAND_W / 2)
    x0, x1 = sorted((inner, inner - side * CUP_D))
    under = y_top - 2 * POLE_R
    box(parts.metal, x0, x1, under - CUP_H, under, z - CUP_W / 2, z + CUP_W / 2)
    box(parts.metal, x0, x1, under - CUP_H, under + 0.035, z - CUP_W / 2 - 0.005, z - CUP_W / 2)
    box(parts.metal, x0, x1, under - CUP_H, under + 0.035, z + CUP_W / 2, z + CUP_W / 2 + 0.005)


def x_end(parts, x):
    """A cavaletti's X: two planks crossing in the y-z plane."""
    w, t = CAVALETTI_PLANK
    for s in (1, -1):
        a = (s * CAVALETTI_FOOT, 0.0)
        b = (-s * CAVALETTI_LEAN, CAVALETTI_TOP)
        # (z, y) plane, extruded along x, the two planks side by side
        dx = t / 2 if s > 0 else -t / 2
        prism(parts.planks, beam_outline(a, b, w), (x + dx - t / 2, 0.0, 0.0), (0, 0, 1), (0, 1, 0), (1, 0, 0), t)
    parts.cols.append((x - t, x + t, 0.0, CAVALETTI_TOP, -CAVALETTI_FOOT - 0.05, CAVALETTI_FOOT + 0.05))


def liverpool_tray(parts):
    """A shallow water tray under the poles and in front of them (the horse comes from +z)."""
    x0, x1, z0, z1 = -1.60, 1.60, -0.20, 1.35
    rim = 0.06
    box(parts.water, x0 + rim, x1 - rim, 0.0, 0.035, z0 + rim, z1 - rim)
    if parts.sponsor:
        # the sponsor's logo on the water's floor (James, 2026-10-31), read by the rider coming
        # from +z: u to their right (+x), v away from them (-z)
        lw, lh = logo_size(x1 - x0 - 2 * rim - 0.3, z1 - z0 - 2 * rim - 0.1)
        zc, y = (z0 + z1) / 2, 0.0365
        logo = Mesh()
        logo.quad([(-lw / 2, y, zc + lh / 2), (lw / 2, y, zc + lh / 2), (lw / 2, y, zc - lh / 2), (-lw / 2, y, zc - lh / 2)],
                  (0, 1, 0), [(0, 0), (1, 0), (1, 1), (0, 1)])
        parts.logos["eqSponsor_3"] = logo
    for bx0, bx1, bz0, bz1 in ((x0, x1, z0, z0 + rim), (x0, x1, z1 - rim, z1), (x0, x0 + rim, z0, z1), (x1 - rim, x1, z0, z1)):
        box(parts.paint, bx0, bx1, 0.0, 0.07, bz0, bz1)


def frame(jump):
    """The stands, wings, cups and fillers of a jump, its collision boxes and the flags' feet."""
    parts, flags = Parts(jump.get("sponsor", False)), Mesh()
    poles = jump["poles"]
    if jump.get("cavaletti"):
        for side in (1, -1):
            x_end(parts, side * CAVALETTI_X)
        half, flag_z = 1.75 + 0.35, 0.0
    else:
        ends = {}
        for a, b in poles:
            for end, side in ((a, 1), (b, -1)):
                ends.setdefault(side, set()).add(round(end[2], 3))
        for side, zs in ends.items():
            x = side * STAND_X
            if side in jump.get("wide", ()):
                stand(parts, x, (min(zs) + max(zs)) / 2, depth=max(zs) - min(zs) + FAN_STEP / 2 + 0.04)
            else:
                for z in sorted(zs):
                    stand(parts, x, z)
            # stands on several rows are joined at the foot
            if len(zs) > 1 and side not in jump.get("wide", ()):
                box(parts.white, x - FOOT_W / 2, x + FOOT_W / 2, 0.0, FOOT_H, min(zs), max(zs))
        for a, b in poles:
            cup(parts, a[0], 1, a[1] + POLE_R, a[2])
            cup(parts, b[0], -1, b[1] + POLE_R, b[2])
        zs = sorted({round(a[2], 3) for a, _ in poles} | {round(b[2], 3) for _, b in poles})
        flag_z = 0.0 if jump.get("fan") or len(zs) == 1 else (zs[0] + zs[-1]) / 2
        width = WINGS[jump["wing"]](Wing(parts, STAND_X, 1, flag_z))
        WINGS[jump["wing"]](Wing(parts, -STAND_X, -1, flag_z))
        half = STAND_X + STAND_W / 2 + width + FLAG_OUT
        if jump.get("liverpool"):
            liverpool_tray(parts)
    top = max(max(a[1], b[1]) for a, b in poles) + POLE_R
    flag(flags, half, 0, 1, max(STAND_H + 0.1, top + 0.55))
    flag(flags, -half, 1, -1, max(STAND_H + 0.1, top + 0.55))
    flags.verts = [((p[0], p[1], p[2] + flag_z), n, uv) for p, n, uv in flags.verts]
    feet = {"eqFlagsRed": (half, 0.0, flag_z), "eqFlagsWhite": (-half, 0.0, flag_z)}
    return parts, flags, feet


# ---------------------------------------------------------------------------------------------
# Poles

def pole_meshes(length):
    """A pole along x round its middle in coloured and white bands (an odd number, colour at both
    ends), white end caps."""
    paint, white, caps = Mesh(), Mesh(), Mesh()
    bands = max(3, round(length / BAND))
    if bands % 2 == 0:
        bands += 1
    step = length / bands
    for i in range(bands):
        a = (-length / 2 + i * step, 0.0, 0.0)
        b = (-length / 2 + (i + 1) * step, 0.0, 0.0)
        scrap = Mesh()
        round_rail(paint if i % 2 == 0 else white, caps if i in (0, bands - 1) else scrap, a, b, POLE_R, sides=16)
    # round_rail put both caps of the end bands in caps: keep only the outer ones
    outer = Mesh()
    for t in caps.tris:
        xs = [caps.verts[k][0][0] for k in t]
        if all(abs(abs(x) - length / 2) < 1e-6 for x in xs):
            outer.tris.append(t)
    outer.verts = caps.verts
    return paint, white, outer


def pole_pose(a, b):
    """A pole group's translation, rotation (degrees, GIANTS order: ry turns x towards -z, rz
    tilts x up) and length from its end points."""
    mid = tuple((a[k] + b[k]) / 2 for k in range(3))
    d = sub(a, b)
    length = math.sqrt(dot(d, d))
    horizontal = math.hypot(d[0], d[2])
    ry = math.atan2(-d[2], d[0])
    rz = math.atan2(d[1], horizontal)
    return mid, (0.0, math.degrees(ry), math.degrees(rz)), length


def place(mesh, mid, rot):
    """A copy of a pole mesh where its group puts it (for the shop image)."""
    ry, rz = math.radians(rot[1]), math.radians(rot[2])

    def turn(v):
        x, y, z = v
        x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
        x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
        return x, y, z
    out = Mesh()
    out.verts = [(tuple(turn(p)[k] + mid[k] for k in range(3)), turn(n), uv) for p, n, uv in mesh.verts]
    out.tris = list(mesh.tris)
    return out


def collision_box(x0, x1, y0, y1, z0, z1):
    mesh = Mesh()
    mesh.box(x0, x1, y0, y1, z0, z1, (0.5, 0.5))
    # with a bottom: a closed box for the physics
    ids = [mesh.vertex(p, (0.0, -1.0, 0.0), (0.5, 0.5)) for p in ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1))]
    mesh.tri(ids[0], ids[1], ids[2])
    mesh.tri(ids[0], ids[2], ids[3])
    return mesh


# ---------------------------------------------------------------------------------------------
# Files

SHADER = "$data/shaders/vehicleShader.xml"
PAINT_MAPS = {"detailDiffuse": "$data/shared/detailLibrary/calibrated/calibratedPaint_diffuse.png",
              "detailNormal": "$data/shared/detailLibrary/calibrated/calibratedPaint_normal.png",
              "detailSpecular": "$data/shared/detailLibrary/calibrated/calibratedPaint_specular.png"}


def write_i3d(jump, path, parts, flags, feet, pole_shapes):
    name = jump["name"]
    files = [SHADER] + list(PAINT_MAPS.values()) + ["../xcJumps/xcFlags_diffuse.dds", "../xcJumps/xcPeeled_diffuse.dds",
                                                    "../xcJumps/xcPlanks_diffuse.dds", "../xcJumps/xcPlanks_normal.dds"]
    fid = {f: i + 1 for i, f in enumerate(files)}

    def paint_material(mname, mid, colour, smooth=0.55, metal=0.0):
        lines = [f'    <Material name="{mname}" materialId="{mid}" customShaderId="{fid[SHADER]}">']
        lines += [f'      <Custommap name="{k}" fileId="{fid[v]}"/>' for k, v in PAINT_MAPS.items()]
        lines.append(f'      <CustomParameter name="colorScale" value="{fmt(colour)}"/>')
        lines.append(f'      <CustomParameter name="smoothnessScale" value="{smooth}"/>')
        lines.append(f'      <CustomParameter name="metalnessScale" value="{metal}"/>')
        lines.append("    </Material>")
        return lines

    materials = {"white": 1, "paint": 2, "wing": 3, "metal": 4, "water": 5, "flags": 6, "peeled": 7, "planks": 8}
    logos = sorted(parts.logos)
    if logos:
        files.append(SPONSOR_TEXTURE)
        fid[SPONSOR_TEXTURE] = len(files)
    for i, logo in enumerate(logos):
        materials[logo] = 9 + i
    lines = [
        '<?xml version="1.0" encoding="iso-8859-1"?>',
        "",
        f'<i3D name="{name}" version="1.6" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="http://i3d.giants.ch/schema/i3d-1.6.xsd">',
        "  <Asset>",
        '    <Export program="Realistic Equestrian show_jumps.py" version="2"/>',
        "  </Asset>",
        "  <Files>",
    ]
    lines += [f'    <File fileId="{fid[f]}" filename="{f}"/>' for f in files]
    lines += ["  </Files>", "  <Materials>"]
    lines += paint_material("sjWhite", materials["white"], WHITE)
    lines += paint_material("sjPaint", materials["paint"], COLOUR[jump["colour"]])
    lines += paint_material("sjWingPaint", materials["wing"], COLOUR[jump["wingColour"]])
    lines += paint_material("sjMetal", materials["metal"], METAL, smooth=0.6, metal=0.8)
    lines += paint_material("sjWater", materials["water"], WATER, smooth=0.95)
    lines += [f'    <Material name="sjFlags" materialId="{materials["flags"]}" specularColor="0.1 0.6 0">',
              f'      <Texture fileId="{fid["../xcJumps/xcFlags_diffuse.dds"]}"/>', "    </Material>",
              f'    <Material name="sjPeeled" materialId="{materials["peeled"]}" specularColor="0.1 0.6 0">',
              f'      <Texture fileId="{fid["../xcJumps/xcPeeled_diffuse.dds"]}"/>', "    </Material>",
              f'    <Material name="sjPlanks" materialId="{materials["planks"]}" specularColor="0.1 0.6 0">',
              f'      <Texture fileId="{fid["../xcJumps/xcPlanks_diffuse.dds"]}"/>',
              f'      <Normalmap fileId="{fid["../xcJumps/xcPlanks_normal.dds"]}"/>', "    </Material>"]
    # one material per logo, so each can show its own brand (EqSponsors replaces the texture)
    for logo in logos:
        lines += [f'    <Material name="{logo.replace("_", "")}" materialId="{materials[logo]}" specularColor="0.2 0.5 0" alphaBlending="true">',
                  f'      <Texture fileId="{fid[SPONSOR_TEXTURE]}"/>', "    </Material>"]
    lines.append("  </Materials>")

    # static shapes: (node name, mesh, material)
    statics = [("frame", parts.white, "white"), ("eqPaint", parts.paint, "paint"), ("eqWingPaint", parts.wing, "wing"),
               ("cups", parts.metal, "metal"), ("water", parts.water, "water"), ("logs", parts.peeled, "peeled"),
               ("planks", parts.planks, "planks"), ("flags", flags, "flags")]
    statics = [s for s in statics if s[1].tris]
    shapes = [(f"s_{n}", m) for n, m, _ in statics]
    sponsored = [("eqWingPaint", parts.board_paint, "paint"), ("eqBoardFace", parts.board, "white")]
    sponsored = [(n, m, mat) for n, m, mat in sponsored if m.tris] + [(logo, parts.logos[logo], logo) for logo in logos]
    shapes += [(f"on_{n}", m) for n, m, _ in sponsored]
    if parts.unsponsored_wing.tris:
        shapes.append(("off_fan", parts.unsponsored_wing))
    shapes += [(f"col{i + 1}", collision_box(*b)) for i, b in enumerate(parts.cols)]
    for length, (paint, white, caps) in pole_shapes.items():
        shapes += [(f"polePaint{length:.3f}", paint), (f"poleWhite{length:.3f}", white), (f"poleEnds{length:.3f}", caps),
                   (f"poleCol{length:.3f}", collision_box(-length / 2, length / 2, -POLE_R, POLE_R, -POLE_R, POLE_R))]
    ids = {shape: i + 1 for i, (shape, _) in enumerate(shapes)}
    lines.append("  <Shapes>")
    for shape, mesh in shapes:
        lines += shape_lines(mesh, f"{name}_{shape}", ids[shape])
    lines += ["  </Shapes>", "  <Scene>"]
    node = [1]

    def next_id():
        node[0] += 1
        return node[0]

    def col_line(indent, shape_name, shape):
        return (f'{indent}<Shape name="{shape_name}" shapeId="{ids[shape]}" static="true" collisionFilterGroup="{COLLISION_GROUP}" '
                f'collisionFilterMask="{COLLISION_MASK}" density="0.01" nodeId="{next_id()}" nonRenderable="true" materialIds="1"/>')

    def vis_line(indent, node_name, shape, material, shadows=True):
        return (f'{indent}<Shape name="{node_name}" shapeId="{ids[shape]}" clipDistance="{CLIP}" nodeId="{next_id()}" '
                f'materialIds="{materials[material]}" castsShadows="{str(shadows).lower()}" receiveShadows="true"/>')

    lines.append(f'    <TransformGroup name="{name}" nodeId="1">')
    for n, _, material in statics:
        lines.append(vis_line("      ", n, f"s_{n}", material, shadows=material != "water"))
    if sponsored:
        # shown only with the Sponsor boards choice (EqSponsors); the trim takes the pole colour
        lines.append(f'      <TransformGroup name="eqSponsorOn" visibility="false" nodeId="{next_id()}">')
        for n, _, material in sponsored:
            node_name = "eqPaint" if n == "eqWingPaint" else n
            lines.append(vis_line("        ", node_name, f"on_{n}", material, shadows=not n.startswith("eqSponsor_")))
        lines.append("      </TransformGroup>")
    if parts.unsponsored_wing.tris:
        lines.append(f'      <TransformGroup name="eqSponsorOff" nodeId="{next_id()}">')
        lines.append(vis_line("        ", "eqWingPaint", "off_fan", "wing"))
        lines.append("      </TransformGroup>")
    for flag_name in ("eqFlagsRed", "eqFlagsWhite"):
        lines.append(f'      <TransformGroup name="{flag_name}" translation="{fmt(feet[flag_name])}" nodeId="{next_id()}"/>')
    lines.append(f'      <TransformGroup name="collision" nodeId="{next_id()}">')
    for i in range(len(parts.cols)):
        lines.append(col_line("        ", "col", f"col{i + 1}"))
    lines.append("      </TransformGroup>")
    # Poles from the bottom up, so eqPole1 is the lowest (EqPoles drops the highest it can).
    poles = sorted(jump["poles"], key=lambda p: (p[0][1] + p[1][1]) / 2)
    for i, (a, b) in enumerate(poles):
        mid, rot, length = pole_pose(a, b)
        key = round(length, 3)
        lines.append(f'      <TransformGroup name="eqPole{i + 1}" translation="{fmt(mid)}" rotation="{fmt(rot)}" nodeId="{next_id()}">')
        lines.append(vis_line("        ", "eqPaint", f"polePaint{key:.3f}", "paint"))
        lines.append(vis_line("        ", "white", f"poleWhite{key:.3f}", "white"))
        lines.append(vis_line("        ", "ends", f"poleEnds{key:.3f}", "white", shadows=False))
        lines.append(col_line("        ", "poleCol", f"poleCol{key:.3f}"))
        lines.append(f'        <TransformGroup name="eqEnd" translation="{fmt((length / 2, 0.0, 0.0))}" nodeId="{next_id()}"/>')
        lines.append("      </TransformGroup>")
    lines += ["    </TransformGroup>", "  </Scene>", "</i3D>"]
    with open(path, "w", encoding="iso-8859-1", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def colour_configurations(key, default):
    """The shop's colour options; the jump's own colour is picked first."""
    lines = [f"    <{key}>", f"        <{key}Configurations>"]
    for name, rgb in COLOURS:
        extra = ' isDefault="true"' if name == default else ""
        lines.append(f'            <{key}Configuration name="$l10n_eq_colour_{name}" price="0"{extra}/>')
    lines += [f"        </{key}Configurations>", f"    </{key}>"]
    return "\n".join(lines)


def write_xml(jump, path):
    name = jump["name"]
    poles = jump["poles"]
    top = max(max(a[1], b[1]) for a, b in poles) + POLE_R
    zs = [p[k][2] for p in poles for k in (0, 1)]
    wing_colour = colour_configurations("eqWingColour", jump["wingColour"]) + "\n\n" if jump["wing"] else ""
    sponsor = f"""    <!-- Sponsor boards: No (the first, default) or Yes, dearer: boards on the wings showing your
         sponsor, counted towards your branding (EqSponsors shows the eqSponsorOn parts). -->
    <eqSponsorBoards>
        <eqSponsorBoardsConfigurations>
            <eqSponsorBoardsConfiguration name="$l10n_ui_no" price="0"/>
            <eqSponsorBoardsConfiguration name="$l10n_ui_yes" price="{SPONSOR_PRICE}"/>
        </eqSponsorBoardsConfigurations>
    </eqSponsorBoards>

""" if jump.get("sponsor") else ""
    functions = "\n            <function>$l10n_eq_shop_sponsorBoards_function</function>" if jump.get("sponsor") else ""
    text = f"""<?xml version="1.0" encoding="utf-8" standalone="no"?>
<!-- Made by art/source/show_jumps.py: change that and run it again rather than editing this. -->
<placeable type="simplePlaceable">
    <storeData>
        <name>$l10n_eq_shop_{name}</name>
        <functions>
            <function>$l10n_eq_shop_showJump_function</function>
            <function>$l10n_eq_shop_showJumpHidden_function</function>{functions}
        </functions>
        <image>placeables/showJumps/store_{name}.dds</image>
        <price>{jump["price"]}</price>
        <dailyUpkeep>0</dailyUpkeep>
        <lifetime>1000</lifetime>
        <rotation>0</rotation>
        <brand>NONE</brand>
        <species>placeable</species>
        <category>animalpens</category>
        <brush>
            <type>placeable</type>
            <category>animals</category>
            <tab>horses</tab>
        </brush>
    </storeData>

    <base>
        <filename>placeables/showJumps/{name}.i3d</filename>
        <canBeRenamed>false</canBeRenamed>
    </base>

    <placement useRandomYRotation="false" useManualYRotation="true">
        <!-- {top:.2f} m high, {max(zs) - min(zs):.2f} m spread; jumped along z, red flag at +x. Poles eqPole1.. fall (EqPoles). -->
    </placement>

    <!-- Disappearing: No (the first, default) keeps the jump in the world; Yes hides it outside
         construction, course editing and rounds, like the cross country pieces (EqXcHide). -->
    <eqDisappearing>
        <eqDisappearingConfigurations>
            <eqDisappearingConfiguration name="$l10n_ui_no" price="0"/>
            <eqDisappearingConfiguration name="$l10n_ui_yes" price="0"/>
        </eqDisappearingConfigurations>
    </eqDisappearing>

{colour_configurations("eqPoleColour", jump["colour"])}

{wing_colour}{sponsor}</placeable>
"""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def flat(rgb, gamma=True):
    """A 1x1 texture for the shop render, from a linear colour."""
    c = [min(255, int(255 * (v ** (1 / 2.2) if gamma else v))) for v in rgb]
    return np.array([[c]], dtype=float)


def flags_texture():
    cell = 32
    img = np.zeros((cell, cell * len(FLAG_CELLS), 3))
    for i, colour in enumerate(FLAG_CELLS):
        img[:, i * cell:(i + 1) * cell] = colour
    return img


def main(names=()):
    from PIL import Image
    preview_dir = os.environ.get("XC_PREVIEW_DIR", "art/previews")
    os.makedirs(OUT, exist_ok=True)
    for old in ("sjPalette_diffuse.dds", "sjPole_red_diffuse.dds", "sjPole_blue_diffuse.dds"):
        if os.path.exists(os.path.join(OUT, old)):
            os.remove(os.path.join(OUT, old))
    def texture(file):
        return np.asarray(Image.open(os.path.join("placeables/xcJumps", file)).convert("RGB"), dtype=float)
    peeled, planks = texture("xcPeeled_diffuse.dds"), texture("xcPlanks_diffuse.dds")
    for jump in JUMPS:
        if names and jump["name"] not in names:
            continue
        parts, flags, feet = frame(jump)
        pole_shapes = {}
        for a, b in jump["poles"]:
            _, _, length = pole_pose(a, b)
            key = round(length, 3)
            if key not in pole_shapes:
                pole_shapes[key] = pole_meshes(key)
        write_i3d(jump, os.path.join(OUT, jump["name"] + ".i3d"), parts, flags, feet, pole_shapes)
        write_xml(jump, os.path.join(OUT, jump["name"] + ".xml"))
        # the shop image: the poles placed where the i3d puts them
        paint_rgb, wing_rgb, white_rgb = flat(COLOUR[jump["colour"]]), flat(COLOUR[jump["wingColour"]]), flat(WHITE)
        # the shop image shows the jump plain (Sponsor boards is a choice); the env var shows them
        if os.environ.get("SJ_SPONSOR_PREVIEW"):
            sponsor_rgb = np.asarray(Image.open(os.path.join("placeables/bleachers", "bleacherSponsor_diffuse.dds")).convert("RGB"), dtype=float)
            extra = [(parts.board, white_rgb), (parts.board_paint, paint_rgb)]
            for logo in parts.logos.values():
                m = Mesh()
                m.verts = [(p, n, (uv[0], 1 - uv[1])) for p, n, uv in logo.verts]
                m.tris = list(logo.tris)
                extra.append((m, sponsor_rgb))
        else:
            extra = [(parts.unsponsored_wing, flat(COLOUR[jump["wingColour"]]))]
        meshes = extra + [(parts.white, white_rgb), (parts.paint, paint_rgb), (parts.wing, wing_rgb), (parts.metal, flat(METAL)),
                  (parts.water, flat(WATER)), (parts.peeled, peeled), (parts.planks, planks), (flags, flags_texture())]
        for a, b in jump["poles"]:
            mid, rot, length = pole_pose(a, b)
            paint, white, caps = pole_shapes[round(length, 3)]
            meshes += [(place(paint, mid, rot), paint_rgb), (place(white, mid, rot), white_rgb), (place(caps, mid, rot), white_rgb)]
        top = max(max(a[1], b[1]) for a, b in jump["poles"]) + POLE_R
        store_image([m for m in meshes if m[0].tris], os.path.join(OUT, "store_" + jump["name"] + ".dds"), preview_dir)
        print(jump["name"], f"{top:.2f} m,", len(jump["poles"]), "poles,", len(parts.cols), "collision boxes")


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
