#!/usr/bin/env python3
"""Generate 5 .cube LUT files for VideoEditor beauty presets.

Each LUT is a 17x17x17 3D lookup table in Adobe .cube format.
Generated via numpy linear color mapping + tone shifts.
"""

import logging
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

LUT_SIZE = 17  # 17^3 = 4913 entries (standard for lightweight LUTs)

def _write_cube(path: Path, title: str, table: np.ndarray):
    """Write a .cube LUT file."""
    with open(path, "w") as f:
        f.write(f"TITLE \"{title}\"\n")
        f.write(f"LUT_3D_SIZE {LUT_SIZE}\n")
        f.write(f"DOMAIN_MIN 0.0 0.0 0.0\n")
        f.write(f"DOMAIN_MAX 1.0 1.0 1.0\n")
        f.write("\n")
        for entry in table:
            f.write(f"{entry[0]:.6f} {entry[1]:.6f} {entry[2]:.6f}\n")


def _identity_table() -> np.ndarray:
    """Generate identity LUT table (no color change)."""
    steps = np.linspace(0.0, 1.0, LUT_SIZE)
    table = []
    for b in steps:
        for g in steps:
            for r in steps:
                table.append([r, g, b])
    return np.array(table, dtype=np.float64)


def _apply_curve(table: np.ndarray, channel: int, gamma: float, offset: float = 0.0) -> np.ndarray:
    """Apply gamma curve + offset to a single channel."""
    t = table.copy()
    t[:, channel] = np.clip(np.power(t[:, channel], gamma) + offset, 0.0, 1.0)
    return t


def _apply_saturation(table: np.ndarray, factor: float) -> np.ndarray:
    """Adjust saturation (1.0 = no change, >1 = more saturated)."""
    t = table.copy()
    lum = 0.2126 * t[:, 0] + 0.7152 * t[:, 1] + 0.0722 * t[:, 2]
    for ch in range(3):
        t[:, ch] = np.clip(lum + factor * (t[:, ch] - lum), 0.0, 1.0)
    return t


def generate_outdoor_natural(out_dir: Path):
    """Outdoor natural: slight warm tone, gentle contrast boost, natural saturation."""
    t = _identity_table()
    # Warm: slight red lift, blue reduction
    t = _apply_curve(t, 0, 0.95, 0.01)   # R: slight lift
    t = _apply_curve(t, 2, 1.05, -0.01)   # B: slight drop
    # Gentle S-curve contrast via midtone gamma
    t = _apply_curve(t, 0, 0.97)
    t = _apply_curve(t, 1, 0.97)
    t = _apply_saturation(t, 1.05)
    _write_cube(out_dir / "outdoor_natural.cube", "Outdoor Natural", t)


def generate_indoor_warm(out_dir: Path):
    """Indoor warm: golden tone, soft shadows, warm highlights."""
    t = _identity_table()
    t = _apply_curve(t, 0, 0.90, 0.02)   # R: warm lift
    t = _apply_curve(t, 1, 0.95, 0.01)   # G: slight warm
    t = _apply_curve(t, 2, 1.10, -0.02)  # B: cool reduction
    t = _apply_saturation(t, 1.08)
    _write_cube(out_dir / "indoor_warm.cube", "Indoor Warm", t)


def generate_food(out_dir: Path):
    """Food: enhanced reds/oranges, warm midtones, vibrant."""
    t = _identity_table()
    t = _apply_curve(t, 0, 0.88, 0.03)   # R: strong warm
    t = _apply_curve(t, 1, 0.93, 0.01)   # G: slight lift
    t = _apply_curve(t, 2, 1.12, -0.02)  # B: reduce
    t = _apply_saturation(t, 1.15)
    _write_cube(out_dir / "food.cube", "Food", t)


def generate_night(out_dir: Path):
    """Night: cool tones, lifted shadows, blue/teal accent."""
    t = _identity_table()
    t = _apply_curve(t, 0, 1.05, -0.01)  # R: slight cool
    t = _apply_curve(t, 1, 1.02)          # G: neutral
    t = _apply_curve(t, 2, 0.92, 0.02)   # B: teal lift
    # Lift shadows (add small offset to all channels)
    t[:, 0] = np.clip(t[:, 0] + 0.02, 0.0, 1.0)
    t[:, 1] = np.clip(t[:, 1] + 0.02, 0.0, 1.0)
    t[:, 2] = np.clip(t[:, 2] + 0.03, 0.0, 1.0)
    t = _apply_saturation(t, 0.95)
    _write_cube(out_dir / "night.cube", "Night", t)


def generate_travel(out_dir: Path):
    """Travel: vibrant, warm highlights, slightly faded shadows (film look)."""
    t = _identity_table()
    t = _apply_curve(t, 0, 0.92, 0.02)
    t = _apply_curve(t, 1, 0.95, 0.01)
    t = _apply_curve(t, 2, 1.03, -0.01)
    # Film fade: lift blacks slightly
    t[:, 0] = np.clip(t[:, 0] * 0.95 + 0.03, 0.0, 1.0)
    t[:, 1] = np.clip(t[:, 1] * 0.95 + 0.03, 0.0, 1.0)
    t[:, 2] = np.clip(t[:, 2] * 0.95 + 0.03, 0.0, 1.0)
    t = _apply_saturation(t, 1.10)
    _write_cube(out_dir / "travel.cube", "Travel", t)


def generate_all():
    """Generate all 5 LUT presets."""
    out_dir = Path(__file__).parent / "luts"
    out_dir.mkdir(exist_ok=True)

    generators = [
        generate_outdoor_natural,
        generate_indoor_warm,
        generate_food,
        generate_night,
        generate_travel,
    ]
    for gen in generators:
        gen(out_dir)
        logger.info("Generated LUT: %s", gen.__name__)

    logger.info("Generated %d LUT files in %s", len(generators), out_dir)


if __name__ == "__main__":
    generate_all()
