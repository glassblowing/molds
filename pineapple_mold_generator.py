#!/usr/bin/env -S uv run --python 3.13 --script --no-cache
# /// script
# requires-python = "==3.13"
# dependencies = [
#   "build123d",
#   "numpy",
#   "ocp-vscode"
# ]
# ///

"""Twisted pineapple optic mold, built with build123d.

A pineapple mold is a dip mold whose wall is covered in diamond-shaped pyramids,
packed edge to edge, that press a grid of dimples into the gather. Turning each
row a little further than the one below leans the diamonds over, so the pattern
spirals around the cavity.

The points are as deep as POINT_DEPTH asks, in the manner of cast bronze
pineapple molds: on a nearly straight wall their undersides overhang. That works
because the glass only ever touches the tips, never the wall between them, so
there is nothing for an overhang to trap. It does mean the points can't be
milled from above.

The bottom of the cavity curves in like a bowl and the points carry on round
it, shrinking as they go, so the rounded end of a bubble meets the same pattern
as its sides. Only a small flat floor is left in the middle, for the vent.

The same cavity is built four ways:

Stacked plates, for laser cutting. The cavity is sliced into flat rings, so the
pyramids come out stepped; thinner plates follow them more closely. Overhangs
cost nothing here, because every plate is cut on its own. Floor spikes can't be
cut this way, since each would be a loose island, so the base plates get a hole
at each one to tap for a cone-point set screw instead. The plates follow the
mold's taper, with a lug reaching out to each rod, which uses less sheet and
less cutting than plain discs big enough to hold the rods.

Solid, for casting or metal printing. One piece with true pyramids, a thin even
wall that tapers with the cavity, and a foot. Both are priced by the metal used.

Inserts in a sleeve, for CNC machining. The points are on four identical loose
inserts, each a quarter of the wall, that drop into a sleeve with a tapered
bore. A cutter comes at each insert from its open inside face, turned a little to
either side to get behind the points. The taper is what makes the fit work: the
inserts wedge snug under their own weight, with no play, and are free the moment
they lift. If the glass chills and grabs the points, pulling it out brings the
inserts with it and they peel off sideways. A small step down each seam laps
every insert over its neighbor, so none can drop inward, yet each still pulls
straight off. Hot inserts that have grown just sit
a little higher in the taper instead of jamming, as they would in a straight
bore. The sleeve's floor is dished, with a vent, so the glass can't seal to it.
Four more sets of inserts fit the same sleeve in place of the pineapple ones:

Rings running round the cavity.
Spiral ribs, which give a swirl without twisting the glass by hand.
Hobnail, round pockets that the glass is blown into to raise rows of beads.
Sparse spikes, a few tall points for deliberate air-trap bubbles.

Rings and spiral ribs hold the glass against a straight pull far more than
points do, which is what the loose inserts are for: they come out with the glass
and pull off sideways.

The sleeve is drawn two ways for a mill, to quote against each other: as one
square block with the bore milled down from the top, and as two blocks bolted
together, whose bore is two shallow troughs instead of one deep hole.

Rings, also for CNC machining. The solid cut into short rings that bolt together, each
shallow enough for a ball end mill to finish from above on a 3-axis machine.
Only written when the points are shallow enough not to overhang.

The outsides differ, which is fine for heat. A dip lasts a second or two, and in
that time heat gets only about 10 mm into aluminum and 5 mm into steel, so how
evenly the glass is chilled is set by the points, which are the same all the way
round. Between dips the metal evens itself out, within seconds in aluminum and
about a minute in steel. Metal further out only adds heat capacity, which slows
how fast the mold warms up over a session.

Run:
    ./pineapple_mold_generator.py

Outputs go to ./mold-designs/:
    pineapple/solid.step             the one-piece mold
    pineapple/plates/plate_NN.dxf    one cutting file per plate, numbered from the bottom
    pineapple/stack.step             the assembled plates (reference)
    pineapple/cnc_rings/ring_N.step  one part per ring, if the points allow it
    insert-mold/inserts/<set>.step   one insert of each set; make four
    insert-mold/sleeve_solid.step    the sleeve the inserts drop into, in one piece
    insert-mold/sleeve_half_X.step   the same sleeve as two halves
    insert-mold/foot_plate_*.dxf     the foot that screws under each sleeve
    *.stl                            the same parts as meshes
"""

import math
from pathlib import Path

import numpy as np

from build123d import (
    Align,
    Axis,
    Box,
    Circle,
    Compound,
    Cone,
    Cylinder,
    EllipticalCenterArc,
    ExportDXF,
    Face,
    Plane,
    Polygon,
    Polyline,
    Pos,
    Rectangle,
    Rot,
    Shell,
    Solid,
    Sphere,
    Unit,
    Vector,
    Wire,
    export_step,
    export_stl,
    extrude,
    make_face,
    revolve,
)
from ocp_vscode import show

# --- Mold (all units mm) --------------------------------------------------------
# Outside of the mold at its rim. The cavity fills it, less SOLID_WALL around the
# rim and the base underneath, and tapers down to BOTTOM_RADIUS at the floor. The
# outside tapers with it, so the wall stays about SOLID_WALL thick.
MOLD_DIAMETER = 100.0
MOLD_HEIGHT = 130.0
# Metal around the cavity, measured at the creases between points. The points
# themselves add to it, so this can be thin. In the sleeved version it is shared
# between the sleeve's rim and the inserts.
SOLID_WALL = 9.0
# Cavity wall radius the taper would reach at the floor. Smaller gives more
# taper, which is also the taper the inserts seat on.
BOTTOM_RADIUS = 30.0
# Below this height the wall curves in to meet the floor, like the bottom of a
# bowl. 0 leaves a straight wall and a flat floor.
BOWL_HEIGHT = 28.0
# Flat floor left in the middle of the bowl. The points get smaller toward it,
# so it can't shrink to nothing.
FLOOR_RADIUS = 16.0
# Flange around the bottom to stand on, so the mold stays down while the glass
# is pulled out.
FOOT_WIDTH = 15.0      # how far it sticks out past the body
FOOT_THICKNESS = 8.0
VENT_DIAMETER = 3.2    # air vent through the base; 0 to omit

# --- Pattern --------------------------------------------------------------------
POINTS_PER_ROW = 16
# Height of each diamond divided by its width, halfway up the cavity. The actual
# value is adjusted slightly so whole rows fit the cavity.
DIAMOND_ASPECT = 1.3
# How far each tip stands in from the wall, as a fraction of its diamond's width.
POINT_DEPTH = 0.6
# How far each row is turned from the row below, as a fraction of the spacing
# between points. 0.5 is the classic upright diamond; moving away from 0.5 leans
# the diamonds into a spiral, one way below 0.5 and the other way above.
TWIST_PER_ROW = 0.35
# Where the tip sits between the middle of the diamond (0) and its top corner
# (1). Raising it steepens the underside, which reduces the overhang.
TIP_LIFT = 0.0
# Grid of square pyramids on the flat floor, as wide as the bottom row's diamonds
# and as deep in proportion. Not in the sleeved version.
FLOOR_SPIKES = False

# --- Stacked plates -------------------------------------------------------------
# Sheet you will have cut. 3.175 is 1/8", stocked by most laser services in
# aluminum and mild steel, and gives each point several steps; 6.35 halves the
# plate count but leaves the points blocky. Never use galvanized steel.
PLATE_THICKNESS = 3.175
# Solid plates under the cavity floor. The solid mold's base is as thick.
BASE_PLATES = 2
# Hole through the base plates at each floor spike, to tap for a cone-point set
# screw that stands up into the cavity.
FLOOR_SCREW_TAP_DRILL = 5.0   # tap M6
# Threaded rods clamp the stack and line the plates up. The holes are unevenly
# spaced so a plate only fits one way round and one way up.
BOLT_HOLE_DIAMETER = 6.4   # close fit for M6
BOLT_ANGLES_DEG = (0, 110, 240)
EDGE_MARGIN = 6.0          # metal between a bolt hole and the cavity or the rim
# Each plate gets a notch in its rim, a little further round than the plate
# below, so a correctly ordered stack shows one diagonal line of notches.
NOTCH_RADIUS = 1.5
NOTCH_START_DEG = 140
NOTCH_SPAN_DEG = 70        # must stay between two bolt holes

# --- Inserts in a sleeve, for CNC machining -------------------------------------
# Loose inserts the wall is divided into. POINTS_PER_ROW must be a multiple of
# this, so that they are all the same part.
INSERT_COUNT = 4
# Sleeve wall at the rim. The sleeve's outside is straight, so its wall is
# thicker lower down. The rest of SOLID_WALL is the thickness of the inserts.
SLEEVE_RIM_WALL = 4.0
# For the sleeve made as two halves: bolts through the split, in a flange down
# each side of the bore, at these fractions of the mold's height. A dowel pin
# sits between them on each side. The inserts' seams don't line up with the split.
SLEEVE_BOLT_HOLE_DIAMETER = 5.2   # close fit for M5
SLEEVE_BOLT_HEIGHTS = (0.2, 0.85)
SLEEVE_DOWEL_DIAMETER = 4.0
SLEEVE_DOWEL_DEPTH = 8.0          # into each half
# Size of the step in each seam, halfway through the insert's wall. On one side
# of an insert it is a lip, on the other a matching rebate. Its faces run along
# and across the directions the two inserts pull off in, so it never binds, and
# the cutter that does the points can cut it.
SEAM_STEP = 2.5
# How far the inserts stand clear of the sleeve's floor when seated, so that the
# taper locates them and not the floor. It also absorbs error in the diameters.
INSERT_FLOOR_GAP = 1.5
FLOOR_DISH = 2.5       # how deep the sleeve's floor is dished at the middle
# Directions the cutter comes at an insert from, each as (turn, tip) in degrees.
# Turn is to either side of square-on to the insert's inside face, about the
# mold's axis; more turns reach further behind the points. Tip is down toward
# the floor. Each direction is another index of a rotary axis or another tilted
# setup.
INSERT_TOOL_DIRECTIONS_DEG = ((0, 0), (-40, 0), (40, 0))
# On the inserts each point is a separate flat-sided boss standing on the smooth
# wall, not a facet of a wall made entirely of triangles. Shops reject the
# all-triangle form as an unmeasurable mesh. A strip of bare wall is left round
# every point, this share of the diamond's width, which is also where the cutter
# runs; and the tip is cut off flat, this share of the way down, so it doesn't
# fold over.
POINT_GAP = 0.15
POINT_TIP_FLAT = 0.1

# --- Ring inserts ---------------------------------------------------------------
# A second set of inserts for the same sleeve: V-shaped rings round the cavity,
# carrying on round the bowl as circles on the bottom.
RING_PITCH = 12.0      # spacing of the rings up the wall, adjusted to fit a whole number
RING_DEPTH = 5.0       # how far each ring stands in from the wall
RING_CREST = 1.0       # flat along the top of each ring, so it doesn't chip
# Rings face the cutter all the way round, so square-on does the wall. The
# second direction, tipped down, is for the rings on the bottom of the bowl.
RING_TOOL_DIRECTIONS_DEG = ((0, 0), (0, 50))

# --- Spiral rib inserts ---------------------------------------------------------
# V-shaped ribs that wind up the wall and in across the bowl.
SPIRAL_RIBS = 16           # must be a multiple of INSERT_COUNT
SPIRAL_TURN_DEG = 120.0    # how far each rib turns about the axis from floor to rim
SPIRAL_DEPTH = 0.35        # how far a rib stands in, as a fraction of the rib spacing
SPIRAL_TOOL_DIRECTIONS_DEG = ((0, 0), (0, 50))

# --- Hobnail inserts ------------------------------------------------------------
# Round pockets in the wall, in staggered rows. Blown into, each raises a bead.
HOBNAIL_PER_ROW = 16       # must be a multiple of INSERT_COUNT
HOBNAIL_FILL = 0.8         # pocket width as a share of the spacing between pockets
# Pocket depth as a fraction of its radius. Up to about 0.4 an insert still pulls
# straight off the beads and is cut square-on; deeper pockets near the seams hook
# behind the beads, and need the cutter turned to each side.
HOBNAIL_DEPTH = 0.35
# The staggered rows put a pocket on every seam between inserts. True cuts those
# half into each insert, so the pattern runs unbroken round the glass, but each
# insert then has half-pockets running out to a sharp edge down both sides, and
# the two halves of a bead only line up as well as the inserts seat. False
# leaves those pockets out, which gives a plain stripe at each seam instead.
HOBNAIL_SPLIT_ON_SEAMS = True
HOBNAIL_TOOL_DIRECTIONS_DEG = ((0, 0), (0, 50))

# --- Sparse spike inserts -------------------------------------------------------
# A few tall cones standing square off the wall, in staggered rows.
SPIKES_PER_ROW = 8         # must be a multiple of INSERT_COUNT
SPIKE_ROW_SPACING = 18.0   # between rows, measured up the wall
SPIKE_HEIGHT = 7.0
SPIKE_BASE_DIAMETER = 7.0
SPIKE_TIP_DIAMETER = 0.6   # a small flat so the tip doesn't fold over
SPIKE_TOOL_DIRECTIONS_DEG = ((0, 0), (-40, 0), (40, 0), (0, 50))
# Holes in the underside of the sleeve for the screws that hold the foot plate.
FOOT_TAP_DRILL = 4.2       # tap M5
FOOT_TAP_DEPTH = 10.0

# --- Rings for CNC machining ----------------------------------------------------
# Used only when the points don't overhang. The pyramids are finished with a
# ball end mill working down from the top of each ring. The creases between pyramids come out rounded to the cutter's
# radius, which the glass never touches. A smaller cutter leaves crisper creases
# but reaches less far, so it needs more rings, and every ring is another part
# and another setup: this is the main cost control. 12 gives 3 rings, 6 gives 5.
CNC_TOOL_DIAMETER = 12.0
# Deepest a cutter may reach, in cutter diameters. Around 8 is a long-reach
# cutter that still cuts well; much more chatters and gets expensive.
CNC_MAX_REACH = 8.0
# Rods run through the rim wall of every ring to clamp them and line them up.
# They have to fit inside SOLID_WALL, so they are smaller than the plate stack's.
RING_BOLT_HOLE_DIAMETER = 5.2   # close fit for M5

# Density in g/cm^3 and specific heat in J/(g K), for the weight and heat
# capacity in the report. More heat capacity means the mold warms up more slowly
# over repeated dips.
MATERIALS = {"aluminum": (2.70, 0.90), "steel": (7.85, 0.49)}

OUT_DIR = Path(__file__).parent / "mold-designs"

BASE_THICKNESS = BASE_PLATES * PLATE_THICKNESS
CAVITY_DEPTH = MOLD_HEIGHT - BASE_THICKNESS
TOP_RADIUS = MOLD_DIAMETER / 2 - SOLID_WALL
CONE_SLOPE = (TOP_RADIUS - BOTTOM_RADIUS) / CAVITY_DEPTH
CONE_ANGLE_DEG = math.degrees(math.atan(CONE_SLOPE))
# The stack is built from whole plates, so it comes out within half a plate of
# MOLD_HEIGHT.
CAVITY_PLATES = round(CAVITY_DEPTH / PLATE_THICKNESS)
PLATE_COUNT = BASE_PLATES + CAVITY_PLATES
BODY_BOTTOM_RADIUS = BOTTOM_RADIUS + SOLID_WALL
INSERT_WALL = SOLID_WALL - SLEEVE_RIM_WALL
FOOT_RADIUS = BODY_BOTTOM_RADIUS + FOOT_WIDTH
FOOT_PLATES = max(1, round(FOOT_THICKNESS / PLATE_THICKNESS))
PITCH_DEG = 360 / POINTS_PER_ROW
FLOOR_EDGE = FLOOR_RADIUS if BOWL_HEIGHT > 0 else BOTTOM_RADIUS


def wall_samples():
    """The cavity wall in profile: distance along it, radius and height.

    Distance is measured up the wall from the edge of the floor. The samples run
    on straight down below the floor and up past the rim, so that rows of points
    can overhang both ends and be trimmed flat.
    """
    bowl_top = BOTTOM_RADIUS + BOWL_HEIGHT * CONE_SLOPE
    points = [(FLOOR_EDGE, -2 * MOLD_HEIGHT), (FLOOR_EDGE, 0.0)]
    if BOWL_HEIGHT > 0:
        # A quarter of an ellipse: level where it leaves the floor, upright where
        # it meets the wall.
        for a in np.linspace(0, math.pi / 2, 200)[1:]:
            points.append((
                FLOOR_EDGE + (bowl_top - FLOOR_EDGE) * math.sin(a),
                BOWL_HEIGHT * (1 - math.cos(a)),
            ))
    points.append((BOTTOM_RADIUS + 3 * MOLD_HEIGHT * CONE_SLOPE, 3.0 * MOLD_HEIGHT))
    radius, height = np.array(points).T
    along = np.concatenate([[0], np.cumsum(np.hypot(np.diff(radius), np.diff(height)))])
    return along - along[1], radius, height


WALL_ALONG, WALL_RADIUS, WALL_HEIGHT = wall_samples()
# Distance up the wall from the floor to the rim.
WALL_LENGTH = float(np.interp(CAVITY_DEPTH, WALL_HEIGHT[1:], WALL_ALONG[1:]))
# Rows are evenly spaced up the wall, as near to DIAMOND_ASPECT as a whole number
# allows, taking the diamond width halfway up the straight part.
ROWS = max(1, round(
    WALL_LENGTH
    / (DIAMOND_ASPECT / 2 * (BOTTOM_RADIUS + BOWL_HEIGHT * CONE_SLOPE + TOP_RADIUS)
       * math.sin(math.pi / POINTS_PER_ROW))
))
ROW_PITCH = WALL_LENGTH / ROWS


# --- Diamond pyramids -----------------------------------------------------------


def wall_at(along):
    """Radius and height of the wall at a distance up it from the floor."""
    return (
        float(np.interp(along, WALL_ALONG, WALL_RADIUS)),
        float(np.interp(along, WALL_ALONG, WALL_HEIGHT)),
    )


def row_radius(row):
    """Wall radius at a row's widest corners. Row 0 sits at the edge of the floor."""
    return wall_at(row * ROW_PITCH)[0]


def row_z(row):
    return wall_at(row * ROW_PITCH)[1]


def diamond_width(row):
    return 2 * row_radius(row) * math.sin(math.pi / POINTS_PER_ROW)


def point_depth(row):
    return POINT_DEPTH * diamond_width(row)


def wall_point(radius, angle_deg, z):
    a = math.radians(angle_deg)
    return Vector(radius * math.cos(a), radius * math.sin(a), z)


def pyramid(row, i):
    """Corners of one pyramid: its tip, then the diamond's left, bottom, right, top.

    The side corners sit on this row's ring and the bottom and top corners on the
    rings of the rows below and above, where they are the side corners of those
    rows' diamonds, so the diamonds tile the wall with no gaps. The twist shifts
    the bottom and top corners sideways, which leans the diamond.
    """
    center = (i + row * TWIST_PER_ROW) * PITCH_DEG
    lean = (TWIST_PER_ROW - 0.5) * PITCH_DEG
    # The tip stands square off the wall, which on the bowl means partly upward.
    along = (row + TIP_LIFT) * ROW_PITCH
    (r0, z0), (r1, z1) = wall_at(along - 0.5), wall_at(along + 0.5)
    slope = math.hypot(r1 - r0, z1 - z0)
    wall_r, wall_z = wall_at(along)
    tip_r = wall_r - (z1 - z0) / slope * point_depth(row)
    tip_z = wall_z + (r1 - r0) / slope * point_depth(row)
    if tip_r < 2:
        raise ValueError("The points meet in the middle of the cavity. Lower POINT_DEPTH.")
    return (
        wall_point(tip_r, center, tip_z),
        wall_point(row_radius(row), center - PITCH_DEG / 2, row_z(row)),
        wall_point(row_radius(row - 1), center - lean, row_z(row - 1)),
        wall_point(row_radius(row), center + PITCH_DEG / 2, row_z(row)),
        wall_point(row_radius(row + 1), center + lean, row_z(row + 1)),
    )


def underside_draft():
    """Least lean from vertical, in degrees, of any pyramid's two lower faces.

    Negative means the undersides overhang.
    """
    drafts = []
    for row in range(ROWS + 1):
        tip, left, bottom, right, top = pyramid(row, 0)
        for a, b in ((left, bottom), (bottom, right)):
            normal = (a - tip).cross(b - tip).normalized()
            # Point the normal out of the metal, into the cavity: toward the axis.
            middle = (tip + a + b) / 3
            if normal.dot(Vector(middle.X, middle.Y, 0)) > 0:
                normal = -normal
            drafts.append(math.degrees(math.asin(normal.Z)))
    return min(drafts)


def floor_spikes():
    """Tip and four base corners of each floor spike, on a square grid.

    The grid straddles the axes, so the vent sits in the crease at the middle.
    """
    if not FLOOR_SPIKES:
        return []
    pitch = diamond_width(0)
    height = POINT_DEPTH * pitch
    reach = math.ceil(FLOOR_EDGE / pitch)
    spikes = []
    for i in range(-reach, reach):
        for j in range(-reach, reach):
            x, y = (i + 0.5) * pitch, (j + 0.5) * pitch
            # Keep to the clear floor inside the bottom row's tips. Spikes
            # further out would tangle with the wall's points, where no cutter
            # could separate them.
            clear_r = FLOOR_EDGE - point_depth(0) + pitch / 4
            if math.hypot(abs(x) + pitch / 2, abs(y) + pitch / 2) > clear_r:
                continue
            corners = [
                Vector(x + dx * pitch / 2, y + dy * pitch / 2, 0)
                for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))
            ]
            spikes.append((Vector(x, y, height), corners))
    return spikes


def build_cavity(spikes=()):
    """The cavity as one solid, its wall made entirely of pyramid faces.

    Any floor spikes given are left standing in it.
    """
    # Rows run past the floor and the rim, and are trimmed flat afterwards.
    first, last = -1, ROWS + 1
    below = Vector(0, 0, row_z(first - 1) - 5)
    above = Vector(0, 0, row_z(last + 1) + 5)
    triangles = []
    for row in range(first, last + 1):
        for i in range(POINTS_PER_ROW):
            tip, left, bottom, right, top = pyramid(row, i)
            triangles += [
                (tip, left, bottom), (tip, bottom, right),
                (tip, right, top), (tip, top, left),
            ]
            # Close the ends of the tube with fans to a point on the axis.
            if row == first:
                triangles += [(below, bottom, left), (below, right, bottom)]
            if row == last:
                triangles += [(above, top, right), (above, left, top)]
    tube = Solid(Shell([Face(Wire.make_polygon(t, close=True)) for t in triangles]))
    # Trim slightly past the top so the cut goes cleanly through the mold's top face.
    cavity = tube & Cylinder(
        2 * TOP_RADIUS, CAVITY_DEPTH + 2, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    for tip, corners in spikes:
        # Carry the faces a little below the floor so the cut is clean.
        sunk = [c + (c - tip) * 0.1 for c in corners]
        faces = [(tip, sunk[k], sunk[(k + 1) % 4]) for k in range(4)] + [sunk[::-1]]
        cavity -= Solid(Shell([Face(Wire.make_polygon(f, close=True)) for f in faces]))
    return cavity


# --- Solid mold -----------------------------------------------------------------


def body_radius(z):
    """Outside radius of the tapered body at a height above the cavity floor."""
    taper = (MOLD_DIAMETER / 2 - BODY_BOTTOM_RADIUS) / MOLD_HEIGHT
    return BODY_BOTTOM_RADIUS + (z + BASE_THICKNESS) * taper


def build_solid(cavity):
    low = (Align.CENTER, Align.CENTER, Align.MIN)
    mold = Cone(BODY_BOTTOM_RADIUS, MOLD_DIAMETER / 2, MOLD_HEIGHT, align=low)
    mold += Cylinder(FOOT_RADIUS, FOOT_THICKNESS, align=low)
    mold = Pos(0, 0, -BASE_THICKNESS) * mold
    mold -= cavity
    if VENT_DIAMETER > 0:
        mold -= Pos(0, 0, -BASE_THICKNESS - 1) * Cylinder(
            VENT_DIAMETER / 2, BASE_THICKNESS + 2, align=low
        )
    return mold.solid()


# --- Inserts in a sleeve, for CNC machining -------------------------------------


def seat_radius(z):
    """Radius of the tapered seat between the inserts and the sleeve."""
    return BOTTOM_RADIUS + INSERT_WALL + z * CONE_SLOPE


def build_insert(cavity, bosses=()):
    """The insert on the +X side. The others are the same part, turned.

    `bosses` are solids to add standing on the wall.
    """
    if INSERT_WALL < 3:
        raise ValueError("The inserts are under 3 mm thick. Raise SOLID_WALL.")
    low = (Align.CENTER, Align.CENTER, Align.MIN)
    height = CAVITY_DEPTH - INSERT_FLOOR_GAP
    shell = Pos(0, 0, INSERT_FLOOR_GAP) * Cone(
        seat_radius(INSERT_FLOOR_GAP), seat_radius(CAVITY_DEPTH), height, align=low
    )
    shell -= cavity
    if bosses:
        shell += list(bosses)
        # Bosses at the floor and the rim stick out past the ends; trim them off.
        shell &= Pos(0, 0, INSERT_FLOOR_GAP) * Cylinder(MOLD_DIAMETER, height, align=low)
    insert = shell & build_sector()
    if len(insert.solids()) != 1:
        raise ValueError(f"The insert came out in {len(insert.solids())} pieces.")
    if not insert.is_valid:
        raise ValueError("The insert came out as a faulty solid.")
    # A real misfit, or a cut gone wrong, shows up as a percent or so. Curved
    # faces alone leave the volumes a few parts in a hundred thousand apart.
    if abs(INSERT_COUNT * insert.volume - shell.volume) > 5e-4 * shell.volume:
        raise ValueError("The inserts don't fit together into a full ring.")
    return insert.solid()


def build_sector():
    """The slice of the mold that one insert takes up, as a solid with flat sides.

    The outline is the same shape at every height, only wider toward the rim, so
    each side between the bottom outline and the top one is a flat face. A shop
    can measure flat faces; a blended surface through the same points it can't.
    """
    bottom = [Vector(p.X, p.Y, INSERT_FLOOR_GAP) for p in sector_outline(INSERT_FLOOR_GAP)]
    top = [Vector(p.X, p.Y, CAVITY_DEPTH) for p in sector_outline(CAVITY_DEPTH)]
    outlines = [bottom[::-1], top]
    for k in range(len(bottom)):
        n = (k + 1) % len(bottom)
        outlines.append([bottom[k], bottom[n], top[n], top[k]])
    return Solid(Shell([Face(Wire.make_polygon(o, close=True)) for o in outlines]))


def sector_outline(z):
    """Outline, seen from above, of the slice of the mold that one insert takes up.

    It is a wedge from the axis with a step in each side, halfway through the
    insert's wall. The step on the +seam runs along the direction the neighbor
    there pulls off in, and reaches over it as a lip. The step on the -seam is the
    same one seen from the other side: a rebate that the neighbor's lip fills.
    """
    half = math.pi / INSERT_COUNT
    step_r = seat_radius(z) - INSERT_WALL / 2
    far = 3 * MOLD_DIAMETER
    plus = Vector(math.cos(half), math.sin(half))
    minus = Vector(math.cos(half), -math.sin(half))
    lip = Vector(math.cos(2 * half), math.sin(2 * half)) * SEAM_STEP
    rebate = Vector(SEAM_STEP, 0)
    return [
        Vector(0, 0),
        minus * step_r,
        minus * step_r + rebate,
        minus * far + rebate,
        plus * far + lip,
        plus * step_r + lip,
        plus * step_r,
    ]


def sleeve_block(split):
    """Half-widths of the sleeve's block, and where its bolts sit if it is split."""
    rim_r = seat_radius(CAVITY_DEPTH) + SLEEVE_RIM_WALL
    if not split:
        return rim_r, rim_r, None
    # A flange down each side of the bore carries the bolts.
    bolt_x = seat_radius(CAVITY_DEPTH) + 3 + SLEEVE_BOLT_HOLE_DIAMETER / 2
    return bolt_x + SLEEVE_BOLT_HOLE_DIAMETER / 2 + 4, rim_r, bolt_x


def foot_screws(split):
    """Where the foot plate's screws go into the underside of the sleeve."""
    half_x, half_y, bolt_x = sleeve_block(split)
    if split:
        return [(x, y) for x in (-bolt_x, bolt_x) for y in (-half_y / 2, half_y / 2)]
    # In the corners of the block, where it is thickest.
    inset = half_x - 10
    return [(x, y) for x in (-inset, inset) for y in (-inset, inset)]


def build_point_bosses():
    """One solid per pineapple point, standing on the bare wall of an insert.

    Each is the point's pyramid with its tip cut off flat and its base carried a
    little way into the wall, so its sides are four flat faces that meet the
    smooth wall in a clean edge.
    """
    bosses = []
    for row in range(ROWS + 1):
        tip, *corners = (np.array(tuple(v)) for v in pyramid(row, 0))
        middle = sum(corners) / 4
        axis = (middle - tip) / np.linalg.norm(middle - tip)
        depth = (middle - tip) @ axis
        feet, crown = [], []
        for corner in corners:
            # Pull the corner in to leave the gap, then run on down the same edge
            # of the pyramid until it is buried in the wall.
            edge = (middle + (1 - POINT_GAP) * (corner - middle) - tip) * 1.15
            feet.append(Vector(*(tip + edge)))
            # Where the same edge crosses the flat that cuts off the tip.
            crown.append(Vector(*(tip + edge * POINT_TIP_FLAT * depth / (edge @ axis))))
        outlines = [crown[::-1], feet[:3], [feet[0], feet[2], feet[3]]]
        for k in range(4):
            n = (k + 1) % 4
            outlines.append([crown[k], crown[n], feet[n], feet[k]])
        boss = Solid(Shell([Face(Wire.make_polygon(o, close=True)) for o in outlines]))
        if not boss.is_valid or boss.volume <= 0:
            raise ValueError(f"The point for row {row} came out as a faulty solid.")
        bosses += [Rot(0, 0, i * PITCH_DEG) * boss for i in range(POINTS_PER_ROW)]
    return bosses


def build_sleeve(split):
    """The sleeve's parts: plain block outside, tapered bore, dished and vented floor.

    In one piece the bore is milled down from the top. Split, it is two blocks
    with half the bore in each, bolted and doweled together.
    """
    low = (Align.CENTER, Align.CENTER, Align.MIN)
    half_x, half_y, bolt_x = sleeve_block(split)
    sleeve = Pos(0, 0, -BASE_THICKNESS) * Box(2 * half_x, 2 * half_y, MOLD_HEIGHT, align=low)
    sleeve -= Cone(seat_radius(0), seat_radius(CAVITY_DEPTH + 2), CAVITY_DEPTH + 2, align=low)
    # The dish is the cap of a sphere as wide as the flat floor.
    dish_r = (FLOOR_EDGE**2 + FLOOR_DISH**2) / (2 * FLOOR_DISH)
    below_floor = Pos(0, 0, -FLOOR_DISH) * Cylinder(FLOOR_EDGE, FLOOR_DISH, align=low)
    sleeve -= (Pos(0, 0, dish_r - FLOOR_DISH) * Sphere(dish_r)) & below_floor
    if VENT_DIAMETER > 0:
        sleeve -= Pos(0, 0, -BASE_THICKNESS - 1) * Cylinder(
            VENT_DIAMETER / 2, BASE_THICKNESS + 2, align=low
        )
    for x, y in foot_screws(split):
        sleeve -= Pos(x, y, -BASE_THICKNESS - 1) * Cylinder(
            FOOT_TAP_DRILL / 2, FOOT_TAP_DEPTH + 1, align=low
        )
    if not split:
        return [sleeve.solid()]

    across = Rot(90, 0, 0)   # along Y, through the split
    for side in (-1, 1):
        for fraction in SLEEVE_BOLT_HEIGHTS:
            z = fraction * MOLD_HEIGHT - BASE_THICKNESS
            sleeve -= Pos(side * bolt_x, 0, z) * across * Cylinder(
                SLEEVE_BOLT_HOLE_DIAMETER / 2, 2 * half_y + 2
            )
        sleeve -= Pos(side * bolt_x, 0, MOLD_HEIGHT / 2 - BASE_THICKNESS) * across * Cylinder(
            SLEEVE_DOWEL_DIAMETER / 2, 2 * SLEEVE_DOWEL_DEPTH
        )
    halves = []
    for side in (-1, 1):
        half = sleeve & Pos(0, side * half_y, 0) * Box(4 * half_x, 2 * half_y, 4 * MOLD_HEIGHT)
        if len(half.solids()) != 1:
            raise ValueError(f"A sleeve half came out in {len(half.solids())} pieces.")
        halves.append(half.solid())
    return halves


def build_foot_plate(split):
    """Plate that screws under the sleeve and sticks out to stand on."""
    half_x, half_y, bolt_x = sleeve_block(split)
    face = Rectangle(2 * (half_x + FOOT_WIDTH), 2 * (half_y + FOOT_WIDTH))
    for x, y in foot_screws(split):
        face -= Pos(x, y) * Circle(RING_BOLT_HOLE_DIAMETER / 2 + 0.15)
    if VENT_DIAMETER > 0:
        face -= Circle(VENT_DIAMETER / 2)
    return face.face()


def ray_hits(origin, direction, triangles):
    """Whether a ray meets any of the triangles (Moller-Trumbore)."""
    corner = triangles[:, 0]
    edge1, edge2 = triangles[:, 1] - corner, triangles[:, 2] - corner
    h = np.cross(direction, edge2)
    det = (edge1 * h).sum(1)
    facing = np.abs(det) > 1e-12
    inv = np.where(facing, 1 / np.where(facing, det, 1), 0)
    s = origin - corner
    u = inv * (s * h).sum(1)
    q = np.cross(s, edge1)
    v = inv * (q @ direction)
    t = inv * (edge2 * q).sum(1)
    return bool(np.any(facing & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6)))


def point_facets():
    """The pineapple wall as triangles, with normals pointing into the cavity."""
    triangles = []
    for row in range(-1, ROWS + 2):
        for i in range(POINTS_PER_ROW):
            tip, left, bottom, right, top = pyramid(row, i)
            triangles += [(tip, left, bottom), (tip, bottom, right),
                          (tip, right, top), (tip, top, left)]
    triangles = np.array([[tuple(v) for v in t] for t in triangles])
    centers = triangles.mean(1)
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    # Out of the metal here is toward the axis.
    normals[(normals[:, :2] * centers[:, :2]).sum(1) > 0] *= -1
    return triangles, normals


def ring_outline():
    """The ring inserts' wall in profile, as (radius, height) points up the wall.

    A zigzag: down in a crease on the wall, out to a flat-topped crest standing
    square off it, and back. It overruns the floor and the rim by a ring each way.
    """
    count = max(1, round(WALL_LENGTH / RING_PITCH))
    pitch = WALL_LENGTH / count
    outline = []
    for k in range(-1, count + 1):
        outline.append(wall_at(k * pitch))
        for along in ((k + 0.5) * pitch - RING_CREST / 2, (k + 0.5) * pitch + RING_CREST / 2):
            (r0, z0), (r1, z1) = wall_at(along - 0.5), wall_at(along + 0.5)
            slope = math.hypot(r1 - r0, z1 - z0)
            r, z = wall_at(along)
            outline.append((r - (z1 - z0) / slope * RING_DEPTH, z + (r1 - r0) / slope * RING_DEPTH))
    outline.append(wall_at((count + 1) * pitch))
    if min(r for r, _ in outline) < 2:
        raise ValueError("The rings meet in the middle of the cavity. Lower RING_DEPTH.")
    return outline


def build_ring_cavity():
    """The cavity of the ring inserts: the ring profile turned about the axis."""
    return turned_cavity(ring_outline())


def ring_facets(steps=72):
    """The ring wall as triangles, with normals pointing into the cavity."""
    outline = ring_outline()
    angles = np.linspace(0, 2 * math.pi, steps + 1)
    triangles, normals = [], []
    for (r0, z0), (r1, z1) in zip(outline, outline[1:]):
        slope = math.hypot(r1 - r0, z1 - z0)
        # Square off the wall, on the side of the axis.
        out_r, out_z = -(z1 - z0) / slope, (r1 - r0) / slope
        for a0, a1 in zip(angles, angles[1:]):
            corners = [
                (r * math.cos(a), r * math.sin(a), z)
                for r, z, a in ((r0, z0, a0), (r1, z1, a0), (r1, z1, a1), (r0, z0, a1))
            ]
            mid = (a0 + a1) / 2
            for triangle in ((corners[0], corners[1], corners[2]), (corners[0], corners[2], corners[3])):
                triangles.append(triangle)
                normals.append((out_r * math.cos(mid), out_r * math.sin(mid), out_z))
    return np.array(triangles), np.array(normals)


def turned_cavity(outline):
    """A cavity whose wall is the given (radius, height) outline turned about the axis."""
    section = [(0, outline[0][1] - 5)] + list(outline) + [(0, outline[-1][1] + 5)]
    turned = revolve(Plane.XZ * Polygon(*section, align=None), Axis.Z)
    return turned & Cylinder(
        2 * TOP_RADIUS, CAVITY_DEPTH + 2, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )


def wall_square(along):
    """Unit direction square off the wall into the cavity, as (radial, upward)."""
    (r0, z0), (r1, z1) = wall_at(along - 0.5), wall_at(along + 0.5)
    slope = math.hypot(r1 - r0, z1 - z0)
    return -(z1 - z0) / slope, (r1 - r0) / slope


def wall_spot(along, angle_deg):
    """A point on the plain wall, and the direction square off it into the cavity."""
    r, z = wall_at(along)
    out_r, out_z = wall_square(along)
    a = math.radians(angle_deg)
    return (
        np.array([r * math.cos(a), r * math.sin(a), z]),
        np.array([out_r * math.cos(a), out_r * math.sin(a), out_z]),
    )


def plain_cavity():
    """The cavity with a bare wall, for patterns that are cut into it or stand on it.

    Drawn from the true curves, not from points along them, so the wall is one
    smooth cone and the bowl one smooth surface in the files a shop receives.
    """
    low, high = -6.0, CAVITY_DEPTH + 6.0
    bowl_top = BOTTOM_RADIUS + BOWL_HEIGHT * CONE_SLOPE
    outline = Polyline((0, low), (FLOOR_EDGE, low), (FLOOR_EDGE, 0))
    if BOWL_HEIGHT > 0:
        # The same quarter-ellipse that wall_samples() steps along.
        outline += EllipticalCenterArc(
            (FLOOR_EDGE, BOWL_HEIGHT), bowl_top - FLOOR_EDGE, BOWL_HEIGHT,
            start_angle=270, arc_size=90,
        )
    outline += Polyline(
        (bowl_top, BOWL_HEIGHT), (BOTTOM_RADIUS + high * CONE_SLOPE, high), (0, high), (0, low)
    )
    turned = revolve(Plane.XZ * make_face(outline), Axis.Z)
    return turned & Cylinder(
        2 * TOP_RADIUS, CAVITY_DEPTH + 2, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )


def perpendiculars(axis):
    """Two unit vectors square to `axis` and to each other."""
    helper = np.array([0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    first = np.cross(axis, helper)
    first /= np.linalg.norm(first)
    return first, np.cross(axis, first)


# --- Spiral rib inserts ---------------------------------------------------------


def spiral_loops():
    """Loops of points round the spiral-rib wall, from below the floor to past the rim.

    Each loop zigzags between creases on the wall and rib crests standing square
    off it, and each is turned a little further than the one below.
    """
    count = round(WALL_LENGTH / 5)
    pitch = 360 / SPIRAL_RIBS
    loops = []
    for k in range(-2, count + 3):
        along = k * WALL_LENGTH / count
        r, z = wall_at(along)
        out_r, out_z = wall_square(along)
        if k in (-2, count + 2):
            # The end loops are trimmed away, and have to lie flat to be capped.
            out_r, out_z = -1.0, 0.0
        depth = SPIRAL_DEPTH * 2 * r * math.sin(math.pi / SPIRAL_RIBS)
        turn = SPIRAL_TURN_DEG * along / WALL_LENGTH
        loop = []
        for i in range(SPIRAL_RIBS):
            loop.append(wall_point(r, turn + i * pitch, z))
            loop.append(wall_point(r + out_r * depth, turn + (i + 0.5) * pitch, z + out_z * depth))
        loops.append(loop)
    return loops


def loop_triangles(loops):
    """Triangles joining each loop to the next, wound to face out of the cavity."""
    triangles = []
    for lower, upper in zip(loops, loops[1:]):
        for k in range(len(lower)):
            a, b = lower[k], lower[(k + 1) % len(lower)]
            c, d = upper[(k + 1) % len(upper)], upper[k]
            triangles += [(a, b, c), (a, c, d)]
    return triangles


def build_spiral_cavity():
    """The spiral cavity, with each rib flank one smooth surface through the loops."""
    wires = [Wire.make_polygon(loop, close=True) for loop in spiral_loops()]
    tube = Solid.make_loft(wires)
    return tube & Cylinder(
        2 * TOP_RADIUS, CAVITY_DEPTH + 2, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )


def spiral_facets():
    """The spiral-rib wall as triangles, with normals pointing into the cavity."""
    triangles = np.array([[tuple(v) for v in t] for t in loop_triangles(spiral_loops())])
    normals = -np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    return triangles, normals / np.linalg.norm(normals, axis=1)[:, None]


# --- Hobnail inserts ------------------------------------------------------------


def hobnail_pockets():
    """Each pocket as (spot on the wall, direction into the cavity, radius at the wall).

    The pockets shrink with the wall, so they stay the same share of their
    spacing, and the rows close up to match.
    """
    pockets = []
    row = 0
    along = math.pi * FLOOR_EDGE / HOBNAIL_PER_ROW
    while True:
        spacing = 2 * math.pi * wall_at(along)[0] / HOBNAIL_PER_ROW
        radius = HOBNAIL_FILL * spacing / 2
        if along + radius > WALL_LENGTH:
            return pockets
        # Leave out rows that would run off the bottom of the inserts.
        if wall_at(along - radius)[1] < INSERT_FLOOR_GAP + 0.5:
            along += 0.866 * spacing
            row += 1
            continue
        for i in range(HOBNAIL_PER_ROW):
            # Even rows sit either side of the seams between inserts. Odd rows
            # are staggered, which puts a pocket on every seam.
            angle = (i + 0.5 * ((row + 1) % 2)) * 360 / HOBNAIL_PER_ROW
            seam = 360 / INSERT_COUNT
            off_seam = math.radians(abs(angle % seam - seam / 2))
            on_seam = wall_at(along)[0] * math.sin(off_seam) < 1.15 * radius
            if on_seam and not HOBNAIL_SPLIT_ON_SEAMS:
                continue
            spot, inward = wall_spot(along, angle)
            pockets.append((spot, inward, radius))
        along += 0.866 * spacing
        row += 1


def pocket_ball(radius):
    """Radius of the ball that cuts a pocket, and how far its center sits inside the wall."""
    depth = HOBNAIL_DEPTH * radius
    ball = (radius**2 + depth**2) / (2 * depth)
    return ball, ball - depth


def build_hobnail_insert():
    """A bare insert with its pockets cut one at a time, each cut checked.

    Cutting a round pocket into the middle of the smooth wall sometimes silently
    does nothing. So each pocket is cut on its own, measured, and tried again a
    few hundredths of a millimetre deeper or shallower until it takes.
    """
    insert = build_insert(plain_cavity())
    half_sector = math.pi / INSERT_COUNT
    for spot, inward, radius in hobnail_pockets():
        # Only the pockets that reach this insert. One on a seam is cut half into
        # this insert and half into its neighbor.
        off_center = abs(math.atan2(spot[1], spot[0]))
        spread = math.asin(min(1.0, 1.2 * radius / math.hypot(spot[0], spot[1])))
        if off_center > half_sector + spread:
            continue
        whole = off_center < half_sector - spread
        ball, inset = pocket_ball(radius)
        depth = HOBNAIL_DEPTH * radius
        # The cutter is the part of the ball from well inside the cavity outward,
        # so that only its rounded end touches the wall. It faces along -X, which
        # keeps the ball's seam and poles out of the cut, and is then turned to
        # point out through the wall.
        start = 0.35 * radius - inset
        slab = Pos((start - ball - 1) / 2, 0, 0) * Box(start + ball + 1, 2 * ball + 2, 2 * ball + 2)
        cutter = Sphere(ball) & slab
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, inward[2]))))
        bearing = math.degrees(math.atan2(inward[1], inward[0]))
        turn = Rot(0, 0, bearing) * Rot(0, tilt - 90, 0)
        # What a pocket this size removes from a flat wall; a curved one loses more.
        expected = math.pi * depth**2 * (3 * ball - depth) / 3
        before = insert.volume
        for nudge in (0, 0.02, -0.02, 0.05, -0.05, 0.1, -0.1, 0.2):
            trial = insert - Pos(*(spot + inward * (inset + nudge))) * turn * cutter
            least = 0.7 if whole else 0.25
            if len(trial.solids()) == 1 and least * expected < before - trial.volume < 2 * expected:
                insert = trial
                break
        else:
            raise ValueError(f"The hobnail pocket {spot[2]:.0f} mm up could not be cut.")
    if not insert.is_valid:
        raise ValueError("The hobnail insert came out as a faulty solid.")
    return insert.solid()


def hobnail_facets(around=8, across=3):
    """The pockets as triangles, with normals pointing into the cavity."""
    triangles, normals = [], []
    for spot, inward, radius in hobnail_pockets():
        ball, inset = pocket_ball(radius)
        center = spot + inward * inset
        side_a, side_b = perpendiculars(inward)
        rim = math.asin(radius / ball)

        def on_ball(i, j):
            tilt, swing = rim * i / across, 2 * math.pi * j / around
            away = (-inward * math.cos(tilt)
                    + (side_a * math.cos(swing) + side_b * math.sin(swing)) * math.sin(tilt))
            return center + ball * away

        for i in range(across):
            for j in range(around):
                quad = [on_ball(i, j), on_ball(i + 1, j), on_ball(i + 1, j + 1), on_ball(i, j + 1)]
                for triangle in ((quad[0], quad[1], quad[2]), (quad[0], quad[2], quad[3])):
                    # At the bottom of the pocket the quad closes up to one triangle.
                    if np.allclose(triangle[0], triangle[2]):
                        continue
                    triangles.append(triangle)
                    middle = sum(triangle) / 3
                    normals.append((center - middle) / np.linalg.norm(center - middle))
    return np.array(triangles), np.array(normals)


# --- Sparse spike inserts -------------------------------------------------------


def spike_spots():
    """Where each spike stands: (spot on the wall, direction into the cavity)."""
    rows = max(1, round(WALL_LENGTH / SPIKE_ROW_SPACING))
    spots = []
    for row in range(rows):
        along = (row + 0.5) * WALL_LENGTH / rows
        for i in range(SPIKES_PER_ROW):
            # The quarter-step keeps every spike clear of the seams between
            # inserts, so none is split in two.
            around = i + 0.25 + 0.5 * (row % 2)
            spots.append(wall_spot(along, around * 360 / SPIKES_PER_ROW))
    return spots


def build_spikes():
    """One cone per spike, standing on the wall, to add to the bare inserts."""
    low = (Align.CENTER, Align.CENTER, Align.MIN)
    # The cone starts a little behind the wall, wider to match, so it joins cleanly.
    buried = 1.5
    flare = (SPIKE_BASE_DIAMETER - SPIKE_TIP_DIAMETER) / 2 / SPIKE_HEIGHT
    cone = Pos(0, 0, -buried) * Cone(
        SPIKE_BASE_DIAMETER / 2 + buried * flare, SPIKE_TIP_DIAMETER / 2,
        SPIKE_HEIGHT + buried, align=low,
    )
    cones = []
    for spot, inward in spike_spots():
        # Turn the cone from pointing up to pointing along `inward`.
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, inward[2]))))
        bearing = math.degrees(math.atan2(inward[1], inward[0]))
        # The quarter turn about its own axis first puts the cone's seam on its
        # side. With the seam up the wall, the join to the wall comes out wrong.
        cones.append(Pos(*spot) * Rot(0, 0, bearing) * Rot(0, tilt, 0) * Rot(0, 0, 90) * cone)
    return cones


def spike_facets(around=12):
    """The spikes as triangles, with normals pointing into the cavity."""
    triangles, normals = [], []
    for spot, inward in spike_spots():
        side_a, side_b = perpendiculars(inward)
        tip = spot + inward * SPIKE_HEIGHT
        for j in range(around):
            a0, a1 = 2 * math.pi * j / around, 2 * math.pi * (j + 1) / around
            foot0 = spot + (side_a * math.cos(a0) + side_b * math.sin(a0)) * SPIKE_BASE_DIAMETER / 2
            foot1 = spot + (side_a * math.cos(a1) + side_b * math.sin(a1)) * SPIKE_BASE_DIAMETER / 2
            normal = np.cross(foot1 - foot0, tip - foot0)
            normal /= np.linalg.norm(normal)
            # Away from the spike's own axis.
            if normal @ ((foot0 + foot1) / 2 - spot) < 0:
                normal = -normal
            triangles.append((foot0, foot1, tip))
            normals.append(normal)
    return np.array(triangles), np.array(normals)


def sideways_reach(triangles, normals, tool_directions):
    """Fraction of an insert's patterned surface a cutter can see from the directions.

    A spot counts when, from at least one of the directions, the cutter meets it
    at 5 degrees or more and nothing else on the same insert is in the way. This
    is line of sight only: it ignores the cutter's width, so creases still come
    out rounded.
    """
    centers = triangles.mean(1)
    areas = np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1
    ) / 2
    in_cavity = (centers[:, 2] > 0) & (centers[:, 2] < CAVITY_DEPTH)

    # Which insert each face is on. Insert 0 is centered on +X.
    sector = 360 / INSERT_COUNT
    bearing = np.degrees(np.arctan2(centers[:, 1], centers[:, 0]))
    owner = np.floor(((bearing + sector / 2) % 360) / sector).astype(int)
    directions = [(math.radians(a), math.radians(b)) for a, b in tool_directions]

    reached = 0.0
    for k in range(INSERT_COUNT):
        mine = owner == k
        insert = triangles[mine]
        for j in np.where(mine & in_cavity)[0]:
            # Test the middle of the face and a spot near each corner.
            spots = [centers[j]] + [0.8 * corner + 0.2 * centers[j] for corner in triangles[j]]
            for turn, tip_down in directions:
                # From the face toward the cutter: across the axis and out.
                a = math.radians(k * sector) + math.pi + turn
                toward_tool = np.array([
                    math.cos(a) * math.cos(tip_down),
                    math.sin(a) * math.cos(tip_down),
                    math.sin(tip_down),
                ])
                if normals[j] @ toward_tool < math.sin(math.radians(5)):
                    continue
                if not any(ray_hits(p + normals[j] * 1e-3, toward_tool, insert) for p in spots):
                    reached += areas[j]
                    break
    return reached / areas[in_cavity].sum()


# --- Rings for CNC machining ----------------------------------------------------


def ring_rod_radii():
    """Closest and furthest a straight rod can sit from the axis inside the wall."""
    clearance = 2 + RING_BOLT_HOLE_DIAMETER / 2
    return TOP_RADIUS + clearance, BODY_BOTTOM_RADIUS - clearance


def ring_obstacle(draft):
    """Why the mold can't be made as machined rings, or None if it can."""
    if draft < 0:
        return "a mill working from above can't reach under the points"
    inner, outer = ring_rod_radii()
    if inner > outer:
        return "the tapered wall leaves no straight path for the rods"
    return None


def build_rings(solid):
    """The solid mold cut into equal rings no taller than the cutter can reach."""
    hole_r = sum(ring_rod_radii()) / 2
    drilled = solid
    for angle in BOLT_ANGLES_DEG:
        drilled -= Rot(0, 0, angle) * Pos(hole_r, 0, -BASE_THICKNESS - 1) * Cylinder(
            RING_BOLT_HOLE_DIAMETER / 2, MOLD_HEIGHT + 2,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

    count = math.ceil(MOLD_HEIGHT / (CNC_TOOL_DIAMETER * CNC_MAX_REACH))
    height = MOLD_HEIGHT / count
    rings = []
    for i in range(count):
        slab = Pos(0, 0, -BASE_THICKNESS + i * height) * Cylinder(
            2 * FOOT_RADIUS, height, align=(Align.CENTER, Align.CENTER, Align.MIN)
        )
        ring = drilled & slab
        if len(ring.solids()) != 1:
            raise ValueError(f"Ring {i + 1} came out in {len(ring.solids())} pieces.")
        rings.append(ring.solid())
    return rings, height


# --- Stacked plates -------------------------------------------------------------


def cavity_openings(cavity):
    """Cavity cross-section at the middle of each cavity plate, bottom to top."""
    sheet = Circle(2 * TOP_RADIUS)
    return [
        (cavity & (Plane.XY.offset((i + 0.5) * PLATE_THICKNESS) * sheet)).face().moved(
            Pos(0, 0, -(i + 0.5) * PLATE_THICKNESS)
        )
        for i in range(CAVITY_PLATES)
    ]


def blank(index, bolt_circle_r):
    """Plate without its cavity: the body, lugs for the rods, and an ordering notch.

    The body follows the mold's taper, so lower plates are smaller. The rods run
    straight, outside the body, so every plate carries a lug reaching out to each
    one. The bottom plates are the foot.
    """
    if index < FOOT_PLATES:
        outer_r = FOOT_RADIUS
    else:
        outer_r = body_radius((index + 0.5) * PLATE_THICKNESS - BASE_THICKNESS)
    face = Circle(outer_r)
    lug_r = BOLT_HOLE_DIAMETER / 2 + EDGE_MARGIN
    lug = Pos(bolt_circle_r, 0) * Circle(lug_r)
    lug += Pos(bolt_circle_r / 2, 0) * Rectangle(bolt_circle_r, 2 * lug_r)
    for a in BOLT_ANGLES_DEG:
        face += Rot(0, 0, a) * lug
    for a in BOLT_ANGLES_DEG:
        face -= Rot(0, 0, a) * Pos(bolt_circle_r, 0) * Circle(BOLT_HOLE_DIAMETER / 2)
    notch_deg = NOTCH_START_DEG + index * NOTCH_SPAN_DEG / max(PLATE_COUNT - 1, 1)
    return face - Rot(0, 0, notch_deg) * Pos(outer_r, 0) * Circle(NOTCH_RADIUS)


def build_plates(cavity):
    """Plate outlines as Faces, bottom to top."""
    openings = cavity_openings(cavity)
    bolt_circle_r = TOP_RADIUS + EDGE_MARGIN + BOLT_HOLE_DIAMETER / 2

    plates = []
    for index in range(PLATE_COUNT):
        face = blank(index, bolt_circle_r)
        if index >= BASE_PLATES:
            face -= openings[index - BASE_PLATES]
        else:
            if VENT_DIAMETER > 0:
                face -= Circle(VENT_DIAMETER / 2)
            for tip, _ in floor_spikes():
                face -= Pos(tip.X, tip.Y) * Circle(FLOOR_SCREW_TAP_DRILL / 2)
        plates.append(face.face())
    return plates


# --- Output ---------------------------------------------------------------------


def write_dxf(face, path):
    dxf = ExportDXF(unit=Unit.MM)
    dxf.add_shape(face)
    dxf.write(path)


def weights(volume_mm3):
    return ", ".join(
        f"{m} {volume_mm3 * rho / 1e6:.1f} kg and {volume_mm3 * rho * heat / 1e3:.0f} J/K"
        for m, (rho, heat) in MATERIALS.items()
    )


def report(draft, solid, insert, reach, other_sets, sleeves, rings, ring_height, ring_problem,
           plates):
    stack_height = PLATE_COUNT * PLATE_THICKNESS

    def bottom_to_top(value):
        return f"{value(0):.1f} -> {value(ROWS):.1f} mm"

    print("pineapple")
    bowl = f", bowl {BOWL_HEIGHT:g} mm high" if BOWL_HEIGHT > 0 else ""
    print(f"  cavity:   {2 * FLOOR_EDGE:.1f} mm floor{bowl}, {2 * TOP_RADIUS:.1f} mm dia at the rim, "
          f"{CAVITY_DEPTH:.1f} mm deep, {CONE_ANGLE_DEG:.1f} deg wall")
    print(f"  diamonds: {ROWS} rows of {POINTS_PER_ROW}, {bottom_to_top(diamond_width)} wide, "
          f"{2 * ROW_PITCH:.1f} mm tall")
    print(f"  points:   {bottom_to_top(point_depth)} deep, leaving a "
          f"{bottom_to_top(lambda row: 2 * (row_radius(row) - point_depth(row)))} "
          "opening between tips")
    spikes = floor_spikes()
    if spikes:
        print(f"  floor:    {len(spikes)} spikes, {diamond_width(0):.1f} mm square, "
              f"{spikes[0][0].Z:.1f} mm tall")
    if draft < 0:
        print(f"  release:  undersides overhang {-draft:.0f} deg; relies on the glass "
              "touching only the tips")
    else:
        print(f"  release:  undersides lean back {draft:.0f} deg; a straight pull clears them")
    print(f"  twist:    {TWIST_PER_ROW * PITCH_DEG:.1f} deg per row, "
          f"{ROWS * TWIST_PER_ROW * PITCH_DEG:.0f} deg bottom to top")
    # What the solid costs to cast or print follows its metal volume.
    print(f"  body:     {2 * BODY_BOTTOM_RADIUS:.1f} -> {MOLD_DIAMETER:.1f} mm dia, "
          f"{MOLD_HEIGHT:.1f} mm tall, on a {2 * FOOT_RADIUS:.1f} x {FOOT_THICKNESS:g} mm foot")
    print(f"  solid:    {solid.volume / 1000:.0f} cm^3 ({weights(solid.volume)})  "
          f"(valid={solid.is_valid}, solids={len(solid.solids())})")
    block = insert.bounding_box().size
    seat_slip = 0.1 / (2 * CONE_SLOPE)
    print(f"  inserts:  {INSERT_COUNT} the same, {INSERT_WALL:g} mm thick behind the points, each "
          f"from {block.Y:.0f} x {block.X:.0f} x {block.Z:.0f} mm ({weights(insert.volume)} each)  "
          f"(valid={insert.is_valid})")
    print(f"            a cutter sees {reach:.1%} of the points from "
          f"{len(INSERT_TOOL_DIRECTIONS_DEG)} directions")
    if reach < 0.98:
        print("  WARNING:  parts of the points can't be reached; add directions to "
              "INSERT_TOOL_DIRECTIONS_DEG or lower POINT_DEPTH")
    for name, part, facts, part_reach, directions in other_sets:
        block = part.bounding_box().size
        print(f"  {name} inserts: {INSERT_COUNT} the same, {facts}, each from {block.Y:.0f} x "
              f"{block.X:.0f} x {block.Z:.0f} mm ({weights(part.volume)} each)  "
              f"(valid={part.is_valid})")
        print(f"            a cutter sees {part_reach:.1%} of the pattern from "
              f"{len(directions)} directions")
    print(f"  sleeve:   bore {2 * seat_radius(0):.1f} -> {2 * seat_radius(CAVITY_DEPTH):.1f} mm at "
          f"{CONE_ANGLE_DEG:.1f} deg a side, outside left as sawn")
    for split, parts in sleeves.items():
        block = parts[0].bounding_box().size
        foot = build_foot_plate(split).bounding_box().size
        stock = len(parts) * block.X * block.Y * block.Z / 1000
        how = (f"2 blocks of {block.X:.0f} x {block.Y:.0f} x {block.Z:.0f} mm, bore cut as troughs "
               f"{seat_radius(CAVITY_DEPTH):.0f} mm deep" if split else
               f"1 block of {block.X:.0f} x {block.Y:.0f} x {block.Z:.0f} mm, bore cut "
               f"{CAVITY_DEPTH + FLOOR_DISH:.0f} mm deep from the top")
        print(f"            {'halves' if split else 'solid'}: {how}")
        print(f"              {stock:.0f} cm^3 of stock, {weights(sum(part.volume for part in parts))}  "
              f"(valid={all(part.is_valid for part in parts)})")
        if split:
            print(f"              {2 * len(SLEEVE_BOLT_HEIGHTS)} x M5 bolts at least "
                  f"{2 * block.Y + 10:.0f} mm long, 2 x {SLEEVE_DOWEL_DIAMETER:g} mm dowels")
        print(f"              {foot.X:.0f} x {foot.Y:.0f} x {FOOT_THICKNESS:g} mm foot plate on "
              f"{len(foot_screws(split))} x M5 screws")
    print(f"  fit:      0.1 mm of error in a diameter moves the inserts {seat_slip:.1f} mm up or "
          f"down; they stand {INSERT_FLOOR_GAP:g} mm clear of the floor")
    if rings:
        print(f"  cnc rings: {len(rings)} x {ring_height:.1f} mm, for a {CNC_TOOL_DIAMETER:g} mm ball "
              f"end mill reaching {ring_height / CNC_TOOL_DIAMETER:.1f}x its diameter "
              f"(valid={all(r.is_valid for r in rings)})")
        print(f"            {len(BOLT_ANGLES_DEG)} x M5 rods at least {MOLD_HEIGHT + 20:.0f} mm long")
    else:
        print(f"  cnc rings: skipped; {ring_problem}")
    sizes = [p.bounding_box().size for p in plates]
    print(f"  plates:   {PLATE_COUNT} x {PLATE_THICKNESS:g} mm, up to "
          f"{max(max(b.X, b.Y) for b in sizes):.1f} mm across, {stack_height:.1f} mm tall "
          f"({weights(sum(p.area for p in plates) * PLATE_THICKNESS)})")
    # What the plates cost to cut follows the sheet they use (each is priced by
    # its bounding square), the length of cut and the number of pierces.
    sheet_m2 = sum(b.X * b.Y for b in sizes) / 1e6
    cut_m = sum(e.length for p in plates for e in p.edges()) / 1000
    pierces = sum(len(p.wires()) for p in plates)
    print(f"  cutting:  {sheet_m2:.2f} m^2 of sheet, {cut_m:.1f} m of cut, {pierces} pierces")
    print(f"  rods:     {len(BOLT_ANGLES_DEG)} x M6, at least {stack_height + 20:.0f} mm long")
    if spikes:
        print(f"            {len(spikes)} x M6 cone-point set screws for the floor, about "
              f"{BASE_THICKNESS + spikes[0][0].Z:.0f} mm long")


def main():
    draft = underside_draft()
    cavity = build_cavity(floor_spikes())
    solid = build_solid(cavity)
    # The floor belongs to the sleeve and the plates can't hold loose spikes, so
    # the inserts and the plates are cut from a cavity without floor spikes.
    bare = build_cavity() if FLOOR_SPIKES else cavity
    if POINTS_PER_ROW % INSERT_COUNT:
        raise ValueError("POINTS_PER_ROW must be a multiple of INSERT_COUNT.")
    insert = build_insert(plain_cavity(), bosses=build_point_bosses())
    for name, count in (("SPIRAL_RIBS", SPIRAL_RIBS), ("HOBNAIL_PER_ROW", HOBNAIL_PER_ROW),
                        ("SPIKES_PER_ROW", SPIKES_PER_ROW)):
        if count % INSERT_COUNT:
            raise ValueError(f"{name} must be a multiple of INSERT_COUNT.")
    ring_count = max(1, round(WALL_LENGTH / RING_PITCH))
    pockets = hobnail_pockets()
    beads = [2 * radius for _, _, radius in pockets]
    spikes = spike_spots()
    # Each other set: name, one insert, a description, the share of its pattern a
    # cutter reaches, and the directions that was worked out for.
    other_sets = [
        ("rings", build_insert(build_ring_cavity()),
         f"{ring_count} rings {WALL_LENGTH / ring_count:.1f} mm apart and {RING_DEPTH:g} mm deep",
         sideways_reach(*ring_facets(), RING_TOOL_DIRECTIONS_DEG), RING_TOOL_DIRECTIONS_DEG),
        ("spiral", build_insert(build_spiral_cavity()),
         f"{SPIRAL_RIBS} ribs turning {SPIRAL_TURN_DEG:g} deg, "
         f"{SPIRAL_DEPTH * 2 * TOP_RADIUS * math.sin(math.pi / SPIRAL_RIBS):.1f} mm deep at the rim",
         sideways_reach(*spiral_facets(), SPIRAL_TOOL_DIRECTIONS_DEG), SPIRAL_TOOL_DIRECTIONS_DEG),
        ("hobnail", build_hobnail_insert(),
         f"{len(pockets)} pockets {min(beads):.1f} -> {max(beads):.1f} mm across and "
         f"{HOBNAIL_DEPTH * min(beads) / 2:.1f} -> {HOBNAIL_DEPTH * max(beads) / 2:.1f} mm deep",
         sideways_reach(*hobnail_facets(), HOBNAIL_TOOL_DIRECTIONS_DEG), HOBNAIL_TOOL_DIRECTIONS_DEG),
        ("spikes", build_insert(plain_cavity(), bosses=build_spikes()),
         f"{len(spikes)} spikes {SPIKE_HEIGHT:g} mm tall on {SPIKE_BASE_DIAMETER:g} mm bases",
         sideways_reach(*spike_facets(), SPIKE_TOOL_DIRECTIONS_DEG), SPIKE_TOOL_DIRECTIONS_DEG),
    ]
    # Keyed by whether the sleeve is split: the one-piece block, then the halves.
    sleeves = {split: build_sleeve(split) for split in (False, True)}
    reach = sideways_reach(*point_facets(), INSERT_TOOL_DIRECTIONS_DEG)
    ring_problem = ring_obstacle(draft)
    rings, ring_height = ([], 0) if ring_problem else build_rings(solid)
    plates = build_plates(bare)
    report(draft, solid, insert, reach, other_sets, sleeves, rings, ring_height, ring_problem,
           plates)

    def export(part, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        export_step(part, path.with_suffix(".step"))
        export_stl(part, path.with_suffix(".stl"), tolerance=0.01, angular_tolerance=0.1)

    def clear(folder, pattern):
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob(pattern):
            old.unlink()

    pineapple_dir = OUT_DIR / "pineapple"
    clear(pineapple_dir / "plates", "plate_*.dxf")
    discs = []
    for index, face in enumerate(plates):
        write_dxf(face, pineapple_dir / "plates" / f"plate_{index + 1:02d}.dxf")
        discs.append(Pos(0, 0, index * PLATE_THICKNESS) * extrude(face, PLATE_THICKNESS))
    export(Compound(children=discs), pineapple_dir / "stack")
    export(solid, pineapple_dir / "solid")
    if rings:
        clear(pineapple_dir / "cnc_rings", "ring_*.step")
        for index, ring in enumerate(rings):
            export_step(ring, pineapple_dir / "cnc_rings" / f"ring_{index + 1}.step")

    insert_dir = OUT_DIR / "insert-mold"
    for name, part in [("pineapple", insert)] + [(name, part) for name, part, *_ in other_sets]:
        export(part, insert_dir / "inserts" / name)
    for split, parts in sleeves.items():
        names = ["sleeve_half_a", "sleeve_half_b"] if split else ["sleeve_solid"]
        for name, part in zip(names, parts):
            export(part, insert_dir / name)
        style = "halves" if split else "solid"
        write_dxf(build_foot_plate(split), insert_dir / f"foot_plate_{style}.dxf")
    print(f"\nWrote files to {OUT_DIR}")

    # Side by side: the rings pulled apart, the solid, the stack, the one-piece
    # sleeve with its inserts lifted and spread, and the sleeve in halves.
    step = 2 * FOOT_RADIUS + 60
    spread = [
        Pos(2 * step, 0, MOLD_HEIGHT * 0.6) * Rot(0, 0, k * 360 / INSERT_COUNT) * Pos(12, 0, 0) * insert
        for k in range(INSERT_COUNT)
    ]
    show(
        [Pos(-step, 0, i * 15) * r for i, r in enumerate(rings)]
        + [solid]
        + [Pos(step, 0, -BASE_THICKNESS) * d for d in discs]
        + [Pos(2 * step, 0, 0) * sleeves[False][0]]
        + spread
        + [Pos(3 * step, side * 15, 0) * h for side, h in zip((-1, 1), sleeves[True])]
        + [Pos((4 + n) * step, 0, 0) * Rot(0, 0, k * 360 / INSERT_COUNT) * Pos(12, 0, 0) * part
           for n, (_, part, _, _, _) in enumerate(other_sets) for k in range(INSERT_COUNT)]
    )

if __name__ == "__main__":
    main()
