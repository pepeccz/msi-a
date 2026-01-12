# Quick Start - Clean Build (Copy & Paste Commands)

## 🚀 Para Windows PowerShell (RECOMENDADO - 30 minutos)

### Opción 1: Script Automático (RECOMENDADO)

```powershell
cd C:\Users\Pepe\Documents\Proyectos\msi-a
.\scripts\clean-build-deploy.bat
```

✅ Esto hace TODO automáticamente

---

### Opción 2: Comandos Manuales Paso a Paso

#### Paso 1: Detener servicios
```powershell
cd C:\Users\Pepe\Documents\Proyectos\msi-a
docker-compose down --remove-orphans
Start-Sleep -Seconds 2
```

#### Paso 2: Limpiar Docker
```powershell
docker-compose rm -f
docker-compose down --rmi all
docker volume prune -f
```

#### Paso 3: Hacer build limpio
```powershell
docker-compose build --no-cache
```

#### Paso 4: Arrancar servicios
```powershell
docker-compose up -d
Start-Sleep -Seconds 10
```

#### Paso 5: Esperar a que PostgreSQL esté listo
```powershell
# Repetir hasta que responda "accepting connections"
docker-compose exec -T postgres pg_isready -U msia -d msia_db

# Si falla, esperar más
Start-Sleep -Seconds 5
```

#### Paso 6: Ejecutar migraciones
```powershell
docker-compose exec -T api alembic upgrade head
```

#### Paso 7: Cargar seed data
```powershell
# Cargar categorías y tarifas
docker-compose exec -T api python -m database.seeds.aseicars_seed

# Cargar elementos (escalera, toldo, etc.)
docker-compose exec -T api python -m database.seeds.elements_from_pdf_seed
```

#### Paso 8: Verificar que todo está bien
```powershell
# Ver estado de contenedores
docker-compose ps

# Contar elementos
docker-compose exec -T postgres psql -U msia -d msia_db -c "SELECT count(*) FROM elements;"

# Probar API
curl http://localhost:8000/health
```

---

## 🌐 Servicios Disponibles Después

Abre en tu navegador:

| Servicio | URL | Usuario | Contraseña |
|----------|-----|---------|-----------|
| API | http://localhost:8000 | - | - |
| Admin Panel | http://localhost:3000 | - | - |
| PgAdmin (DB) | http://localhost:5050 | admin@pgadmin.org | admin |
| Redis Commander | http://localhost:8081 | - | - |

---

## ✅ Verificación Rápida

```powershell
# Todo debe mostrar "Up"
docker-compose ps

# Debe haber 10 elementos
docker-compose exec -T postgres psql -U msia -d msia_db -c "SELECT count(*) FROM elements;"

# Debe haber inclusiones de tarifas
docker-compose exec -T postgres psql -U msia -d msia_db -c "SELECT count(*) FROM tier_element_inclusions;"

# Correr tests (deben pasar 70+)
docker-compose exec -T api pytest tests/ -v
```

---

## 🆘 Si Algo Falla

```powershell
# Ver logs del API
docker-compose logs -f api

# Ver logs de PostgreSQL
docker-compose logs -f postgres

# Ver logs de Redis
docker-compose logs -f redis

# Si necesitas rollback total
docker-compose down -v
docker system prune -a --volumes
# Luego repite desde "Paso 1"
```

---

## ⚡ Atajos Útiles

```powershell
# Entrar al contenedor de API
docker-compose exec -T api bash

# Conectar a la base de datos interactivamente
docker-compose exec -T postgres psql -U msia -d msia_db

# Ver estado de Redis
docker-compose exec -T redis redis-cli ping

# Reiniciar todo
docker-compose restart

# Ver todo en tiempo real
docker-compose logs -f
```

---

## 📊 Limpieza Profunda (Si Needed)

⚠️ **Esto borra TODO - úsalo solo si nada funciona**

```powershell
# Parar todo
docker-compose down -v

# Limpiar todo el sistema Docker
docker system prune -a --volumes

# Iniciar desde cero
docker-compose build --no-cache
docker-compose up -d
# Luego repite los pasos de migraciones y seeds
```

---

## 📱 Resumen en 30 minutos

```
Total time: ~30 minutes

5 min   ├─ Stop & clean
10 min  ├─ Build images
3 min   ├─ Start services & wait
2 min   ├─ Run migrations
5 min   ├─ Load seed data
2 min   ├─ Verify health
3 min   └─ Run tests (optional)
```

---

¡Listo! Tu infraestructura está limpia y funcionando 🚀
