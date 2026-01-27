"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Loader2, Plus, X } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import type {
  Element,
  ElementRequiredField,
  ElementRequiredFieldCreate,
  ElementRequiredFieldUpdate,
  RequiredFieldType,
  ConditionOperator,
} from "@/lib/types";

const FIELD_TYPE_LABELS: Record<RequiredFieldType, string> = {
  text: "Texto",
  number: "Numero",
  select: "Seleccion",
  boolean: "Si/No",
  date: "Fecha",
  photo: "Foto",
};

const CONDITION_OPERATOR_LABELS: Record<ConditionOperator, string> = {
  equals: "Es igual a",
  not_equals: "No es igual a",
  contains: "Contiene",
  greater_than: "Mayor que",
  less_than: "Menor que",
};

interface ElementRequiredFieldsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  element: Element | null;
  existingField?: ElementRequiredField | null;
  allFields: ElementRequiredField[];
  onSuccess?: () => void;
}

export function ElementRequiredFieldsDialog({
  open,
  onOpenChange,
  element,
  existingField,
  allFields,
  onSuccess,
}: ElementRequiredFieldsDialogProps) {
  const isEditing = !!existingField;
  const [isSaving, setIsSaving] = useState(false);

  // Form state
  const [fieldKey, setFieldKey] = useState("");
  const [fieldLabel, setFieldLabel] = useState("");
  const [fieldType, setFieldType] = useState<RequiredFieldType>("text");
  const [options, setOptions] = useState<string[]>([]);
  const [newOption, setNewOption] = useState("");
  const [isRequired, setIsRequired] = useState(true);
  const [exampleValue, setExampleValue] = useState("");
  const [llmInstruction, setLlmInstruction] = useState("");
  const [sortOrder, setSortOrder] = useState(0);
  const [isActive, setIsActive] = useState(true);

  // Validation rules
  const [minLength, setMinLength] = useState<string>("");
  const [maxLength, setMaxLength] = useState<string>("");
  const [minValue, setMinValue] = useState<string>("");
  const [maxValue, setMaxValue] = useState<string>("");
  const [pattern, setPattern] = useState("");

  // Conditional field
  const [conditionFieldId, setConditionFieldId] = useState<string>("");
  const [conditionOperator, setConditionOperator] = useState<ConditionOperator | "">("");
  const [conditionValue, setConditionValue] = useState("");

  // Reset form when dialog opens/closes or when editing different field
  useEffect(() => {
    if (open) {
      if (existingField) {
        setFieldKey(existingField.field_key);
        setFieldLabel(existingField.field_label);
        setFieldType(existingField.field_type);
        setOptions(existingField.options || []);
        setIsRequired(existingField.is_required);
        setExampleValue(existingField.example_value || "");
        setLlmInstruction(existingField.llm_instruction || "");
        setSortOrder(existingField.sort_order);
        setIsActive(existingField.is_active);

        // Validation rules
        const rules = existingField.validation_rules;
        setMinLength(rules?.min_length?.toString() || "");
        setMaxLength(rules?.max_length?.toString() || "");
        setMinValue(rules?.min_value?.toString() || "");
        setMaxValue(rules?.max_value?.toString() || "");
        setPattern(rules?.pattern || "");

        // Conditional
        setConditionFieldId(existingField.condition_field_id || "none");
        setConditionOperator(existingField.condition_operator || "");
        setConditionValue(existingField.condition_value || "");
      } else {
        // Reset to defaults for new field
        setFieldKey("");
        setFieldLabel("");
        setFieldType("text");
        setOptions([]);
        setNewOption("");
        setIsRequired(true);
        setExampleValue("");
        setLlmInstruction("");
        setSortOrder(allFields.length > 0 ? Math.max(...allFields.map((f) => f.sort_order)) + 1 : 0);
        setIsActive(true);
        setMinLength("");
        setMaxLength("");
        setMinValue("");
        setMaxValue("");
        setPattern("");
        setConditionFieldId("none");
        setConditionOperator("");
        setConditionValue("");
      }
    }
  }, [open, existingField, allFields]);

  const handleAddOption = () => {
    if (newOption.trim() && !options.includes(newOption.trim())) {
      setOptions((prev) => [...prev, newOption.trim()]);
      setNewOption("");
    }
  };

  const handleRemoveOption = (option: string) => {
    setOptions((prev) => prev.filter((o) => o !== option));
  };

  const buildValidationRules = () => {
    const rules: Record<string, unknown> = {};
    if (minLength) rules.min_length = parseInt(minLength);
    if (maxLength) rules.max_length = parseInt(maxLength);
    if (minValue) rules.min_value = parseFloat(minValue);
    if (maxValue) rules.max_value = parseFloat(maxValue);
    if (pattern) rules.pattern = pattern;
    return Object.keys(rules).length > 0 ? rules : null;
  };

  const handleSave = async () => {
    if (!element || !fieldKey.trim() || !fieldLabel.trim()) {
      toast.error("El codigo y la etiqueta son requeridos");
      return;
    }

    if (fieldType === "select" && options.length === 0) {
      toast.error("Debes agregar al menos una opcion para el campo de seleccion");
      return;
    }

    setIsSaving(true);
    try {
      const data: ElementRequiredFieldCreate | ElementRequiredFieldUpdate = {
        field_key: fieldKey.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, ""),
        field_label: fieldLabel.trim(),
        field_type: fieldType,
        options: fieldType === "select" ? options : null,
        is_required: isRequired,
        validation_rules: buildValidationRules(),
        example_value: exampleValue.trim() || null,
        llm_instruction: llmInstruction.trim() || null,
        sort_order: sortOrder,
        is_active: isActive,
        condition_field_id: conditionFieldId && conditionFieldId !== "none" ? conditionFieldId : null,
        condition_operator: conditionOperator || null,
        condition_value: conditionValue || null,
      };

      if (isEditing && existingField) {
        await api.updateElementRequiredField(existingField.id, data);
        toast.success("Campo actualizado correctamente");
      } else {
        await api.createElementRequiredField(element.id, data as ElementRequiredFieldCreate);
        toast.success("Campo creado correctamente");
      }

      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      console.error("Error saving field:", error);
      const message = error instanceof Error ? error.message : "Error desconocido";
      toast.error(`Error al guardar: ${message}`);
    } finally {
      setIsSaving(false);
    }
  };

  // Available fields for conditional (exclude self if editing)
  const availableConditionFields = allFields.filter(
    (f) => f.id !== existingField?.id && !f.condition_field_id // Don't allow chaining conditions
  );

  // Get the selected condition field to show appropriate value options
  const selectedConditionField = availableConditionFields.find((f) => f.id === conditionFieldId);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? "Editar Campo Requerido" : "Nuevo Campo Requerido"}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? `Modificar el campo "${existingField?.field_label}"`
              : `Agregar un nuevo campo de datos para ${element?.name}`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Basic Info */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="field_key">Codigo del Campo *</Label>
              <Input
                id="field_key"
                value={fieldKey}
                onChange={(e) =>
                  setFieldKey(
                    e.target.value.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "")
                  )
                }
                placeholder="ej: numero_serie"
                disabled={isSaving}
              />
              <p className="text-xs text-muted-foreground">
                Identificador unico (solo letras, numeros, guiones bajos)
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="field_label">Etiqueta *</Label>
              <Input
                id="field_label"
                value={fieldLabel}
                onChange={(e) => setFieldLabel(e.target.value)}
                placeholder="ej: Numero de Serie"
                disabled={isSaving}
              />
              <p className="text-xs text-muted-foreground">
                Nombre que vera el usuario
              </p>
            </div>
          </div>

          {/* Type and Required */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Tipo de Campo *</Label>
              <Select
                value={fieldType}
                onValueChange={(value) => setFieldType(value as RequiredFieldType)}
                disabled={isSaving}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(FIELD_TYPE_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="sort_order">Orden</Label>
              <Input
                id="sort_order"
                type="number"
                min={0}
                value={sortOrder}
                onChange={(e) => setSortOrder(parseInt(e.target.value) || 0)}
                disabled={isSaving}
              />
              <p className="text-xs text-muted-foreground">
                Menor numero = aparece primero
              </p>
            </div>
          </div>

          {/* Options for Select type */}
          {fieldType === "select" && (
            <div className="space-y-2 p-3 border rounded-lg bg-muted/30">
              <Label>Opciones de Seleccion *</Label>
              <div className="flex gap-2">
                <Input
                  value={newOption}
                  onChange={(e) => setNewOption(e.target.value)}
                  onKeyPress={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddOption();
                    }
                  }}
                  placeholder="Escribe una opcion..."
                  disabled={isSaving}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleAddOption}
                  disabled={isSaving || !newOption.trim()}
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
              {options.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  {options.map((option, idx) => (
                    <Badge key={idx} variant="secondary" className="gap-1">
                      {option}
                      <button
                        type="button"
                        onClick={() => handleRemoveOption(option)}
                        disabled={isSaving}
                        className="ml-1 hover:text-destructive"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Example and Instructions */}
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="example_value">Valor de Ejemplo</Label>
              <Input
                id="example_value"
                value={exampleValue}
                onChange={(e) => setExampleValue(e.target.value)}
                placeholder="ej: ABC123456"
                disabled={isSaving}
              />
              <p className="text-xs text-muted-foreground">
                Ejemplo para ayudar al usuario a entender el formato
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="llm_instruction">Instruccion para el Agente</Label>
              <Textarea
                id="llm_instruction"
                value={llmInstruction}
                onChange={(e) => setLlmInstruction(e.target.value)}
                placeholder="ej: Pide al usuario el numero de serie que aparece en la placa del fabricante..."
                rows={2}
                disabled={isSaving}
              />
              <p className="text-xs text-muted-foreground">
                Indicaciones para que el agente sepa como solicitar este dato
              </p>
            </div>
          </div>

          {/* Validation Rules */}
          {(fieldType === "text" || fieldType === "number") && (
            <div className="space-y-3 p-3 border rounded-lg">
              <Label className="text-sm font-medium">Reglas de Validacion (Opcional)</Label>
              <div className="grid grid-cols-2 gap-3">
                {fieldType === "text" && (
                  <>
                    <div className="space-y-1">
                      <Label htmlFor="min_length" className="text-xs">
                        Longitud Minima
                      </Label>
                      <Input
                        id="min_length"
                        type="number"
                        min={0}
                        value={minLength}
                        onChange={(e) => setMinLength(e.target.value)}
                        placeholder="ej: 5"
                        disabled={isSaving}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="max_length" className="text-xs">
                        Longitud Maxima
                      </Label>
                      <Input
                        id="max_length"
                        type="number"
                        min={0}
                        value={maxLength}
                        onChange={(e) => setMaxLength(e.target.value)}
                        placeholder="ej: 20"
                        disabled={isSaving}
                      />
                    </div>
                    <div className="col-span-2 space-y-1">
                      <Label htmlFor="pattern" className="text-xs">
                        Patron (Regex)
                      </Label>
                      <Input
                        id="pattern"
                        value={pattern}
                        onChange={(e) => setPattern(e.target.value)}
                        placeholder="ej: ^[A-Z]{3}[0-9]{6}$"
                        disabled={isSaving}
                      />
                    </div>
                  </>
                )}
                {fieldType === "number" && (
                  <>
                    <div className="space-y-1">
                      <Label htmlFor="min_value" className="text-xs">
                        Valor Minimo
                      </Label>
                      <Input
                        id="min_value"
                        type="number"
                        value={minValue}
                        onChange={(e) => setMinValue(e.target.value)}
                        placeholder="ej: 0"
                        disabled={isSaving}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="max_value" className="text-xs">
                        Valor Maximo
                      </Label>
                      <Input
                        id="max_value"
                        type="number"
                        value={maxValue}
                        onChange={(e) => setMaxValue(e.target.value)}
                        placeholder="ej: 1000"
                        disabled={isSaving}
                      />
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Conditional Field */}
          {availableConditionFields.length > 0 && (
            <div className="space-y-3 p-3 border rounded-lg border-purple-200 dark:border-purple-800 bg-purple-50/50 dark:bg-purple-950/20">
              <Label className="text-sm font-medium flex items-center gap-2">
                Campo Condicional
                <Badge variant="outline" className="text-xs">
                  Opcional
                </Badge>
              </Label>
              <p className="text-xs text-muted-foreground">
                Este campo solo se mostrara si otro campo cumple una condicion
              </p>

              <div className="space-y-3">
                <div className="space-y-1">
                  <Label htmlFor="condition_field" className="text-xs">
                    Depende del campo
                  </Label>
                  <Select
                    value={conditionFieldId}
                    onValueChange={setConditionFieldId}
                    disabled={isSaving}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Selecciona un campo..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Sin condicion</SelectItem>
                      {availableConditionFields.map((field) => (
                        <SelectItem key={field.id} value={field.id}>
                          {field.field_label}
                          <span className="text-xs text-muted-foreground ml-2">
                            ({FIELD_TYPE_LABELS[field.field_type]})
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {conditionFieldId && conditionFieldId !== "none" && (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label htmlFor="condition_operator" className="text-xs">
                        Operador
                      </Label>
                      <Select
                        value={conditionOperator}
                        onValueChange={(value) =>
                          setConditionOperator(value as ConditionOperator)
                        }
                        disabled={isSaving}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Selecciona..." />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(CONDITION_OPERATOR_LABELS).map(([value, label]) => (
                            <SelectItem key={value} value={value}>
                              {label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-1">
                      <Label htmlFor="condition_value" className="text-xs">
                        Valor
                      </Label>
                      {selectedConditionField?.field_type === "select" &&
                      selectedConditionField.options ? (
                        <Select
                          value={conditionValue}
                          onValueChange={setConditionValue}
                          disabled={isSaving}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Selecciona..." />
                          </SelectTrigger>
                          <SelectContent>
                            {selectedConditionField.options.map((opt) => (
                              <SelectItem key={opt} value={opt}>
                                {opt}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : selectedConditionField?.field_type === "boolean" ? (
                        <Select
                          value={conditionValue}
                          onValueChange={setConditionValue}
                          disabled={isSaving}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Selecciona..." />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="true">Si</SelectItem>
                            <SelectItem value="false">No</SelectItem>
                          </SelectContent>
                        </Select>
                      ) : (
                        <Input
                          id="condition_value"
                          value={conditionValue}
                          onChange={(e) => setConditionValue(e.target.value)}
                          placeholder="Valor..."
                          disabled={isSaving}
                        />
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Switches */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between p-3 border rounded-lg">
              <div>
                <Label htmlFor="is_required" className="cursor-pointer font-medium">
                  Campo Requerido
                </Label>
                <p className="text-xs text-muted-foreground">
                  El agente debe recopilar este dato obligatoriamente
                </p>
              </div>
              <Switch
                id="is_required"
                checked={isRequired}
                onCheckedChange={setIsRequired}
                disabled={isSaving}
              />
            </div>

            <div className="flex items-center justify-between p-3 border rounded-lg">
              <div>
                <Label htmlFor="is_active" className="cursor-pointer font-medium">
                  Campo Activo
                </Label>
                <p className="text-xs text-muted-foreground">
                  Los campos inactivos no se solicitan al usuario
                </p>
              </div>
              <Switch
                id="is_active"
                checked={isActive}
                onCheckedChange={setIsActive}
                disabled={isSaving}
              />
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3 justify-end pt-4 border-t">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSaving}
            >
              Cancelar
            </Button>
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Guardando...
                </>
              ) : isEditing ? (
                "Guardar Cambios"
              ) : (
                "Crear Campo"
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
