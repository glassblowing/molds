#!/usr/bin/env -S uv run --python 3.13 --script --no-cache
# /// script
# requires-python = "==3.13"
# dependencies = [
#   "build123d",
#   "ocp-vscode"
# ]
# ///

"""Parametric optic molds for glass, built with build123d.

An optic mold is a one-piece, open-top dip mold. The gather is pushed in to press
the pattern into it, then pulled straight back out, so the cavity must widen
toward the top (draft) and have no undercuts.

Each pattern is a 2D cross-section at the bottom of the cavity. It is lofted to a
scaled-up copy at the top to give the draft. Scaling about the axis tapers walls
that face outward more than walls that face sideways (the sides of star points,
the creases between petals), so the scale is chosen to give every wall at least
MIN_DRAFT_DEG.

Run:
    ./optic_molds.py            # build every pattern
    ./optic_molds.py star rib   # build only these

Outputs go to ./mold-designs/ as <pattern>.step and <pattern>.stl, plus a cost report
on stdout: bar stock to buy, metal removed, and how hard the cavity is to machine.
"""

import math
import sys
from pathlib import Path

from build123d import (
    Align,
    Circle,
    Cylinder,
    Face,
    Kind,
    Vector,
    Polygon,
    Pos,
    Rot,
    Spline,
    Wire,
    export_step,
    export_stl,
    loft,
    offset,
    scale,
)
from ocp_vscode import show

# --- Mold (all units mm) --------------------------------------------------------
CAVITY_DEPTH = 100.0   # depth of the patterned cavity; ~4" suits work up to ~12" tall
MIN_DRAFT_DEG = 3.0    # least taper anywhere on the cavity wall; the widest
                       # parts of the outline get more
MIN_WALL = 12.0        # thinnest allowed wall, at the top of the cavity
BASE_THICKNESS = 15.0  # material below the cavity floor
VENT_DIAMETER = 2.0    # air vent through the center of the base; 0 to omit

# --- Cost drivers ---------------------------------------------------------------
# The cavity is finished with an end mill that has to reach the full depth. The
# pattern's pocket corners (star tips, the crevices beside flutes) can't be
# sharper than that cutter, so its size sets their radius. A bigger cutter is
# stiffer, cuts faster and needs less relative reach, so it is much cheaper.
TOOL_DIAMETER = 12.0
# Pocket corners get this much more radius than the cutter so it never buries
# itself in a corner, a standard machining rule.
CORNER_MARGIN = 0.5
TIP_RADIUS = TOOL_DIAMETER / 2 + CORNER_MARGIN
# Metal ridges that press into the glass (star valleys, flower creases). The
# cutter goes around these, so they can stay crisp at no extra cost; a little
# radius keeps them from chipping; 1 mm holds up well in soft aluminum.
RIDGE_RADIUS = 1.0

# Standard round bar diameters in mm (these are inch sizes; swap in metric sizes
# if your supplier stocks those). The mold uses the smallest bar that leaves
# MIN_WALL, and keeps the bar's outside as supplied so it needs no turning.
STOCK_DIAMETERS = [25.4 * d for d in (3, 3.5, 4, 4.5, 5, 5.5, 6, 7, 8)]
FACING_ALLOWANCE = 3.0  # extra bar length to face both ends flat

# Density in g/cm^3 (6061 aluminum), for the stock weight in the report.
MATERIALS = {"aluminum": 2.70}

OUT_DIR = Path(__file__).parent / "mold-designs"


# --- Cross-sections at the cavity floor -----------------------------------------
# Each returns a Face in the XY plane, centered on the origin.


def round_star(face, r_inner):
    """Fillet a star polygon: tips get TIP_RADIUS, valleys at r_inner get RIDGE_RADIUS."""
    valleys = [v.center() for v in face.vertices() if v.center().length < r_inner + 0.1]
    tips = [v for v in face.vertices() if v.center().length >= r_inner + 0.1]
    face = face.fillet_2d(TIP_RADIUS, tips)
    # Filleting replaces the tip vertices, so find the valleys again by position.
    return face.fillet_2d(
        RIDGE_RADIUS,
        [v for v in face.vertices() if any((v.center() - p).length < 1e-6 for p in valleys)],
    )


def star(points=8, r_outer=38.0, r_inner=26.0):
    """Pointed star. Deep ribs."""
    verts = []
    for i in range(2 * points):
        r = r_outer if i % 2 == 0 else r_inner
        a = math.pi * i / points
        verts.append((r * math.cos(a), r * math.sin(a)))
    return round_star(Polygon(*verts, align=None).face(), r_inner)


def flower(petals=6, r_core=24.0, petal_ring=24.0, petal_r=13.0):
    """Round petals around a core. Lobes with crisp creases between them."""
    step = 360 / petals
    # Rotating each circle points its seam vertex outward (for petals) or into a
    # petal (for the core), so only the valleys between petals are vertices.
    face = Circle(r_core)
    for i in range(petals):
        face += Rot(0, 0, i * step) * Pos(petal_ring, 0) * Circle(petal_r)
    face = face.face()
    valleys = [v for v in face.vertices() if v.center().length < petal_ring + petal_r - 1]
    return face.fillet_2d(RIDGE_RADIUS, valleys)


def rib(ribs=8, r=32.0, amplitude=2.4, samples_per_rib=12):
    """Classic smooth rib optic: a gentle wave around the circumference.

    The crests' curvature limits the cutter size. Fewer ribs or a smaller
    amplitude allow a bigger cutter.
    """
    n = ribs * samples_per_rib
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r + amplitude * math.cos(ribs * a)
        pts.append((rr * math.cos(a), rr * math.sin(a)))
    return Face(Wire([Spline(*pts, periodic=True)]))


def fluted(flutes=10, r=34.0, flute_r=4.5):
    """Circle with half-round ridges in the mold, giving rounded grooves in the glass."""
    step = 360 / flutes
    # Main circle's seam lands in the middle of flute 0 and is cut away.
    face = Rot(0, 0, step / 2) * Circle(r)
    for i in range(flutes):
        face -= Rot(0, 0, (i + 0.5) * step) * Pos(r, 0) * Circle(flute_r)
    # Every vertex is a crevice between the wall and a ridge: a pocket corner.
    face = face.face()
    return face.fillet_2d(TIP_RADIUS, face.vertices())


def sunburst(rays=6, r_long=38.0, r_short=32.0, r_inner=25.0):
    """Star with alternating long and short rays."""
    verts = []
    for i in range(4 * rays):
        if i % 2:
            r = r_inner
        else:
            r = r_long if i % 4 == 0 else r_short
        a = math.pi * i / (2 * rays)
        verts.append((r * math.cos(a), r * math.sin(a)))
    return round_star(Polygon(*verts, align=None).face(), r_inner)


PATTERNS = {
    "star": star,
    "flower": flower,
    "rib": rib,
    "fluted": fluted,
    "sunburst": sunburst,
}


# --- Mold construction ----------------------------------------------------------


def max_radius(face, samples=100):
    """Largest distance from the axis to the section's outline."""
    return max(
        edge.position_at(i / samples).length
        for edge in face.edges()
        for i in range(samples + 1)
    )


def min_wall_offset(section, samples=400):
    """Smallest distance from the axis to the tangent line of the outline.

    Scaling the outline by s moves a wall point p outward along its normal n by
    (p . n)(s - 1). The wall with the smallest p . n gets the least draft. Zero or
    negative would mean a vertical wall or an undercut.
    """
    smallest = math.inf
    for edge in section.outer_wire().edges():
        for i in range(samples + 1):
            u = i / samples
            p, t = edge.position_at(u), edge.tangent_at(u)
            n = Vector(t.Y, -t.X, 0)
            if section.is_inside(p + n * 0.01):
                n = -n
            smallest = min(smallest, p.X * n.X + p.Y * n.Y)
    if smallest <= 0:
        raise ValueError("Outline has a wall facing away from the axis: it can't release.")
    return smallest


def pick_stock(r_top):
    """Smallest standard bar that leaves MIN_WALL around the top of the cavity."""
    needed = 2 * (r_top + MIN_WALL)
    for d in STOCK_DIAMETERS:
        if d >= needed:
            return d
    raise ValueError(
        f"Mold needs {needed:.1f} mm bar, larger than any in STOCK_DIAMETERS."
    )


def build_mold(section):
    r_bottom = max_radius(section)
    # Scale growth per mm of height that gives the least-drafted wall MIN_DRAFT_DEG.
    grow = math.tan(math.radians(MIN_DRAFT_DEG)) / min_wall_offset(section)
    max_draft = math.degrees(math.atan(r_bottom * grow))
    # Loft slightly past the top so the cut goes cleanly through the top face.
    top_z = CAVITY_DEPTH + 2
    top_section = Pos(0, 0, top_z) * scale(section, 1 + top_z * grow)
    cavity = loft([section, top_section])

    r_top = r_bottom * (1 + CAVITY_DEPTH * grow)
    stock_d = pick_stock(r_top)
    mold = Pos(0, 0, -BASE_THICKNESS) * Rot(0, 0, 90) * Cylinder(
        stock_d / 2,
        CAVITY_DEPTH + BASE_THICKNESS,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    mold -= cavity
    if VENT_DIAMETER > 0:
        mold -= Pos(0, 0, -BASE_THICKNESS - 1) * Cylinder(
            VENT_DIAMETER / 2,
            BASE_THICKNESS + 2,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
    return mold, r_bottom, r_top, stock_d, max_draft


# --- Cost report ----------------------------------------------------------------


def largest_cutter(section, precision=0.05):
    """Diameter of the largest end mill that can finish the whole outline.

    A cutter of radius r reaches everywhere exactly when shrinking the outline by r
    and growing it back by r gives the same shape (a morphological opening).
    """

    def opened_area(r):
        try:
            return offset(offset(section, -r, kind=Kind.ARC), r, kind=Kind.ARC).area
        except Exception:
            return 0.0

    # Offsetting a spline outline is approximate and loses a little area at any
    # radius, so compare against a near-zero radius instead of the exact area.
    area = opened_area(precision / 2)
    lo, hi = 0.0, max_radius(section)
    while hi - lo > precision:
        r = (lo + hi) / 2
        if opened_area(r) >= area * (1 - 1e-4):
            lo = r
        else:
            hi = r
    return 2 * lo


def reach_rating(ratio):
    if ratio <= 4:
        return "standard tooling"
    if ratio <= 6:
        return "long-reach cutter"
    if ratio <= 10:
        return "extended reach: slow, light finishing passes"
    return "too deep to mill economically: wire EDM or casting"


def report(name, section, mold, r_bottom, r_top, stock_d, max_draft):
    stock_len = CAVITY_DEPTH + BASE_THICKNESS + FACING_ALLOWANCE
    stock_cm3 = math.pi * (stock_d / 2) ** 2 * stock_len / 1000
    removed_cm3 = (math.pi * (stock_d / 2) ** 2 * (stock_len - FACING_ALLOWANCE)
                   - mold.volume) / 1000
    cutter = largest_cutter(section)
    ratio = CAVITY_DEPTH / cutter if cutter else math.inf
    weights = ", ".join(f"{m} {stock_cm3 * rho / 1000:.1f} kg" for m, rho in MATERIALS.items())
    print(f"{name}  (valid={mold.is_valid}, solids={len(mold.solids())})")
    print(f"  cavity:   {2 * r_bottom:.1f} -> {2 * r_top:.1f} mm dia, {CAVITY_DEPTH:.0f} mm deep")
    print(f"  draft:    {MIN_DRAFT_DEG:g} deg minimum, {max_draft:.1f} deg at the widest point")
    print(f"  stock:    {stock_d / 25.4:g}\" ({stock_d:.1f} mm) bar x {stock_len:.0f} mm ({weights})")
    print(f"  wall:     {stock_d / 2 - r_top:.1f} mm min at top, "
          f"{stock_d / 2 - r_bottom:.1f} mm at bottom")
    print(f"  removed:  {removed_cm3:.0f} cm^3 from the cavity")
    print(f"  finish:   largest cutter {cutter:.1f} mm, reach {ratio:.1f}x dia "
          f"({reach_rating(ratio)})")
    if cutter < TOOL_DIAMETER - 0.1:
        print(f"  WARNING:  a {TOOL_DIAMETER:g} mm cutter can't finish this shape; "
              "change its parameters or lower TOOL_DIAMETER")


def main(names):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Cutter {TOOL_DIAMETER:g} mm -> pocket corner radius {TIP_RADIUS:g} mm\n")
    parts = []
    for name in names:
        try:
            section = PATTERNS[name]()
        except ValueError:
            print(f"{name}\n  SKIPPED:  features too narrow for {TIP_RADIUS:g} mm corners; "
                  "use fewer or wider points, or a smaller TOOL_DIAMETER")
            continue
        mold, *dims = build_mold(section)
        report(name, section, mold, *dims)
        export_step(mold, OUT_DIR / f"{name}.step")
        export_stl(mold, OUT_DIR / f"{name}.stl", tolerance=0.01, angular_tolerance=0.1)
        parts.append(mold)
    print(f"\nWrote files to {OUT_DIR}")

    show(parts)

if __name__ == "__main__":
    requested = sys.argv[1:] or list(PATTERNS)
    unknown = [n for n in requested if n not in PATTERNS]
    if unknown:
        sys.exit(f"Unknown pattern(s): {', '.join(unknown)}. Choose from {', '.join(PATTERNS)}")
    main(requested)
