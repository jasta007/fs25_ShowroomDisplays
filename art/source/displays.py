"""
Builds the display pieces in placeables/displays/: drive-through display, display ramps (small and
large), platform display ramp and turntable. Started from Realistic Equestrian's plinths.py; the
helpers xc_jumps.py, show_jumps.py and eqdds.py are copied from Realistic Equestrian as they are.

Changes from the REQ plinths (James, 2026-11-02):
- Logos show the whole brand image (the game's logos are 512 x 256, some fill the square edge to
  edge: John Deere, Remprodex) on a 2:1 face with a margin inside the white board.
- Round shapes (turntable base, collar, disc, curved board) have smooth normals, so no shading
  bands, and stone is mapped in world space, so neighbouring panels carry on the texture instead
  of repeating it.
- Copings are mitred where they meet at a corner and follow the top they sit on.

Node names the scripts look for: "eqPaint" (painted copings and rims), "eqBoardFace" (the board's
white face), "eqSponsor_<n>" / "...b" (logo faces), "eqTurntableDisc" (the turning disc). Keep the
deck areas in scripts/SdDisplays.lua (AREAS) in step with the sizes here.

The geometry is inline: re-save the i3ds in GIANTS Editor so their collision works in game.

Run from the repository root: python3 art/source/displays.py [names]

Part of Showroom Displays by Jasta007.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import show_jumps as sj  # noqa: E402
import xc_jumps as xc  # noqa: E402
from xc_jumps import COLLISION_MASK, Mesh, fmt, shape_lines  # noqa: E402

# Logo faces show the whole image, no crop (xc.shape_lines reads this).
xc.LOGO_CROP = (0.0, 1.0, 0.0, 1.0)

COLLISION_GROUP = "0x1037"   # REQ's jumps' group plus the ground bits a drive-on floor has (hoof sounds)
OUT = "placeables/displays"
STONE = "plinthStone_diffuse.dds"
STONE_TILE = 5.0
METAL = "plinthMetal_diffuse.dds"
METAL_TILE = 1.6
LOGO_TEXTURE = "displayLogo_diffuse.dds"
LOGO_ASPECT = 2.0            # the game's brand logos are 512 x 256
LOGO_MARGIN = 0.05           # bare board round the logo image, metres
RIM = 0.04                   # the painted rim round a board's white face
COPING = (0.14, 0.06, 0.04)  # width, how far it stands over the top, how far down it reaches
CLIP = 600

PIECES = [
    {"name": "driveThrough", "colour": "navy"},
    {"name": "displayRamp", "colour": "green", "size": (3.0, 4.6, 1.2)},
    {"name": "displayRampLarge", "colour": "green", "size": (3.8, 6.6, 1.6)},
    {"name": "productRamp", "colour": "red"},
    {"name": "turntable", "colour": "navy"},
]
DRIVE = {"half_x": 1.6, "half_deck": 3.0, "ramp": 3.5, "height": 0.75}
PRODUCT = {"half_x": 2.0, "top": 1.5, "ramp": 7.5, "height": 2.0}
TURNTABLE = {"radius": 4.0, "disc": 3.45, "height": 0.7, "ramp": 3.5, "ramp_half": 1.6, "sides": 96}
DISC = "eqTurntableDisc"


# ---------------------------------------------------------------- mesh helpers

def face_normal(a, b, c):
    return xc.norm(xc.cross(xc.sub(b, a), xc.sub(c, a)))


def world_uv(p, n, tile):
    """Planar mapping by the face's main axis, in metres / tile: faces side by side carry on."""
    ax = max(range(3), key=lambda i: abs(n[i]))
    if ax == 0:
        return (p[2] / tile, p[1] / tile)
    if ax == 1:
        return (p[0] / tile, p[2] / tile)
    return (p[0] / tile, p[1] / tile)


def poly(mesh, pts, inside, tile=None, uvs=None):
    """A flat convex polygon facing away from the point inside."""
    n = face_normal(pts[0], pts[1], pts[2])
    centre = tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))
    if xc.dot(n, xc.sub(centre, inside)) < 0:
        n = (-n[0], -n[1], -n[2])
    ids = [mesh.vertex(p, n, uvs[k] if uvs else world_uv(p, n, tile or 1.0)) for k, p in enumerate(pts)]
    for k in range(1, len(ids) - 1):
        mesh.tri(ids[0], ids[k], ids[k + 1])


def hexa(mesh, bottom, top, tile=1.0):
    """A solid from 4 bottom and 4 top corners (each in the same order round it): flat faces."""
    inside = tuple(sum(p[i] for p in bottom + top) / 8 for i in range(3))
    poly(mesh, bottom, inside, tile)
    poly(mesh, top, inside, tile)
    for k in range(4):
        j = (k + 1) % 4
        poly(mesh, [bottom[k], bottom[j], top[j], top[k]], inside, tile)


def extrude_x(mesh, profile, x0, x1, tile=STONE_TILE):
    """A convex side outline [(z, y), ...] run across x0..x1, every face world mapped."""
    cz = sum(z for z, _ in profile) / len(profile)
    cy = sum(y for _, y in profile) / len(profile)
    inside = ((x0 + x1) / 2, cy, cz)
    poly(mesh, [(x0, y, z) for z, y in profile], inside, tile)
    poly(mesh, [(x1, y, z) for z, y in profile], inside, tile)
    for k in range(len(profile)):
        (za, ya), (zb, yb) = profile[k], profile[(k + 1) % len(profile)]
        poly(mesh, [(x0, ya, za), (x0, yb, zb), (x1, yb, zb), (x1, ya, za)], inside, tile)


def solid(mesh, col, profile, x0, x1):
    extrude_x(mesh, profile, x0, x1)
    extrude_x(col, profile, x0, x1)


def coping_run(mesh, plan, ytop):
    """A painted coping: plan = 4 corners (x, z) in order round it; its bottom and top follow the
    surface height ytop(z), so runs that share corners meet cleanly (mitred in plan)."""
    _, up, down = COPING
    bottom = [(x, ytop(z) - down, z) for x, z in plan]
    top = [(x, ytop(z) + up, z) for x, z in plan]
    hexa(mesh, bottom, top)


def cylinder(mesh, radius, y0, y1, sides, tile=STONE_TILE, caps=True, a0=0.0, a1=2 * math.pi):
    """An upright cylinder (or part of one) with smooth sides: u runs round it, v up it."""
    steps = max(2, int(round(sides * (a1 - a0) / (2 * math.pi))))
    ring = []
    for k in range(steps + 1):
        a = a0 + (a1 - a0) * k / steps
        n = (math.cos(a), 0.0, math.sin(a))
        u = radius * (a - a0) / tile
        p0 = (radius * n[0], y0, radius * n[2])
        p1 = (radius * n[0], y1, radius * n[2])
        ring.append((mesh.vertex(p0, n, (u, y0 / tile)), mesh.vertex(p1, n, (u, y1 / tile))))
    for (b0, t0), (b1, t1) in zip(ring, ring[1:]):
        mesh.tri(b0, b1, t1)
        mesh.tri(b0, t1, t0)
    if caps:
        for y, n in ((y1, (0.0, 1.0, 0.0)), (y0, (0.0, -1.0, 0.0))):
            centre = mesh.vertex((0.0, y, 0.0), n, (0.0, 0.0))
            rim = [mesh.vertex((radius * math.cos(a0 + (a1 - a0) * k / steps), y, radius * math.sin(a0 + (a1 - a0) * k / steps)),
                               n, (radius * math.cos(a0 + (a1 - a0) * k / steps) / tile,
                                   radius * math.sin(a0 + (a1 - a0) * k / steps) / tile))
                   for k in range(steps + 1)]
            for a, b in zip(rim, rim[1:]):
                mesh.tri(centre, a, b)


def flat_cylinder(mesh, radius, y0, y1, sides):
    """Collision: a plain prism is enough."""
    pts = [(radius * math.cos(2 * math.pi * k / sides), radius * math.sin(2 * math.pi * k / sides)) for k in range(sides)]
    sj.prism(mesh, pts, (0.0, y0, 0.0), (1, 0, 0), (0, 0, 1), (0, 1, 0), y1 - y0)


def arc_slab(mesh, r_in, r_out, a0, a1, y0, y1, steps):
    """A curved slab round the front (angle a: x = r sin a, z = -r cos a), smooth on its outer
    face, flat on its ends, top and bottom."""
    def at(r, a, y):
        return (r * math.sin(a), y, -r * math.cos(a))
    outer = []
    for k in range(steps + 1):
        a = a0 + (a1 - a0) * k / steps
        n = (math.sin(a), 0.0, -math.cos(a))
        outer.append((mesh.vertex(at(r_out, a, y0), n, (0, 0)), mesh.vertex(at(r_out, a, y1), n, (0, 0))))
    for (b0, t0), (b1, t1) in zip(outer, outer[1:]):
        mesh.tri(b0, b1, t1)
        mesh.tri(b0, t1, t0)
    mid = (a0 + a1) / 2
    inside = at((r_in + r_out) / 2, mid, (y0 + y1) / 2)
    for k in range(steps):
        b, c = a0 + (a1 - a0) * k / steps, a0 + (a1 - a0) * (k + 1) / steps
        for y in (y0, y1):
            poly(mesh, [at(r_in, b, y), at(r_out, b, y), at(r_out, c, y), at(r_in, c, y)], inside, uvs=[(0, 0)] * 4)
    for a in (a0, a1):
        poly(mesh, [at(r_in, a, y0), at(r_out, a, y0), at(r_out, a, y1), at(r_in, a, y1)], inside, uvs=[(0, 0)] * 4)


# ---------------------------------------------------------------- boards

def logo_size(face_w, face_h):
    """The logo face inside a white face: 2:1, LOGO_MARGIN clear of its edges."""
    lw, lh = face_w - 2 * LOGO_MARGIN, face_h - 2 * LOGO_MARGIN
    if lw / lh > LOGO_ASPECT:
        lw = lh * LOGO_ASPECT
    else:
        lh = lw / LOGO_ASPECT
    return lw, lh


def side_board(white, paint, logos, number, x, z, y0, width, height, facing):
    """A board on a side face at x facing +x (1) or -x (-1), centred on z, foot at y0."""
    t = 0.04
    xa, xb = sorted((x, x + facing * t))
    hexa(paint, [(xa, y0, z - width / 2), (xb, y0, z - width / 2), (xb, y0, z + width / 2), (xa, y0, z + width / 2)],
         [(xa, y0 + height, z - width / 2), (xb, y0 + height, z - width / 2), (xb, y0 + height, z + width / 2),
          (xa, y0 + height, z + width / 2)])
    fa, fb = sorted((x + facing * t, x + facing * (t + 0.005)))
    w, h = width - 2 * RIM, height - 2 * RIM
    hexa(white, [(fa, y0 + RIM, z - w / 2), (fb, y0 + RIM, z - w / 2), (fb, y0 + RIM, z + w / 2), (fa, y0 + RIM, z + w / 2)],
         [(fa, y0 + RIM + h, z - w / 2), (fb, y0 + RIM + h, z - w / 2), (fb, y0 + RIM + h, z + w / 2), (fa, y0 + RIM + h, z + w / 2)])
    lw, lh = logo_size(w, h)
    xl = x + facing * (t + 0.008)
    yc = y0 + height / 2
    left, right = (z + lw / 2, z - lw / 2) if facing > 0 else (z - lw / 2, z + lw / 2)
    logo = Mesh()
    logo.quad([(xl, yc - lh / 2, left), (xl, yc - lh / 2, right), (xl, yc + lh / 2, right), (xl, yc + lh / 2, left)],
              (facing, 0, 0), [(0, 0), (1, 0), (1, 1), (0, 1)])
    logos[f"eqSponsor_{number}" + ("" if facing > 0 else "b")] = logo


def front_board(white, paint, logos, number, z, y0, width, height):
    """A board on a front face at z facing -z, centred on x = 0."""
    t = 0.04
    za, zb = z - t, z
    hexa(paint, [(-width / 2, y0, za), (width / 2, y0, za), (width / 2, y0, zb), (-width / 2, y0, zb)],
         [(-width / 2, y0 + height, za), (width / 2, y0 + height, za), (width / 2, y0 + height, zb), (-width / 2, y0 + height, zb)])
    w, h = width - 2 * RIM, height - 2 * RIM
    fa = z - t - 0.005
    hexa(white, [(-w / 2, y0 + RIM, fa), (w / 2, y0 + RIM, fa), (w / 2, y0 + RIM, za), (-w / 2, y0 + RIM, za)],
         [(-w / 2, y0 + RIM + h, fa), (w / 2, y0 + RIM + h, fa), (w / 2, y0 + RIM + h, za), (-w / 2, y0 + RIM + h, za)])
    lw, lh = logo_size(w, h)
    yc, zl = y0 + height / 2, z - t - 0.008
    logo = Mesh()
    logo.quad([(lw / 2, yc - lh / 2, zl), (-lw / 2, yc - lh / 2, zl), (-lw / 2, yc + lh / 2, zl), (lw / 2, yc + lh / 2, zl)],
              (0, 0, -1), [(0, 0), (1, 0), (1, 1), (0, 1)])
    logos[f"eqSponsor_{number}"] = logo


# ---------------------------------------------------------------- pieces

def side_copings(paint, half_x, stations, ytop, front_mitre=False):
    """Copings along both long top edges, through the z stations given; with front_mitre the
    first corner is cut at 45 degrees to meet a front coping (see front_coping)."""
    w = COPING[0]
    xo, xi = half_x + 0.02, half_x + 0.02 - w
    for side in (1, -1):
        for k, (za, zb) in enumerate(zip(stations, stations[1:])):
            zia = za + w if (front_mitre and k == 0) else za
            plan = [(side * xo, za), (side * xo, zb), (side * xi, zb), (side * xi, zia)]
            coping_run(paint, plan, ytop)


def front_coping(paint, half_x, z_front, ytop):
    """The coping along the front top edge at z_front (outer edge 0.02 proud of it), mitred into
    the side copings."""
    w = COPING[0]
    xo, xi = half_x + 0.02, half_x + 0.02 - w
    zo, zi = z_front - 0.02, z_front - 0.02 + w
    coping_run(paint, [(-xo, zo), (xo, zo), (xi, zi), (-xi, zi)], ytop)


def drive():
    stone, paint, white, col, logos = Mesh(), Mesh(), Mesh(), Mesh(), {}
    hx, hd, r, h = DRIVE["half_x"], DRIVE["half_deck"], DRIVE["ramp"], DRIVE["height"]
    solid(stone, col, [(-hd - r, 0.0), (-hd, 0.0), (-hd, h)], -hx, hx)
    solid(stone, col, [(-hd, 0.0), (hd, 0.0), (hd, h), (-hd, h)], -hx, hx)
    solid(stone, col, [(hd, 0.0), (hd + r, 0.0), (hd, h)], -hx, hx)

    def ytop(z):
        if z < -hd:
            return h * (z + hd + r) / r
        if z > hd:
            return h * (hd + r - z) / r
        return h
    side_copings(paint, hx, [-hd - r, -hd, hd, hd + r], ytop)
    for side in (1, -1):
        side_board(white, paint, logos, 1, side * hx, 0.0, 0.08, 2 * hd - 1.2, h - 0.2, side)
    return {"stone": stone, "paint": paint, "white": white}, logos, col


def ramp(size):
    stone, paint, white, col, logos = Mesh(), Mesh(), Mesh(), Mesh(), {}
    w, length, h = size
    zf, zb = -length / 2, length / 2
    solid(stone, col, [(zf, 0.0), (zb, 0.0), (zf, h)], -w / 2, w / 2)

    def ytop(z):
        return h if z <= zf else h * (zb - z) / length
    front_coping(paint, w / 2, zf, ytop)
    side_copings(paint, w / 2, [zf - 0.02, zb], ytop, front_mitre=True)
    front_board(white, paint, logos, 1, zf, 0.12, w - 0.4, h - 0.32)
    return {"stone": stone, "paint": paint, "white": white}, logos, col


def product():
    """One bank: its 2 m face at z = 0 facing -z, a short flat top, then the ramp down."""
    stone, paint, white, col, logos = Mesh(), Mesh(), Mesh(), Mesh(), {}
    hx, top, r, h = PRODUCT["half_x"], PRODUCT["top"], PRODUCT["ramp"], PRODUCT["height"]
    solid(stone, col, [(0.0, 0.0), (top, 0.0), (top, h), (0.0, h)], -hx, hx)
    solid(stone, col, [(top, 0.0), (top + r, 0.0), (top, h)], -hx, hx)

    def ytop(z):
        return h if z <= top else h * (top + r - z) / r
    front_coping(paint, hx, 0.0, ytop)
    side_copings(paint, hx, [-0.02, top, top + r], ytop, front_mitre=True)
    for side in (1, -1):
        side_board(white, paint, logos, 1, side * hx, 2.0, 0.28, 3.0, 1.05, side)
    return {"stone": stone, "paint": paint, "white": white}, logos, col


def turntable():
    stone, paint, white, col, logos, disc = Mesh(), Mesh(), Mesh(), Mesh(), {}, Mesh()
    t = TURNTABLE
    R, r, h, n = t["radius"], t["disc"], t["height"], t["sides"]
    cylinder(stone, R, 0.0, h, n)
    flat_cylinder(col, R, 0.0, h + 0.02, 48)
    cylinder(paint, R + 0.012, h - 0.12, h + 0.015, n)
    cylinder(disc, r, h - 0.03, h + 0.02, n, tile=METAL_TILE)
    hw, length = t["ramp_half"], t["ramp"]
    z0, z1 = r + 0.02, R + 0.05
    top = h + 0.008
    solid(stone, col, [(z0, 0.0), (R + length, 0.0), (z1, top), (z0, top)], -hw, hw)
    # the curved board round the front, sized to its logo
    # as tall as the base allows (up to the collar), a small margin: most logos have their own
    y0, bh = 0.04, h - 0.12 - 0.04
    margin = 0.025
    face_h = bh - 2 * RIM
    lh = face_h - 2 * margin
    lw = lh * LOGO_ASPECT
    width = lw + 2 * margin + 2 * RIM + 0.16
    steps = 24
    span = width / R
    arc_slab(paint, R - 0.01, R + 0.04, -span / 2, span / 2, y0, y0 + bh, steps)
    trim = RIM / R
    arc_slab(white, R + 0.03, R + 0.046, -span / 2 + trim, span / 2 - trim, y0 + RIM, y0 + bh - RIM, steps)
    logo = Mesh()
    rl = R + 0.048
    la = lw / rl
    yc = y0 + bh / 2
    for k in range(steps):
        a0 = -la / 2 + la * k / steps
        a1 = -la / 2 + la * (k + 1) / steps
        u0, u1 = 1 - k / steps, 1 - (k + 1) / steps
        corners, uvs = [], []
        for a, u in ((a0, u0), (a1, u1)):
            corners.append((rl * math.sin(a), -rl * math.cos(a)))
            uvs.append(u)
        ids = []
        for (x, z), u, a in zip(corners, uvs, (a0, a1)):
            nm = (math.sin(a), 0.0, -math.cos(a))
            ids.append((logo.vertex((x, yc - lh / 2, z), nm, (u, 0)), logo.vertex((x, yc + lh / 2, z), nm, (u, 1))))
        (b0, t0), (b1, t1) = ids
        logo.tri(b0, b1, t1)
        logo.tri(b0, t1, t0)
    logos["eqSponsor_1"] = logo
    return {"stone": stone, "paint": paint, "white": white, "disc": disc}, logos, col


# ---------------------------------------------------------------- i3d

def write_i3d(name, colour, path, statics, logos, col):
    files = [sj.SHADER] + list(sj.PAINT_MAPS.values()) + [STONE, LOGO_TEXTURE, METAL]
    fid = {f: i + 1 for i, f in enumerate(files)}
    mat = {"stone": 1, "paint": 2, "white": 3, "logo": 4, "metal": 5}

    def paint_material(mname, mid, rgb):
        lines = [f'    <Material name="{mname}" materialId="{mid}" customShaderId="{fid[sj.SHADER]}">']
        lines += [f'      <Custommap name="{k}" fileId="{fid[v]}"/>' for k, v in sj.PAINT_MAPS.items()]
        lines += [f'      <CustomParameter name="colorScale" value="{fmt(rgb)}"/>',
                  '      <CustomParameter name="smoothnessScale" value="0.55"/>',
                  '      <CustomParameter name="metalnessScale" value="0"/>', "    </Material>"]
        return lines
    lines = ['<?xml version="1.0" encoding="iso-8859-1"?>', "",
             f'<i3D name="{name}" version="1.6" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
             'xsi:noNamespaceSchemaLocation="http://i3d.giants.ch/schema/i3d-1.6.xsd">',
             "  <Asset>", '    <Export program="Showroom Displays displays.py" version="1"/>', "  </Asset>", "  <Files>"]
    lines += [f'    <File fileId="{fid[f]}" filename="{f}"/>' for f in files]
    lines += ["  </Files>", "  <Materials>",
              f'    <Material name="plinthStone" materialId="{mat["stone"]}" specularColor="0.15 0.6 0">',
              f'      <Texture fileId="{fid[STONE]}"/>', "    </Material>"]
    lines += paint_material("plinthPaint", mat["paint"], sj.COLOUR[colour])
    lines += paint_material("plinthWhite", mat["white"], sj.WHITE)
    # the logo renders as a decal (vehicleShader): nothing shows where its alpha is 0
    lines += [f'    <Material name="eqSponsor" materialId="{mat["logo"]}" specularColor="0.2 0 0" alphaBlending="true" '
              f'customShaderId="{fid[sj.SHADER]}">',
              f'      <Texture fileId="{fid[LOGO_TEXTURE]}"/>']
    lines += [f'      <Custommap name="{k}" fileId="{fid[v]}"/>' for k, v in sj.PAINT_MAPS.items()]
    lines += ["    </Material>",
              f'    <Material name="plinthMetal" materialId="{mat["metal"]}" specularColor="0.6 0.6 0">',
              f'      <Texture fileId="{fid[METAL]}"/>', "    </Material>", "  </Materials>"]
    shapes = [(f"s_{k}", m) for k, m in statics.items() if m.tris] + [(f"l_{k}", m) for k, m in logos.items()]
    shapes.append(("col", col))
    ids = {key: i + 1 for i, (key, _) in enumerate(shapes)}
    lines.append("  <Shapes>")
    for key, mesh in shapes:
        lines += shape_lines(mesh, f"{name}_{key}", ids[key])
    lines += ["  </Shapes>", "  <Scene>"]
    node = [1]

    def nid():
        node[0] += 1
        return node[0]
    names = {"stone": "stone", "paint": "eqPaint", "white": "eqBoardFace"}
    lines.append(f'    <TransformGroup name="{name}" nodeId="1">')
    for key, mesh in statics.items():
        if mesh.tris and key == "disc":
            lines.append(f'      <TransformGroup name="{DISC}" nodeId="{nid()}">')
            lines.append(f'        <Shape name="disc" shapeId="{ids["s_" + key]}" clipDistance="{CLIP}" nodeId="{nid()}" '
                         f'materialIds="{mat["metal"]}" castsShadows="true" receiveShadows="true"/>')
            lines.append("      </TransformGroup>")
        elif mesh.tris:
            lines.append(f'      <Shape name="{names[key]}" shapeId="{ids["s_" + key]}" clipDistance="{CLIP}" nodeId="{nid()}" '
                         f'materialIds="{mat[key]}" castsShadows="true" receiveShadows="true"/>')
    for key in logos:
        lines.append(f'      <Shape name="{key}" shapeId="{ids["l_" + key]}" clipDistance="{CLIP}" nodeId="{nid()}" '
                     f'materialIds="{mat["logo"]}" castsShadows="false" receiveShadows="true"/>')
    lines.append(f'      <TransformGroup name="collision" nodeId="{nid()}">')
    lines.append(f'        <Shape name="col" shapeId="{ids["col"]}" static="true" collisionFilterGroup="{COLLISION_GROUP}" '
                 f'collisionFilterMask="{COLLISION_MASK}" density="0.01" nodeId="{nid()}" nonRenderable="true" materialIds="1"/>')
    lines += ["      </TransformGroup>", "    </TransformGroup>", "  </Scene>", "</i3D>"]
    with open(path, "w", encoding="iso-8859-1", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def main(names=()):
    builders = {"driveThrough": drive, "displayRamp": lambda: ramp(PIECES[1]["size"]),
                "displayRampLarge": lambda: ramp(PIECES[2]["size"]), "productRamp": product, "turntable": turntable}
    for piece in PIECES:
        name = piece["name"]
        if names and name not in names:
            continue
        statics, logos, col = builders[name]()
        write_i3d(name, piece["colour"], os.path.join(OUT, name + ".i3d"), statics, logos, col)
        print(name, len(logos), "logo faces,", sum(len(m.tris) for m in statics.values()), "triangles,",
              len(col.tris), "collision triangles")


if __name__ == "__main__":
    main(tuple(sys.argv[1:]))
