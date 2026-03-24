import { afterEach, vi } from 'vitest';

class ResizeObserverMock {
  observe() {
    // no-op for jsdom tests
  }

  unobserve() {
    // no-op for jsdom tests
  }

  disconnect() {
    // no-op for jsdom tests
  }
}

if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = ResizeObserverMock as typeof ResizeObserver;
}

if (!globalThis.requestAnimationFrame) {
  globalThis.requestAnimationFrame = (cb: FrameRequestCallback): number =>
    setTimeout(() => cb(Date.now()), 16) as unknown as number;
}

if (!globalThis.cancelAnimationFrame) {
  globalThis.cancelAnimationFrame = (id: number): void => {
    clearTimeout(id);
  };
}

if (typeof HTMLCanvasElement !== 'undefined') {
  const noop = () => {};
  const context2d = {
    clearRect: noop,
    createImageData: (width: number, height: number) => ({
      data: new Uint8ClampedArray(width * height * 4),
      width,
      height,
    }),
    putImageData: noop,
    beginPath: noop,
    moveTo: noop,
    lineTo: noop,
    stroke: noop,
    fill: noop,
    arc: noop,
    fillRect: noop,
    strokeRect: noop,
    setLineDash: noop,
    drawImage: noop,
    save: noop,
    restore: noop,
    translate: noop,
    scale: noop,
    measureText: () => ({ width: 0 }),
    fillText: noop,
    setTransform: noop,
    imageSmoothingEnabled: true,
    textAlign: 'center',
    textBaseline: 'middle',
    font: '',
    lineWidth: 1,
    globalAlpha: 1,
    strokeStyle: '#000',
    fillStyle: '#000',
  } as unknown as CanvasRenderingContext2D;

  HTMLCanvasElement.prototype.getContext = ((contextId: string) => {
    if (contextId === '2d') {
      return context2d;
    }
    return null;
  }) as unknown as typeof HTMLCanvasElement.prototype.getContext;

  HTMLCanvasElement.prototype.toBlob = function toBlob(callback) {
    callback?.(new Blob(['canvas'], { type: 'image/png' }));
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});
