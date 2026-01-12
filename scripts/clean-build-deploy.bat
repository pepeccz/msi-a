@echo off
REM ============================================================================
REM Clean Build & Deployment Script for MSI-a (Windows)
REM
REM This script performs a complete clean build and deployment:
REM 1. Stops all services
REM 2. Removes old containers and images
REM 3. Cleans volumes (optional backup first)
REM 4. Builds fresh images
REM 5. Starts fresh services
REM 6. Runs database migrations
REM 7. Loads seed data
REM 8. Verifies health
REM
REM Usage: clean-build-deploy.bat [--backup] [--dry-run]
REM ============================================================================

setlocal enabledelayedexpansion
set DRY_RUN=false
set CREATE_BACKUP=false

REM Parse arguments
for %%A in (%*) do (
    if "%%A"=="--backup" set CREATE_BACKUP=true
    if "%%A"=="--dry-run" set DRY_RUN=true
)

cls
echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                  CLEAN BUILD ^& DEPLOYMENT                      ║
echo ║                        MSI-a Project                           ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

REM Step 1: Backup database (if requested)
if "%CREATE_BACKUP%"=="true" (
    call :backup_database
)

REM Step 2: Stop services
call :stop_services

REM Step 3: Clean Docker
call :clean_docker

REM Step 4: Build images
call :build_images

REM Step 5: Start services
call :start_services

REM Step 6: Run migrations
call :run_migrations

REM Step 7: Load seed data
call :load_seed_data

REM Step 8: Verify health
call :verify_health

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                   ✓ CLEAN BUILD COMPLETE!                      ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.
echo Services ready at:
echo   - API:          http://localhost:8000
echo   - Admin Panel:  http://localhost:3000
echo   - PgAdmin:      http://localhost:5050
echo.
pause
exit /b 0

REM ============================================================================
REM Step 1: Backup Database
REM ============================================================================
:backup_database
echo [INFO] Step 1: Backing up database...

if "%DRY_RUN%"=="true" (
    echo [INFO] (DRY-RUN) Would create database backup
    exit /b 0
)

if not exist ".\backups" mkdir ".\backups"

for /f "tokens=2-4 delims=/ " %%A in ('date /t') do (
    for /f "tokens=1-2 delims=/:" %%B in ('time /t') do (
        set BACKUP_FILE=.\backups\backup_%%C%%A%%B_%%B%%D.sql.gz
    )
)

echo [INFO] Creating database backup...
docker-compose exec -T postgres pg_dump -U msia -d msia_db | gzip > "%BACKUP_FILE%"

if exist "%BACKUP_FILE%" (
    echo [✓] Database backed up: %BACKUP_FILE%
) else (
    echo [✗] Backup failed!
    exit /b 1
)

exit /b 0

REM ============================================================================
REM Step 2: Stop Services
REM ============================================================================
:stop_services
echo [INFO] Step 2: Stopping services...

if "%DRY_RUN%"=="true" (
    echo [INFO] (DRY-RUN) Would stop services
    exit /b 0
)

docker-compose down --remove-orphans
timeout /t 2 /nobreak

echo [✓] Services stopped
exit /b 0

REM ============================================================================
REM Step 3: Clean Docker
REM ============================================================================
:clean_docker
echo [INFO] Step 3: Cleaning Docker environment...

if "%DRY_RUN%"=="true" (
    echo [INFO] (DRY-RUN) Would clean Docker
    exit /b 0
)

echo [INFO] Removing containers...
docker-compose rm -f

echo [INFO] Removing images...
docker-compose down --rmi all 2>nul || true

echo [INFO] Cleaning volumes...
docker volume prune -f 2>nul || true

echo [✓] Docker cleaned
exit /b 0

REM ============================================================================
REM Step 4: Build Images
REM ============================================================================
:build_images
echo [INFO] Step 4: Building fresh Docker images...

if "%DRY_RUN%"=="true" (
    echo [INFO] (DRY-RUN) Would build images
    exit /b 0
)

docker-compose build --no-cache
if errorlevel 1 (
    echo [✗] Build failed!
    exit /b 1
)

echo [✓] Images built
exit /b 0

REM ============================================================================
REM Step 5: Start Services
REM ============================================================================
:start_services
echo [INFO] Step 5: Starting services...

if "%DRY_RUN%"=="true" (
    echo [INFO] (DRY-RUN) Would start services
    exit /b 0
)

docker-compose up -d
if errorlevel 1 (
    echo [✗] Failed to start services!
    exit /b 1
)

echo [INFO] Waiting for services to be ready...
timeout /t 10 /nobreak

echo [✓] Services started
exit /b 0

REM ============================================================================
REM Step 6: Run Migrations
REM ============================================================================
:run_migrations
echo [INFO] Step 6: Running database migrations...

if "%DRY_RUN%"=="true" (
    echo [INFO] (DRY-RUN) Would run migrations
    exit /b 0
)

echo [INFO] Waiting for database to be ready...
for /L %%i in (1,1,30) do (
    docker-compose exec -T postgres pg_isready -U msia -d msia_db >nul 2>&1
    if !errorlevel! equ 0 (
        echo [✓] Database is ready
        goto :db_ready
    )
    if %%i equ 30 (
        echo [✗] Database failed to start!
        exit /b 1
    )
    timeout /t 1 /nobreak
)

:db_ready
echo [INFO] Running Alembic migrations...
docker-compose exec -T api alembic upgrade head
if errorlevel 1 (
    echo [✗] Migrations failed!
    exit /b 1
)

echo [✓] Migrations completed
exit /b 0

REM ============================================================================
REM Step 7: Load Seed Data
REM ============================================================================
:load_seed_data
echo [INFO] Step 7: Loading seed data...

if "%DRY_RUN%"=="true" (
    echo [INFO] (DRY-RUN) Would load seed data
    exit /b 0
)

echo [INFO] Loading category seed...
docker-compose exec -T api python -m database.seeds.aseicars_seed
if errorlevel 1 (
    echo [✗] Category seed failed!
    exit /b 1
)

echo [INFO] Loading element seed...
docker-compose exec -T api python -m database.seeds.elements_from_pdf_seed
if errorlevel 1 (
    echo [✗] Element seed failed!
    exit /b 1
)

echo [✓] Seed data loaded
exit /b 0

REM ============================================================================
REM Step 8: Verify Health
REM ============================================================================
:verify_health
echo [INFO] Step 8: Verifying system health...
echo.
echo Health Checks:
echo ───────────────────────────────────────────

REM Check Database
docker-compose exec -T postgres pg_isready -U msia -d msia_db >nul 2>&1
if !errorlevel! equ 0 (
    echo [✓] Database is healthy
) else (
    echo [✗] Database is not healthy!
)

REM Check Redis
docker-compose exec -T redis redis-cli ping >nul 2>&1
if !errorlevel! equ 0 (
    echo [✓] Redis is healthy
) else (
    echo [WARNING] Could not verify Redis health
)

echo.
echo Container Statuses:
echo ───────────────────────────────────────────
docker-compose ps

echo.
echo Database Contents:
echo ───────────────────────────────────────────

REM Check elements
for /f %%A in ('docker-compose exec -T postgres psql -U msia -d msia_db -t -c "SELECT count(*) FROM elements;" 2^>nul') do set ELEMENT_COUNT=%%A
echo [INFO] Elements in database: %ELEMENT_COUNT%

REM Check tier inclusions
for /f %%A in ('docker-compose exec -T postgres psql -U msia -d msia_db -t -c "SELECT count(*) FROM tier_element_inclusions;" 2^>nul') do set TIER_COUNT=%%A
echo [INFO] Tier inclusions in database: %TIER_COUNT%

echo.
echo [✓] Health verification complete

exit /b 0
