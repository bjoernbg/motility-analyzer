import { strToU8, zipSync, unzipSync } from 'fflate';

import { downloadBlob } from './download';

export interface ZipEntry {
  filename: string;
  blob: Blob;
}

export async function createZipBlob(entries: readonly ZipEntry[]): Promise<Blob> {
  const archiveEntries: Record<string, Uint8Array> = {};

  for (const entry of entries) {
    archiveEntries[entry.filename] = new Uint8Array(await entry.blob.arrayBuffer());
  }

  const archive = zipSync(archiveEntries, { level: 0 });
  const archiveBytes = Uint8Array.from(archive);
  return new Blob([archiveBytes.buffer], { type: 'application/zip' });
}

export async function downloadZip(entries: readonly ZipEntry[], filename: string): Promise<void> {
  const zipBlob = await createZipBlob(entries);
  downloadBlob(zipBlob, filename);
}

export function readZipEntries(buffer: Uint8Array): Record<string, Uint8Array> {
  return unzipSync(buffer);
}

export function textZipEntry(value: string): Uint8Array {
  return strToU8(value);
}
