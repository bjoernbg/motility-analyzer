import { describe, expect, it, vi } from 'vitest';

const downloadBlobMock = vi.hoisted(() => vi.fn());

vi.mock('../download', () => ({
  downloadBlob: downloadBlobMock,
}));

import { createZipBlob, downloadZip, readZipEntries } from '../zip';

describe('zip helpers', () => {
  it('creates a zip blob with the expected filenames', async () => {
    const blob = await createZipBlob([
      {
        filename: 'alpha.txt',
        blob: new Blob(['alpha'], { type: 'text/plain' }),
      },
      {
        filename: 'beta.txt',
        blob: new Blob(['beta'], { type: 'text/plain' }),
      },
    ]);

    const entries = readZipEntries(new Uint8Array(await blob.arrayBuffer()));
    const decoder = new TextDecoder();

    expect(Object.keys(entries).sort()).toEqual(['alpha.txt', 'beta.txt']);
    expect(decoder.decode(entries['alpha.txt'])).toBe('alpha');
    expect(decoder.decode(entries['beta.txt'])).toBe('beta');
  });

  it('downloads a single zip blob', async () => {
    downloadBlobMock.mockClear();

    await downloadZip(
      [
        {
          filename: 'alpha.txt',
          blob: new Blob(['alpha'], { type: 'text/plain' }),
        },
      ],
      'bundle.zip',
    );

    expect(downloadBlobMock).toHaveBeenCalledTimes(1);
    expect(downloadBlobMock.mock.calls[0]?.[1]).toBe('bundle.zip');
  });
});
