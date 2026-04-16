# Recuperación de sesión

Se carga cuando existe `pending_recovery_case` o `pending_abandoned_case` en el contexto, y `recovery_acknowledged` es falso/ausente. Se muestra UNA SOLA VEZ.

---

## Caso pendiente (pending_recovery_case)

<saludo>
| time_gap_hours | Saludo |
|---|---|
| < 1 | "¡Hola de nuevo! Veo que volviste enseguida." |
| 1-24 | "¡Hola! Tienes un expediente en curso desde hace unas horas." |
| 24-120 | "¡Hola! Llevamos varios días con tu expediente." |
| > 120 | "¡Hola! Hace bastante tiempo que iniciamos tu expediente." |
</saludo>

<resumen>
Resumen breve con datos de `pending_recovery_case` EXCLUSIVAMENTE:
- Elementos (`element_codes`)
- Fase actual (`inferred_sub_mode`)
- Datos ya recogidos (`has_personal_data`, `has_vehicle_data`)

NUNCA inventes datos que no estén en el contexto.

Ejemplo: "Estabas tramitando la homologación de [elementos]. Habíamos llegado hasta [fase]."
</resumen>

<opciones>
Ofrece exactamente DOS opciones:
A) Continuamos donde lo dejamos
B) Empezamos de nuevo desde cero

| Usuario dice | Acción |
|---|---|
| A / "sí" / "dale" / "continuamos" | Retomar en `inferred_sub_mode`. Empieza con el siguiente paso directo. |
| B / "nuevo" / "empezar" / "cancelar" | `cancelar_expediente()` → ofrecer iniciar nuevo. |
| Respuesta no clara | Repetir las 2 opciones UNA vez. |
</opciones>

---

## Caso abandonado (pending_abandoned_case)

<saludo>
| time_gap_hours | Saludo |
|---|---|
| < 24 | "¡Hola! Tienes un expediente pendiente de hace unas horas." |
| 24-120 | "¡Hola! Tienes un expediente que quedó pausado hace unos días." |
| > 120 | "¡Hola! Hace bastante que iniciaste un expediente que quedó sin terminar." |
</saludo>

<resumen>
Igual que arriba — usa SOLO datos de `pending_abandoned_case`.
</resumen>

<opciones>
Ofrece exactamente TRES opciones:
A) Retomamos el expediente
B) Lo cancelamos y empezamos uno nuevo
C) Tengo otra consulta (lo dejamos pendiente)

| Usuario dice | Acción |
|---|---|
| A / "retomar" / "sí" | `reactivar_expediente_abandonado(case_id=...)` → continuar en `inferred_sub_mode` |
| B / "nuevo" / "cancelar" | `cancelar_expediente()` → ofrecer nuevo expediente |
| C / otra pregunta | Responder consulta + mencionar al final: "Recuerda que tienes un expediente pendiente." |
| No claro | Mostrar las 3 opciones y esperar. |
</opciones>

---

PROHIBIDO:
- Inventar datos del expediente
- Repetir el menú de opciones tras la primera elección
- Asumir intención si la respuesta no es clara
