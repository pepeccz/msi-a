"use client";

import { AlertCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export default function NormativasPage() {
  return (
    <div className="container mx-auto p-6 max-w-4xl">
      <Alert variant="default" className="border-orange-500 bg-orange-50">
        <AlertCircle className="h-5 w-5 text-orange-600" />
        <AlertTitle className="text-orange-900 text-lg font-semibold">
          Sistema RAG Temporalmente Desactivado
        </AlertTitle>
        <AlertDescription className="text-orange-800 mt-2">
          <p className="mb-3">
            El sistema de consulta de normativas (RAG) está actualmente desactivado
            mientras se realizan mejoras en su arquitectura.
          </p>
          <p className="text-sm text-orange-700">
            <strong>Fecha:</strong> 6 de febrero de 2026
          </p>
          <p className="text-sm text-orange-700 mt-1">
            Esta funcionalidad será reactivada en una próxima actualización con mejor rendimiento.
          </p>
        </AlertDescription>
      </Alert>
      
      <div className="mt-6 p-4 bg-gray-50 rounded-md border">
        <h3 className="font-medium text-gray-900 mb-2">Funcionalidades desactivadas:</h3>
        <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
          <li>Consulta de normativas mediante IA</li>
          <li>Gestión de documentos regulatorios</li>
          <li>Sistema de embeddings y búsqueda vectorial</li>
        </ul>
      </div>
    </div>
  );
}
