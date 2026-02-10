# Arquitectura de Conversación - Estado: COLLECT_PERSONAL

## 📋 Metadatos del Estado

| Campo | Valor |
|-------|-------|
| **Nombre del Estado** | Recolección de Datos Personales |
| **Código del Estado** | `collect_personal` |
| **Versión** | 1.0 |
| **Fecha de Creación** | Febrero 2026 |
| **Responsable** | Equipo de Conversación |
| **Estado de Implementación** | En producción |

---

## 🎯 Propósito y Alcance

### Objetivo Principal
Recopilar la información personal completa del titular del vehículo: identificación, contacto, domicilio fiscal, y preferencias de ITV.

### Datos Recolectados (Slots)

| Campo | Tipo | Obligatorio | Validación | Descripción |
|-------|------|-------------|------------|-------------|
| `nombre` | Texto | Sí | Longitud > 1 | Nombre del titular |
| `apellidos` | Texto | Sí | Longitud > 1 | Apellidos del titular |
| `dni_cif` | Texto | Sí | Formato DNI/NIE/CIF | Documento de identidad |
| `email` | Email | Sí | Regex email | Correo electrónico |
| `telefono` | Teléfono | No | Formato español | Teléfono de contacto (adicional) |
| `domicilio_calle` | Texto | Sí | Longitud > 5 | Dirección completa |
| `domicilio_localidad` | Texto | Sí | - | Ciudad/Municipio |
| `domicilio_provincia` | Texto | Sí | - | Provincia |
| `domicilio_cp` | Código postal | Sí | 5 dígitos, rango 01000-52999 | Código postal |
| `itv_nombre` | Texto | Sí | - | Nombre de la estación ITV preferida |

---

## 🔄 Contexto de Navegación

### Estados Predecesores

| Estado Origen | Activador | Condiciones |
|---------------|-----------|-------------|
| COLLECT_BASE_DOCS | Confirmación de documentación base | Documentación base recibida |
| REVIEW_SUMMARY | Edición de sección "personal" | Usuario solicita corregir datos personales |

### Estados Sucesores

| Estado Destino | Activador | Condiciones |
|----------------|-----------|-------------|
| COLLECT_VEHICLE | `actualizar_datos_expediente()` | Todos los campos personales válidos completados |

---

## 🛠️ Capacidades

### Herramientas Disponibles

| Herramienta | Propósito | Entrada | Salida |
|-------------|-----------|---------|--------|
| `actualizar_datos_expediente` | Guardar datos personales | Mapa de campos personales | Confirmación + campos faltantes |

### Reciclaje de Datos

Si el usuario tiene expedientes anteriores, el sistema puede:
1. Cargar datos previos automáticamente
2. Mostrar resumen al usuario
3. Preguntar "¿Son correctos estos datos?"
4. Si sí → Autocompletar y saltar a COLLECT_VEHICLE
5. Si no → Pedir datos nuevos

---

## 📜 Reglas de Negocio

### Reglas de Validación

1. **DNI/NIE/CIF Válido**
   - DNI: 8 dígitos + letra
   - NIE: X/Y/Z + 7 dígitos + letra
   - CIF: Letra + 8 dígitos
   - **Acción si falla**: Mensaje específico por tipo de documento

2. **Email Válido**
   - Formato estándar con @ y dominio válido
   - **Acción si falla**: Pedir corrección

3. **Código Postal Español**
   - 5 dígitos
   - Rango válido para provincias españolas
   - **Acción si falla**: Pedir código correcto

4. **Campos Obligatorios**
   - No se puede transicionar hasta tener todos los campos obligatorios
   - Teléfono es opcional (ya tenemos WhatsApp)

---

## 🎭 Casos de Uso

### Caso Principal: Datos Nuevos

**Flujo**:
1. Agente: "Ahora necesito tus datos personales:
            • Nombre y apellidos
            • DNI o CIF
            • Email
            • Domicilio completo
            • Nombre de la ITV
            
            Puedes enviarlo todo junto."
2. Usuario: "Juan García López, 12345678A, juan@email.com, 
            C/ Mayor 15, Madrid, Madrid, 28001, ITV Aluche"
3. Agente: [Parsea y llama `actualizar_datos_expediente`]
4. Agente: "Perfecto, datos guardados. Ahora los del vehículo..."
5. [Transiciona a COLLECT_VEHICLE]

### Caso Alternativo: Reutilización de Datos Previos

**Flujo**:
1. Agente: "Veo que ya tienes datos guardados de un expediente anterior:
            • Juan García López
            • juan@email.com
            • C/ Mayor 15, Madrid
            
            ¿Son correctos? Responde 'sí' para usarlos o 'no' para cambiarlos."
2. Usuario: "Sí"
3. Agente: [Carga datos automáticamente]
4. [Transiciona directo a COLLECT_VEHICLE]

### Caso de Error: DNI Inválido

**Flujo**:
1. Usuario: "Mi DNI es 1234567A"
2. Agente: [Validación falla - falta dígito]
3. Agente: "El DNI parece incompleto. Debe tener 8 dígitos y una letra 
            (ejemplo: 12345678A). ¿Cuál es tu DNI completo?"
4. Usuario: "12345678A"
5. [Continúa flujo normal]

---

## 💬 Interacción Típica

```
Agente: ¡Perfecto! Ya tengo toda la información de los elementos.

       Ahora necesito tus datos personales:
       • Nombre y apellidos
       • DNI o CIF
       • Email
       • Domicilio completo (calle, número, localidad, provincia, CP)
       • Nombre de la ITV donde pasarás la inspección

       Puedes enviarlo en un solo mensaje, por ejemplo:
       "Juan García López, 12345678A, juan@email.com
       C/ Mayor 10, Madrid, Madrid, 28001
       ITV Alcobendas"

Usuario: Ana Martínez Ruiz, 87654321B, ana@mail.com
       Avda. Diagonal 45, Barcelona, Barcelona, 08001
       ITV Barcelona Centro

Agente: [Valida y guarda datos]

       ¡Gracias Ana! Datos personales guardados.
       Ahora necesito los datos de tu vehículo...
       [Transiciona a COLLECT_VEHICLE]
```

---

## ⚠️ Consideraciones

### Privacidad y GDPR

- Todos los datos personales se almacenan encriptados
- El usuario tiene derecho a solicitar eliminación
- No se comparten datos con terceros sin consentimiento
- Se informa al usuario sobre uso de datos

### Recuperación desde Review

Este estado es accesible desde REVIEW_SUMMARY si el usuario detecta errores:
- Usuario dice "Quiero cambiar mis datos personales"
- Se carga este estado con datos actuales pre-llenos
- Usuario corrige lo necesario
- Se retorna a REVIEW_SUMMARY (no se avanza por el flujo normal)

---

## 📚 Referencias

- **Anterior**: [03-estado-collect-base-docs.md](03-estado-collect-base-docs.md)
- **Siguiente**: [05-estado-collect-vehicle.md](05-estado-collect-vehicle.md)
- **Transiciones**: [08-transiciones-fsm.md](08-transiciones-fsm.md)

---

**Nota**: Este estado es crítico para la validez legal del expediente. La validación de documentos de identidad debe ser robusta.
