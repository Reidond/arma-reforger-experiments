"""Fabric panel layout of the MCDU APEX pants (olive vs camo), read from all reference photos.

Per leg, symmetric. phi: 0 front, +90 outseam, ±180 back, -90 inseam (degrees); z in metres.

  knee band (K_BOT..K_TOP):  olive all round (500D front panel + stretch back panel), except two
                             camo wedges pointed at the top: OUTER under the side-zip end
                             (photos 5, 6, 12, 17) and INNER between knee panel and inner strip
                             (photo 15)
  inner strip:               olive stretch along the inseam from the crotch to the knee band,
                             continuing below the knee strap as a V ending at mid-shin (12, 15)
  back of knee/thigh:        part of the knee band, rises to the back-pocket bottom (8, 13)
  yoke:                      olive stretch under the back waistband, front edge at the side seam
  everything else:           camo ripstop

panel_fields() returns material ids per point and the signed distances of every seam line, so
apex_features can lay seams/stitching on exactly these boundaries.
"""

import numpy as np

# --- layout parameters (tuned against the compare renders) ---
K_BOT = 0.382            # knee band bottom (knee strap sits on it) — 70 % down the garment in photo 15
K_TOP_FRONT = 0.610      # knee band top at the front (cargo pocket bottom) — 46 % down in photo 15
K_TOP_BACK = 0.600       # ... at the back (back pocket bottom)
OUTER_WEDGE = [(72.0, 0.580), (38.0, K_BOT), (122.0, K_BOT)]    # apex, base front, base back (photos 15, 8)
INNER_WEDGE = [(-27.0, 0.561), (-62.0, K_BOT), (20.0, K_BOT)]    # apex, base inner, base front (photo 15 left leg)
STRIP = (-128.0, -50.0)  # inner strip angular span above the knee band
STRIP_TOP = 0.80         # where the inner strip meets the crotch seam
V_TIP_Z = 0.268          # lower V tip below the knee strap
V_CENTRE = -84.0
YOKE_BOT_BACK = 0.908
YOKE_BOT_SIDE = 0.935
YOKE_FRONT_THW = 96.0    # pelvis angle of the yoke's front edge (just behind the side seam)
R_KNEE = 0.085           # metres per radian around the knee (for wedge/strip distances)


def wrap(d):
    return (d + 180.0) % 360.0 - 180.0


def ang_sd(phi, lo, hi, R):
    """Signed arc distance (m) to the angular interval [lo, hi] deg; negative inside; wrap aware."""
    mid, half = 0.5 * (lo + hi), 0.5 * (hi - lo)
    return np.radians(np.abs(wrap(phi - mid)) - half) * R


def tri_sd(phi, z, tri, R):
    """Signed distance to a triangle given in (phi deg, z m) — local, wrap aware around its apex."""
    (pa, za), (pb, zb), (pc, zc) = tri
    ref = pa
    x = np.radians(wrap(phi - ref)) * R
    pts = [(np.radians(wrap(p - ref)) * R, q) for p, q in tri]
    d = np.full(x.shape, -1e9, np.float32)
    inside = np.ones(x.shape, bool)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        ex, ey = x1 - x0, y1 - y0
        L = np.hypot(ex, ey)
        nx, ny = ey / L, -ex / L               # outward normal for clockwise order, fixed below
        dist = (x - x0) * nx + (z - y0) * ny
        d = np.maximum(d, dist)
    # orientation: make the centroid negative
    cx = sum(p[0] for p in pts) / 3
    cy = sum(p[1] for p in pts) / 3
    dc = -1e9
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        ex, ey = x1 - x0, y1 - y0
        L = np.hypot(ex, ey)
        dc = max(dc, (cx - x0) * ey / L + (cy - y0) * -ex / L)
    if dc > 0:   # counter-clockwise: flip normals
        d = np.full(x.shape, -1e9, np.float32)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            ex, ey = x1 - x0, y1 - y0
            L = np.hypot(ex, ey)
            d = np.maximum(d, (x - x0) * -ey / L + (z - y0) * ex / L)
    return d


def k_top(phi):
    """Top of the knee band: front at the cargo pocket bottom, back at the back pocket bottom."""
    t = 0.5 - 0.5 * np.cos(np.radians(phi))          # 0 front .. 1 back
    return K_TOP_FRONT + (K_TOP_BACK - K_TOP_FRONT) * t


def panel_fields(phi, z, thw, ax):
    """Return dict with boolean masks and signed distances (m, negative inside) of the panels."""
    R = R_KNEE
    ktop = k_top(phi)
    d_band = np.maximum(K_BOT - z, z - ktop)                          # knee band
    d_wo = tri_sd(phi, z, OUTER_WEDGE, R)
    d_wi = tri_sd(phi, z, INNER_WEDGE, R)
    # inner strip: span above the band; V below it
    vt = np.clip((z - V_TIP_Z) / (K_BOT - V_TIP_Z), 0, 1)
    v_half = 0.5 * (STRIP[1] - STRIP[0]) * vt
    d_v = np.maximum(ang_sd(phi, V_CENTRE - v_half, V_CENTRE + v_half, R), np.maximum(z - K_BOT, V_TIP_Z - z))
    d_strip = np.maximum(ang_sd(phi, STRIP[0], STRIP[1], R), np.maximum(ktop - z, z - STRIP_TOP))
    # crotch gusset: the strips meet at the crotch; a small diamond between the legs
    d_crotch = np.maximum(ax - 0.014 * (1 - np.clip((z - 0.76) / 0.04, 0, 1)), np.maximum(0.75 - z, z - 0.80))
    # yoke under the back waistband (pelvis angle thw: 0 front, 180 back)
    yb = YOKE_BOT_SIDE + (YOKE_BOT_BACK - YOKE_BOT_SIDE) * np.clip((thw - 110.0) / 60.0, 0, 1)
    d_yoke = np.maximum(yb - z, np.radians(YOKE_FRONT_THW - thw) * 0.165)

    knee_olive = (d_band < 0) & (d_wo >= 0) & (d_wi >= 0)
    front_500d = knee_olive & (ang_sd(phi, INNER_WEDGE[2][0], OUTER_WEDGE[1][0], R) < 0.02)
    olive = knee_olive | (d_strip < 0) | (d_v < 0) | (d_crotch < 0)
    return dict(olive=olive, front_500d=front_500d, d_band=d_band, d_wo=d_wo, d_wi=d_wi,
                d_strip=d_strip, d_v=d_v, d_crotch=d_crotch, d_yoke=d_yoke, ktop=ktop)
