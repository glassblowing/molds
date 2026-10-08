#!/usr/bin/env -S uv run --python 3.13 --script --no-cache
# /// script
# requires-python = "==3.13"
# dependencies = [
#   "build123d",
#   "ocp-vscode"
# ]
# ///

"""Segmented blow mold for glass: four loose staves in a square tube, with build123d.

The pattern is cut into the inside faces of four identical staves that stand in
a length of square steel tube. The glass is blown out against them, filling the
pattern. Once it has set, lifting the pipe brings the staves up out of the tube
with the glass, and they fall away sideways. Because each stave comes off
sideways, the pattern can be far deeper than a dip mold allows.

This is a blow mold, not a dip mold: the glass takes the whole shape of the
cavity, and it comes out as soon as it is stiff, still hot, to go in the
annealer. Left to go cold in the mold it would crack.

Each stave is machined square-on to its inside face, and pulls off the glass in
the same direction, so one rule covers both: seen from the middle of the mold,
no part of a stave's pattern may hide behind another. The ribs between the
squares are V-shaped for that reason, and a rib runs down every seam, so each
stave only carries the half that faces it.

The pattern here is "grenade": a grid of raised squares on the glass, formed by
ribs in the mold.

Run:
    ./segmented_mold_generator.py

Outputs go to ./mold-designs/segmented/:
    stave.step        one stave; make four
    base_plate.dxf    plate the tube stands on, which forms the bottom of the glass
    glass.step        the finished glass shape (reference)
    assembly.step     staves, tube and base plate together (reference)
    *.stl             the stave and glass as meshes
"""

import math
from pathlib import Path

from build123d import (
    Align,
    Axis,
    Compound,
    Cylinder,
    ExportDXF,
    Plane,
    Polygon,
    Pos,
    Rectangle,
    RectangleRounded,
    Rot,
    Unit,
    export_step,
    export_stl,
    extrude,
    revolve,
)
from ocp_vscode import show

# --- Container (all units mm) ---------------------------------------------------
# Square steel tube the staves stand in, bought as stock. 88.9 x 4.76 is
# 3.5" x 3/16". Its inside corners are rounded, so the staves are cut back there.
TUBE_OUTER = 88.9
TUBE_WALL = 4.76
FIT_CLEARANCE = 0.3    # gap between the staves and the tube, each side
CORNER_RELIEF = 8.0    # how much is cut off the staves at the tube's corners
BASE_THICKNESS = 6.35
FOOT_WIDTH = 15.0      # how far the base plate sticks out, to stand on

# --- Glass ----------------------------------------------------------------------
HEIGHT = 100.0         # height of the staves and of the patterned glass
MIN_WALL = 9.0         # thinnest part of a stave, at the bottom of a pocket

# --- Grenade pattern ------------------------------------------------------------
# Squares around the glass. Must be a multiple of 4, so a rib lands on each seam
# and all four staves are the same part.
COLUMNS = 12
RIB_DEPTH = 3.0        # how far the ribs stand in; the depth of the grooves in the glass
# Half the angle of the V. It must exceed the furthest any rib sits from the
# middle of its stave, plus some draft, and a rib on a seam sits at 45.
RIB_HALF_ANGLE_DEG = 50.0

# Density in g/cm^3 (6061 aluminum), for the weight in the report.
MATERIALS = {"aluminum": 2.70}

OUT_DIR = Path(__file__).parent / "mold-designs" / "segmented"

if COLUMNS % 4:
    raise ValueError("COLUMNS must be a multiple of 4.")

INSERT_SIDE = TUBE_OUTER - 2 * TUBE_WALL - 2 * FIT_CLEARANCE
GLASS_RADIUS = INSERT_SIDE / 2 - MIN_WALL
# Rows are as near square as a whole number allows.
ROWS = max(1, round(HEIGHT / (2 * math.pi * GLASS_RADIUS / COLUMNS)))
RIB_SLOPE = math.tan(math.radians(RIB_HALF_ANGLE_DEG))
LOW = (Align.CENTER, Align.CENTER, Align.MIN)


# --- Glass shape ----------------------------------------------------------------


def rib_profile():
    """Cross-section of a rib: a V with its tip RIB_DEPTH inside the glass.

    Drawn pointing along -X from the glass surface on the +X side, and carried a
    little past the surface so it cuts cleanly.
    """
    past = 1.0
    half_width = (RIB_DEPTH + past) * RIB_SLOPE
    return (
        (GLASS_RADIUS - RIB_DEPTH, 0),
        (GLASS_RADIUS + past, -half_width),
        (GLASS_RADIUS + past, half_width),
    )


def build_glass():
    """The glass shape: a cylinder with a grid of V-grooves, one per mold rib."""
    glass = Pos(0, 0, -1) * Cylinder(GLASS_RADIUS, HEIGHT + 2, align=LOW)
    upright = Pos(0, 0, -1) * extrude(Polygon(*rib_profile(), align=None), HEIGHT + 2)
    for k in range(COLUMNS):
        # Starting at 45 degrees puts a rib on every seam.
        glass -= Rot(0, 0, 45 + k * 360 / COLUMNS) * upright
    ring = revolve(Plane.XZ * Polygon(*rib_profile(), align=None), Axis.Z)
    for k in range(1, ROWS):
        glass -= Pos(0, 0, k * HEIGHT / ROWS) * ring
    return glass


# --- Staves ---------------------------------------------------------------------


def build_stave(glass):
    """The stave on the +X side. The other three are the same part, turned."""
    outline = Rectangle(INSERT_SIDE, INSERT_SIDE)
    # Cut the corners back to clear the rounded inside corners of the tube.
    cut = CORNER_RELIEF * math.sqrt(2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            outline -= Pos(sx * INSERT_SIDE / 2, sy * INSERT_SIDE / 2) * Rot(0, 0, 45) * Rectangle(cut, cut)
    insert = extrude(outline, HEIGHT) - glass
    # The seams run corner to corner, so each stave is the quarter facing one wall.
    reach = INSERT_SIDE
    quarter = extrude(Polygon((0, 0), (reach, -reach), (reach, reach), align=None), HEIGHT)
    stave = insert & quarter
    if len(stave.solids()) != 1:
        raise ValueError(f"The stave came out in {len(stave.solids())} pieces.")
    return stave.solid()


def least_draft(stave):
    """Least angle, in degrees, at which the pattern faces the middle of the mold.

    Zero or less would mean a face the cutter can't see and the stave can't pull
    away from. Only the patterned faces are checked, picked out as the ones lying
    inside the glass surface.
    """
    drafts = []
    for face in stave.faces():
        center = face.center()
        if math.hypot(center.X, center.Y) > GLASS_RADIUS + 0.01:
            continue
        normal = face.normal_at(center)
        if abs(normal.Z) > 0.99:
            continue
        # This stave is on the +X side, so it faces the middle along -X.
        drafts.append(math.degrees(math.asin(max(-1.0, min(1.0, -normal.X)))))
    return min(drafts)


# --- Container ------------------------------------------------------------------


def build_tube():
    inner = TUBE_OUTER - 2 * TUBE_WALL
    section = RectangleRounded(TUBE_OUTER, TUBE_OUTER, 2 * TUBE_WALL)
    section -= RectangleRounded(inner, inner, TUBE_WALL)
    return extrude(section, HEIGHT)


def build_base_plate():
    side = TUBE_OUTER + 2 * FOOT_WIDTH
    return Rectangle(side, side).face()


# --- Output ---------------------------------------------------------------------


def write_dxf(face, path):
    dxf = ExportDXF(unit=Unit.MM)
    dxf.add_shape(face)
    dxf.write(path)


def report(glass, stave, draft):
    pitch = 2 * math.pi * GLASS_RADIUS / COLUMNS
    rib_width = 2 * RIB_DEPTH * RIB_SLOPE
    block = stave.bounding_box().size
    weights = ", ".join(f"{m} {stave.volume * rho / 1e6:.2f} kg" for m, rho in MATERIALS.items())
    print(f"segmented  (valid={stave.is_valid}, solids={len(stave.solids())})")
    print(f"  glass:    {2 * GLASS_RADIUS:.1f} mm dia x {HEIGHT:.0f} mm, {glass.volume / 1000:.0f} cm^3 inside")
    print(f"  pattern:  {ROWS} rows of {COLUMNS} squares, {pitch - rib_width:.1f} x "
          f"{HEIGHT / ROWS - rib_width:.1f} mm, with grooves {RIB_DEPTH:g} mm deep "
          f"and {rib_width:.1f} mm wide between them")
    print(f"  staves:   4 the same, each from {block.Y:.0f} x {block.X:.0f} x {block.Z:.0f} mm bar "
          f"({weights} each)")
    print(f"  release:  least draft {draft:.1f} deg, machined and pulled square-on")
    print(f"  tube:     {TUBE_OUTER:g} mm square x {TUBE_WALL:g} mm wall x {HEIGHT:.0f} mm long")
    print(f"  base:     {TUBE_OUTER + 2 * FOOT_WIDTH:.0f} mm square x {BASE_THICKNESS:g} mm plate")
    if draft < 1:
        print("  WARNING:  part of the pattern faces away from the middle of the mold; "
              "raise RIB_HALF_ANGLE_DEG")


def main():
    glass = build_glass()
    stave = build_stave(glass)
    report(glass, stave, least_draft(stave))

    # The glass as it would be, trimmed to the height of the staves.
    piece = glass & Cylinder(2 * GLASS_RADIUS, HEIGHT, align=LOW)
    staves = [Rot(0, 0, 90 * k) * stave for k in range(4)]
    base_plate = build_base_plate()
    base = Pos(0, 0, -BASE_THICKNESS) * extrude(base_plate, BASE_THICKNESS)
    tube = build_tube()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    export_step(stave, OUT_DIR / "stave.step")
    export_stl(stave, OUT_DIR / "stave.stl", tolerance=0.01, angular_tolerance=0.1)
    export_step(piece, OUT_DIR / "glass.step")
    export_stl(piece, OUT_DIR / "glass.stl", tolerance=0.01, angular_tolerance=0.1)
    export_step(Compound(children=staves + [tube, base]), OUT_DIR / "assembly.step")
    write_dxf(base_plate, OUT_DIR / "base_plate.dxf")
    print(f"\nWrote files to {OUT_DIR}")

    # The mold assembled, and beside it the glass with the staves pulled away.
    step = TUBE_OUTER + 2 * FOOT_WIDTH + 40
    apart = [Pos(step, 0, 0) * Rot(0, 0, 90 * k) * Pos(25, 0, 0) * stave for k in range(4)]
    show(staves + [tube, base, Pos(step, 0, 0) * piece] + apart)


if __name__ == "__main__":
    main()
