#!/usr/bin/env -S uv run --python 3.13 --script --no-cache
# /// script
# requires-python = "==3.13"
# dependencies = [
#   "matplotlib",
#   "numpy"
# ]
# ///

"""Render the preview pictures in the README from the generated STL files.

Run the mold generators first, then:
    ./render_previews.py

Pictures go to ./docs/images/. Each is a row of parts drawn as shaded meshes.
Hollow parts are drawn cut in half, so the inside shows.
"""

import struct
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).parent
MOLDS = ROOT / "mold-designs"
OUT_DIR = ROOT / "docs" / "images"

METAL = np.array([0.72, 0.75, 0.78])
GLASS = np.array([0.55, 0.78, 0.74])

# Each picture: file name, then one (STL, caption, view, color) per part.
# Views: "whole" and "above" show the outside, "cut" removes the near half of a
# hollow part, and "inside" and the "half" views look at the patterned face of an
# insert, stave or mold half.
PICTURES = {
    "insert-sets.png": [
        ("insert-mold/inserts/pineapple.stl", "Pineapple", "inside", METAL),
        ("insert-mold/inserts/rings.stl", "Rings", "inside", METAL),
        ("insert-mold/inserts/spiral.stl", "Spiral ribs", "inside", METAL),
        ("insert-mold/inserts/hobnail.stl", "Hobnail", "inside", METAL),
        ("insert-mold/inserts/spikes.stl", "Sparse spikes", "inside", METAL),
    ],
    "insert-mold.png": [
        ("insert-mold/sleeve_solid.stl", "Sleeve, in one piece", "above", METAL),
        ("insert-mold/sleeve_half_b.stl", "Sleeve, as two halves (one shown)", "half", METAL),
        ("insert-mold/inserts/pineapple.stl", "One of four inserts", "inside", METAL),
    ],
    "pineapple.png": [
        ("pineapple/solid.stl", "Solid (cut away)", "cut", METAL),
        ("pineapple/stack.stl", "Laser-cut plate stack (cut away)", "cut", METAL),
    ],
    "optic.png": [
        ("optic/star.stl", "star", "above", METAL),
        ("optic/flower.stl", "flower", "above", METAL),
        ("optic/rib.stl", "rib", "above", METAL),
        ("optic/fluted.stl", "fluted", "above", METAL),
        ("optic/sunburst.stl", "sunburst", "above", METAL),
    ],
    "blow.png": [
        ("blow/mold_half_a.stl", "One mold half", "half_a", METAL),
        ("blow/glass_piece.stl", "The glass it makes", "whole", GLASS),
    ],
    "segmented.png": [
        ("segmented/stave.stl", "One of four staves", "inside", METAL),
        ("segmented/glass.stl", "The glass it makes", "whole", GLASS),
    ],
}

# For each view: camera elevation and azimuth in degrees, and which triangles to keep.
VIEWS = {
    "whole": (22, -60, "all"),
    "above": (52, -60, "all"),
    "cut": (30, -90, "far"),
    "inside": (12, 180, "facing"),
    "half": (15, -90, "facing"),
    "half_a": (15, 90, "facing"),
}


def load_stl(path):
    """Triangles of an STL file, binary or text, as an (n, 3, 3) array."""
    data = path.read_bytes()
    if data[:5] == b"solid" and b"facet" in data[:400]:
        points = [line.split()[1:] for line in data.decode().splitlines()
                  if line.strip().startswith("vertex")]
        return np.array(points, dtype=float).reshape(-1, 3, 3)
    count = struct.unpack("<I", data[80:84])[0]
    record = np.dtype([("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("pad", "<u2")])
    return np.frombuffer(data, dtype=record, count=count, offset=84)["corners"].astype(float)


def draw(ax, triangles, view, color):
    elevation, azimuth, keep = VIEWS[view]
    e, a = np.radians(elevation), np.radians(azimuth)
    toward_camera = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])

    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    normals /= np.linalg.norm(normals, axis=1)[:, None] + 1e-12
    centers = triangles.mean(axis=1)
    middle = (triangles.reshape(-1, 3).min(axis=0) + triangles.reshape(-1, 3).max(axis=0)) / 2
    if keep == "far":
        # Drop the half of the part nearest the camera.
        level = np.array([toward_camera[0], toward_camera[1], 0.0])
        shown = (centers - middle) @ level < 0
    elif keep == "facing":
        shown = normals @ toward_camera > -0.15
    else:
        shown = normals @ toward_camera > 0
    triangles, normals = triangles[shown], normals[shown]

    # Light from over the camera's left shoulder.
    side = np.cross([0.0, 0.0, 1.0], toward_camera)
    light = toward_camera + 0.7 * np.array([0.0, 0.0, 1.0]) - 0.6 * side / (np.linalg.norm(side) + 1e-12)
    light /= np.linalg.norm(light)
    lit = np.abs(normals @ light) if keep == "far" else np.clip(normals @ light, 0, 1)
    shade = 0.25 + 0.8 * lit
    ax.add_collection3d(Poly3DCollection(
        triangles, facecolors=np.clip(shade[:, None] * color, 0, 1), edgecolors="none"
    ))

    reach = (triangles.reshape(-1, 3).max(axis=0) - triangles.reshape(-1, 3).min(axis=0)).max() / 2
    for set_limits, center in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), middle):
        set_limits(center - reach, center + reach)
    ax.set_box_aspect((1, 1, 1), zoom=1.25 if keep == "facing" else 1.0)
    ax.view_init(elev=elevation, azim=azimuth)
    ax.set_axis_off()


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, parts in PICTURES.items():
        fig = plt.figure(figsize=(3.4 * len(parts), 4.2))
        for index, (stl, caption, view, color) in enumerate(parts):
            ax = fig.add_subplot(1, len(parts), index + 1, projection="3d")
            draw(ax, load_stl(MOLDS / stl), view, color)
            ax.set_title(caption, y=-0.06, fontsize=11)
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0.1, wspace=0)
        fig.savefig(OUT_DIR / name, dpi=110, facecolor="white")
        plt.close(fig)
        print(f"Wrote {OUT_DIR / name}")


if __name__ == "__main__":
    main()
