export interface NamedEntity {
  display_name?: string | null;
}

export interface NamedVideo extends NamedEntity {
  filename: string;
}

export function getTrimmedDisplayName(entity: NamedEntity): string | null {
  const trimmed = entity.display_name?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : null;
}

export function hasCustomDisplayName(entity: NamedEntity): boolean {
  return getTrimmedDisplayName(entity) !== null;
}

export function getVideoDisplayName(video: NamedVideo): string {
  return getTrimmedDisplayName(video) ?? video.filename;
}
