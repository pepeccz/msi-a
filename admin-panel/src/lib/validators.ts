/**
 * Filename validation and file utility helpers.
 * Used by image upload dialogs to sanitize and validate filenames.
 */

/** Validation result for filename checks */
export interface ValidationResult {
  isValid: boolean;
  error: string | null;
}

/**
 * Validate a full filename (including extension).
 * Allows alphanumeric characters, hyphens, underscores, and a single dot for the extension.
 */
export function validateFilename(filename: string): ValidationResult {
  if (!filename || filename.trim().length === 0) {
    return { isValid: false, error: "El nombre del archivo no puede estar vacío" };
  }

  if (filename.length > 200) {
    return { isValid: false, error: "El nombre del archivo no puede superar los 200 caracteres" };
  }

  // Prevent path traversal
  if (filename.includes("..") || filename.includes("/") || filename.includes("\\")) {
    return { isValid: false, error: "El nombre del archivo contiene caracteres no permitidos" };
  }

  // Allow: letters, numbers, hyphens, underscores, dots (for extension)
  const validPattern = /^[a-zA-Z0-9._-]+$/;
  if (!validPattern.test(filename)) {
    return {
      isValid: false,
      error: "El nombre solo puede contener letras, números, guiones, guiones bajos y puntos",
    };
  }

  return { isValid: true, error: null };
}

/**
 * Extract the basename (filename without extension) from a full filename.
 * Example: "photo.jpg" → "photo", "my.image.png" → "my.image"
 */
export function getBasename(filename: string): string {
  const lastDot = filename.lastIndexOf(".");
  if (lastDot <= 0) return filename; // No extension or hidden file (e.g. ".gitignore")
  return filename.slice(0, lastDot);
}

/**
 * Extract the extension (including dot) from a full filename.
 * Example: "photo.jpg" → ".jpg", "my.image.png" → ".png"
 * Returns empty string if no extension found.
 */
export function getFileExtension(filename: string): string {
  const lastDot = filename.lastIndexOf(".");
  if (lastDot <= 0) return ""; // No extension or hidden file
  return filename.slice(lastDot);
}

/**
 * Format a file size in bytes to a human-readable string.
 * Example: 1024 → "1.0 KB", 1048576 → "1.0 MB"
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Get the natural dimensions of an image File.
 * Returns width and height in pixels.
 */
export function getImageDimensions(
  file: File
): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new window.Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("No se pudo cargar la imagen"));
    };
    img.src = url;
  });
}
