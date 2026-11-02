"""
Builds the cross country fences in placeables/xcJumps/: one .xml and .i3d per fence, the textures
they share and a shop image for each.

The cross country flags are the core: one spline fence (courseFlags) whose segment types are a
white flag, a gold guide line on the ground and a red flag, set along anything the player wants
ridden as a fence (a map's logs, a table or hedge from any mod). EqXcFlags pairs each red flag with
the nearest white one and the line between them is where the fence is crossed; the obstacle itself
is what gets jumped. The log piles and drop walls are ready-made
fences.

Like the dressage arenas, the .i3d files keep their geometry inline (<IndexedTriangleSet>), so no
GIANTS tools are needed, and the textures are painted here rather than downloaded, so every pixel
is ours.

A log pile is a pyramid of logs lying along x, so the horse jumps it along z. Each fence has:
- "logs" and "logEnds": the visible logs (bark) and their sawn ends (rings),
- "flags": a flag at each end of the face, red at +x and white at -x; the empty transform groups
  "eqFlagsRed" and "eqFlagsWhite" at their feet are what the course recorder reads as the jump's
  two ends (EqCourseHooks.findFlags, as with Riding Hall's "modernFlagsRed"/"modernFlagsWhite"),
- "collision": one invisible static prism following the pile's outline, with the collision filter
  Riding Hall 2k26's jumps use, so the horse has to jump it and can't snag on single logs.

Run from the repository root: python3 art/source/xc_jumps.py

Part of Realistic Equestrian by Jasta007.
"""

import math
import os
import random
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from eqdds import save_bc7, save_dxt1

OUT = "placeables/xcJumps"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# name, price, the logs in each row from the bottom up, log diameter and length (metres)
LOG_PILES = [
    {"name": "xcLogPileSmall", "price": 600, "rows": [2, 1], "diameter": 0.40, "length": 3.6, "seed": 3},
    {"name": "xcLogPile", "price": 900, "rows": [3, 2, 1], "diameter": 0.38, "length": 4.2, "seed": 7},
]

# The flag fence (James, 2026-10-27): one spline fence, placed like the base game's pillar fences,
# whose N/M segment types are a white flag (a one-click post), a gold guide line on the ground
# that stretches along whatever the player wants jumped, and a red flag. The line shows only in
# construction mode and while a course is edited. It was a bar at the fence height (0.6, 0.9 or
# 1.2 m) with collision until James found it looked bad and gave false faults (2026-10-28): now
# the jump is judged by the obstacle itself.
FLAG_FENCE = "courseFlags"
FLAG_FENCE_PRICE = 10
FLAG_POST = 0.3         # a flag post's length along the fence line (a fixed "gate" segment)
LINE_ID = "BAR_90"      # the guide line's segment id: the old 0.9 m bar's, so saved fences keep it
LINE_NODE = "eqXcLine"
LINE_WIDTH = 0.08
LINE_BOTTOM = 0.01      # just off the ground
LINE_TOP = 0.025
BAR_PANEL = 1.0         # line panels repeat every metre, stretched up to BAR_MAX_SCALE
BAR_MAX_SCALE = 1.5
FENCE_COLLISION_GROUP = "0x3e"   # the base game fences' collision, which construction picks to delete
GUIDE = "eqXcGuide"     # the gold guide line: construction mode and course editing only
GUIDE_LENGTH = 0.9
GUIDE_SIZE = 0.03

# Drop walls: a timber retaining wall for the edge of a bank the player sculpts (James, 2026-10-27).
# The face is along x and faces -z (the low side); its top edge, the lip, is 1 m in front of the
# origin, so the placeable takes its height from the flat top of the bank, not the slope. The boards
# go SKIRT below the drop so they tuck into wherever the low ground ends up. Triangle wing walls at
# each end run back over the bank's sides; a half-round log caps the lip. No terrain levelling.
DROP_WALLS = [
    {"name": "xcDropWall08", "price": 1500, "drop": 0.8},
    {"name": "xcDropWall12", "price": 1800, "drop": 1.2},
    {"name": "xcDropWall16", "price": 2100, "drop": 1.6, "sponsor": True},
]
# The biggest drop wall carries a sponsor board high on its face instead of the two middle posts
# (James, 2026-10-31: the bottom gets clipped by the ground a lot): width, height, gap under the lip.
DROP_BOARD = (3.2, 0.9, 0.08)
LOGO_ASPECT = 2.7       # a logo's width over its height on every board (as on the bleachers)
LOGO_MARGIN = 0.03
SPONSOR_TEXTURE = "../bleachers/bleacherSponsor_diffuse.dds"
DROP_WIDTH = 4.0
DROP_LIP = 1.0          # the lip is this far in front of the origin
SKIRT = 0.5             # boards and posts reach this far below the drop
BOARD_T = 0.05          # board thickness
POST_W = 0.16           # square posts
POST_STEP = 1.4         # most space between posts along the face
CAP_R = 0.15            # the half-round log along the lip
RAIL_R = 0.07           # the round rail along each wing's top
DECK_Y = 0.05           # the plank deck's top, over the wall tops (James: hides the bank top)
PLANK_TILE = (2.0, 1.6) # metres one plank texture covers, along and up (8 boards of 0.2 m)

SIDES = 22              # faces round each log
RING_STEP = 0.22        # metres between rings along a log (more rings: room to bend and bulge)
SINK = 0.04             # logs sit this far into the ground so they never float on a slope
STAGGER = 0.18          # most a log's ends stick out past the others (either way)
TAPER = 0.10            # a log is up to this share thinner at one end
LUMPS = 0.05            # how far a log's outline wanders from a circle (share of radius)
BEND = 0.035            # most a log bows sideways along its length (metres)
KNOTS = (2, 5)          # swellings round old branches, per log
STUBS = (1, 3)          # sawn-off branch stubs, per log
CUT_TILT = 0.14         # a sawn end leans by up to this (rise over run)
BARK_TILE = 1.1         # metres of log one bark texture covers along it (it wraps once round)
FLAG_GAP = 0.3          # flags stand this far past the logs' ends
POLE_HEIGHT = 1.5       # above the ground; the pole goes 0.15 m into it
POLE_R = 0.018
PENNANT_H = 0.30        # down the pole
PENNANT_W = 0.40        # out from the pole
SLEEVE_R = 0.026        # the pennant's sleeve wraps the top of the pole
CLIP = 300              # fences are small: drawn out to 300 m
# Riding Hall 2k26's static jump collision ("col" in props01.i3d): blocks the horse and the player.
COLLISION_GROUP = "0x1034"
COLLISION_MASK = "0xfffffbff"


# ---------------------------------------------------------------------------------------------
# Textures

def periodic_noise(size, rng, scale_u, scale_v):
    """Smooth noise that tiles: white noise filtered in frequency space. scale_* = feature size in
    pixels across u (columns) and v (rows); a long v scale makes streaks running along v."""
    white = rng.standard_normal((size, size))
    fu = np.fft.fftfreq(size)[None, :]
    fv = np.fft.fftfreq(size)[:, None]
    gain = np.exp(-((fu * scale_u) ** 2 + (fv * scale_v) ** 2) * 4)
    out = np.real(np.fft.ifft2(np.fft.fft2(white) * gain))
    return (out - out.mean()) / (out.std() + 1e-9)


def save_dds(rgb, path):
    save_dxt1(rgb, path)


def normal_map(height, path, strength):
    """A tangent space normal map (green up) from a tiling height field."""
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * strength
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * strength
    n = np.stack([-dx, dy, np.ones_like(height)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    save_dds((n * 0.5 + 0.5) * 255, path)


# Two barks, so neighbouring logs differ: a deeply fissured old trunk and a smoother, younger one
# with lichen. u runs once round the log, starting on top (u = 0 and 1); v runs along it.
BARKS = [
    {"name": "xcBarkA", "seed": 11, "lanes": 9, "fissure": 0.62, "plates": 70, "base": (104, 86, 68),
     "lichen": 0.0, "moss": 0.9, "bare": 0.10},
    {"name": "xcBarkB", "seed": 23, "lanes": 14, "fissure": 0.35, "plates": 30, "base": (118, 104, 88),
     "lichen": 0.7, "moss": 0.55, "bare": 0.05},
]


def bark_texture(bark, path, normal_path, size=512):
    """Bark with fissures along the log, cross breaks, moss along the top of the log, lichen
    spots and a few patches where the bark has come off and the grey wood shows."""
    rng = np.random.default_rng(bark["seed"])
    wobble = periodic_noise(size, rng, 40, 90) * 6
    cols = (np.arange(size)[None, :] + wobble) % size
    ridges = np.zeros((size, size))
    lanes = bark["lanes"]
    phase = periodic_noise(size, rng, 200, 160)
    for k in range(lanes):
        centre = (k + rng.uniform(0.2, 0.8)) * size / lanes
        d = np.abs(((cols - centre + size / 2) % size) - size / 2)
        width = (4.5 + 2.5 * phase) * (12 / lanes) ** 0.5
        ridges = np.maximum(ridges, np.clip(1 - d / np.maximum(width, 1.5), 0, 1))
    breaks = np.clip(periodic_noise(size, rng, 6, 2) - 1.5, 0, 1)
    plates = periodic_noise(size, rng, 30, bark["plates"])
    grain = periodic_noise(size, rng, 1.5, 6)
    height = 1 - bark["fissure"] * ridges ** 1.5 - 0.3 * breaks + 0.15 * plates + 0.05 * grain
    light = 0.62 + 0.10 * plates + 0.06 * grain - bark["fissure"] * 0.9 * ridges ** 1.5 - 0.25 * breaks
    base = np.array(bark["base"], dtype=float)
    tint = periodic_noise(size, rng, 80, 80)[..., None] * np.array([7, 5, 3])
    rgb = np.clip(light, 0.08, 1)[..., None] * (base + tint) * 1.25

    u = (np.arange(size)[None, :] + 0.5) / size
    top = np.exp(-(np.minimum(u, 1 - u) / 0.16) ** 2)   # u = 0 is the top of the log
    # moss: soft green clumps along the top, filling the fissures first
    clumps = periodic_noise(size, rng, 14, 18) + 0.8 * periodic_noise(size, rng, 5, 5)
    moss = np.clip((clumps + 1.6 * top - 1.2 + 0.6 * ridges) * 1.4, 0, 1) * bark["moss"] * (0.25 + 0.75 * top)
    moss_colour = np.array([78, 104, 38]) + periodic_noise(size, rng, 6, 6)[..., None] * np.array([12, 14, 6])
    rgb = rgb * (1 - moss[..., None]) + moss_colour * (0.6 + 0.4 * light[..., None]) * moss[..., None]
    height = height + 0.25 * moss
    # lichen: small pale grey-green spots anywhere
    spots = np.clip((periodic_noise(size, rng, 7, 7) - 1.7) * 1.5, 0, 0.75) * bark["lichen"]
    spots *= np.clip(periodic_noise(size, rng, 40, 40) + 0.5, 0, 1)
    rgb = rgb * (1 - spots[..., None]) + np.array([150, 160, 128]) * (0.8 + 0.2 * grain[..., None]) * spots[..., None]
    # bare patches: smooth grey weathered wood where the bark fell away
    bare = np.clip((periodic_noise(size, rng, 22, 40) - 2.2 + 10 * bark["bare"]) * 3, 0, 1) * (1 - top)
    bare_colour = np.array([150, 138, 120]) * (0.85 + 0.15 * periodic_noise(size, rng, 1, 30))[..., None]
    rgb = rgb * (1 - bare[..., None]) + bare_colour * bare[..., None]
    height = height * (1 - bare) + 0.55 * bare
    save_dds(rgb, path)
    normal_map(height, normal_path, strength=3.0)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def log_end_texture(path, size=256):
    """A sawn log end: pale wood with growth rings, a dark pith, a few cracks and the bark rim."""
    rng = np.random.default_rng(5)
    y, x = np.mgrid[0:size, 0:size]
    u = (x + 0.5) / size * 2 - 1
    v = (y + 0.5) / size * 2 - 1
    r = np.hypot(u, v)
    a = np.arctan2(v, u)
    wobble = periodic_noise(size, rng, 30, 30) * 0.015
    rr = r + wobble + 0.01 * np.sin(a * 3 + 1)
    rings = 0.5 + 0.5 * np.sin(rr * 2 * math.pi * 16) ** 9
    light = 0.95 - 0.10 * rings - 0.08 * rr
    # checks: splits running in from the rim, of different lengths
    for crack_angle, inner in ((0.4, 0.35), (2.6, 0.62), (4.1, 0.5), (5.3, 0.78)):
        da = np.abs((a - crack_angle + 0.04 * np.sin(r * 30) + math.pi) % (2 * math.pi) - math.pi)
        light -= 0.4 * np.clip(1 - da * r / 0.008, 0, 1) * (r > inner) * (r < 0.9)
    light -= 0.5 * np.clip(1 - r / 0.05, 0, 1)
    # a sawn end greys with weather from the rim in, and darkens where it touches the ground
    weather = np.clip(rr * 1.1 - 0.2 + periodic_noise(size, rng, 20, 20) * 0.12, 0, 1)
    rgb = light[..., None] * (np.array([214, 178, 128]) * (1 - weather[..., None]) + np.array([168, 156, 140]) * weather[..., None])
    # bark rim
    rim = np.clip((r - 0.86) / 0.04, 0, 1)[..., None]
    rgb = rgb * (1 - rim) + rim * np.array([74, 58, 44])
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    save_dxt1(rgb, path)
    return rgb


def plank_texture(path, normal_path, size=512):
    """Eight horizontal boards of sawn, weathered softwood: grain along them, a few knots, dark
    gaps between boards, each board its own shade, the lower boards darker and greener (damp)."""
    rng = np.random.default_rng(31)
    boards = 8
    row = (np.arange(size)[:, None] + 0.5) / size * boards
    board = np.floor(row).astype(int) % boards
    within = row - np.floor(row)
    grain = periodic_noise(size, rng, 40, 1.2) * 0.6 + periodic_noise(size, rng, 120, 3) * 0.4
    shade = rng.uniform(-0.08, 0.08, boards)[board]
    gap = np.clip(1 - np.minimum(within, 1 - within) / 0.035, 0, 1)
    light = 0.78 + 0.06 * grain + shade - 0.55 * gap
    # knots: dark ovals stretched along the board
    for _ in range(14):
        kx, ky = rng.uniform(0, size), (rng.integers(0, boards) + rng.uniform(0.3, 0.7)) * size / boards
        dx = np.minimum(np.abs(np.arange(size)[None, :] - kx), size - np.abs(np.arange(size)[None, :] - kx)) / 9
        dy = np.abs(np.arange(size)[:, None] - ky) / 5
        light -= 0.35 * np.exp(-(dx ** 2 + dy ** 2))
    weather = np.clip(periodic_noise(size, rng, 30, 20) * 0.5 + 0.2, 0, 1)
    damp = np.clip((row / boards - 0.55) * 2.2, 0, 1) * np.clip(periodic_noise(size, rng, 25, 8) + 0.8, 0, 1)
    colour = np.array([186, 148, 104]) * (1 - weather[..., None] * 0.35) + np.array([150, 144, 130]) * weather[..., None] * 0.35
    colour = colour * (1 - damp[..., None] * 0.4) + np.array([86, 84, 52]) * damp[..., None] * 0.4
    rgb = np.clip(light, 0.1, 1.1)[..., None] * colour
    save_dds(rgb, path)
    normal_map(0.4 * grain * 0.1 - gap, normal_path, strength=2.5)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def peeled_texture(path, size=256, seed=37, colour=(214, 178, 128), contrast=0.07):
    """Peeled softwood for posts and rails: pale, streaked along the grain (v), with a few strips
    of bark left on. Another seed, colour and contrast give a second log's wood."""
    rng = np.random.default_rng(seed)
    streaks = periodic_noise(size, rng, 1.5, 40) * 0.6 + periodic_noise(size, rng, 6, 80) * 0.4
    light = 0.82 + contrast * streaks
    rgb = light[..., None] * np.array(colour)
    bark = np.clip((periodic_noise(size, rng, 10, 60) - 1.6) * 3, 0, 1)
    rgb = rgb * (1 - bark[..., None]) + np.array([92, 74, 56]) * bark[..., None]
    save_dds(rgb, path)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def stain_texture(path, normal_path, size=512):
    """Eight boards painted with a brown wood stain (the plank corner's deck and trim): the grain
    shows through, the stain wears pale along the boards' edges, dark gaps between boards."""
    rng = np.random.default_rng(43)
    boards = 8
    row = (np.arange(size)[:, None] + 0.5) / size * boards
    board = np.floor(row).astype(int) % boards
    within = row - np.floor(row)
    grain = periodic_noise(size, rng, 50, 1.0) * 0.6 + periodic_noise(size, rng, 140, 3) * 0.4
    shade = rng.uniform(-0.05, 0.05, boards)[board]
    gap = np.clip(1 - np.minimum(within, 1 - within) / 0.03, 0, 1)
    edge = np.clip(1 - np.minimum(within, 1 - within) / 0.12, 0, 1) * np.clip(periodic_noise(size, rng, 20, 4) + 0.3, 0, 1)
    light = 0.80 + 0.07 * grain + shade - 0.6 * gap
    colour = np.array([118, 80, 62]) * (1 - 0.3 * edge[..., None]) + np.array([150, 128, 112]) * 0.3 * edge[..., None]
    rgb = np.clip(light, 0.1, 1.1)[..., None] * colour
    save_dds(rgb, path)
    normal_map(0.04 * grain - gap, normal_path, strength=2.5)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def dark_wood_texture(path, size=256):
    """Round wood treated almost black (the half roll top): streaked along the grain (v), a little
    sheen of brown where the treatment has worn."""
    rng = np.random.default_rng(47)
    streaks = periodic_noise(size, rng, 1.5, 40) * 0.6 + periodic_noise(size, rng, 6, 80) * 0.4
    worn = np.clip(periodic_noise(size, rng, 12, 50) - 0.8, 0, 1)
    light = 0.85 + 0.12 * streaks
    rgb = light[..., None] * (np.array([46, 38, 32]) * (1 - worn[..., None]) + np.array([92, 70, 52]) * worn[..., None])
    save_dds(rgb, path)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def big_log_texture(path, size=1024):
    """The whole of the big log's skin in one image (James, 2026-10-29: the tiling wood looked
    too procedural on one big trunk): u once round it (top at 0.25, underside at 0.75), v from
    one end to the other. Weathered peeled wood with long wandering cracks, knots with the grain
    swirling round them, a knothole, a strip of bark left on, sun-bleached on top and damp, dirty
    and mossy underneath, greyer towards one end."""
    rng = np.random.default_rng(61)
    u = (np.arange(size)[None, :] + 0.5) / size
    v = (np.arange(size)[:, None] + 0.5) / size
    wander = periodic_noise(size, rng, 30, 160) * 0.012
    uu = (u + wander) % 1.0
    # knots: the grain bends round them, a dark core with rings
    knots = [(0.18, 0.22, 0.020), (0.33, 0.58, 0.028), (0.47, 0.81, 0.016), (0.62, 0.35, 0.022), (0.08, 0.66, 0.014)]
    bend = np.zeros((size, size))
    core = np.zeros((size, size))
    for ku, kv, kr in knots:
        du = (uu - ku + 0.5) % 1.0 - 0.5
        dv = (v - kv) * 4.2 / 2.9          # metres along over metres round, so knots come out round
        d = np.sqrt(du ** 2 + dv ** 2)
        bend += kr * 1.6 * np.exp(-(d / (kr * 3)) ** 2) * np.sign(du)
        core = np.maximum(core, np.clip(1 - d / kr, 0, 1))
        core = np.maximum(core, 0.22 * np.clip(1 - np.abs(d - kr * 1.8) / (kr * 0.6), 0, 1))
    ug = (uu + bend) % 1.0
    grain = np.sin(ug * 2 * math.pi * 70 + periodic_noise(size, rng, 6, 60) * 1.5)
    streaks = periodic_noise(size, rng, 1.5, 50) * 0.6 + periodic_noise(size, rng, 8, 120) * 0.4
    light = 0.80 + 0.05 * grain + 0.07 * streaks
    # cracks (checks): dark, wandering along the log, wider in the middle of their length
    for cu, v0, v1, w in ((0.24, 0.05, 0.62, 0.0035), (0.29, 0.40, 0.95, 0.0025), (0.12, 0.30, 0.55, 0.002),
                          (0.40, 0.10, 0.38, 0.002), (0.55, 0.55, 0.92, 0.0018), (0.95, 0.20, 0.48, 0.0015)):
        path_u = cu + periodic_noise(size, rng, 1, 140)[:, :1] * 0.004 + 0.01 * np.sin(v * 9 + cu * 20)
        along = np.clip((v - v0) / (v1 - v0), 0, 1)
        width = 1.7 * w * np.sin(math.pi * along) ** 0.6 * ((v > v0) & (v < v1))
        dist = np.abs((uu - path_u + 0.5) % 1.0 - 0.5)
        light -= 0.55 * np.clip(1 - dist / np.maximum(width, 1e-6), 0, 1)
        light += 0.06 * np.clip(1 - dist / np.maximum(width * 3, 1e-6), 0, 1) * (dist > width)  # pale edges
    # the knothole: a deep dark hollow in the biggest knot
    du = (uu - 0.33 + 0.5) % 1.0 - 0.5
    hole = np.clip(1 - np.sqrt(du ** 2 + ((v - 0.58) * 1.45) ** 2) / 0.016, 0, 1)
    light = light * (1 - 0.5 * core) - 0.55 * np.clip(hole * 2, 0, 1)
    colour = np.array([200, 172, 132], dtype=float)
    # sun-bleached top, greyer towards the v = 1 end
    top = np.exp(-(((u - 0.25 + 0.5) % 1.0 - 0.5) / 0.18) ** 2)
    grey = np.clip(v * 0.9 - 0.2 + periodic_noise(size, rng, 40, 40) * 0.15, 0, 1) * 0.6 + top * 0.35
    rgb = light[..., None] * (colour * (1 - grey[..., None]) + np.array([168, 162, 150]) * grey[..., None])
    # underneath: damp, dirt and moss where it lies on the ground
    under = np.exp(-(((u - 0.75 + 0.5) % 1.0 - 0.5) / 0.12) ** 2)
    damp = np.clip(under * 1.3 + periodic_noise(size, rng, 20, 30) * 0.25 - 0.35, 0, 1)
    rgb = rgb * (1 - 0.45 * damp[..., None]) + np.array([70, 72, 40]) * 0.45 * damp[..., None]
    moss = np.clip((periodic_noise(size, rng, 10, 14) - 0.6) * 2, 0, 1) * damp
    rgb = rgb * (1 - moss[..., None] * 0.7) + np.array([84, 110, 44]) * moss[..., None] * 0.7
    # a strip of bark left on, low on one side
    bark = np.clip((periodic_noise(size, rng, 12, 60) - 0.9) * 3, 0, 1) * np.exp(-(((u - 0.62 + 0.5) % 1.0 - 0.5) / 0.05) ** 2)
    rgb = rgb * (1 - bark[..., None]) + np.array([86, 68, 52]) * (0.8 + 0.2 * streaks[..., None]) * bark[..., None]
    rgb = np.clip(rgb, 0, 255)
    save_dds(rgb, path)
    return rgb.astype(np.uint8)


# One row of four cells: red flag, white flag, pole, gold (the height guide).
FLAG_CELLS = [(200, 26, 30), (244, 244, 240), (232, 232, 228), (236, 184, 52)]


def flag_texture(path, cell=32):
    img = Image.new("RGB", (cell * len(FLAG_CELLS), cell))
    draw = ImageDraw.Draw(img)
    for i, colour in enumerate(FLAG_CELLS):
        draw.rectangle([i * cell, 0, (i + 1) * cell - 1, cell - 1], fill=colour)
    save_dxt1(img, path)
    return np.asarray(img)


def flag_uv(index):
    """Centre of a flag texture cell."""
    return (index + 0.5) / len(FLAG_CELLS), 0.5


# ---------------------------------------------------------------------------------------------
# Geometry

def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def norm(a):
    length = math.sqrt(dot(a, a)) or 1.0
    return (a[0] / length, a[1] / length, a[2] / length)


class Mesh:
    def __init__(self):
        self.verts = []  # (p, n, uv)
        self.tris = []

    def vertex(self, p, n, uv):
        self.verts.append((p, n, uv))
        return len(self.verts) - 1

    def tri(self, a, b, c):
        """Wound counter-clockwise seen from the side its vertex normals face."""
        pa, pb, pc = self.verts[a][0], self.verts[b][0], self.verts[c][0]
        n = self.verts[a][1]
        if dot(cross(sub(pb, pa), sub(pc, pa)), n) < 0:
            b, c = c, b
        self.tris.append((a, b, c))

    def quad(self, corners, n, uvs):
        ids = [self.vertex(p, n, uv) for p, uv in zip(corners, uvs)]
        self.tri(ids[0], ids[1], ids[2])
        self.tri(ids[0], ids[2], ids[3])

    def box(self, x0, x1, y0, y1, z0, z1, uv):
        """A box in one flat texture cell, without its bottom."""
        faces = [
            ((0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
            ((0, 0, -1), [(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)]),
            ((1, 0, 0), [(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)]),
            ((-1, 0, 0), [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)]),
            ((0, 1, 0), [(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)]),
        ]
        for n, corners in faces:
            self.quad(corners, n, [uv] * 4)

    def bounds(self):
        ps = [p for p, _, _ in self.verts]
        lo = [min(p[i] for p in ps) for i in range(3)]
        hi = [max(p[i] for p in ps) for i in range(3)]
        centre = [(lo[i] + hi[i]) / 2 for i in range(3)]
        radius = max(math.dist(centre, p) for p in ps)
        return centre, radius


def layout(jump):
    """Every log as (y, z, x0, x1, r0, r1, seed): rows stacked in the grooves of the row below."""
    rng = random.Random(jump["seed"])
    d = jump["diameter"]
    half = jump["length"] / 2
    logs = []
    for row, count in enumerate(jump["rows"]):
        y = d / 2 + row * d * math.sqrt(3) / 2 - SINK
        for i in range(count):
            z = (i - (count - 1) / 2) * d
            r = d / 2 * rng.uniform(0.94, 1.03)
            thin = r * (1 - rng.uniform(0.2, 1) * TAPER)
            r0, r1 = (r, thin) if rng.random() < 0.5 else (thin, r)
            x0 = -half + rng.uniform(-STAGGER, STAGGER)
            x1 = half + rng.uniform(-STAGGER, STAGGER)
            logs.append((y, z, x0, x1, r0, r1, rng.randrange(1 << 30)))
    return logs


def height(jump):
    """Top of the top log above the ground."""
    d = jump["diameter"]
    return d + (len(jump["rows"]) - 1) * d * math.sqrt(3) / 2 - SINK


def lumps(rng):
    """A log's slow wobble round and along it: a function of angle a and position t (0..1)."""
    waves = [(rng.choice([2, 3, 4]), rng.uniform(0, 6.3), rng.uniform(-3, 3), rng.uniform(0.3, 1)) for _ in range(3)]
    total = sum(w[3] for w in waves)

    def at(a, t):
        return sum(amp * math.sin(k * a + phase + drift * t) for k, phase, drift, amp in waves) / total
    return at


def tube(mesh, rings, uvs):
    """Join rings of vertex ids (all the same length, last = first again) into a skin."""
    for i in range(len(rings) - 1):
        for k in range(len(rings[i]) - 1):
            a, b = rings[i][k], rings[i][k + 1]
            c, d = rings[i + 1][k + 1], rings[i + 1][k]
            mesh.tri(a, b, c)
            mesh.tri(a, c, d)


def smooth_normals(grid):
    """Normals for a grid of points (rows along the log, columns round it) from its neighbours."""
    rows, cols = len(grid), len(grid[0])
    out = []
    for i in range(rows):
        row = []
        for k in range(cols):
            along = sub(grid[min(i + 1, rows - 1)][k], grid[max(i - 1, 0)][k])
            round_ = sub(grid[i][(k + 1) % cols], grid[i][(k - 1) % cols])
            row.append(norm(cross(round_, along)))
        out.append(row)
    return out


def build_log(log, bark, ends):
    """One log: a bowed, lumpy, tapering trunk with knots and branch stubs, and sawn ends that
    lean a little. Bark wraps once round it with u = 0 on top."""
    y, z, x0, x1, r0, r1, seed = log
    rng = random.Random(seed)
    length = x1 - x0
    steps = max(4, int(math.ceil(length / RING_STEP)))
    wobble = lumps(rng)
    bow_y = rng.uniform(-0.3, 1) * BEND
    bow_z = rng.uniform(-1, 1) * BEND
    knots = [(rng.uniform(0, 2 * math.pi), rng.uniform(0.1, 0.9), rng.uniform(0.06, 0.16))
             for _ in range(rng.randint(*KNOTS))]
    tilt = [(rng.uniform(-1, 1) * CUT_TILT, rng.uniform(-1, 1) * CUT_TILT) for _ in range(2)]
    v_shift = rng.uniform(0, 1)

    def centre(t):
        bow = math.sin(math.pi * t)
        return y + bow_y * bow, z + bow_z * bow

    def radius(a, t):
        r = (r0 + (r1 - r0) * t) * (1 + LUMPS * wobble(a, t))
        for ka, kt, size in knots:
            da = (a - ka + math.pi) % (2 * math.pi) - math.pi
            dt = (t - kt) * length
            r += (r0 + r1) / 2 * size * math.exp(-(da / 0.35) ** 2 - (dt / 0.12) ** 2)
        return r

    grid = []
    for i in range(steps + 1):
        t = i / steps
        cy, cz = centre(t)
        row = []
        for k in range(SIDES):
            a = 2 * math.pi * k / SIDES
            r = radius(a, t)
            dy, dz = math.cos(a) * r, math.sin(a) * r     # a = 0 is the top
            x = x0 + length * t
            if i == 0:
                x += tilt[0][0] * dy + tilt[0][1] * dz
            elif i == steps:
                x += tilt[1][0] * dy + tilt[1][1] * dz
            row.append((x, cy + dy, cz + dz))
        grid.append(row)
    normals = smooth_normals(grid)
    rings = []
    for i, row in enumerate(grid):
        ring = []
        for k in range(SIDES + 1):
            p, n = row[k % SIDES], normals[i][k % SIDES]
            ring.append(bark.vertex(p, n, (k / SIDES, (p[0] - x0) / BARK_TILE + v_shift)))
        rings.append(ring)
    tube(bark, rings, None)

    # sawn ends: a fan round the middle, the ring texture laid flat and turned at random
    for i, sign, (ty, tz) in ((0, -1.0, tilt[0]), (steps, 1.0, tilt[1])):
        n = norm((sign, -sign * ty, -sign * tz))
        cy, cz = centre(i / steps)
        cx = sum(p[0] for p in grid[i]) / SIDES
        spin = rng.uniform(0, 2 * math.pi)
        middle = ends.vertex((cx, cy, cz), n, (0.5, 0.5))
        rim = []
        for k, p in enumerate(grid[i]):
            a = 2 * math.pi * k / SIDES + spin
            rel = radius(2 * math.pi * k / SIDES, i / steps) / ((r0 + r1) / 2)
            uv = (0.5 + 0.5 * math.cos(a) * 0.93 * rel, 0.5 + 0.5 * math.sin(a) * 0.93 * rel)
            rim.append(ends.vertex(p, n, uv))
        for k in range(SIDES):
            ends.tri(middle, rim[k], rim[(k + 1) % SIDES])

    # branch stubs, sawn or snapped off, on the sides and top (never underneath)
    for _ in range(rng.randint(*STUBS)):
        a = rng.uniform(-1.9, 1.9)
        t = rng.uniform(0.15, 0.85)
        cy, cz = centre(t)
        r = radius(a, t)
        out = (0.0, math.cos(a), math.sin(a))
        lean = rng.choice([-1, 1]) * rng.uniform(0.3, 0.7)
        axis = norm((lean, out[1], out[2]))
        base = (x0 + length * t, cy + out[1] * r * 0.7, cz + out[2] * r * 0.7)
        stub_r = rng.uniform(0.025, 0.05)
        stub_len = r * 0.3 + rng.uniform(0.05, 0.16)
        side = norm(cross(axis, (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (0.0, 1.0, 0.0)))
        up = cross(side, axis)
        stub_rings = []
        for j, (along, rr) in enumerate(((0.0, stub_r * 1.25), (stub_len, stub_r * 0.8))):
            ring = []
            for k in range(9):
                b = 2 * math.pi * k / 8
                d = tuple(side[m] * math.cos(b) + up[m] * math.sin(b) for m in range(3))
                p = tuple(base[m] + axis[m] * along + d[m] * rr for m in range(3))
                ring.append(bark.vertex(p, d, (k / 8 * 0.15, j * 0.12)))
            stub_rings.append(ring)
        tube(bark, stub_rings, None)
        tip = tuple(base[m] + axis[m] * stub_len for m in range(3))
        middle = ends.vertex(tip, axis, (0.5, 0.5))
        rim = []
        for k in range(8):
            b = 2 * math.pi * k / 8
            d = tuple(side[m] * math.cos(b) + up[m] * math.sin(b) for m in range(3))
            p = tuple(tip[m] + d[m] * stub_r * 0.8 for m in range(3))
            rim.append(ends.vertex(p, axis, (0.5 + 0.45 * math.cos(b), 0.5 + 0.45 * math.sin(b))))
        for k in range(8):
            ends.tri(middle, rim[k], rim[(k + 1) % 8])


def build_logs(jump):
    """The pile's logs, alternating between the two barks. Returns one mesh per bark, and the ends."""
    barks = [Mesh() for _ in BARKS]
    ends = Mesh()
    for i, log in enumerate(layout(jump)):
        pick = (i + random.Random(log[6]).randint(0, 1)) % len(BARKS)
        build_log(log, barks[pick], ends)
    return barks, ends


def cylinder(mesh, x, z, y0, y1, r, uv, sides=10):
    """An upright cylinder with a top cap."""
    rings = []
    for y in (y0, y1):
        ring = []
        for k in range(sides + 1):
            a = 2 * math.pi * k / sides
            n = (math.cos(a), 0.0, math.sin(a))
            ring.append(mesh.vertex((x + n[0] * r, y, z + n[2] * r), n, uv))
        rings.append(ring)
    tube(mesh, rings, None)
    middle = mesh.vertex((x, y1, z), (0.0, 1.0, 0.0), uv)
    rim = [mesh.vertex((x + math.cos(2 * math.pi * k / sides) * r, y1, z + math.sin(2 * math.pi * k / sides) * r),
                       (0.0, 1.0, 0.0), uv) for k in range(sides)]
    for k in range(sides):
        mesh.tri(middle, rim[k], rim[(k + 1) % sides])


def pole_height(fence_height):
    """Flags stand about half a metre above the fence."""
    return max(1.3, fence_height + 0.55)


def flag(mesh, x, colour, side, pole=POLE_HEIGHT):
    """A thin white pole with a triangle pennant flying towards side (+1 = +x), its sleeve wrapped
    round the top of the pole. Both faces of the pennant are drawn."""
    cylinder(mesh, x, 0.0, -0.15, pole, POLE_R, flag_uv(2))
    top = pole - 0.03
    bottom = top - PENNANT_H
    cylinder(mesh, x, 0.0, bottom, top, SLEEVE_R, flag_uv(colour), sides=12)
    tip = (x + side * (SLEEVE_R + PENNANT_W), (top + bottom) / 2, 0.0)
    uv = flag_uv(colour)
    for nz in (1.0, -1.0):
        n = (0.0, 0.0, nz)
        a = mesh.vertex((x + side * SLEEVE_R * 0.7, top, 0.0), n, uv)
        b = mesh.vertex((x + side * SLEEVE_R * 0.7, bottom, 0.0), n, uv)
        c = mesh.vertex(tip, n, uv)
        mesh.tri(a, b, c)


def guide_bar(fence_height, side):
    """The gold bar at the fence's height, from the pole towards the fence (against side)."""
    mesh = Mesh()
    s = GUIDE_SIZE / 2
    x0, x1 = (-GUIDE_LENGTH, -POLE_R) if side > 0 else (POLE_R, GUIDE_LENGTH)
    mesh.box(x0, x1, fence_height - s, fence_height + s, -s, s, flag_uv(3))
    return mesh


def flag_posts(half, fence_height, mesh=None):
    """A flag at each end of a fence face, red at +x and white at -x, flying outwards.
    Returns the mesh and the flags' feet."""
    mesh = mesh or Mesh()
    flag(mesh, half, 0, 1, pole_height(fence_height))
    flag(mesh, -half, 1, -1, pole_height(fence_height))
    return mesh, {"eqFlagsRed": (half, 0.0, 0.0), "eqFlagsWhite": (-half, 0.0, 0.0)}


def log_pile_half(jump):
    """Half the distance between a log pile's flags."""
    return jump["length"] / 2 + STAGGER + FLAG_GAP


def slab(mesh, outline, thickness, plane, uv):
    """A flat slab: outline (a convex polygon, counter-clockwise) in the plane's own (a, b)
    coordinates, extruded by thickness behind it. plane(a, b, c) gives a 3D point, c being the
    depth behind the front face (c = -1 is in front, the way the front faces); uv(a, b) the
    texture coordinates of the broad faces."""
    def at(a, b, c):
        return plane(a, b, c)
    n_front = norm(sub(at(0, 0, -1), at(0, 0, 0)))
    n_back = (-n_front[0], -n_front[1], -n_front[2])
    for c, n in ((0.0, n_front), (thickness, n_back)):
        ids = [mesh.vertex(at(a, b, c), n, uv(a, b)) for a, b in outline]
        for k in range(1, len(ids) - 1):
            mesh.tri(ids[0], ids[k], ids[k + 1])
    centre = (sum(a for a, _ in outline) / len(outline), sum(b for _, b in outline) / len(outline))
    for k in range(len(outline)):
        (a0, b0), (a1, b1) = outline[k], outline[(k + 1) % len(outline)]
        p0, p1 = at(a0, b0, 0.0), at(a1, b1, 0.0)
        q0, q1 = at(a0, b0, thickness), at(a1, b1, thickness)
        edge_mid = at((a0 + a1) / 2, (b0 + b1) / 2, 0.0)
        out = norm(sub(edge_mid, at(centre[0], centre[1], 0.0)))
        length = math.dist(p0, p1)
        mesh.quad([p0, p1, q1, q0], out, [(0, 0), (length / PLANK_TILE[0], 0), (length / PLANK_TILE[0], 0.02), (0, 0.02)])


def textured_box(mesh, x0, x1, y0, y1, z0, z1, tile=1.0):
    """A box with its texture's v running up (posts) on the sides, and a flat top."""
    faces = [
        ((0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], lambda p: (p[0], p[1])),
        ((0, 0, -1), [(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)], lambda p: (p[0], p[1])),
        ((1, 0, 0), [(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)], lambda p: (p[2], p[1])),
        ((-1, 0, 0), [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)], lambda p: (p[2], p[1])),
        ((0, 1, 0), [(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)], lambda p: (p[0], p[2])),
    ]
    for n, corners, project in faces:
        mesh.quad(corners, n, [tuple(c / tile for c in project(p)) for p in corners])


def round_rail(mesh, ends, a, b, r, half=False, sides=12):
    """A round (or half-round, flat side down) log from a to b, both (x, y, z), with end caps in
    the ends mesh. v runs along it."""
    axis = sub(b, a)
    length = math.sqrt(dot(axis, axis))
    axis = norm(axis)
    side = norm(cross(axis, (0.0, 1.0, 0.0)))
    up = cross(side, axis)
    angles = [math.pi * k / sides for k in range(sides + 1)] if half else [2 * math.pi * k / sides for k in range(sides + 1)]
    rings = []
    for end, t in ((a, 0.0), (b, length)):
        ring = []
        for k, angle in enumerate(angles):
            d = tuple(side[m] * math.cos(angle) + up[m] * math.sin(angle) for m in range(3))
            p = tuple(end[m] + d[m] * r for m in range(3))
            ring.append(mesh.vertex(p, d, (k / sides * 0.5, t / 1.5)))
        rings.append(ring)
    tube(mesh, rings, None)
    for end, sign in ((a, -1.0), (b, 1.0)):
        n = tuple(axis[m] * sign for m in range(3))
        middle = ends.vertex(end, n, (0.5, 0.5))
        rim = []
        for angle in angles:
            d = tuple(side[m] * math.cos(angle) + up[m] * math.sin(angle) for m in range(3))
            rim.append(ends.vertex(tuple(end[m] + d[m] * r for m in range(3)), n,
                                   (0.5 + 0.45 * math.cos(angle), 0.5 + 0.45 * math.sin(angle))))
        for k in range(len(rim) - 1):
            ends.tri(middle, rim[k], rim[k + 1])
        if not half:
            ends.tri(middle, rim[-1], rim[0])


def drop_depth(wall):
    """How far each wing runs back over the bank's side."""
    return max(2.4, 2.5 * wall["drop"])


def logo_size(width, height):
    """The biggest logo of LOGO_ASPECT inside a board of width x height."""
    width, height = width - 2 * LOGO_MARGIN, height - 2 * LOGO_MARGIN
    return (width, width / LOGO_ASPECT) if width / height < LOGO_ASPECT else (height * LOGO_ASPECT, height)


def drop_board(wall):
    """The sponsor board on a drop wall's face, if it has one: its stained backing and the logo
    (a quad of its own, "eqSponsor_1", whose texture EqSponsors swaps for a brand's logo)."""
    backing, logo = Mesh(), Mesh()
    if not wall.get("sponsor"):
        return backing, logo
    w, h, gap = DROP_BOARD
    lip = -DROP_LIP
    y1, y0 = -gap, -gap - h
    textured_box(backing, -w / 2, w / 2, y0, y1, lip - 0.04, lip)
    lw, lh = logo_size(w, h)
    yc, z = (y0 + y1) / 2, lip - 0.042
    # facing -z: seen from the front +x is on the left, so u runs from +x to -x
    logo.quad([(lw / 2, yc - lh / 2, z), (-lw / 2, yc - lh / 2, z), (-lw / 2, yc + lh / 2, z), (lw / 2, yc + lh / 2, z)],
              (0, 0, -1), [(0, 0), (1, 0), (1, 1), (0, 1)])
    return backing, logo


def build_drop_wall(wall):
    """The plank face, deck, posts, lip cap and wings; and one collision mesh (face, deck and wings)."""
    planks, wood, ends, col = Mesh(), Mesh(), Mesh(), Mesh()
    h = wall["drop"]
    half = DROP_WIDTH / 2
    lip = -DROP_LIP           # z of the face's front
    bottom = -h - SKIRT
    depth = drop_depth(wall)

    def face_plane(a, b, c):
        return (a, b, lip + c)
    face = [(-half, bottom), (half, bottom), (half, 0.0), (-half, 0.0)]
    slab(planks, face, BOARD_T, face_plane, lambda a, b: (a / PLANK_TILE[0], -b / PLANK_TILE[1]))
    slab(col, face, BOARD_T + 0.1, face_plane, lambda a, b: (0, 0))
    # wings: top edge level with the lip, front edge the full drop, the bottom rising to nothing
    # at the back; boards run horizontally, the outline reaches SKIRT below the slope
    wing = [(0.0, bottom), (depth, -SKIRT * 0.6), (depth, 0.0), (0.0, 0.0)]
    for x, sign in ((-half, -1), (half, 1)):
        def wing_plane(a, b, c, x=x, sign=sign):
            return (x - sign * c, b, lip + a)
        outline = wing if sign > 0 else list(reversed(wing))
        slab(planks, outline, BOARD_T, wing_plane, lambda a, b: (a / PLANK_TILE[0], -b / PLANK_TILE[1]))
        slab(col, outline, BOARD_T + 0.1, wing_plane, lambda a, b: (0, 0))
        round_rail(wood, ends, (x, DECK_Y + RAIL_R * 0.8, lip + 0.05), (x, DECK_Y + RAIL_R * 0.8, lip + depth + 0.15), RAIL_R)
    # a plank deck over the whole box, boards parallel to the lip, so the bank top needn't be flat
    def deck_plane(a, b, c):
        return (a, DECK_Y - c, b)
    deck = [(-half, lip), (half, lip), (half, lip + depth), (-half, lip + depth)]
    slab(planks, deck, BOARD_T, deck_plane, lambda a, b: (a / PLANK_TILE[0], b / PLANK_TILE[1]))
    slab(col, deck, BOARD_T, deck_plane, lambda a, b: (0, 0))
    # posts along the face (in front of the boards), corner posts a little proud
    count = max(2, int(math.ceil(DROP_WIDTH / POST_STEP)) + 1)
    s = POST_W / 2
    for i in range(count):
        x = -half + DROP_WIDTH * i / (count - 1)
        x = min(max(x, -half + s), half - s)
        corner = i in (0, count - 1)
        if wall.get("sponsor") and not corner:
            continue    # the sponsor board covers the middle
        textured_box(wood, x - s, x + s, bottom, 0.12 if corner else -0.02, lip - POST_W, lip)
    # the half-round log along the lip, flat side down, overhanging the face a little
    round_rail(wood, ends, (-half + s * 2, DECK_Y, lip + CAP_R * 0.6), (half - s * 2, DECK_Y, lip + CAP_R * 0.6), CAP_R, half=True)
    return planks, wood, ends, col


def collision(jump):
    """One prism round the pile's outline (seen from the side), as long as the shortest log."""
    d = jump["diameter"]
    logs = layout(jump)
    x0 = max(log[2] for log in logs)
    x1 = min(log[3] for log in logs)
    bottom = jump["rows"][0] * d / 2
    top_half = jump["rows"][-1] * d / 2 * 0.7
    top = height(jump) - 0.03
    outline = [(-bottom, 0.0), (bottom, 0.0), (top_half, top), (-top_half, top)]
    mesh = Mesh()
    uv = (0.5, 0.5)
    for x, nx in ((x0, -1.0), (x1, 1.0)):
        ids = [mesh.vertex((x, y, z), (nx, 0.0, 0.0), uv) for z, y in outline]
        mesh.tri(ids[0], ids[1], ids[2])
        mesh.tri(ids[0], ids[2], ids[3])
    for i in range(4):
        (za, ya), (zb, yb) = outline[i], outline[(i + 1) % 4]
        n = norm((0.0, zb - za, -(yb - ya)))
        if dot(n, (0.0, (ya + yb) / 2 - top / 2, (za + zb) / 2)) < 0:
            n = (0.0, -n[1], -n[2])
        mesh.quad([(x0, ya, za), (x1, ya, za), (x1, yb, zb), (x0, yb, zb)], n, [uv] * 4)
    return mesh


# ---------------------------------------------------------------------------------------------
# Files

def fmt(values):
    return " ".join(f"{v:.5g}" for v in values)


# The part of a brand's logo image a logo face shows (James, 2026-11-01: fill more of the board).
# The game's brand logos are all 512 x 256 with the logo across the middle (measured on the game's
# 261 logos: most sit within 0.02-0.98 across and 0.1-0.9 up). A face of LOGO_ASPECT 2.7 shows
# 0.1-0.9 up and a little more than the whole width (LOGO_PAD each side, James: Volvo's O touched
# the right edge), so logos are not stretched; the face is cut back to where the image is
# (clip_logo), leaving the padding as bare board.
LOGO_PAD = 0.04
LOGO_CROP = (-LOGO_PAD, 1 + LOGO_PAD, 0.10, 0.90)


def logo_uv(uv):
    u0, u1, v0, v1 = LOGO_CROP
    return (u0 + (u1 - u0) * uv[0], v0 + (v1 - v0) * uv[1])


def _lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def clip_logo(mesh):
    """The logo faces' triangles cut to 0 <= u <= 1 (logo_uv runs a little past both edges)."""
    out = Mesh()
    for tri in mesh.tris:
        poly = [mesh.verts[i] for i in tri]
        for edge, keep in ((0.0, lambda u: u >= 0.0), (1.0, lambda u: u <= 1.0)):
            clipped = []
            for k, cur in enumerate(poly):
                prev = poly[k - 1]
                cin, pin = keep(cur[2][0]), keep(prev[2][0])
                if cin != pin:
                    t = (edge - prev[2][0]) / (cur[2][0] - prev[2][0])
                    n = _lerp(prev[1], cur[1], t)
                    length = sum(c * c for c in n) ** 0.5 or 1.0
                    clipped.append((_lerp(prev[0], cur[0], t), tuple(c / length for c in n), (edge, prev[2][1] + (cur[2][1] - prev[2][1]) * t)))
                if cin:
                    clipped.append(cur)
            poly = clipped
            if not poly:
                break
        if len(poly) < 3:
            continue
        ids = [out.vertex(*v) for v in poly]
        for k in range(1, len(ids) - 1):
            out.tris.append((ids[0], ids[k], ids[k + 1]))
    return out


def logo_preview(path="placeables/bleachers/bleacherSponsor_diffuse.dds"):
    """Our board texture as a shop picture should show it: the LOGO_CROP window, padding as board."""
    img = Image.open(path).convert("RGB")
    u0, u1, v0, v1 = LOGO_CROP
    w, h = img.size
    pad = int(round(LOGO_PAD * w))
    framed = Image.new("RGB", (w + 2 * pad, h), img.getpixel((1, 1)))
    framed.paste(img, (pad, 0))
    return np.asarray(framed.crop((0, int(round((1 - v1) * h)), w + 2 * pad, int(round((1 - v0) * h)))), dtype=float)


def shape_lines(mesh, name, shape_id, uv1=None):
    """uv1(p): an optional second UV set, e.g. the vertexOffset shader's slope gradient. Logo faces
    (shapes whose name has "eqSponsor") show only LOGO_CROP of the logo image."""
    if "eqSponsor" in name:
        cropped = Mesh()
        cropped.verts = [(p, n, logo_uv(uv)) for p, n, uv in mesh.verts]
        cropped.tris = mesh.tris
        mesh = clip_logo(cropped)
    centre, radius = mesh.bounds()
    lines = [
        f'    <IndexedTriangleSet name="{name}" shapeId="{shape_id}" bvCenter="{fmt(centre)}" bvRadius="{radius:.5g}">',
        f'      <Vertices count="{len(mesh.verts)}" normal="true" uv0="true"{' uv1="true"' if uv1 else ""}>',
    ]
    for p, n, uv in mesh.verts:
        second = f' t1="{fmt(uv1(p))}"' if uv1 else ""
        lines.append(f'        <v p="{fmt(p)}" n="{fmt(n)}" t0="{fmt(uv)}"{second}/>')
    lines.append("      </Vertices>")
    lines.append(f'      <Triangles count="{len(mesh.tris)}">')
    for a, b, c in mesh.tris:
        lines.append(f'        <t vi="{a} {b} {c}"/>')
    lines.append("      </Triangles>")
    lines.append('      <Subsets count="1">')
    lines.append(f'        <Subset firstVertex="0" numVertices="{len(mesh.verts)}" firstIndex="0" numIndices="{len(mesh.tris) * 3}"/>')
    lines.append("      </Subsets>")
    lines.append("    </IndexedTriangleSet>")
    return lines


MATERIALS = [
    # name, texture, normal map, emissive (glows without light)
    ("xcBarkA", "xcBarkA_diffuse.dds", "xcBarkA_normal.dds", False),
    ("xcBarkB", "xcBarkB_diffuse.dds", "xcBarkB_normal.dds", False),
    ("xcLogEnd", "xcLogEnd_diffuse.dds", None, False),
    ("xcPlanks", "xcPlanks_diffuse.dds", "xcPlanks_normal.dds", False),
    ("xcPeeled", "xcPeeled_diffuse.dds", None, False),
    ("xcPeeledB", "xcPeeledB_diffuse.dds", None, False),
    ("xcStain", "xcStain_diffuse.dds", "xcStain_normal.dds", False),
    ("xcDark", "xcDark_diffuse.dds", None, False),
    ("xcBigLog", "xcBigLog_diffuse.dds", None, False),
    ("xcFlags", "xcFlags_diffuse.dds", None, False),
    ("xcGuideGold", "xcFlags_diffuse.dds", None, True),
]


def write_i3d(name, path, shapes, feet, col=None, guide=None):
    """shapes: (node name, mesh, material name, casts shadows). guide: a (mesh, material) shown
    only in construction mode, under a transform group named GUIDE (EqXcFlags hides it)."""
    if guide is not None:
        shapes = shapes + [("guide", guide[0], guide[1], False)]
    used = [m for m in MATERIALS if m[0] in {shape[2] for shape in shapes}]
    used += [(m, SPONSOR_TEXTURE, None, False) for m in sorted({shape[2] for shape in shapes}) if m.startswith("eqSponsor")]
    files = sorted({texture for _, texture, _, _ in used} | {n for _, _, n, _ in used if n})
    lines = [
        '<?xml version="1.0" encoding="iso-8859-1"?>',
        "",
        f'<i3D name="{name}" version="1.6" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="http://i3d.giants.ch/schema/i3d-1.6.xsd">',
        "  <Asset>",
        '    <Export program="Realistic Equestrian xc_jumps.py" version="1"/>',
        "  </Asset>",
        "  <Files>",
    ]
    for i, texture in enumerate(files):
        lines.append(f'    <File fileId="{i + 1}" filename="{texture}"/>')
    lines.append("  </Files>")
    lines.append("  <Materials>")
    material_ids = {}
    for i, (material, texture, normal, emissive) in enumerate(used):
        material_ids[material] = i + 1
        blend = ' alphaBlending="true"' if material.startswith("eqSponsor") else ""
        lines.append(f'    <Material name="{material}" materialId="{i + 1}" specularColor="0.1 0.7 0"{blend}>')
        lines.append(f'      <Texture fileId="{files.index(texture) + 1}"/>')
        if normal:
            lines.append(f'      <Normalmap fileId="{files.index(normal) + 1}"/>')
        if emissive:
            lines.append(f'      <Emissivemap fileId="{files.index(texture) + 1}"/>')
        lines.append("    </Material>")
    lines.append("  </Materials>")
    lines.append("  <Shapes>")
    for i, (node, mesh, _, _) in enumerate(shapes):
        lines += shape_lines(mesh, f"{name}_{node}", i + 1)
    if col is not None:
        lines += shape_lines(col, name + "_collision", len(shapes) + 1)
    lines.append("  </Shapes>")
    lines.append("  <Scene>")
    lines.append(f'    <TransformGroup name="{name}" nodeId="1">')
    node_id = 2
    for i, (node, _, material, shadows) in enumerate(shapes):
        cast = "true" if shadows else "false"
        shape = (f'<Shape name="{node}" shapeId="{i + 1}" clipDistance="{CLIP}" nodeId="{node_id}" '
                 f'materialIds="{material_ids[material]}" castsShadows="{cast}" receiveShadows="true"/>')
        if node == "guide":
            lines.append(f'      <TransformGroup name="{GUIDE}" nodeId="{node_id + 1}">')
            lines.append("        " + shape)
            lines.append("      </TransformGroup>")
            node_id += 1
        else:
            lines.append("      " + shape)
        node_id += 1
    for name_ in ("eqFlagsRed", "eqFlagsWhite"):
        if name_ in feet:
            lines.append(f'      <TransformGroup name="{name_}" translation="{fmt(feet[name_])}" nodeId="{node_id}"/>')
            node_id += 1
    if col is not None:
        lines.append(f'      <TransformGroup name="collision" nodeId="{node_id}">')
        lines.append(f'        <Shape name="col" shapeId="{len(shapes) + 1}" static="true" collisionFilterGroup="{COLLISION_GROUP}" '
                     f'collisionFilterMask="{COLLISION_MASK}" density="0.01" nodeId="{node_id + 1}" nonRenderable="true" materialIds="1"/>')
        lines.append("      </TransformGroup>")
    lines += ["    </TransformGroup>", "  </Scene>", "</i3D>"]
    with open(path, "w", encoding="iso-8859-1", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def turned(mesh):
    """The mesh turned a quarter round y, so what ran along +x runs along +z."""
    out = Mesh()
    out.verts = [((-p[2], p[1], p[0]), (-n[2], n[1], n[0]), uv) for p, n, uv in mesh.verts]
    out.tris = list(mesh.tris)
    return out


def build_flag_fence():
    """The flag fence's pieces, each along +z from 0 (a fence segment's direction):
    the two flag posts with a thin collision box (so they can be picked to delete), and the guide
    line with a flat box half sunk in the ground for picking."""
    posts = {}
    for colour, side, name in ((1, -1, "eqXcFlagWhite"), (0, 1, "eqXcFlagRed")):
        mesh = Mesh()
        flag(mesh, 0.0, colour, side, POLE_HEIGHT)   # white flies back down the line, red on ahead
        mesh = turned(mesh)
        for v in range(len(mesh.verts)):
            p, n, uv = mesh.verts[v]
            mesh.verts[v] = ((p[0], p[1], p[2] + FLAG_POST / 2), n, uv)
        col = Mesh()
        col.box(-0.04, 0.04, 0.0, POLE_HEIGHT, FLAG_POST / 2 - 0.04, FLAG_POST / 2 + 0.04, (0.5, 0.5))
        posts[name] = (mesh, col)
    w = LINE_WIDTH / 2
    line = Mesh()
    line.box(-w, w, LINE_BOTTOM, LINE_TOP, 0.0, BAR_PANEL, flag_uv(3))
    col = Mesh()
    col.box(-0.03, 0.03, -0.03, 0.03, BAR_PANEL / 2 - 0.03, BAR_PANEL / 2 + 0.03, (0.5, 0.5))
    return posts, {LINE_NODE: (line, col)}


def write_flag_fence_i3d(path, posts, bars):
    """gates (the flag posts), poles (one empty: the line has none) and panels (the line), looked
    up by index from the fence xml."""
    shapes = []   # (mesh, material or None for collision)
    for mesh, col in list(posts.values()) + list(bars.values()):
        shapes += [(mesh, None), (col, "col")]
    used = [m for m in MATERIALS if m[0] in ("xcFlags", "xcGuideGold")]
    lines = [
        '<?xml version="1.0" encoding="iso-8859-1"?>',
        "",
        f'<i3D name="{FLAG_FENCE}" version="1.6" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="http://i3d.giants.ch/schema/i3d-1.6.xsd">',
        "  <Asset>",
        '    <Export program="Realistic Equestrian xc_jumps.py" version="1"/>',
        "  </Asset>",
        "  <Files>",
        '    <File fileId="1" filename="xcFlags_diffuse.dds"/>',
        '    <File fileId="2" filename="$data/shaders/placeableShader.xml"/>',
        "  </Files>",
        "  <Materials>",
    ]
    for i, (material, _, _, emissive) in enumerate(used):
        # the line leans with the slope like the base game's fence panels: the placeable shader's
        # vertexOffset variation lifts each vertex by the panel's yOffset times its uv1.x
        shader = ' customShaderId="2" customShaderVariation="vertexOffset"' if emissive else ""
        lines.append(f'    <Material name="{material}" materialId="{i + 1}" specularColor="0.1 0.7 0"{shader}>')
        lines.append('      <Texture fileId="1"/>')
        if emissive:
            lines.append('      <Emissivemap fileId="1"/>')
        lines.append("    </Material>")
    lines += ["  </Materials>", "  <Shapes>"]
    bar_meshes = {id(mesh) for mesh, _ in bars.values()}
    for i, (mesh, _) in enumerate(shapes):
        slope = (lambda p: (p[2] / BAR_PANEL, 0.0)) if id(mesh) in bar_meshes else None
        lines += shape_lines(mesh, f"{FLAG_FENCE}_{i + 1}", i + 1, uv1=slope)
    lines += ["  </Shapes>", "  <Scene>"]
    node_id = [1]

    def next_id():
        node_id[0] += 1
        return node_id[0] - 1

    def col_line(shape_id, indent):
        return (f'{indent}<Shape name="col" shapeId="{shape_id}" static="true" collisionFilterGroup="{FENCE_COLLISION_GROUP}" '
                f'collisionFilterMask="{COLLISION_MASK}" density="0.01" nodeId="{next_id()}" nonRenderable="true" materialIds="1"/>')
    shape_id = 1
    lines.append(f'    <TransformGroup name="gates" nodeId="{next_id()}">')
    for name in posts:
        lines.append(f'      <TransformGroup name="{name}" nodeId="{next_id()}">')
        lines.append(f'        <Shape name="flag" shapeId="{shape_id}" clipDistance="{CLIP}" nodeId="{next_id()}" materialIds="1" castsShadows="true" receiveShadows="true"/>')
        lines.append(col_line(shape_id + 1, "        "))
        lines.append("      </TransformGroup>")
        shape_id += 2
    lines.append("    </TransformGroup>")
    lines.append(f'    <TransformGroup name="poles" nodeId="{next_id()}">')
    lines.append(f'      <TransformGroup name="eqXcNoPole" nodeId="{next_id()}"/>')
    lines.append("    </TransformGroup>")
    lines.append(f'    <TransformGroup name="panels" nodeId="{next_id()}">')
    for name in bars:
        lines.append(f'      <TransformGroup name="{name}" nodeId="{next_id()}">')
        lines.append(f'        <TransformGroup name="{GUIDE}" nodeId="{next_id()}">')
        lines.append(f'          <Shape name="line" shapeId="{shape_id}" clipDistance="{CLIP}" nodeId="{next_id()}" materialIds="2" castsShadows="false" receiveShadows="true"/>')
        lines.append("        </TransformGroup>")
        lines.append(col_line(shape_id + 1, "        "))
        lines.append("      </TransformGroup>")
        shape_id += 2
    lines.append("    </TransformGroup>")
    lines += ["  </Scene>", "</i3D>"]
    with open(path, "w", encoding="iso-8859-1", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def write_flag_fence_xml(path, posts, bars):
    """A newFence like the base game's pillar fences: flag posts are fixed "gates" placed with one
    click, without poles of their own; the line is a stretchy segment with an empty pole."""
    segments = []
    gate = lambda i, sid: f"""        <segment id="{sid}" class="FenceGate" maxVerticalAngle="45">
            <gate node="0>{i}" length="{FLAG_POST:g}" hasStartPole="false" hasEndPole="false"/>
        </segment>"""
    segments.append(gate(0, "WHITE_FLAG"))
    for i, _ in enumerate(bars):
        segments.append(f"""        <segment id="{LINE_ID}" class="FenceSegment" maxVerticalAngle="45">
            <poles>
                <pole node="1>0" radius="0.0"/>
            </poles>
            <panels maxScale="{BAR_MAX_SCALE:g}">
                <panel node="2>{i}" length="{BAR_PANEL:g}"/>
            </panels>
        </segment>""")
    segments.append(gate(1, "RED_FLAG"))
    body = "\n".join(segments)
    text = f"""<?xml version="1.0" encoding="utf-8" standalone="no"?>
<!-- Made by art/source/xc_jumps.py: change that and run it again rather than editing this. -->
<!-- Segments (N/M): white flag, guide line on the ground, red flag. -->
<placeable type="newFence">
    <storeData>
        <name>$l10n_eq_shop_{FLAG_FENCE}</name>
        <functions>
            <function>$l10n_eq_shop_{FLAG_FENCE}_function</function>
            <function>$l10n_eq_shop_xcFlagsHidden_function</function>
        </functions>
        <image>placeables/xcJumps/store_{FLAG_FENCE}.dds</image>
        <price>{FLAG_FENCE_PRICE}</price>
        <dailyUpkeep>0</dailyUpkeep>
        <lifetime>1000</lifetime>
        <rotation>0</rotation>
        <brand>NONE</brand>
        <species>placeable</species>
        <category>fences</category>
        <canBeSold>true</canBeSold>
        <showInStore>true</showInStore>
        <brush>
            <type>newFence</type>
            <category>animals</category>
            <tab>horses</tab>
        </brush>
    </storeData>

    <base>
        <filename>placeables/xcJumps/{FLAG_FENCE}.i3d</filename>
        <canBeRenamed>false</canBeRenamed>
    </base>

    <placement useRandomYRotation="false" useManualYRotation="true">
        <sounds>
            <place template="fenceWoodImp"/>
            <destroy template="destroyFence"/>
        </sounds>
    </placement>

    <fence>
{body}
    </fence>
</placeable>
"""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_xml(name, price, note, path, extra="", made_by="art/source/xc_jumps.py", functions=()):
    """extra: more configuration blocks, before the end; functions: more shop function text keys."""
    text = f"""<?xml version="1.0" encoding="utf-8" standalone="no"?>
<!-- Made by {made_by}: change that and run it again rather than editing this. -->
<placeable type="simplePlaceable">
    <storeData>
        <name>$l10n_eq_shop_{name}</name>
        <functions>
            <function>$l10n_eq_shop_{"xcDrop" if "Drop" in name else "xcJump"}_function</function>
            <function>$l10n_eq_shop_xcHidden_function</function>
{"".join(f"            <function>$l10n_{key}</function>\n" for key in functions)}        </functions>
        <image>placeables/xcJumps/store_{name}.dds</image>
        <price>{price}</price>
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
        <filename>placeables/xcJumps/{name}.i3d</filename>
        <canBeRenamed>false</canBeRenamed>
    </base>

    <placement useRandomYRotation="false" useManualYRotation="true">
        <!-- {note} -->
    </placement>

    <!-- Disappearing: Yes (the first, default) hides the piece outside construction, course editing
         and rounds (EqXcHide). Stored as eqAlwaysVisible, so 2 (No) is still "always visible". -->
    <eqAlwaysVisible>
        <eqAlwaysVisibleConfigurations>
            <eqAlwaysVisibleConfiguration name="$l10n_ui_yes" price="0"/>
            <eqAlwaysVisibleConfiguration name="$l10n_ui_no" price="0"/>
        </eqAlwaysVisibleConfigurations>
    </eqAlwaysVisible>
{extra}</placeable>
"""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


# ---------------------------------------------------------------------------------------------
# Shop image: a small software render of the fence itself, three-quarter view.

def render(meshes, size=512, yaw=-40, pitch=26, ss=4):
    """A small z-buffered rasteriser: textured, smooth-shaded triangles, supersampled, on a
    transparent background like the game's own shop images.
    meshes: (mesh, texture as an RGB array)."""
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    rot = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rot = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]]) @ rot
    light = np.array(norm((-0.4, 0.8, 0.5)))
    pts = np.concatenate([np.array([v[0] for v in m.verts]) for m, _ in meshes if m.verts]) @ rot.T
    span = max(np.ptp(pts[:, 0]), np.ptp(pts[:, 1]))
    w = size * ss
    scale = w * 0.9 / span
    ox = w / 2 - (pts[:, 0].max() + pts[:, 0].min()) / 2 * scale
    oy = w / 2 + (pts[:, 1].max() + pts[:, 1].min()) / 2 * scale

    image = np.zeros((w, w, 3))
    depth = np.full((w, w), np.inf)
    for mesh, tex in meshes:
        if not mesh.tris:
            continue
        P = np.array([v[0] for v in mesh.verts]) @ rot.T
        N = np.array([v[1] for v in mesh.verts])
        UV = np.array([v[2] for v in mesh.verts])
        sx = ox + P[:, 0] * scale
        sy_ = oy - P[:, 1] * scale
        th, tw = tex.shape[:2]
        facing = (N @ rot.T)[:, 2]
        for a, b, c in mesh.tris:
            if facing[a] + facing[b] + facing[c] < -0.15:
                continue  # facing away
            xs = np.array([sx[a], sx[b], sx[c]])
            ys = np.array([sy_[a], sy_[b], sy_[c]])
            area = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
            if abs(area) < 1e-9:
                continue
            x0, x1 = max(int(xs.min()), 0), min(int(xs.max()) + 1, w)
            y0, y1 = max(int(ys.min()), 0), min(int(ys.max()) + 1, w)
            if x0 >= x1 or y0 >= y1:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            l1 = ((xs[1] - gx) * (ys[2] - gy) - (xs[2] - gx) * (ys[1] - gy)) / area
            l2 = ((xs[2] - gx) * (ys[0] - gy) - (xs[0] - gx) * (ys[2] - gy)) / area
            l3 = 1 - l1 - l2
            inside = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
            if not inside.any():
                continue
            z = l1 * P[a, 2] + l2 * P[b, 2] + l3 * P[c, 2]
            region = depth[y0:y1, x0:x1]
            closer = inside & (-z < region)
            if not closer.any():
                continue
            u = (l1 * UV[a, 0] + l2 * UV[b, 0] + l3 * UV[c, 0]) % 1
            v = (l1 * UV[a, 1] + l2 * UV[b, 1] + l3 * UV[c, 1]) % 1
            n = l1[..., None] * N[a] + l2[..., None] * N[b] + l3[..., None] * N[c]
            n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
            shade = 0.42 + 0.7 * np.clip(n @ light, 0, 1)
            colour = tex[(v * th).astype(int) % th, (u * tw).astype(int) % tw][..., :3] * shade[..., None]
            region[closer] = -z[closer]
            image[y0:y1, x0:x1][closer] = colour[closer]
    # box filter the supersamples: colour weighted by coverage, coverage becomes alpha
    cover = np.isfinite(depth).astype(float)
    alpha = cover.reshape(size, ss, size, ss).mean(axis=(1, 3))
    rgb = (image * cover[..., None]).reshape(size, ss, size, ss, 3).sum(axis=(1, 3))
    rgb /= np.maximum(cover.reshape(size, ss, size, ss).sum(axis=(1, 3)), 1)[..., None]
    rgba = np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def store_image(meshes, path, preview_dir, **view):
    """A shop image like the game's own: the object at a three-quarter angle, no background, no text."""
    img = render(meshes, **view)
    save_bc7(img, path)
    # a PNG copy to look at, kept out of the mod
    os.makedirs(preview_dir, exist_ok=True)
    img.save(os.path.join(preview_dir, os.path.basename(path).replace(".dds", ".png")))


def drop_walls(names, preview_dir, planks_rgb, peeled_rgb, ends):
    """The drop walls' i3d, xml and shop image (names: only those)."""
    import bleachers
    stain_rgb = stain_texture(os.path.join(tempfile.mkdtemp(), "s.dds"), os.path.join(tempfile.mkdtemp(), "n.dds"))
    sponsor_rgb = bleachers.sponsor_board(os.path.join(tempfile.mkdtemp(), "b.dds"))
    for wall in DROP_WALLS:
        name = wall["name"]
        if names and name not in names:
            continue
        planks, wood, ends_mesh, col = build_drop_wall(wall)
        backing, logo = drop_board(wall)
        shapes = [("planks", planks, "xcPlanks", True), ("wood", wood, "xcPeeled", True), ("ends", ends_mesh, "xcLogEnd", True)]
        if logo.tris:
            shapes += [("sponsorBoard", backing, "xcStain", True), ("eqSponsor_1", logo, "eqSponsor1", False)]
        write_i3d(name, os.path.join(OUT, name + ".i3d"), shapes, {}, col=col)
        write_xml(name, wall["price"], f"A {wall['drop']:.1f} m drop: set the origin on the flat top of a bank, the lip {DROP_LIP:g} m in front of it.",
                  os.path.join(OUT, name + ".xml"),
                  functions=["eq_shop_plinth_function"] + (["eq_shop_signboard_function"] if logo.tris else []))
        flipped = Mesh()
        flipped.verts = [(p, n, (uv[0], 1 - uv[1])) for p, n, uv in logo.verts]
        flipped.tris = list(logo.tris)
        store_image([(planks, planks_rgb), (wood, peeled_rgb), (ends_mesh, ends), (backing, stain_rgb), (flipped, sponsor_rgb)],
                    os.path.join(OUT, "store_" + name + ".dds"), preview_dir, yaw=-140)
        print(name, f"{wall['drop']:.1f} m drop,", len(planks.tris) + len(wood.tris) + len(ends_mesh.tris), "triangles")


def main():
    preview_dir = os.environ.get("XC_PREVIEW_DIR", "art/previews")
    os.makedirs(OUT, exist_ok=True)
    bark_rgbs = [bark_texture(b, os.path.join(OUT, b["name"] + "_diffuse.dds"), os.path.join(OUT, b["name"] + "_normal.dds"))
                 for b in BARKS]
    ends = log_end_texture(os.path.join(OUT, "xcLogEnd_diffuse.dds"))
    flags = flag_texture(os.path.join(OUT, "xcFlags_diffuse.dds"))
    for jump in LOG_PILES:
        name = jump["name"]
        bark_meshes, ends_mesh = build_logs(jump)
        posts, feet = flag_posts(log_pile_half(jump), height(jump))
        shapes = [(f"logs{chr(65 + i)}", m, b["name"], True) for i, (m, b) in enumerate(zip(bark_meshes, BARKS)) if m.tris]
        shapes += [("logEnds", ends_mesh, "xcLogEnd", True), ("flags", posts, "xcFlags", True)]
        write_i3d(name, os.path.join(OUT, name + ".i3d"), shapes, feet, col=collision(jump))
        depth = jump["rows"][0] * jump["diameter"]
        write_xml(name, jump["price"], f"{height(jump):.2f} m high, {depth:.2f} m deep; jumped along z, red flag at +x.",
                  os.path.join(OUT, name + ".xml"))
        store_image([(m, rgb) for m, rgb in zip(bark_meshes, bark_rgbs)] + [(ends_mesh, ends), (posts, flags)],
                    os.path.join(OUT, "store_" + name + ".dds"), preview_dir)
        print(name, f"{height(jump):.2f} m high,", len(layout(jump)), "logs,",
              sum(len(m.tris) for m in bark_meshes) + len(ends_mesh.tris) + len(posts.tris), "triangles")
    planks_rgb = plank_texture(os.path.join(OUT, "xcPlanks_diffuse.dds"), os.path.join(OUT, "xcPlanks_normal.dds"))
    peeled_rgb = peeled_texture(os.path.join(OUT, "xcPeeled_diffuse.dds"))
    drop_walls((), preview_dir, planks_rgb, peeled_rgb, ends)
    flag_fence(flags, preview_dir)


def flag_fence(flags, preview_dir):
    """The flag fence's i3d, xml and shop image. python3 art/source/xc_jumps.py flags makes only these."""
    posts, bars = build_flag_fence()
    write_flag_fence_i3d(os.path.join(OUT, FLAG_FENCE + ".i3d"), posts, bars)
    write_flag_fence_xml(os.path.join(OUT, FLAG_FENCE + ".xml"), posts, bars)
    # shop image: white flag, the guide line over 3 m, red flag
    white, red, bar = posts["eqXcFlagWhite"][0], posts["eqXcFlagRed"][0], bars[LINE_NODE][0]
    span = Mesh()
    for mesh, dz, stretch in ((white, 0.0, 1.0), (bar, FLAG_POST, 3.0), (red, FLAG_POST + 3.0, 1.0)):
        base = len(span.verts)
        span.verts += [((p[0], p[1], p[2] * stretch + dz), n, uv) for p, n, uv in mesh.verts]
        span.tris += [(a + base, b + base, c + base) for a, b, c in mesh.tris]
    store_image([(span, flags)], os.path.join(OUT, "store_" + FLAG_FENCE + ".dds"), preview_dir, yaw=-55, pitch=18)
    print(FLAG_FENCE, sum(len(m.tris) for m, _ in list(posts.values()) + list(bars.values())), "triangles")

if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["drops"]:
        # python3 art/source/xc_jumps.py drops [names]: only the drop walls (textures to a scratch folder)
        tmp = tempfile.mkdtemp()
        drop_walls(sys.argv[2:], os.environ.get("XC_PREVIEW_DIR", "art/previews"),
                   plank_texture(os.path.join(tmp, "p.dds"), os.path.join(tmp, "pn.dds")),
                   peeled_texture(os.path.join(tmp, "e.dds")), log_end_texture(os.path.join(tmp, "l.dds")))
    elif sys.argv[1:] == ["flags"]:
        flag_fence(flag_texture(os.path.join(tempfile.mkdtemp(), "xcFlags_diffuse.dds")),
                   os.environ.get("XC_PREVIEW_DIR", "art/previews"))
    else:
        main()
