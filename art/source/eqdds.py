"""DDS writers for the art scripts, in the formats GIANTS' TestRunner asks for.

- 3D textures: DXT1 (BC1) with a full mipmap chain.
- Shop images: BC7_UNORM in a DX10 header, no mipmaps.
- Wardrobe icons (see-through): DXT5, no mipmaps.

Needs numpy, Pillow and etcpak (pip install etcpak) for the block compression.
"""

import struct

import etcpak
import numpy as np
from PIL import Image

MARK = b"Realistic Equestrian by Jasta007"

DDSD_CAPS, DDSD_HEIGHT, DDSD_WIDTH, DDSD_PIXELFORMAT = 0x1, 0x2, 0x4, 0x1000
DDSD_MIPMAPCOUNT, DDSD_LINEARSIZE = 0x20000, 0x80000
DDPF_FOURCC = 0x4
DDSCAPS_COMPLEX, DDSCAPS_TEXTURE, DDSCAPS_MIPMAP = 0x8, 0x1000, 0x400000
DXGI_FORMAT_BC7_UNORM = 98
D3D10_RESOURCE_DIMENSION_TEXTURE2D = 3


def _rgba(image):
    """An RGBA uint8 array from a Pillow image or an RGB/RGBA array."""
    if isinstance(image, Image.Image):
        return np.asarray(image.convert("RGBA"))
    a = np.clip(np.asarray(image), 0, 255).astype(np.uint8)
    if a.shape[2] == 3:
        a = np.concatenate([a, np.full(a.shape[:2] + (1,), 255, np.uint8)], axis=2)
    return np.ascontiguousarray(a)


def _blocks(rgba, compress, *args):
    """Compress one level, padding it to whole 4x4 blocks (the small mip levels)."""
    h, w = rgba.shape[:2]
    ph, pw = -h % 4, -w % 4
    if ph or pw:
        rgba = np.pad(rgba, ((0, ph), (0, pw), (0, 0)), mode="edge")
    return compress(np.ascontiguousarray(rgba).tobytes(), w + pw, h + ph, *args)


def _header(width, height, linear_size, mip_count, fourcc):
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_LINEARSIZE
    caps = DDSCAPS_TEXTURE
    if mip_count > 1:
        flags |= DDSD_MIPMAPCOUNT
        caps |= DDSCAPS_COMPLEX | DDSCAPS_MIPMAP
    # the reserved bytes name the author, like the mod icon
    reserved = MARK[:44].ljust(44, b"\0")
    pixel_format = struct.pack("<II4s5I", 32, DDPF_FOURCC, fourcc, 0, 0, 0, 0, 0)
    return (b"DDS " + struct.pack("<7I", 124, flags, height, width, linear_size, 0, mip_count)
            + reserved + pixel_format + struct.pack("<5I", caps, 0, 0, 0, 0))


def save_dxt1(image, path):
    """A 3D texture: DXT1 with every mip level down to 1x1."""
    top = Image.fromarray(_rgba(image), "RGBA")
    width, height = top.size
    levels = []
    w, h = width, height
    while True:
        level = top if (w, h) == (width, height) else top.resize((w, h), Image.LANCZOS)
        levels.append(_blocks(np.asarray(level), etcpak.compress_bc1))
        if w == 1 and h == 1:
            break
        w, h = max(1, w // 2), max(1, h // 2)
    with open(path, "wb") as f:
        f.write(_header(width, height, len(levels[0]), len(levels), b"DXT1"))
        for data in levels:
            f.write(data)


def save_dxt5(image, path):
    """An image with see-through parts (wardrobe icons): DXT5, one level. BC7 icons came out as
    "undefined channel count, assuming 3 channels" and lose their alpha."""
    rgba = _rgba(image)
    height, width = rgba.shape[:2]
    data = _blocks(rgba, etcpak.compress_bc3)
    with open(path, "wb") as f:
        f.write(_header(width, height, len(data), 1, b"DXT5"))
        f.write(data)


def save_bc7(image, path):
    """A shop image: BC7_UNORM, one level."""
    rgba = _rgba(image)
    height, width = rgba.shape[:2]
    data = _blocks(rgba, etcpak.compress_bc7, None)
    with open(path, "wb") as f:
        f.write(_header(width, height, len(data), 1, b"DX10"))
        f.write(struct.pack("<5I", DXGI_FORMAT_BC7_UNORM, D3D10_RESOURCE_DIMENSION_TEXTURE2D, 0, 1, 0))
        f.write(data)
