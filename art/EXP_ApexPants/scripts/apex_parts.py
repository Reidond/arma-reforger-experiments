"""3D parts of the MCDU APEX pants, placed in surface coordinates read off the photo overlays.

Coordinates: phi in degrees around each leg (0 front, +90 outer seam, 180 back, -90 inner),
z in metres. Both legs share the layout (mirrored). Offsets are in metres from the trouser shell.

kind:
  patch   quad (phi0, z0)-(phi1, z1) with optional sloped edges, solidified
  pocket  bellows pocket bag: domed patch with steep sides
  flap    pocket flap lying on top of a pocket, lifted at its free (bottom) edge
  band    strip around part of the leg (straps, cuffs, knee pad)
  loop    belt loop (pelvis angle `thw`, 0 = centre front, 180 = centre back)
  tab     small hanging piece (zip pulls, strap tabs)
"""

MM = 0.001

# front cargo pocket (both legs) — overlay_15 / overlay_13
CARGO = dict(phi0=-5.0, phi1=88.0, z0=0.612, z1=0.770)
CARGO_FLAP = dict(phi0=-8.0, phi1=90.0, zb0=0.758, zb1=0.762, zt0=0.792, zt1=0.804)
# back pocket on the back-outer thigh — overlay_13 / overlay_8
BACK = dict(phi0=100.0, phi1=152.0, z0=0.603, z1=0.770)
BACK_FLAP = dict(phi0=97.0, phi1=155.0, zb0=0.760, zb1=0.758, zt0=0.812, zt1=0.806)

PARTS = [
    # pockets
    dict(name="CargoPocket", kind="pocket", **CARGO, depth=7 * MM, side_w=0.03, dome=0.12, pleat=(28.0, 44.0)),
    dict(name="CargoFlap", kind="flap", **CARGO_FLAP, under="CargoPocket", thick=2.2 * MM, lift=2.5 * MM),
    dict(name="BackPocket", kind="pocket", **BACK, depth=5 * MM, side_w=0.025, dome=0.1, pleat=(118.0, 134.0)),
    dict(name="BackFlap", kind="flap", **BACK_FLAP, under="BackPocket", thick=2.2 * MM, lift=2 * MM),
    # welt pocket lips (front slot above the cargo flap, back welt under the yoke)
    dict(name="CargoWelt", kind="patch", phi0=52.0, phi1=80.0, z0=0.818, z1=0.828, off=1.0 * MM, thick=1.5 * MM),
    dict(name="BackWelt", kind="patch", phi0=108.0, phi1=150.0, z0=0.914, z1=0.928, off=1.0 * MM, thick=1.5 * MM),
    # side vent zip (outseam) and its pull
    dict(name="SideZip", kind="patch", fabric="tape", phi0=87.5, phi1=92.5, z0=0.606, z1=0.830, off=0.1 * MM, thick=0.9 * MM),
    dict(name="SideZipPull", kind="tab", phi=91.0, z=0.608, length=0.045, width=0.011, thick=2.5 * MM, out=5 * MM),
    # knee: 500D double layer with pad pocket, strap round the back, lower zip
    dict(name="KneeStrap", kind="band", phi0=72.0, phi1=290.0, z0=0.358, z1=0.382, off=0.8 * MM, thick=2.0 * MM),
    dict(name="KneeStrapTab", kind="patch", phi0=62.0, phi1=76.0, z0=0.356, z1=0.384, off=2.6 * MM, thick=2.0 * MM),
    dict(name="LowerZip", kind="patch", fabric="tape", phi0=85.5, phi1=90.5, z0=0.200, z1=0.352, off=0.1 * MM, thick=0.9 * MM),
    dict(name="LowerZipPull", kind="tab", phi=88.0, z=0.346, length=0.04, width=0.010, thick=2.5 * MM, out=4 * MM),
    # hem cuff and its velcro tab
    dict(name="HemCuff", kind="band", phi0=-180.0, phi1=180.0, z0=0.112, z1=0.136, off=0.3 * MM, thick=1.0 * MM),
    dict(name="CuffTab", kind="patch", phi0=100.0, phi1=150.0, z0=0.116, z1=0.144, off=1.6 * MM, thick=2.0 * MM),
]

# waistband and belt loops are built around the pelvis, not per leg
WAISTBAND = dict(height=0.042, off=0.8 * MM, thick=2.0 * MM)
BELT_LOOPS = dict(thw=(22.0, 62.0, 112.0, 152.0), centre_back=True, width=0.018, height=0.056,
                  off=4.0 * MM, thick=1.8 * MM)
