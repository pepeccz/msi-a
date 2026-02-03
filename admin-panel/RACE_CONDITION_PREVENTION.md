# Race Condition Prevention Guide

## Problema Común: useEffect con Async Functions Sin Await

Este documento describe el **patrón incorrecto** que causa race conditions y el **patrón correcto** para evitarlas en el admin panel de MSI-a.

---

## ❌ Patrón INCORRECTO (Causa Race Condition)

```typescript
"use client";

import { useState, useEffect } from "react";

export default function MyPage() {
  const [data, setData] = useState([]);
  const [moreData, setMoreData] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchMoreData = async () => {
    const result = await api.getMoreData();
    setMoreData(result);
  };

  useEffect(() => {
    async function fetchData() {
      try {
        setIsLoading(true);
        const result = await api.getData();
        setData(result);
        
        // ❌ PROBLEMA: No se espera a que complete
        fetchMoreData();
      } catch (error) {
        console.error(error);
      } finally {
        // ❌ Se ejecuta ANTES de que fetchMoreData() complete
        setIsLoading(false);
      }
    }
    fetchData();
  }, []);

  if (isLoading) return <div>Cargando...</div>;

  // ❌ moreData todavía es [] cuando se renderiza
  return (
    <div>
      <h1>Data: {data.length}</h1>
      <h2>More Data: {moreData.length}</h2> {/* ← Muestra 0 */}
    </div>
  );
}
```

### ¿Por Qué Falla?

**Flujo de ejecución**:
1. `setIsLoading(true)` ✅
2. `await api.getData()` ✅ (espera)
3. `setData(result)` ✅
4. `fetchMoreData()` ❌ (lanza promesa, NO espera)
5. `setIsLoading(false)` ❌ (INMEDIATO, antes de que fetchMoreData complete)
6. Componente renderiza con `moreData = []` ❌
7. ... más tarde ...
8. `fetchMoreData()` completa
9. `setMoreData(result)` (actualiza estado, causa re-render)

**Resultado**: El usuario ve `moreData = []` hasta que la promesa completa, causando:
- UI mostrando datos vacíos o incompletos
- Mensajes de "No hay datos" cuando SÍ hay datos
- Loading state que desaparece antes de que los datos lleguen

---

## ✅ Patrón CORRECTO (Opción 1: await Secuencial)

```typescript
useEffect(() => {
  async function fetchData() {
    try {
      setIsLoading(true);
      const result = await api.getData();
      setData(result);
      
      // ✅ CORRECTO: Espera a que complete
      await fetchMoreData();
    } catch (error) {
      console.error(error);
    } finally {
      // ✅ Se ejecuta DESPUÉS de que ambas completen
      setIsLoading(false);
    }
  }
  fetchData();
}, []);
```

**Beneficios**:
- ✅ Garantiza que `fetchMoreData()` complete antes de `setIsLoading(false)`
- ✅ Datos disponibles en primer render
- ✅ No race condition

**Desventaja**:
- ⚠️ Secuencial (más lento si las llamadas son independientes)

---

## ✅ Patrón CORRECTO (Opción 2: Promise.all Paralelo) - **RECOMENDADO**

```typescript
useEffect(() => {
  async function fetchData() {
    try {
      setIsLoading(true);
      
      // ✅ MEJOR: Ambas en paralelo, espera a que completen
      const [dataResult, moreDataResult] = await Promise.all([
        api.getData(),
        api.getMoreData(),
      ]);
      
      setData(dataResult);
      setMoreData(moreDataResult);
    } catch (error) {
      console.error(error);
    } finally {
      // ✅ Se ejecuta DESPUÉS de que AMBAS completen
      setIsLoading(false);
    }
  }
  fetchData();
}, []);
```

**Beneficios**:
- ✅ Más rápido (paralelo en vez de secuencial)
- ✅ Garantiza que ambas completen antes de `setIsLoading(false)`
- ✅ Código más limpio y conciso

**Cuándo usar**:
- ✅ Las llamadas son independientes (no dependen una de otra)
- ✅ Quieres optimizar performance
- ✅ Ambas deben completar antes de mostrar datos

---

## ✅ Patrón CORRECTO (Opción 3: Fire-and-Forget Intencional)

```typescript
useEffect(() => {
  async function fetchData() {
    try {
      setIsLoading(true);
      const result = await api.getData();
      setData(result);
      
      // ✅ INTENCIONAL: Se carga independientemente
      // (documentado con comentario)
      fetchMoreData(); // Fire-and-forget: Datos opcionales/secundarios
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }
  fetchData();
}, []);
```

**Cuándo usar**:
- ✅ Los datos secundarios NO son críticos para el render inicial
- ✅ El componente funciona correctamente sin esos datos
- ✅ Los datos se muestran cuando llegan (sin bloquear loading)
- ⚠️ **SIEMPRE documentar con comentario explícito**

**Ejemplo real**: `reformas/[categoryId]/page.tsx` carga servicios globales en background mientras muestra la categoría.

---

## 📋 Checklist para Code Review

Cuando revises código con `useEffect` + async, verifica:

- [ ] ¿Todas las funciones async dentro del useEffect tienen `await`?
- [ ] ¿`setIsLoading(false)` se ejecuta DESPUÉS de todas las llamadas async?
- [ ] Si hay llamadas sin `await`, ¿está documentado como fire-and-forget intencional?
- [ ] ¿Las llamadas independientes usan `Promise.all` para paralelizar?
- [ ] ¿Los errores en funciones async se manejan correctamente?

---

## 🐛 Bug Real Encontrado y Solucionado

### Caso: `elementos/[id]/page.tsx` (2024-02-03)

**Problema**: Los campos requeridos y warnings NO se mostraban en el admin panel.

**Causa**: Race condition por llamadas sin await.

**Código buggy**:
```typescript
// Líneas 285-287
// Fetch warnings and required fields
fetchWarnings();          // ❌ Sin await
fetchRequiredFields();    // ❌ Sin await
```

**Fix aplicado**:
```typescript
// Fetch warnings and required fields
await Promise.all([
  fetchWarnings(),
  fetchRequiredFields(),
]);
```

**Resultado**: ✅ Campos requeridos y warnings ahora se muestran correctamente en primer render.

---

## 📚 Referencias

- [React useEffect documentation](https://react.dev/reference/react/useEffect)
- [Promise.all() MDN](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/all)
- [Admin Panel AGENTS.md](./AGENTS.md) - Patrones generales del admin panel

---

## 🎯 Resumen TL;DR

**Regla de oro**: Si una función async actualiza estado que se muestra en el render, **SIEMPRE usa `await`** o `Promise.all` antes de `setIsLoading(false)`.

```typescript
// ❌ MAL
fetchData();
setIsLoading(false);

// ✅ BIEN
await fetchData();
setIsLoading(false);

// ✅ MEJOR (si son independientes)
await Promise.all([fetchData(), fetchMoreData()]);
setIsLoading(false);
```
