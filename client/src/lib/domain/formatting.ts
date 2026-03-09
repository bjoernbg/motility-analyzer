import { DEFAULT_NUM_TRACKING_POINTS } from '../constants';

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function formatDurationSeconds(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${minutes}m ${secs}s`;
}

export function formatTimestampWithMilliseconds(timeInSeconds: number): string {
  const totalMilliseconds = Math.max(0, Math.round(timeInSeconds * 1000));
  const minutes = Math.floor(totalMilliseconds / 60000);
  const seconds = Math.floor((totalMilliseconds % 60000) / 1000);
  const milliseconds = totalMilliseconds % 1000;
  return `${minutes}:${seconds.toString().padStart(2, '0')}.${milliseconds
    .toString()
    .padStart(3, '0')}`;
}

export function formatDistributionMethod(rawMethod: unknown): string {
  return rawMethod === 'center_line_projection' ? 'Center Line' : 'X-Axis Even';
}

export function formatTrackingPoints(points: unknown): string {
  const count = typeof points === 'number' ? points : DEFAULT_NUM_TRACKING_POINTS;
  return `${count} points`;
}

export function formatWindowRange(
  left: unknown,
  right: unknown,
  separator: string = ' ↔ '
): string | null {
  if (typeof left === 'number' && typeof right === 'number') {
    return `Window ${left}${separator}${right}`;
  }
  return null;
}
