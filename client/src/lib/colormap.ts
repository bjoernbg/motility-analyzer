/**
 * Precompute a color map: value in [0, 1] → RGB
 * Red → Orange → Yellow → Green → Cyan → Blue → Violet/Ultraviolet gradient
 */
export function createColormap(): Uint8Array {
  const map = new Uint8Array(256 * 3);

  const colors: [number, number, number][] = [
    [255, 0, 0],     // Red
    [255, 127, 0],   // Orange
    [255, 255, 0],   // Yellow
    [0, 255, 0],     // Green
    [0, 255, 255],   // Cyan
    [0, 0, 255],     // Blue
    [148, 0, 211],   // Violet/Ultraviolet
  ];

  const numSegments = colors.length - 1;

  for (let i = 0; i < 256; i++) {
    const t = i / 255;

    const segmentSize = 1 / numSegments;
    const segmentIndex = Math.min(Math.floor(t / segmentSize), numSegments - 1);
    const localT = (t - segmentIndex * segmentSize) / segmentSize;

    const color1 = colors[segmentIndex];
    const color2 = colors[segmentIndex + 1];

    if (!color1 || !color2) continue;

    const r = Math.round(color1[0] + (color2[0] - color1[0]) * localT);
    const g = Math.round(color1[1] + (color2[1] - color1[1]) * localT);
    const b = Math.round(color1[2] + (color2[2] - color1[2]) * localT);

    map[i * 3 + 0] = r;
    map[i * 3 + 1] = g;
    map[i * 3 + 2] = b;
  }
  return map;
}

/**
 * Map a normalized [0,1] value to [r, g, b] floats (0–1 range)
 * through a 256-entry colormap. Useful for Three.js vertex colors.
 */
export function colormapValueToRgb(
  colormap: Uint8Array,
  normalizedValue: number,
): [number, number, number] {
  const idx = Math.max(0, Math.min(255, Math.round(normalizedValue * 255)));
  return [
    colormap[idx * 3] / 255,
    colormap[idx * 3 + 1] / 255,
    colormap[idx * 3 + 2] / 255,
  ];
}
