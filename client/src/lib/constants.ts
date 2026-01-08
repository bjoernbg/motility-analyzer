/**
 * Shared constants for the Motility Analyzer frontend
 */

/**
 * Conversion factor from pixels to millimeters
 * Used for displaying distance measurements in mm
 *
 * ⚠️ IMPORTANT: This constant is also defined in the backend at server/config.py
 * If you change this value, you MUST also update it in server/config.py to keep them in sync!
 */
export const PIXEL_TO_MM_FACTOR = 11; // 11 pixels = 1 mm

/**
 * Fixed color scale constants for heatmap visualization
 * Measured in millimeters
 */
export const HEATMAP_MIN_MM = 3; // Red color = 3mm
export const HEATMAP_MAX_MM = 30; // Violet color = 30mm
