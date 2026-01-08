"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Upload,
  Search,
  FileText,
  CheckCircle,
  XCircle,
  Loader2,
  Trash2,
  Power,
  PowerOff,
  RefreshCw,
  HardDrive,
  Database,
} from "lucide-react";
import api from "@/lib/api";
import type { RegulatoryDocument, RegulatoryDocumentStats } from "@/lib/types";

const DOCUMENT_TYPES = [
  { value: "reglamento", label: "Reglamento" },
  { value: "directiva", label: "Directiva" },
  { value: "orden", label: "Orden" },
  { value: "circular", label: "Circular" },
  { value: "manual", label: "Manual Tecnico" },
  { value: "otro", label: "Otro" },
];

export default function DocumentosPage() {
  const [documents, setDocuments] = useState<RegulatoryDocument[]>([]);
  const [stats, setStats] = useState<RegulatoryDocumentStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadForm, setUploadForm] = useState({
    title: "",
    document_type: "reglamento",
    document_number: "",
    description: "",
  });
  const [isUploading, setIsUploading] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const fetchDocuments = useCallback(async () => {
    try {
      const [docsData, statsData] = await Promise.all([
        api.getRegulatoryDocuments(),
        api.getRegulatoryDocumentStats(),
      ]);
      setDocuments(docsData.items);
      setStats(statsData);
    } catch (error) {
      console.error("Error fetching documents:", error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
    // Poll every 5s for processing updates
    const interval = setInterval(fetchDocuments, 5000);
    return () => clearInterval(interval);
  }, [fetchDocuments]);

  const handleUpload = async () => {
    if (!uploadFile || !uploadForm.title) return;

    setIsUploading(true);
    try {
      await api.uploadRegulatoryDocument(uploadFile, uploadForm);
      setShowUploadDialog(false);
      setUploadFile(null);
      setUploadForm({
        title: "",
        document_type: "reglamento",
        document_number: "",
        description: "",
      });
      fetchDocuments();
    } catch (error) {
      console.error("Upload failed:", error);
      alert("Error al subir el documento");
    } finally {
      setIsUploading(false);
    }
  };

  const toggleActivation = async (doc: RegulatoryDocument) => {
    try {
      if (doc.is_active) {
        await api.deactivateRegulatoryDocument(doc.id);
      } else {
        await api.activateRegulatoryDocument(doc.id);
      }
      fetchDocuments();
    } catch (error) {
      console.error("Toggle failed:", error);
      alert("Error al cambiar el estado del documento");
    }
  };

  const handleDelete = async (docId: string) => {
    setIsDeleting(true);
    try {
      await api.deleteRegulatoryDocument(docId);
      setDeleteConfirm(null);
      fetchDocuments();
    } catch (error) {
      console.error("Delete failed:", error);
      alert("Error al eliminar el documento");
    } finally {
      setIsDeleting(false);
    }
  };

  const handleReprocess = async (docId: string) => {
    try {
      await api.reprocessRegulatoryDocument(docId);
      fetchDocuments();
    } catch (error) {
      console.error("Reprocess failed:", error);
      alert("Error al reprocesar el documento");
    }
  };

  const getStatusBadge = (status: string, progress: number) => {
    switch (status) {
      case "pending":
        return (
          <Badge variant="secondary">
            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
            Pendiente
          </Badge>
        );
      case "processing":
        return (
          <Badge variant="secondary">
            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
            Procesando {progress}%
          </Badge>
        );
      case "indexed":
        return (
          <Badge variant="default" className="bg-green-600">
            <CheckCircle className="h-3 w-3 mr-1" />
            Indexado
          </Badge>
        );
      case "failed":
        return (
          <Badge variant="destructive">
            <XCircle className="h-3 w-3 mr-1" />
            Error
          </Badge>
        );
      default:
        return <Badge>{status}</Badge>;
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const filteredDocuments = documents.filter((doc) =>
    doc.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    doc.document_number?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Documentos
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_documents ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Activos en RAG
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">
              {stats?.active_documents ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1">
              <Database className="h-3 w-3" />
              Total Chunks
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_chunks ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1">
              <HardDrive className="h-3 w-3" />
              Almacenamiento
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_size_mb ?? 0} MB</div>
          </CardContent>
        </Card>
      </div>

      {/* Document Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Documentos Regulatorios</CardTitle>
            <Button onClick={() => setShowUploadDialog(true)}>
              <Upload className="h-4 w-4 mr-2" />
              Subir Documento
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="mb-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Buscar documentos..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : filteredDocuments.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <FileText className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground">No hay documentos</p>
              <p className="text-sm text-muted-foreground mt-1">
                Sube tu primer documento PDF para comenzar
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Documento</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-center">Chunks</TableHead>
                  <TableHead className="text-center">Tamano</TableHead>
                  <TableHead className="text-center">Activo</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredDocuments.map((doc) => (
                  <TableRow key={doc.id}>
                    <TableCell>
                      <div>
                        <p className="font-medium">{doc.title}</p>
                        {doc.document_number && (
                          <p className="text-sm text-muted-foreground">
                            {doc.document_number}
                          </p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="capitalize">{doc.document_type}</TableCell>
                    <TableCell>
                      {getStatusBadge(doc.status, doc.processing_progress)}
                      {doc.error_message && (
                        <p className="text-xs text-destructive mt-1 max-w-[200px] truncate">
                          {doc.error_message}
                        </p>
                      )}
                    </TableCell>
                    <TableCell className="text-center">
                      {doc.total_chunks ?? "-"}
                    </TableCell>
                    <TableCell className="text-center">
                      {formatFileSize(doc.file_size)}
                    </TableCell>
                    <TableCell className="text-center">
                      <Button
                        variant={doc.is_active ? "default" : "outline"}
                        size="sm"
                        onClick={() => toggleActivation(doc)}
                        disabled={doc.status !== "indexed"}
                        className={doc.is_active ? "bg-green-600 hover:bg-green-700" : ""}
                      >
                        {doc.is_active ? (
                          <>
                            <Power className="h-3 w-3 mr-1" />
                            Activo
                          </>
                        ) : (
                          <>
                            <PowerOff className="h-3 w-3 mr-1" />
                            Inactivo
                          </>
                        )}
                      </Button>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        {doc.status === "failed" && (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleReprocess(doc.id)}
                            title="Reprocesar"
                          >
                            <RefreshCw className="h-4 w-4" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setDeleteConfirm(doc.id)}
                          title="Eliminar"
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Upload Dialog */}
      <Dialog open={showUploadDialog} onOpenChange={setShowUploadDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Subir Documento Regulatorio</DialogTitle>
            <DialogDescription>
              Sube un documento PDF para indexarlo en el sistema RAG
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Archivo PDF *</Label>
              <Input
                type="file"
                accept=".pdf"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                className="mt-1"
              />
              {uploadFile && (
                <p className="text-xs text-muted-foreground mt-1">
                  {uploadFile.name} ({formatFileSize(uploadFile.size)})
                </p>
              )}
            </div>
            <div>
              <Label>Titulo *</Label>
              <Input
                value={uploadForm.title}
                onChange={(e) =>
                  setUploadForm({ ...uploadForm, title: e.target.value })
                }
                placeholder="Ej: RD 2822/1998 - Alumbrado y senalizacion"
                className="mt-1"
              />
            </div>
            <div>
              <Label>Tipo de Documento *</Label>
              <Select
                value={uploadForm.document_type}
                onValueChange={(value) =>
                  setUploadForm({ ...uploadForm, document_type: value })
                }
              >
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DOCUMENT_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Numero de Documento</Label>
              <Input
                value={uploadForm.document_number}
                onChange={(e) =>
                  setUploadForm({ ...uploadForm, document_number: e.target.value })
                }
                placeholder="Ej: RD 2822/1998"
                className="mt-1"
              />
            </div>
            <div>
              <Label>Descripcion</Label>
              <Textarea
                value={uploadForm.description}
                onChange={(e) =>
                  setUploadForm({ ...uploadForm, description: e.target.value })
                }
                placeholder="Breve descripcion del documento"
                className="mt-1"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowUploadDialog(false)}
              disabled={isUploading}
            >
              Cancelar
            </Button>
            <Button
              onClick={handleUpload}
              disabled={!uploadFile || !uploadForm.title || isUploading}
            >
              {isUploading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Subiendo...
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4 mr-2" />
                  Subir
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirmar Eliminacion</DialogTitle>
            <DialogDescription>
              Esta accion eliminara permanentemente el documento, todos sus chunks
              y los datos indexados. Esta accion no se puede deshacer.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteConfirm(null)}
              disabled={isDeleting}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteConfirm && handleDelete(deleteConfirm)}
              disabled={isDeleting}
            >
              {isDeleting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Eliminando...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-2" />
                  Eliminar
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
