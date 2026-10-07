"""Turn photo-projected texture colour into albedo + relief (texture space, numpy).

* fill_gaps: normalised convolution inside the UV islands fills texels no photo saw.
* intrinsic: Retinex-style split of the projected photos into reflectance and shading.
  Gradients of log-luminance that come with a chromaticity change belong to the print
  (camo edges); the rest is shading (folds, seams, pocket edges, flap shadows). The
  shading gradients are integrated with an FFT Poisson solve; its high-pass part is used
  as relief for the normal map and divided out of the albedo.
"""

import numpy as np
from scipy import ndimage


def fill_gaps(rgb, w, valid, sigmas=(2, 4, 8, 16, 32, 64)):
    """Fill texels with low photo weight from nearby covered texels of the same UV island."""
    out = rgb.copy()
    cov = np.clip(w, 0, 1) * valid
    filled = cov.copy()
    num = rgb * cov[..., None]
    for s in sigmas:
        den = ndimage.gaussian_filter(cov, s)
        nm = np.stack([ndimage.gaussian_filter(num[..., c], s) for c in range(3)], -1)
        est = nm / np.maximum(den, 1e-6)[..., None]
        take = (filled < 0.99) & (den > 0.02) & valid
        a = np.where(take, (1 - filled), 0.0)[..., None]
        out = out * (1 - a) + est * a
        filled = np.where(take, 1.0, filled)
    return out, filled


def poisson_fft(gx, gy):
    """Least-squares integration of a gradient field (periodic boundary)."""
    h, w = gx.shape
    div = (gx - np.roll(gx, 1, 1)) + (gy - np.roll(gy, 1, 0))
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    denom = (2 * np.cos(2 * np.pi * fx) - 2) + (2 * np.cos(2 * np.pi * fy) - 2)
    denom[0, 0] = 1.0
    F = np.fft.fft2(div) / denom
    F[0, 0] = 0
    return np.real(np.fft.ifft2(F)).astype(np.float32)


def intrinsic(rgb, valid, texel_m, chroma_tau=0.012, hp_m=0.03, strength=0.85):
    """Return (albedo, log_shading_highpass) for linear rgb on valid texels."""
    eps = 1e-3
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    l = np.log(np.maximum(lum, eps))
    chrom = rgb / np.maximum(rgb.sum(-1, keepdims=True), eps)
    l = np.where(valid, l, 0)
    gx = np.roll(l, -1, 1) - l
    gy = np.roll(l, -1, 0) - l
    cgx = np.abs(np.roll(chrom, -1, 1) - chrom).sum(-1)
    cgy = np.abs(np.roll(chrom, -1, 0) - chrom).sum(-1)
    vx = valid & np.roll(valid, -1, 1)
    vy = valid & np.roll(valid, -1, 0)
    # soft classification: big chroma change => print edge => not shading
    kx = np.clip(1 - cgx / chroma_tau, 0, 1) ** 2 * vx
    ky = np.clip(1 - cgy / chroma_tau, 0, 1) ** 2 * vy
    # very large luminance jumps are print edges too (cream flecks on tan have little chroma change)
    kx *= np.clip(1 - (np.abs(gx) - 0.25) / 0.25, 0, 1)
    ky *= np.clip(1 - (np.abs(gy) - 0.25) / 0.25, 0, 1)
    s = poisson_fft(gx * kx, gy * ky)
    s = np.where(valid, s, 0)
    # keep only the fold/crease scale: subtract the masked low-pass
    sig = hp_m / texel_m
    den = ndimage.gaussian_filter(valid.astype(np.float32), sig)
    low = ndimage.gaussian_filter(s * valid, sig) / np.maximum(den, 1e-4)
    shp = np.where(valid, s - low, 0)
    albedo = rgb * np.exp(-strength * shp)[..., None]
    return albedo.astype(np.float32), shp.astype(np.float32)
