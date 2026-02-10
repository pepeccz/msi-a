# Arquitectura de Conversación - Estado: COLLECT_VEHICLE

## 📋 Metadatos del Estado

| Campo | Valor |
|-------|-------|
| **Nombre del Estado** | Recolección de Datos del Vehículo |
| **Código del Estado** | `collect_vehicle` |
| **Versión** | 1.0 |
| **Fecha de Creación** | Febrero 2026 |
| **Responsable** | Equipo de Conversación |
| **Estado de Implementación** | En producción |

---

## 🎯 Propósito y Alcance

### Objetivo Principal
Recopilar la información de identificación del vehículo: marca, modelo, año de matriculación, matrícula y número de bastidor.

### Datos Recolectados (Slots)

| Campo | Tipo | Obligatorio | Validación | Descripción |
|-------|------|-------------|------------|-------------|
| `marca` | Texto | Sí | - | Marca del vehículo (ej: BMW, Honda) |
| `modelo` | Texto | Sí | - | Modelo específico (ej: R1200GS, CBF600) |
| `anio` | Año | Sí | 1900-2030 | Año de primera matriculación |
| `matricula` | Matrícula | Sí | Formato español | Matrícula del vehículo |
| `bastidor` | Texto | No | - | Número de bastidor (VIN) |

### Validación de Matrícula Española

- **Formato moderno**: 1234ABC (4 dígitos + 3 letras)
- **Formato antiguo**: A1234BC (1-2 letras + 4 dígitos + 0-2 letras)
- **Normalización**: Mayúsculas, sin espacios ni guiones

---

## 🔄 Contexto de Navegación

### Estados Predecesores

| Estado Origen | Activador | Condiciones |
|---------------|-----------|-------------|
| COLLECT_PERSONAL | Datos personales completos | Todos los campos personales guardados |
| REVIEW_SUMMARY | Edición de sección "vehículo" | Usuario solicita corregir datos del vehículo |

### Estados Sucesores

| Estado Destino | Activador | Condiciones |
|----------------|-----------|-------------|
| COLLECT_WORKSHOP | `actualizar_datos_expediente()` | Todos los campos vehículo válidos completados |

---

## 🛠️ Capacidades

### Herramientas Disponibles

| Herramienta | Propósito | Entrada | Salida |
|-------------|-----------|---------|--------|
| `actualizar_datos_expediente` | Guardar datos del vehículo | Mapa de campos de vehículo | Confirmación + campos faltantes |

---

## 📜 Reglas de Negocio

### Reglas de Validación

1. **Año Razonable**
   - Rango: 1900 a 2030
   - **Acción si falla**: "Por favor, indica un año válido entre 1900 y 2030"

2. **Matrícula Válida**
   - Debe coincidir con formato español
   - **Acción si falla**: "La matrícula no tiene formato español válido"

3. **Consistencia Implícita**
   - Año de matriculación debe ser razonable para el modelo
   - (Nota: No se valida estrictamente, es advertencia)

---

## 🎭 Casos de Uso

### Caso Principal: Datos Completos

**Flujo**:
1. Agente: "Ahora los datos del vehículo:
            • Marca
            • Modelo
            • Matrícula
            • Año de primera matriculación
            
            Ejemplo: BMW R1200GS, 1234ABC, 2019"
2. Usuario: "Honda CBF600, 5678XYZ, 2015"
3. Agente: [Valida y guarda]
4. Agente: "Perfecto. Ahora una pregunta sobre el taller..."
5. [Transiciona a COLLECT_WORKSHOP]

### Caso Alternativo: Edición desde Review

**Flujo**:
1. [En REVIEW_SUMMARY]
2. Usuario: "La matrícula está mal, es 5679XYZ no 5678XYZ"
3. Agente: [Carga COLLECT_VEHICLE con datos actuales]
4. Agente: "¿Qué datos del vehículo quieres corregir?"
5. Usuario: "Matrícula: 5679XYZ"
6. Agente: [Actualiza solo matrícula]
7. [Retorna a REVIEW_SUMMARY]

---

## 💬 Interacción Típica

```
Agente: Ahora necesito los datos del vehículo:

       • Marca
       • Modelo
       • Matrícula
       • Año de primera matriculación

       Puedes enviarlo en un solo mensaje, por ejemplo:
       "BMW R1200GS, 1234ABC, 2019"

Usuario: Yamaha MT-07, 9876DEF, 2020

Agente: [Valida y guarda]

       ¡Perfecto! Datos del vehículo guardados.
       
       Ahora necesito saber sobre el certificado del taller...
       [Transiciona a COLLECT_WORKSHOP]
```

---

## ⚠️ Consideraciones

### Simplicidad Deliberada

Este estado es intencionalmente simple porque:
1. Los datos del vehículo son generalmente conocidos por el propietario
2. Menos campos que en datos personales
3. No hay campos condicionales complejos
4. Validaciones básicas y claras

### Datos Opcionales

El bastidor (VIN) es opcional porque:
- No siempre es visible fácilmente en todos los vehículos
- Puede obtenerse de la ficha técnica ya proporcionada
- No es crítico para el proceso de homologación inicial

---

## 📚 Referencias

- **Anterior**: [04-estado-collect-personal.md](04-estado-collect-personal.md)
- **Siguiente**: [06-estado-collect-workshop.md](06-estado-collect-workshop.md)
- **Transiciones**: [08-transiciones-fsm.md](08-transiciones-fsm.md)

---

**Nota**: Estado simple pero esencial para la identificación correcta del vehículo a homologar.
