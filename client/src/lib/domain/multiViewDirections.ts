import type { MultiViewAnalysisDirection, MultiViewSessionMetadata } from '../api';

export const DEFAULT_LEFT_MULTI_VIEW_DIRECTION: MultiViewAnalysisDirection = 'front';
export const DEFAULT_RIGHT_MULTI_VIEW_DIRECTION: MultiViewAnalysisDirection = 'bottom';

export interface MultiViewDirectionPair {
  leftDirection: MultiViewAnalysisDirection;
  rightDirection: MultiViewAnalysisDirection;
  isValid: boolean;
}

type DirectionCarrier = Pick<MultiViewSessionMetadata, 'left_direction' | 'right_direction'>;

function normalizeDirection(value: unknown): MultiViewAnalysisDirection | null {
  if (value === 'front' || value === 'bottom') {
    return value;
  }
  return null;
}

export function getOppositeMultiViewDirection(
  direction: MultiViewAnalysisDirection
): MultiViewAnalysisDirection {
  return direction === 'front' ? 'bottom' : 'front';
}

export function formatMultiViewDirection(direction: MultiViewAnalysisDirection): string {
  return direction === 'front' ? 'Front' : 'Bottom';
}

export function resolveMultiViewDirectionPair(
  metadata?: DirectionCarrier | null
): MultiViewDirectionPair {
  const leftDirection = normalizeDirection(metadata?.left_direction);
  const rightDirection = normalizeDirection(metadata?.right_direction);

  if (leftDirection && rightDirection) {
    return {
      leftDirection,
      rightDirection,
      isValid: leftDirection !== rightDirection,
    };
  }

  if (leftDirection) {
    return {
      leftDirection,
      rightDirection: getOppositeMultiViewDirection(leftDirection),
      isValid: true,
    };
  }

  if (rightDirection) {
    return {
      leftDirection: getOppositeMultiViewDirection(rightDirection),
      rightDirection,
      isValid: true,
    };
  }

  return {
    leftDirection: DEFAULT_LEFT_MULTI_VIEW_DIRECTION,
    rightDirection: DEFAULT_RIGHT_MULTI_VIEW_DIRECTION,
    isValid: true,
  };
}

export function selectMultiViewDirection(
  currentPair: Pick<MultiViewDirectionPair, 'leftDirection' | 'rightDirection'>,
  slot: 'left' | 'right',
  nextDirection: MultiViewAnalysisDirection
): MultiViewDirectionPair {
  if (slot === 'left') {
    return {
      leftDirection: nextDirection,
      rightDirection:
        currentPair.rightDirection === nextDirection
          ? getOppositeMultiViewDirection(nextDirection)
          : currentPair.rightDirection,
      isValid: true,
    };
  }

  return {
    leftDirection:
      currentPair.leftDirection === nextDirection
        ? getOppositeMultiViewDirection(nextDirection)
        : currentPair.leftDirection,
    rightDirection: nextDirection,
    isValid: true,
  };
}
