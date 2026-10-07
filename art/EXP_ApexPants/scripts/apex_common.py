"""Shared geometry helpers for the MCDU APEX pants build (run inside Blender).

Coordinates follow the Reforger character template: metres, Z up, character
faces -Y, left side is +X. "phi" is the angle around a trouser leg measured from
the front centre line (0) towards the outer side (+90), back (180), inner (-90).
"""

import math

# Leg axis centre (x for the left leg, y) by height, used for phi and fitting.
LEG_CENTRE = [
    (0.08, (0.173, 0.071)), (0.25, (0.168, 0.078)), (0.40, (0.160, 0.085)),
    (0.50, (0.138, 0.058)), (0.60, (0.123, 0.033)), (0.70, (0.111, 0.021)),
    (0.80, (0.102, 0.017)), (0.90, (0.100, 0.017)),
]

# Minimum trouser cross-section per height: (cx, cy, half-width x, half-depth y).
LEG_ELLIPSE = [
    (0.08, (0.172, 0.073, 0.071, 0.075)), (0.25, (0.167, 0.079, 0.071, 0.075)),
    (0.40, (0.160, 0.085, 0.074, 0.077)), (0.50, (0.138, 0.058, 0.074, 0.083)),
    (0.60, (0.123, 0.033, 0.076, 0.085)), (0.70, (0.111, 0.021, 0.088, 0.093)),
    (0.80, (0.104, 0.017, 0.097, 0.101)), (0.90, (0.100, 0.017, 0.097, 0.101)),
]

CROTCH_Z = 0.785  # where the two legs join


def sstep(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def _interp(table, z):
    if z <= table[0][0]:
        return table[0][1]
    for (z0, a), (z1, b) in zip(table, table[1:]):
        if z0 <= z <= z1:
            t = sstep(z0, z1, z)
            return tuple(x + (y - x) * t for x, y in zip(a, b))
    return table[-1][1]


def leg_centre(z):
    return _interp(LEG_CENTRE, z)


def leg_ellipse(z):
    return _interp(LEG_ELLIPSE, z)


def phi_of(x, y, z):
    """Return (phi_degrees, side) for a point; side is +1 left, -1 right."""
    s = 1 if x >= 0 else -1
    cx, cy = leg_centre(z)
    return math.degrees(math.atan2(x * s - cx, -(y - cy))), s


def clearance(z):
    """Fabric gap over the skin: snug at the waist, looser on the legs."""
    return 0.012 + (0.007 - 0.012) * sstep(0.80, 0.97, z)


def smax(a, b, k=0.012):
    return 0.5 * (a + b + math.sqrt((a - b) ** 2 + k * k))
