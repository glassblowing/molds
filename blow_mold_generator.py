#!/usr/bin/env -S uv run --python 3.13 --script --no-cache
# /// script
# requires-python = "==3.13"
# dependencies = [
#   "build123d",
#   "ocp-vscode"
# ]
# ///

"""Parametric two-part hinged blow mold for glass, built with build123d.
Edit the parameters below, then run:
    ./blow_mold_generator.py

Outputs go to ./mold-designs/blow/:
    glass_piece.step   the finished glass shape (reference)
    mold_half_a.step   mold half on the -Y side of the parting plane
    mold_half_b.step   mold half on the +Y side of the parting plane
    *.stl              the same parts as meshes, for 3D-printed test molds
"""

from pathlib import Path

from build123d import (
    Align,
    Axis,
    Cone,
    Cylinder,
    Face,
    Keep,
    Line,
    Location,
    Plane,
    Pos,
    Rot,
    Spline,
    Wire,
    export_step,
    export_stl,
    revolve,
    split,
)
from ocp_vscode import show


# --- Glass piece (all units mm) ------------------------------------------------
# Outer profile of the finished piece as (radius, height) points, bottom to lip.
# The spline passes through every point. The first point is where the flat
# bottom ends; the last point is the lip at the top of the mold.
PROFILE = [
    (32, 0),
    (40, 5),
    (50, 30),
    (55, 70),
    (50, 110),
    (33, 145),
    (26, 165),
    (27, 180),
]

# Cavity oversize to compensate for glass shrinking and the mold expanding at
# working temperature. Depends on glass COE, mold material and mold temperature,
# so confirm with test blows or your mold maker.
SHRINK_SCALE = 1.007

# How strongly the profile is pulled horizontal at the base and vertical at the
# lip. High values make the spline overshoot and the profile intersect itself.
TANGENT_STRENGTH = 1.0

# --- Mold block -----------------------------------------------------------------
WALL = 20.0            # minimum wall around the widest part of the cavity
BASE_THICKNESS = 20.0  # material below the bottom of the cavity
TOP_CHAMFER = 4.0      # lead-in chamfer at the neck opening

# Vent holes through the base, placed off the parting line.
VENT_DIAMETER = 1.5
VENT_COUNT = 4
VENT_RADIUS_FRACTION = 0.6  # fraction of the flat-bottom radius

# Dowel pin holes in the parting faces to align the two halves.
DOWEL_DIAMETER = 6.0
DOWEL_CLEARANCE = 0.05     # added to the diameter
DOWEL_DEPTH = 10.0         # per half
DOWEL_HEIGHTS = (0.25, 0.75)  # fractions of mold height

OUT_DIR = Path(__file__).parent / "mold-designs" / "blow"


def check_profile(spline, z0, z1, samples=2000):
    """Reject splines that overshoot the floor or lip, or cross the axis.

    An overshooting spline makes a self-intersecting profile. The revolve still
    succeeds, but later booleans and the mold split silently produce broken solids.
    """
    tol = 1e-3
    for i in range(samples + 1):
        p = spline.position_at(i / samples)
        if p.Z < z0 - tol or p.Z > z1 + tol or p.X <= 0:
            raise ValueError(
                f"Profile spline leaves the valid region at r={p.X:.3f}, z={p.Z:.3f}. "
                "Lower TANGENT_STRENGTH or adjust PROFILE points near the ends."
            )


def glass_profile_face(points, extend_top=0.0):
    """Closed half-section of the piece in the XZ plane, ready to revolve."""
    pts = [(r * SHRINK_SCALE, 0, z * SHRINK_SCALE) for r, z in points]
    r0, _, z0 = pts[0]
    r1, _, z1 = pts[-1]
    top = z1 + extend_top
    # Horizontal start and vertical end keep the bottom corner and lip smooth.
    spline = Spline(
        *pts,
        tangents=[(1, 0, 0), (0, 0, 1)],
        tangent_scalars=(TANGENT_STRENGTH, TANGENT_STRENGTH),
    )
    check_profile(spline, z0, z1)
    edges = [Line((0, 0, z0), (r0, 0, z0)), spline]
    if extend_top > 0:
        edges.append(Line((r1, 0, z1), (r1, 0, top)))
    edges += [
        Line((r1, 0, top), (0, 0, top)),
        Line((0, 0, top), (0, 0, z0)),
    ]
    return Face(Wire(edges))


def build():
    # Revolved and cylindrical faces have a seam edge. Rotating by 90 degrees keeps
    # those seams off the XZ parting plane, where a split along a seam edge can be
    # unreliable in OpenCascade.
    seam_rot = Rot(0, 0, 90)
    glass = seam_rot * revolve(glass_profile_face(PROFILE), Axis.Z)
    # Taller than the mold so the boolean punches cleanly through the top.
    cavity = seam_rot * revolve(glass_profile_face(PROFILE, extend_top=10), Axis.Z)

    bb = glass.bounding_box()
    cavity_r = max(bb.max.X, bb.max.Y)
    height = bb.max.Z
    mold_r = cavity_r + WALL
    mold_h = height + BASE_THICKNESS
    lip_r = PROFILE[-1][0] * SHRINK_SCALE
    foot_r = PROFILE[0][0] * SHRINK_SCALE

    mold = Pos(0, 0, -BASE_THICKNESS) * seam_rot * Cylinder(
        mold_r, mold_h, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    mold -= cavity
    # 45 degree lead-in. The cone starts 1 mm inside the cavity wall and ends 1 mm
    # above the top, so it crosses both surfaces instead of just touching them.
    mold -= Pos(0, 0, height - TOP_CHAMFER - 1) * seam_rot * Cone(
        lip_r - 1,
        lip_r + TOP_CHAMFER + 1,
        TOP_CHAMFER + 2,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )

    vent_r = foot_r * VENT_RADIUS_FRACTION
    for i in range(VENT_COUNT):
        angle = 360 / VENT_COUNT * (i + 0.5)  # stays clear of the parting plane
        loc = Location((0, 0, 0), (0, 0, angle)) * Pos(vent_r, 0, -BASE_THICKNESS - 1)
        mold -= loc * Cylinder(
            VENT_DIAMETER / 2,
            BASE_THICKNESS + 2,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

    dowel_x = cavity_r + WALL / 2
    dowel_r = (DOWEL_DIAMETER + DOWEL_CLEARANCE) / 2
    for frac in DOWEL_HEIGHTS:
        z = -BASE_THICKNESS + mold_h * frac
        for x in (-dowel_x, dowel_x):
            # Cylinder rotated onto the Y axis, straddling the parting plane.
            mold -= Pos(x, 0, z) * Cylinder(dowel_r, 2 * DOWEL_DEPTH, rotation=(90, 0, 0))

    half_a = split(mold, Plane.XZ, keep=Keep.TOP)
    half_b = split(mold, Plane.XZ, keep=Keep.BOTTOM)

    # Lower bound on the wall between a dowel hole and the cavity.
    dowel_wall = WALL / 2 - dowel_r
    print(f"Cavity: max radius {cavity_r:.2f} mm, height {height:.2f} mm")
    print(f"Mold block: diameter {2 * mold_r:.2f} mm, height {mold_h:.2f} mm")
    print(f"Min wall between dowel hole and cavity: {dowel_wall:.2f} mm")
    for name, part in (("glass", glass), ("half_a", half_a), ("half_b", half_b)):
        print(f"{name}: valid={part.is_valid}, volume={part.volume / 1000:.1f} cm^3")

    return glass, half_a, half_b


if __name__ == "__main__":
    glass, half_a, half_b = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, part in (
        ("glass_piece", glass),
        ("mold_half_a", half_a),
        ("mold_half_b", half_b),
    ):
        export_step(part, OUT_DIR / f"{name}.step")
        export_stl(part, OUT_DIR / f"{name}.stl", tolerance=0.01, angular_tolerance=0.1)

    show(glass, half_a, half_b)
    print(f"Wrote files to {OUT_DIR}")
