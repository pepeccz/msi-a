# Arquitectura de Conversación - Estado: REVIEW_SUMMARY

## 📋 Metadatos del Estado

| Campo | Valor |
|-------|-------|
| **Nombre del Estado** | Revisión y Confirmación Final |
| **Código del Estado** | `review_summary` |
| **Versión** | 1.0 |
| **Fecha de Creación** | Febrero 2026 |
| **Responsable** | Equipo de Conversación |
| **Estado de Implementación** | En producción |

---

## 🎯 Propósito y Alcance

### Objetivo Principal
Presentar al usuario un resumen completo del expediente recopilado, permitir correcciones de último momento, y obtener confirmación explícita antes de enviar el caso a revisión humana.

### Objetivos Secundarios
- Permitir edición de cualquier sección del expediente
- Mostrar transparencia total de datos recopilados
- Crear registro de confirmación explícita
- Generar escalación para revisión humana

### Definición del Éxito
El estado se considera completado cuando:
1. El usuario ha revisado el resumen completo
2. El usuario confirma explícitamente que todo es correcto ("sí", "correcto", "adelante")
3. Se crea la escalación en estado "pending"
4. El expediente queda en estado "completed"

---

## 🔄 Contexto de Navegación

### Estados Predecesores

| Estado Origen | Activador | Condiciones |
|---------------|-----------|-------------|
| COLLECT_WORKSHOP | Datos del taller completos | Taller (MSI o propio) guardado |

### Estados Sucesores

| Estado Destino | Activador | Condiciones |
|----------------|-----------|-------------|
| COMPLETED | `finalizar_expediente()` + confirmación usuario | Usuario confirma que todo es correcto |
| COLLECT_BASE_DOCS | `editar_expediente(seccion="documentacion")` | Usuario quiere corregir documentación base |
| COLLECT_PERSONAL | `editar_expediente(seccion="personal")` | Usuario quiere corregir datos personales |
| COLLECT_VEHICLE | `editar_expediente(seccion="vehiculo")` | Usuario quiere corregir datos del vehículo |
| COLLECT_WORKSHOP | `editar_expediente(seccion="taller")` | Usuario quiere cambiar decisión de taller |
| IDLE | `cancelar_expediente()` | Usuario decide cancelar completamente |

**Nota**: No se permite edición de elementos ya recopilados (COLLECT_ELEMENT_DATA) desde este estado para evitar inconsistencias.

---

## 🛠️ Capacidades

### Herramientas Disponibles

#### Herramientas de Acción

| Herramienta | Propósito | Efecto | Salida |
|-------------|-----------|--------|--------|
| `finalizar_expediente` | Confirmar y enviar expediente | Crea escalación, marca expediente "completed" | Confirmación + ID de escalación |
| `editar_expediente` | Navegar a sección específica para corrección | Transiciona a estado de edición seleccionado | Confirmación de navegación |

#### Herramientas Universales

| Herramienta | Propósito |
|-------------|-----------|
| `cancelar_expediente` | Cancelar completamente el proceso |
| `escalar_a_humano` | Solicitar ayuda humana |
| `obtener_estado_expediente` | Consultar progreso |

---

## 📊 Datos del Estado

### Resumen Presentado al Usuario

El resumen incluye:

```
RESUMEN DEL EXPEDIENTE
======================

DATOS PERSONALES:
  Nombre: [nombre] [apellidos]
  DNI/CIF: [dni_cif]
  Email: [email]
  Domicilio: [domicilio_calle], [localidad], [provincia], [cp]
  ITV: [itv_nombre]

VEHÍCULO:
  Marca/Modelo: [marca] [modelo]
  Matrícula: [matricula]

TALLER:
  [MSI aporta certificado] O [Datos del taller propio]

ELEMENTOS A HOMOLOGAR:
  ✓ [elemento 1] - [status]
  ✓ [elemento 2] - [status]
  ...

DOCUMENTACIÓN BASE:
  ✓ Ficha técnica, permiso de circulación, vistas del vehículo

FOTOS RECIBIDAS: [N]

TARIFA: [X] EUR + IVA
```

---

## 📜 Reglas de Negocio

### Reglas de Confirmación

1. **Confirmación Explícita Requerida**
   - **Descripción**: El usuario debe responder afirmativamente de forma clara ("sí", "correcto", "adelante")
   - **Prioridad**: Crítica
   - **Consecuencia**: Sin confirmación clara, no se finaliza

2. **Rechazo Aceptable**
   - **Descripción**: Si el usuario dice "no" o "hay errores", se debe ofrecer edición
   - **Prioridad**: Alta
   - **Acción**: "¿Qué quieres corregir? Puedes editar: datos personales, vehículo, taller..."

3. **No Finalización Ambigua**
   - **Descripción**: Respuestas como "ok", "vale" deben confirmarse con "¿Todo es correcto? Responde sí o no"
   - **Prioridad**: Alta

### Reglas de Edición

1. **Secciones Editables**
   - Datos personales, vehículo, taller, documentación base
   - **NO elementos ya recopilados** (requeriría reinicio completo)

2. **Retorno Automático**
   - Después de editar cualquier sección, se retorna a REVIEW_SUMMARY (no se avanza por el flujo)

---

## 🎭 Casos de Uso

### Caso Principal: Confirmación Directa

**Flujo**:
1. Agente: [Muestra resumen completo]
            
            "¿Todo es correcto? Responde 'Sí' para enviar el expediente
            o 'No' si necesitas modificar algo."
2. Usuario: "Sí, todo correcto"
3. Agente: [Valida confirmación]
4. Agente: [Llama `finalizar_expediente()`]
5. Agente: "¡Perfecto! Tu expediente ha sido enviado para revisión.
            Un agente lo revisará y se pondrá en contacto contigo pronto."
6. [Transiciona a COMPLETED]

### Caso Alternativo: Corrección de Datos

**Flujo**:
1. Agente: [Muestra resumen]
2. Usuario: "No, el email está mal"
3. Agente: "¿Qué quieres corregir?"
4. Usuario: "El email"
5. Agente: [Llama `editar_expediente(seccion="personal")`]
6. [Transiciona a COLLECT_PERSONAL con datos pre-llenos]
7. [Usuario corrige email]
8. [Retorna a REVIEW_SUMMARY con nuevo resumen]
9. Usuario: "Sí, ahora sí"
10. [Finaliza]

### Caso de Cancelación

**Flujo**:
1. Agente: [Muestra resumen]
2. Usuario: "Mejor cancelo todo"
3. Agente: "¿Estás seguro? Se perderá toda la información recopilada."
4. Usuario: "Sí, cancela"
5. Agente: [Llama `cancelar_expediente()`]
6. Agente: "Expediente cancelado. Si necesitas ayuda en el futuro, 
            puedes escribirme cuando quieras."
7. [Transiciona a IDLE]

---

## 💬 Interacciones Típicas

### Escenario 1: Confirmación Exitosa

```
Agente: RESUMEN DEL EXPEDIENTE
       ======================
       
       DATOS PERSONALES:
         Nombre: Ana Martínez Ruiz
         DNI/CIF: 87654321B
         Email: ana@mail.com
         Domicilio: Avda. Diagonal 45, Barcelona, Barcelona, 08001
         ITV: ITV Barcelona Centro
       
       VEHÍCULO:
         Marca/Modelo: Yamaha MT-07
         Matrícula: 9876DEF
       
       TALLER:
         MSI aporta el certificado
       
       ELEMENTOS A HOMOLOGAR:
         ✓ Escape
         ✓ Manillar
       
       DOCUMENTACIÓN BASE:
         ✓ Ficha técnica, permiso de circulación y vistas del vehículo
       
       FOTOS RECIBIDAS: 8
       
       TARIFA: 890 EUR + IVA
       
       ¿Todo es correcto? Responde "Sí" para enviar el expediente
       o "No" si necesitas modificar algo.

Usuario: Sí, todo correcto

Agente: [Procesa finalización]

       ¡Perfecto! Tu expediente ha sido enviado para revisión.
       Un agente lo revisará y se pondrá en contacto contigo pronto.
       
       Gracias por confiar en MSI Automotive.
       
       [Transiciona a COMPLETED]
```

### Escenario 2: Corrección de Datos

```
Agente: [Muestra resumen]

Usuario: No, la matrícula está mal

Agente: ¿Qué quieres corregir?
       • Datos personales
       • Datos del vehículo
       • Taller
       • Documentación base

Usuario: Los del vehículo

Agente: [Navega a COLLECT_VEHICLE]

       Dime los datos correctos del vehículo...
       [Usuario corrige]
       [Retorna a REVIEW_SUMMARY]

Agente: [Muestra resumen actualizado]

       ¿Ahora todo es correcto?

Usuario: Sí

Agente: [Finaliza]
```

---

## ⚠️ Consideraciones

### Importancia de la Confirmación

Este estado es el último punto de control antes de:
- Crear una escalación (coste operativo)
- Comprometer recursos humanos de revisión
- Iniciar procesos administrativos

Por eso la confirmación debe ser:
- **Explícita**: No asumir "ok" o "vale" como confirmación
- **Informada**: Usuario sabe exactamente qué se enviará
- **Registrada**: Queda constancia de la aceptación

### Sin Vuelta Atrás

Una vez confirmado:
- No se puede editar el expediente (está "completed")
- Las correcciones requieren nueva escalación
- El proceso continúa manualmente con agentes humanos

---

## 📚 Referencias

- **Anterior**: [06-estado-collect-workshop.md](06-estado-collect-workshop.md)
- **Siguiente**: Estado terminal COMPLETED (no hay más estados después)
- **Transiciones**: [08-transiciones-fsm.md](08-transiciones-fsm.md)

---

**Nota**: Este estado es crítico para la calidad de datos y la satisfacción del cliente. Un error aquí puede resultar en retrabajo costoso.
