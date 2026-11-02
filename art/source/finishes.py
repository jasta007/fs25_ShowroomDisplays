"""
The Finish option's textures (James, 2026-11-02): an alternative to the pale plaster (plinthStone),
subtle, and tiling cleanly. Each covers displays.STONE_TILE metres each way, as the plaster does,
and the pieces are mapped in world space, so the pattern carries on across faces.

- finishWood_diffuse.dds: horizontal timber cladding, boards 0.2 m tall in staggered lengths,
  soft grain, a thin shadow line between boards.
- finishMetal_diffuse.dds: dark painted steel panels 1.25 m square with fine seams and faint
  brushing.

Noise is smoothed in frequency space, so every texture tiles without a seam.

Run from the repository root: python3 art/source/finishes.py

Part of Showroom Displays by Jasta007.
"""

import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from eqdds import save_dxt1  # noqa: E402

OUT = "placeables/displays"
SIZE = 1024
TILE = 5.0   # metres the texture covers (displays.STONE_TILE)


def tiling_noise(rng, size, sx, sy):
    """Gaussian-smoothed noise that tiles: sx, sy the blob size in pixels across and up."""
    fx = np.fft.fftfreq(size)[None, :]
    fy = np.fft.fftfreq(size)[:, None]
    spectrum = np.fft.fft2(rng.normal(0, 1, (size, size))) * np.exp(-((fx * sx) ** 2 + (fy * sy) ** 2) * 2)
    field = np.real(np.fft.ifft2(spectrum))
    return field / (field.std() + 1e-9)


def wood(size=SIZE):
    rng = np.random.default_rng(21)
    px_per_m = size / TILE
    board_h = int(round(0.2 * px_per_m))        # 0.2 m boards; 25 to the tile
    rows = size // board_h
    board_h = size / rows
    base = np.array([118.0, 86.0, 58.0])        # weathered oak brown, kept quiet
    img = np.zeros((size, size, 3)) + base
    grain = tiling_noise(rng, size, 160.0, 2.0) * 5.0 + tiling_noise(rng, size, 40.0, 0.8) * 3.0
    cloud = tiling_noise(rng, size, 120.0, 120.0) * 4.0
    y = np.arange(size)
    row_of = np.minimum((y / board_h).astype(int), rows - 1)
    shade = np.zeros(size)
    tone = rng.normal(0, 4.5, (rows, 8))
    lengths = rng.integers(2, 4, rows)           # boards 2-3 m long, staggered
    offsets = rng.uniform(0, size, rows)
    out = img.copy()
    xs = np.arange(size)
    for r in range(rows):
        y0, y1 = int(round(r * board_h)), int(round((r + 1) * board_h))
        seg = size / (TILE / lengths[r])         # board length in pixels (a whole number to the tile)
        n = int(round(size / seg))
        seg = size / n
        k = (((xs - offsets[r]) % size) / seg).astype(int) % n
        t = tone[r, k % tone.shape[1]]
        out[y0:y1] += t[None, :, None]
        # end joints: a thin dark line where boards butt
        joint = (((xs - offsets[r]) % seg) < 1.5)
        out[y0:y1, joint] -= 22
        # the shadow under each board's lap, and a lighter top edge
        out[y0:y0 + 2] += 6
        out[max(y1 - 3, 0):y1] -= 26
    out += (grain + cloud)[..., None] * np.array([1.0, 0.8, 0.6])
    return np.clip(out, 0, 255).astype(np.uint8)


def metal(size=SIZE):
    rng = np.random.default_rng(33)
    px_per_m = size / TILE
    panel = int(round(1.25 * px_per_m))
    base = np.array([58.0, 60.0, 63.0])          # dark painted steel
    img = np.zeros((size, size, 3)) + base
    img += (tiling_noise(rng, size, 150.0, 150.0) * 2.5)[..., None]
    img += (tiling_noise(rng, size, 1.0, 200.0) * 1.2)[..., None]       # faint brushing, streaks running up
    img += rng.normal(0, 0.8, (size, size, 1))
    n = size // panel
    panel = size / n
    tone = rng.normal(0, 1.6, (n, n))
    yy, xx = np.mgrid[0:size, 0:size]
    img += tone[(yy / panel).astype(int) % n, (xx / panel).astype(int) % n][..., None]
    seam_x = (xx % panel) < 2
    seam_y = (yy % panel) < 2
    img[seam_x | seam_y] -= 14
    img[((xx % panel) >= 2) & ((xx % panel) < 3)] += 5     # a lit edge beside each seam
    img[((yy % panel) >= 2) & ((yy % panel) < 3)] += 5
    return np.clip(img, 0, 255).astype(np.uint8)


TEXTURES = {"finishWood_diffuse.dds": wood, "finishMetal_diffuse.dds": metal}


def main():
    for name, make in TEXTURES.items():
        rgb = make()
        save_dxt1(Image.fromarray(rgb), os.path.join(OUT, name))
        print(name, rgb.shape)


if __name__ == "__main__":
    main()
