export function downloadUrl(url: string, filename: string): void {
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  anchor.style.display = 'none';

  const parent = document.body ?? document.documentElement;
  parent.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export function downloadBlob(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob);
  try {
    downloadUrl(objectUrl, filename);
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export function canvasToBlob(
  canvas: HTMLCanvasElement,
  type = 'image/png',
  quality?: number,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) {
        resolve(blob);
        return;
      }

      reject(new Error('Failed to convert canvas to image blob'));
    }, type, quality);
  });
}

export async function downloadCanvas(
  canvas: HTMLCanvasElement,
  filename: string,
  type = 'image/png',
  quality?: number,
): Promise<void> {
  const blob = await canvasToBlob(canvas, type, quality);
  downloadBlob(blob, filename);
}
