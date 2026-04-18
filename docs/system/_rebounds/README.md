# Rebounds — canal Ingeniero → Arquitecto

## Para qué sirve esta carpeta

Cuando el **Ingeniero-AI** lee un spec y se da cuenta de que no puede implementarlo tal cual está, **no puede arreglar el spec solo**: su permiso de escritura está limitado a código. La única forma de comunicarse de vuelta con el **Arquitecto-AI** es dejando una nota en esta carpeta.

Una nota de rebound describe el problema, propone opciones de resolución, y detiene la implementación hasta que el Arquitecto-AI (con el owner) decida.

## Cuándo crear un rebound

Cualquiera de estas situaciones:

- **Ambigüedad**: el spec se puede interpretar de dos formas razonables y el Ingeniero no puede elegir.
- **Contradicción**: dos reglas o escenarios del spec se contradicen entre sí, o con otro spec.
- **Imposibilidad técnica**: implementar lo que pide el spec requiere una capacidad no listada en `00-capacidades.md`.
- **Precondition rota**: un archivo listado en "Mapeo al código" no existe o ha sido renombrado.
- **Fuera de alcance descubierto**: para implementar lo pedido hay que tocar un archivo que el spec lista en "Fuera de alcance". Esto es señal roja.

## Cuándo NO crear un rebound

- El spec es claro y solo te resulta difícil — **primero implementalo**.
- Querés refactorizar "mientras tocás" — **no lo hagas**. El rebound no es un canal para mejorar código.
- Encontraste un bug en código no relacionado con el spec actual — **abrí un change aparte**, no rebotes.

## Plantilla

Copiar este template al archivo `_rebounds/YYYY-MM-DD-<slug-corto>.md`:

```markdown
---
spec_afectado: docs/system/agente/flujos/pre-expediente/flujo.md
seccion: Escenarios > Escenario N
estado: abierto
---

# Rebound — <título breve>

## Cita textual ambigua / problemática

> "<copiar fragmento exacto del spec>"

## Conflicto / imposibilidad

<explicar en lenguaje de negocio por qué no se puede implementar tal cual>

## Opciones propuestas

1. **Opción A — <nombre>**: <descripción corta>. Tradeoff: <qué se gana, qué se pierde>.
2. **Opción B — <nombre>**: <descripción corta>. Tradeoff: <qué se gana, qué se pierde>.

## Recomendación del Ingeniero-AI

<cuál recomienda y por qué, en 2-3 frases>

## Acción requerida

Arquitecto-AI debe decidir entre las opciones, actualizar el spec, y mover este archivo a `_rebounds/_resolved/` con un commit que referencie este archivo.
```

## Flujo de resolución

```
1. Ingeniero-AI crea:  _rebounds/2026-04-17-variante-multi-select.md
                       └── estado: abierto

2. Ingeniero-AI detiene implementación y notifica al owner

3. Owner invoca al Arquitecto-AI:
   "Hay un rebound abierto, resolvelo"

4. Arquitecto-AI:
   a. Lee el rebound
   b. Decide (puede conversar con owner para elegir opción)
   c. Actualiza el spec afectado
   d. Edita el rebound:  estado: resuelto
                         añade sección "## Resolución" con decisión tomada
   e. Mueve archivo a: _rebounds/_resolved/2026-04-17-variante-multi-select.md
   f. Commitea:  "spec: resolve rebound variante-multi-select"

5. Owner re-invoca al Ingeniero-AI con el spec actualizado
```

## Qué NO es un rebound

- **Una queja sobre el spec**: "este spec está mal escrito" — no es un rebound, es feedback al Arquitecto. Canal normal de conversación.
- **Un bug en código no relacionado**: abrí un change separado.
- **Una sugerencia de mejora**: si el spec funciona pero creés que hay mejor forma, anotalo en una issue del proyecto, no en `_rebounds/`.

## Histórico

Los rebounds resueltos quedan en `_resolved/` como histórico consultable. Son valiosos para entender decisiones pasadas, parecido a ADRs pero más tácticos.

## Referencias

- Protocolo completo de cambios: `../99-protocolo-cambios.md`
- Capacidades del sistema: `../00-capacidades.md`
