# Regenerates the mold files and README pictures from the scripts.
# Needs only uv besides just; each script fetches its own dependencies.
#
# A generator is skipped when its files are newer than its script. To run it
# regardless:  just force=true pineapple
#
# Each generator ends by sending its parts to the OCP CAD Viewer. Without the
# viewer running it prints a connection error after its files are written,
# which can be ignored.

force := "false"

# List the recipes.
default:
    @just --list

# Regenerate whatever is out of date: every mold, then the README pictures.
all: molds previews

# Regenerate every mold that is out of date.
molds: optic blow pineapple segmented

# Optic dip molds. Name patterns to build only those, always: just optic star rib
optic *patterns:
    @if [ -n "{{patterns}}" ]; then ./optic_mold_generator.py {{patterns}}; \
     else just force={{force}} _generate optic_mold_generator.py mold-designs/optic/sunburst.stl; fi

# Two-part blow mold.
blow: (_generate "blow_mold_generator.py" "mold-designs/blow/mold_half_b.stl")

# Pineapple mold and the insert mold with all its insert sets. About three minutes.
pineapple: (_generate "pineapple_mold_generator.py" "mold-designs/insert-mold/foot_plate_halves.dxf")

# Segmented grenade blow mold.
segmented: (_generate "segmented_mold_generator.py" "mold-designs/segmented/base_plate.dxf")

# Redraw the README pictures if any mold file, or the renderer, is newer than they are.
previews:
    @if [ "{{force}}" != "true" ] && [ -e docs/images/segmented.png ] \
        && [ ! render_previews.py -nt docs/images/segmented.png ] \
        && [ -z "$(find mold-designs -name '*.stl' -newer docs/images/segmented.png -print -quit)" ]; \
     then echo "previews: up to date"; else ./render_previews.py; fi

# Delete everything the generators write.
[confirm("Delete mold-designs/ and docs/images/?")]
clean:
    rm -rf mold-designs docs/images

# Run a script unless the last file it writes is newer than the script itself.
_generate script last_output:
    @if [ "{{force}}" != "true" ] && [ "{{last_output}}" -nt "{{script}}" ]; \
     then echo "{{script}}: up to date"; else ./{{script}}; fi
