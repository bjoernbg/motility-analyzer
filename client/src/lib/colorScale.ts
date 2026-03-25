export interface ColorScaleLabel {
  value: string;
  percent: number;
}

function formatColorScaleValue(value: number): string {
  if (Number.isInteger(value)) {
    return `${value}`;
  }

  return `${Math.round(value * 10) / 10}`;
}

export function buildColorScaleLabels(min: number, max: number): ColorScaleLabel[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return [];
  }

  const range = max - min;
  if (range <= 0) {
    return [];
  }

  const labels: ColorScaleLabel[] = [
    { value: formatColorScaleValue(min), percent: 0 },
  ];

  const startMm = Math.ceil(min);
  const endMm = Math.floor(max);
  for (let mm = startMm; mm <= endMm; mm += 1) {
    if (mm <= min || mm >= max) {
      continue;
    }

    labels.push({
      value: `${mm}`,
      percent: ((mm - min) / range) * 100,
    });
  }

  labels.push({
    value: formatColorScaleValue(max),
    percent: 100,
  });

  return labels;
}

export function resolveColorScaleColorIndex(y: number, height: number): number {
  if (height <= 1) {
    return 255;
  }

  const clampedY = Math.max(0, Math.min(height - 1, y));
  const t = 1 - clampedY / (height - 1);
  return Math.round(t * 255);
}
