# Plan: Fix Variant Keywords Empty Array 422 Error

**Fecha de Creación**: 3 de Febrero de 2026  
**Autor**: architect  
**Estado**: PENDIENTE APROBACIÓN

---

## Resumen Ejecutivo

Al crear variantes de elementos desde el admin panel, el formulario envía `keywords: []` (array vacío) si el usuario NO agrega keywords manualmente. El backend rechaza la petición con **422 Unprocessable Entity** debido a una validación Pydantic que exige al menos un keyword.

**Solución propuesta**: Heredar keywords del elemento padre automáticamente cuando el usuario no proporciona keywords, con fallback al `variant_code` para garantizar que nunca se envíe un array vacío.

**Impacto**: Fix de 5 minutos sin cambios en el backend ni breaking changes. Solo requiere modificación del formulario en frontend.

---

## Servicios Afectados

- [ ] Database
- [ ] API
- [x] Admin Panel
- [ ] Agent
- [ ] Shared

---

## Análisis del Problema

### Error Actual

**HTTP 422 Unprocessable Entity** al crear variante con payload:

```json
{
  "category_id": "...",
  "code": "SUSPENSION_DELANTERA",
  "name": "Suspensión Delantera",
  "keywords": [],  // ← PROBLEMA: Array vacío
  "parent_element_id": "...",
  "variant_type": "suspension_type",
  "variant_code": "DELANTERA",
  "inherit_parent_data": true,
  "is_active": true
}
```

**Backend validation error** (línea 146-150 en `api/models/element.py`):

```python
@field_validator("keywords")
@classmethod
def validate_keywords(cls, v):
    """Ensure keywords is not empty."""
    if not v:
        raise ValueError("At least one keyword is required")
    return v
```

**Stack trace** (típico):
```
422 Unprocessable Entity
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "keywords"],
      "msg": "Value error, At least one keyword is required",
      "input": []
    }
  ]
}
```

### Causa Raíz

**Archivo**: `admin-panel/src/components/elements/create-variant-dialog.tsx`

**Línea 46**: Estado inicial del formulario
```typescript
const [formData, setFormData] = useState({
  name: "",
  variant_code: "",
  variant_type: parentElement.variant_type || "",
  keywords: [] as string[],  // ← CAUSA: Array vacío por defecto
  inherit_parent_data: true,
});
```

**Línea 113**: Payload enviado sin transformación
```typescript
const data: ElementCreate = {
  category_id: parentElement.category_id,
  code: generatedCode,
  name: formData.name.trim(),
  keywords: formData.keywords,  // ← PROBLEMA: Puede estar vacío
  parent_element_id: parentElement.id,
  variant_type: formData.variant_type.trim() || null,
  variant_code: formData.variant_code.toUpperCase().trim(),
  inherit_parent_data: formData.inherit_parent_data,
  is_active: true,
};
```

**Flujo del error**:
1. Usuario abre diálogo de "Nueva Variante"
2. Completa nombre y variant_code (requeridos)
3. NO agrega keywords manualmente (campo opcional en UI)
4. Submit → `formData.keywords` = `[]`
5. API rechaza con 422

### Impacto

**Quiénes se ven afectados**:
- Administradores del sistema que gestionan el catálogo de elementos
- Usuarios que intentan crear variantes sin conocimiento técnico de keywords

**Cuándo ocurre**:
- Al crear CUALQUIER variante de elemento sin agregar keywords explícitamente
- Afecta todas las categorías (motos-part, aseicars-prof, etc.)

**Frecuencia**:
- Alta: Keywords son técnicos y poco intuitivos para usuarios finales
- Los usuarios esperan heredar keywords del padre automáticamente

**Severidad**: Media-Alta
- Bloquea la creación de variantes → requiere workaround manual de agregar keywords
- No afecta a funcionalidad existente (elementos base se crean correctamente)

---

## Solución Propuesta

### Opción Elegida: **Herencia Automática de Keywords con Fallback**

**Implementación**: Modificar `create-variant-dialog.tsx` línea 113 para detectar keywords vacíos y usar keywords del padre + variant_code como fallback.

```typescript
// Línea 113 (modificada)
const data: ElementCreate = {
  category_id: parentElement.category_id,
  code: generatedCode,
  name: formData.name.trim(),
  
  // ✅ NUEVO: Heredar keywords si está vacío
  keywords: formData.keywords.length > 0 
    ? formData.keywords  // Usuario proporcionó keywords custom
    : [
        ...parentElement.keywords,  // Heredar del padre
        formData.variant_code.toLowerCase()  // + variant_code como keyword adicional
      ],
  
  parent_element_id: parentElement.id,
  variant_type: formData.variant_type.trim() || null,
  variant_code: formData.variant_code.toUpperCase().trim(),
  inherit_parent_data: formData.inherit_parent_data,
  is_active: true,
};
```

**Por qué esta opción**:
- ✅ **Semánticamente correcto**: Las variantes comparten el contexto semántico del padre
- ✅ **Fix mínimo**: 1 línea de código, sin cambios en backend
- ✅ **No breaking**: Si el usuario agrega keywords custom, se respetan
- ✅ **UX mejorada**: Usuario no necesita pensar en keywords técnicos
- ✅ **Garantía de datos**: `parentElement.keywords` siempre tiene al menos 1 keyword (validado en backend)
- ✅ **Keyword adicional**: `variant_code` como keyword extra ayuda a matching específico de variante

**Ejemplo práctico**:

```
Padre: SUSPENSION
  keywords: ["suspension", "amortiguador", "horquilla"]

Usuario crea variante:
  variant_code: "DELANTERA"
  keywords: []  (vacío, no agrega nada)

Backend recibe:
  keywords: ["suspension", "amortiguador", "horquilla", "delantera"]
                ↑________________________________↑           ↑
                     Heredado del padre              variant_code
```

---

## Alternativas Consideradas

### Opción 1: Herencia Simple (Sin Fallback)

```typescript
keywords: formData.keywords.length > 0 
  ? formData.keywords 
  : parentElement.keywords  // Solo hereda
```

**Pros**:
- Más simple
- Semánticamente puro

**Contras**:
- ⚠️ Si padre no tiene keywords, falla igual (poco probable pero posible)
- Pierde oportunidad de agregar keyword específico de variante

**Complejidad**: Baja (5 min)

**Decisión**: ❌ Rechazada - Opción elegida es más robusta

---

### Opción 2: Hacer Keywords Obligatorios en UI

```typescript
// Validación en submit
if (formData.keywords.length === 0) {
  toast.error("Debes agregar al menos un keyword");
  return;
}
```

**Pros**:
- Usuario explícito sobre keywords
- No asume nada

**Contras**:
- ❌ Peor UX: Fricción innecesaria para el usuario
- ❌ Keywords son técnicos → barrera de entrada
- ❌ No resuelve el problema de fondo (datos repetitivos)

**Complejidad**: Baja (5 min)

**Decisión**: ❌ Rechazada - Empeora UX sin beneficio claro

---

### Opción 3: Cambiar Validación Backend (NO Recomendada)

```python
# api/models/element.py
@field_validator("keywords")
@classmethod
def validate_keywords(cls, v):
    """Allow empty keywords for variants."""
    if not v:
        return ["placeholder"]  # Auto-generar placeholder
    return v
```

**Pros**:
- Frontend no cambia

**Contras**:
- ❌ Viola contrato del modelo (keywords siempre debe ser semántico)
- ❌ Puede romper lógica del agente (element matching por keywords)
- ❌ "placeholder" no es un keyword válido → matching fallido
- ❌ Requiere cambio en backend + potencial breaking change

**Complejidad**: Baja (10 min) pero con riesgos altos

**Decisión**: ❌ Rechazada - Viola principios de arquitectura

---

### Opción 4: Auto-generar Solo con Variant Code

```typescript
keywords: formData.keywords.length > 0
  ? formData.keywords
  : [formData.variant_code.toLowerCase()]
```

**Pros**:
- Garantiza al menos 1 keyword
- Simple

**Contras**:
- ⚠️ Pierde contexto semántico del padre (ej: "delantera" sin "suspension")
- ⚠️ Matching más débil en agente

**Complejidad**: Baja (5 min)

**Decisión**: ❌ Rechazada - Opción elegida es mejor semánticamente

---

## Tareas por Servicio

### Admin Panel → frontend-dev

- [ ] **Modificar `create-variant-dialog.tsx` línea 113-117**
  - Agregar lógica de herencia de keywords
  - Heredar `parentElement.keywords` si `formData.keywords` vacío
  - Agregar `variant_code.toLowerCase()` como keyword adicional
  - **Estimación**: 5 minutos

- [ ] **Testing manual**
  - Crear variante sin agregar keywords → verificar hereda del padre + variant_code
  - Crear variante con keywords custom → verificar NO hereda (respeta custom)
  - Verificar en Network tab del navegador: POST debe ser 201, no 422
  - **Estimación**: 10 minutos

**Total estimado**: 15 minutos

**Interfaz**: No cambia
- `ElementCreate` type ya soporta `keywords: string[]` (no hay cambios en tipos)
- No se agregan props ni se cambia la firma del componente

---

## Dependencias entre Tareas

**No hay dependencias** - Es una tarea única y autocontenida en el frontend.

---

## Tests Requeridos

### Tests Manuales (15 minutos total)

- [ ] **Test 1: Herencia automática de keywords** (5 min)
  - **Setup**: Elemento padre "SUSPENSION" con keywords `["suspension", "amortiguador"]`
  - **Acción**: Crear variante "DELANTERA" sin agregar keywords
  - **Esperado**: Backend recibe `keywords: ["suspension", "amortiguador", "delantera"]`
  - **Verificar**: Network tab → POST → payload → keywords array tiene 3 elementos
  - **Resultado**: ✅ 201 Created

- [ ] **Test 2: Keywords custom respetados** (5 min)
  - **Setup**: Mismo elemento padre "SUSPENSION"
  - **Acción**: Crear variante "DELANTERA" con keywords custom `["frontal", "delantera"]`
  - **Esperado**: Backend recibe `keywords: ["frontal", "delantera"]` (NO hereda)
  - **Verificar**: Network tab → keywords solo contiene los 2 custom
  - **Resultado**: ✅ 201 Created

- [ ] **Test 3: Elemento base sin parent_element_id** (2 min)
  - **Acción**: Verificar que crear elemento BASE (no variante) sigue funcionando
  - **Esperado**: No se rompe (no hay parent → no intenta heredar)
  - **Resultado**: ✅ Funciona correctamente

- [ ] **Test 4: Verificar variant_code en keywords** (3 min)
  - **Setup**: Crear variante "TRASERA" sin keywords
  - **Esperado**: Keywords incluyen "trasera" (en minúsculas)
  - **Verificar**: En admin panel → ver elemento creado → keywords contiene "trasera"
  - **Resultado**: ✅ Keyword adicional presente

### Criterio de Éxito para Tests

- ✅ TODOS los tests manuales pasan
- ✅ NO hay errores 422 al crear variantes sin keywords
- ✅ Keywords custom se respetan (no se sobrescriben)
- ✅ NO se rompe creación de elementos base

---

## Criterios de Aceptación

- [ ] **Usuario puede crear variante sin agregar keywords manualmente**
  - Formulario NO marca keywords como requeridos
  - Submit exitoso (201 Created)

- [ ] **Keywords heredadas del elemento padre correctamente**
  - Backend recibe `parentElement.keywords + [variant_code]`
  - Verificable en PostgreSQL: `SELECT keywords FROM elements WHERE code = 'SUSPENSION_DELANTERA'`

- [ ] **Keywords custom NO se sobrescriben**
  - Si usuario agrega keywords, se usan SOLO esos (no hereda)
  - Verificable en Network tab

- [ ] **NO se rompe la creación de elementos base (sin parent)**
  - Elementos sin `parent_element_id` siguen requiriendo keywords manuales
  - Validación backend sigue aplicándose correctamente

- [ ] **Variant code incluido como keyword adicional**
  - Si variant_code = "DELANTERA", keywords incluye "delantera" (lowercase)
  - Mejora matching en agente

---

## Checklist de Verificación Pre-Deploy

- [ ] **Tests manuales ejecutados y documentados** (15 min)
  - Captura de pantalla del Network tab (202 → 201 exitoso)
  - Verificar en PostgreSQL: `\x on; SELECT * FROM elements WHERE code LIKE '%DELANTERA%';`

- [ ] **No hay errores en consola del navegador**
  - Abrir DevTools → Console → verificar sin errores ni warnings
  - Verificar en Network tab → NO hay requests fallidos

- [ ] **Build de Next.js exitoso** (2 min)
  - `cd admin-panel && npm run build`
  - Verificar `✓ Compiled successfully`

- [ ] **Code review** (5 min)
  - Revisar que la lógica de herencia es correcta
  - Verificar que `parentElement.keywords` existe (TypeScript types correctos)
  - Confirmar que `.toLowerCase()` se aplica a variant_code

- [ ] **Verificar con elementos reales en dev**
  - Probar con categoría "motos-part" → "SUSPENSION" → crear "DELANTERA"
  - Probar con categoría "aseicars-prof" → cualquier elemento con variantes

---

## Riesgos y Consideraciones

### Riesgos Identificados

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| **Padre sin keywords** | Muy Baja | Alto | Imposible por validación backend: todos los elementos tienen ≥1 keyword |
| **`parentElement.keywords` undefined** | Muy Baja | Alto | TypeScript type `Element` garantiza que existe (ver `lib/types.ts`) |
| **Duplicados en keywords array** | Baja | Bajo | No es problema: backend no valida duplicados, agent usa Set internally |
| **Variant_code con espacios** | Baja | Bajo | Ya se aplica `.toUpperCase().trim()` en línea 120 → usar ese valor |

### Consideraciones de Diseño

1. **No validar duplicados en frontend**
   - Si padre tiene `["suspension"]` y variant_code es "SUSPENSION", resultaría en `["suspension", "suspension"]`
   - **Decisión**: Aceptar duplicados → el agente usa Set para matching (elimina duplicados internamente)

2. **Normalización de variant_code**
   - Aplicar `.toLowerCase()` para consistencia con keywords del padre (todos en minúsculas)
   - Ya se hace `.trim()` → reutilizar esa transformación

3. **TypeScript safety**
   - `parentElement` es tipo `Element | ElementWithImagesAndChildren` (ver props)
   - Ambos tipos tienen `keywords: string[]` → seguro acceder
   - No necesita optional chaining (`?.`) ni null checks

---

## Rollback Plan

### Si algo sale mal

**Escenario 1: Error en producción**
```bash
# Revertir commit
git revert <commit-hash>

# Deploy inmediato
docker-compose restart admin-panel
```

**Tiempo de rollback**: 2 minutos

**Escenario 2: Comportamiento inesperado en testing**
```typescript
// Rollback temporal en código (línea 113)
keywords: formData.keywords,  // Volver a versión original

// O forzar keywords no vacíos
if (formData.keywords.length === 0) {
  toast.error("Debes agregar keywords (temporal fix)");
  return;
}
```

**Sin impacto en backend**: No hay cambios en API → rollback solo afecta frontend

---

## Timeline Estimado

| Fase | Duración | Responsable |
|------|----------|-------------|
| **Modificación código** | 5 min | frontend-dev |
| **Testing manual** | 15 min | frontend-dev |
| **Build + verificación** | 5 min | frontend-dev |
| **Deploy** | 2 min | deploy-dev (tras aprobación) |
| **Total** | **27 minutos** | — |

---

## Aprobación y Next Steps

### Esperando Aprobación de:
- [ ] **Usuario** - Confirmar solución propuesta

### Tras Aprobación:
1. **frontend-dev** implementa cambio en `create-variant-dialog.tsx`
2. **frontend-dev** ejecuta tests manuales
3. **frontend-dev** reporta resultados
4. **Usuario** da OK final
5. **deploy-dev** ejecuta deploy (con confirmación)

---

**Plan creado por**: architect  
**Fecha**: 3 de Febrero de 2026  
**Versión**: 1.0
