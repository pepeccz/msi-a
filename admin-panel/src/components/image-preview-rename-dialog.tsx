"use client";

import { useEffect, useState, useRef } from "react";
import Image from "next/image";
import { Loader2, Check, AlertCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  validateFilename,
  getBasename,
  getFileExtension,
  formatFileSize,
  getImageDimensions,
} from "@/lib/validators";

interface ImagePreviewRenameDialogProps {
  file: File | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (newFilename: string) => void;
  onCancel: () => void;
}

export function ImagePreviewRenameDialog({
  file,
  open,
  onOpenChange,
  onConfirm,
  onCancel,
}: ImagePreviewRenameDialogProps) {
  const [filename, setFilename] = useState("");
  const [validation, setValidation] = useState<{
    isValid: boolean;
    error: string | null;
  }>({ isValid: true, error: null });
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [dimensions, setDimensions] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset state and prepare filename when file changes
  useEffect(() => {
    if (file && open) {
      const basename = getBasename(file.name);
      setFilename(basename);
      setValidation({ isValid: true, error: null });

      // Create object URL for preview
      const url = URL.createObjectURL(file);
      setImageUrl(url);

      // Get image dimensions
      const getDimensions = async () => {
        const dims = await getImageDimensions(file);
        setDimensions(dims);
      };
      getDimensions();

      // Auto-focus on filename input
      setTimeout(() => {
        inputRef.current?.select();
      }, 100);

      return () => {
        if (url) {
          URL.revokeObjectURL(url);
        }
      };
    }
  }, [file, open]);

  const handleFilenameChange = (newValue: string) => {
    setFilename(newValue);

    // Create full filename with extension for validation
    const ext = file ? getFileExtension(file.name) : "";
    const fullFilename = newValue + ext;

    // Validate
    const result = validateFilename(fullFilename);
    setValidation(result);
  };

  const handleConfirm = () => {
    if (!file || !validation.isValid) {
      return;
    }

    const ext = getFileExtension(file.name);
    const newFilename = filename + ext;

    setIsLoading(true);
    // Simulate a slight delay for UX feedback
    setTimeout(() => {
      onConfirm(newFilename);
      setIsLoading(false);
      setFilename("");
      setImageUrl(null);
      setDimensions(null);
    }, 100);
  };

  const handleCancel = () => {
    onOpenChange(false);
    setFilename("");
    setImageUrl(null);
    setDimensions(null);
    onCancel();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && validation.isValid && !isLoading) {
      handleConfirm();
    } else if (e.key === "Escape") {
      handleCancel();
    }
  };

  if (!file) {
    return null;
  }

  const ext = getFileExtension(file.name);
  const charCount = filename.length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Renombrar Imagen</DialogTitle>
          <DialogDescription>
            Modifica el nombre de la imagen antes de subirla
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Image Preview */}
          {imageUrl && (
            <div className="relative w-full aspect-video rounded-lg border bg-muted overflow-hidden">
              <Image
                src={imageUrl}
                alt="Preview"
                fill
                className="object-contain"
                unoptimized
              />
            </div>
          )}

          {/* Image Info */}
          <div className="space-y-2 text-sm text-muted-foreground">
            <div className="flex justify-between">
              <span>Tamaño:</span>
              <span>{formatFileSize(file.size)}</span>
            </div>
            {dimensions && (
              <div className="flex justify-between">
                <span>Dimensiones:</span>
                <span>
                  {dimensions.width} × {dimensions.height} px
                </span>
              </div>
            )}
          </div>

          {/* Filename Input */}
          <div className="space-y-2">
            <Label htmlFor="filename" className="text-sm font-medium">
              Nombre del archivo{" "}
              <span className="text-destructive">*</span>
            </Label>

            <div className="flex gap-2">
              <div className="flex-1">
                <Input
                  ref={inputRef}
                  id="filename"
                  value={filename}
                  onChange={(e) => handleFilenameChange(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="mi-imagen"
                  disabled={isLoading}
                  className={
                    !validation.isValid && filename.length > 0
                      ? "border-destructive focus-visible:ring-destructive"
                      : validation.isValid && filename.length > 0
                        ? "border-green-500 focus-visible:ring-green-500"
                        : ""
                  }
                  aria-invalid={!validation.isValid}
                  aria-describedby={
                    !validation.isValid ? "filename-error" : undefined
                  }
                />
              </div>

              {/* Extension Display and Validation Icon */}
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground whitespace-nowrap">
                  {ext}
                </span>
                {filename.length > 0 && validation.isValid && (
                  <Check className="h-5 w-5 text-green-500 flex-shrink-0" />
                )}
                {filename.length > 0 && !validation.isValid && (
                  <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0" />
                )}
              </div>
            </div>

            {/* Character Counter */}
            <div className="flex justify-between items-start">
              <div>
                {validation.error && (
                  <p
                    id="filename-error"
                    className="text-xs text-destructive mt-1"
                  >
                    {validation.error}
                  </p>
                )}
              </div>
              <span className="text-xs text-muted-foreground ml-auto">
                {charCount}/200
              </span>
            </div>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={handleCancel}
            disabled={isLoading}
          >
            Cancelar
          </Button>
          <Button
            type="button"
            onClick={handleConfirm}
            disabled={!validation.isValid || isLoading || filename.length === 0}
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Subiendo...
              </>
            ) : (
              "Confirmar"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
