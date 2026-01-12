# Clean Build & Deployment Guide

Complete guide to create a clean build and deploy the infrastructure from scratch.

---

## 🚀 Quick Start (Automated)

### Option 1: Windows (Recommended)

```bash
# Navigate to project root
cd C:\Users\Pepe\Documents\Proyectos\msi-a

# Run clean build script
.\scripts\clean-build-deploy.bat

# With backup
.\scripts\clean-build-deploy.bat --backup

# Dry run (see what will happen)
.\scripts\clean-build-deploy.bat --dry-run
```

### Option 2: Linux/Mac (Bash)

```bash
# Navigate to project root
cd ~/path/to/msi-a

# Make script executable
chmod +x scripts/clean-build-deploy.sh

# Run clean build script
./scripts/clean-build-deploy.sh

# With backup
./scripts/clean-build-deploy.sh --backup

# Dry run
./scripts/clean-build-deploy.sh --dry-run
```

---

## 🔧 Manual Step-by-Step (If you prefer to do it manually)

### Step 1: Stop Services (2 minutes)

```bash
cd C:\Users\Pepe\Documents\Proyectos\msi-a

# Stop all running containers
docker-compose down --remove-orphans

# Wait for services to stop
# (automatic, but wait 2 seconds to be sure)
timeout /t 2
```

**What happens:**
- All running containers are stopped
- Containers are removed
- Network connections are cleaned up
- Data persists (volumes are kept unless you add --volumes flag)

### Step 2: Backup Database (Optional but Recommended)

```bash
# Create backup directory
mkdir backups

# Backup database (if PostgreSQL is still running from previous compose)
docker-compose exec -T postgres pg_dump -U msia -d msia_db | gzip > backups/backup_$(Get-Date -Format "yyyyMMdd_HHmmss").sql.gz
```

**Output:** `backups/backup_20260109_143022.sql.gz`

### Step 3: Deep Clean (5 minutes)

⚠️ **WARNING:** This removes ALL Docker images, containers, and volumes related to this project.

```bash
# Remove containers
docker-compose rm -f

# Remove images (--rmi all removes all images)
docker-compose down --rmi all

# Clean unused volumes
docker volume prune -f

# Optional: View what will be deleted
docker system df
```

**What gets deleted:**
- ❌ All Docker containers for this project
- ❌ All Docker images built for this project
- ❌ All Docker volumes (database data, Redis data, etc.)

**What stays:**
- ✅ Your source code
- ✅ Backups you created manually
- ✅ Other projects' containers

### Step 4: Pull Latest Code (1 minute)

```bash
# Ensure you're on main branch
git status
# Should show "On branch main"

# Stash any local changes
git stash

# Pull latest code
git pull origin main
```

### Step 5: Build Fresh Images (10-15 minutes)

```bash
# Build all images without cache (forces rebuild)
docker-compose build --no-cache

# Or use BuildKit for faster builds (optional)
DOCKER_BUILDKIT=1 docker-compose build --no-cache
```

**What happens:**
- Downloads base images (python:3.11, node:18, postgres:15, redis:7)
- Installs all dependencies
- Builds your application images
- Creates fresh images (no cache reuse)

### Step 6: Start All Services (3 minutes)

```bash
# Start all services in detached mode (-d)
docker-compose up -d

# Wait for services to fully initialize
timeout /t 10

# Check service status
docker-compose ps
```

**Expected output:**
```
NAME              STATUS
msia-postgres     Up 2 minutes (healthy)
msia-redis        Up 2 minutes
msia-api          Up 1 minute
msia-admin-panel  Up 1 minute
pgadmin           Up 1 minute
```

### Step 7: Wait for Database Ready (30 seconds - 1 minute)

```bash
# Check if database is ready
docker-compose exec -T postgres pg_isready -U msia -d msia_db

# Repeat until you see: accepting connections
# If not ready, wait and try again
```

**If database takes too long:**
```bash
# Check logs
docker-compose logs postgres

# If it shows "waiting for server to start", wait more
timeout /t 5
```

### Step 8: Run Database Migrations (2 minutes)

```bash
# Run all pending migrations
docker-compose exec -T api alembic upgrade head

# Verify migrations ran
docker-compose exec -T postgres psql -U msia -d msia_db -c "SELECT * FROM alembic_version;"
```

**Expected output:**
```
           version_num
────────────────────────
 012_element_system
(1 row)
```

### Step 9: Load Seed Data (3 minutes)

```bash
# Load category seed (creates T1-T6 tiers)
docker-compose exec -T api python -m database.seeds.aseicars_seed

# Watch for output showing tiers created
```

```bash
# Load element seed (creates 10 elements with images)
docker-compose exec -T api python -m database.seeds.elements_from_pdf_seed

# Watch for detailed progress output
```

**Expected output:**
```
================================================================================
Starting Element System Seed
================================================================================

[STEP 1] Getting category: aseicars
✓ Found category: Autocaravanas (32xx, 33xx) (ID: ...)

[STEP 2] Creating elements
✓ ESC_MEC: Created with 4 images
✓ TOLDO_LAT: Created with 4 images
...

[STEP 3] Creating tier element inclusions
✓ Committed successfully
```

### Step 10: Verify Everything Works (2 minutes)

```bash
# Check container health
docker-compose ps

# All should show "Up"

# Test API
curl http://localhost:8000/health

# Should return healthy status

# Check database
docker-compose exec -T postgres psql -U msia -d msia_db -c "SELECT count(*) FROM elements;"

# Should show: 10 (if seed loaded correctly)

# Check admin panel
# Open browser to http://localhost:3000
# Should load without errors
```

---

## 🧪 Post-Deployment Tests

### Test 1: Verify Elements Loaded

```bash
# Count elements
docker-compose exec -T postgres psql -U msia -d msia_db -c "
  SELECT code, name FROM elements ORDER BY code;
"

# Expected output: 10 elements
# ESC_MEC, TOLDO_LAT, PLACA_200W, etc.
```

### Test 2: Verify Tier Resolution

```bash
# Connect to Python shell
docker-compose exec -T api python

# In Python:
from agent.services.tarifa_service import TarifaService
from database.connection import get_async_session
import asyncio

async def test():
    service = TarifaService()
    # Get a tier ID (you'll need to get it from DB first)
    result = await service.resolve_tier_elements('tier_id_here')
    print(result)

asyncio.run(test())
```

### Test 3: Test Agent Tools

```bash
# Run agent tool tests
docker-compose exec -T api pytest tests/test_agent_tools_integration.py -v

# Should see all tests pass
```

### Test 4: Full Test Suite

```bash
# Run all tests
docker-compose exec -T api pytest tests/ -v

# Should see 70+ tests pass
```

---

## 🆘 Troubleshooting

### Problem: "Database connection refused"

**Solution:**
```bash
# Wait longer for database to start
timeout /t 5

# Check database logs
docker-compose logs postgres

# If still failing, recreate database
docker-compose down -v
docker-compose up -d postgres
timeout /t 15
```

### Problem: "alembic not found" or migration fails

**Solution:**
```bash
# Check if API container is running
docker-compose ps api

# If not running:
docker-compose up -d api

# Check API logs
docker-compose logs api

# Retry migration
docker-compose exec -T api alembic upgrade head
```

### Problem: Seed data script hangs or fails

**Solution:**
```bash
# Check API logs for errors
docker-compose logs api

# Try seed with verbose output
docker-compose exec -T api python -m database.seeds.elements_from_pdf_seed 2>&1 | head -50

# If category not found error:
docker-compose exec -T api python -m database.seeds.aseicars_seed

# Retry element seed
docker-compose exec -T api python -m database.seeds.elements_from_pdf_seed
```

### Problem: Redis connection issues

**Solution:**
```bash
# Check Redis status
docker-compose exec -T redis redis-cli ping

# Should respond: PONG

# If not responding:
docker-compose restart redis
timeout /t 5
```

### Problem: Port already in use

**Solution:**
```bash
# Find what's using port 8000
netstat -ano | findstr :8000

# Kill process
taskkill /PID <PID> /F

# Or use different port
docker-compose -p msia_alt up -d
```

### Problem: Out of disk space

**Solution:**
```bash
# Check Docker disk usage
docker system df

# Clean up unused images/containers/volumes
docker system prune -a --volumes

# Remove dangling images
docker rmi $(docker images -f "dangling=true" -q)
```

---

## ✅ Verification Checklist

After clean build, verify:

- [ ] **Services Running**
  ```bash
  docker-compose ps
  ```
  All containers show "Up"

- [ ] **Database Healthy**
  ```bash
  docker-compose exec -T postgres pg_isready -U msia -d msia_db
  ```
  Shows "accepting connections"

- [ ] **Migrations Applied**
  ```bash
  docker-compose exec -T postgres psql -U msia -d msia_db -c "SELECT * FROM alembic_version;"
  ```
  Shows "012_element_system"

- [ ] **Elements Loaded**
  ```bash
  docker-compose exec -T postgres psql -U msia -d msia_db -c "SELECT count(*) FROM elements;"
  ```
  Shows "10"

- [ ] **API Responds**
  ```bash
  curl http://localhost:8000/health
  ```
  Returns 200 with health status

- [ ] **Admin Panel Loads**
  Open http://localhost:3000 in browser
  Should load without errors

- [ ] **Tests Pass**
  ```bash
  docker-compose exec -T api pytest tests/ -v
  ```
  All 70+ tests should pass

- [ ] **No Error Logs**
  ```bash
  docker-compose logs api | grep -i error
  ```
  Should be empty or minimal

---

## 📊 What Gets Created/Cleaned

### Gets Deleted
- ❌ All Docker containers
- ❌ All Docker images
- ❌ All volumes (database, cache)
- ❌ Old build artifacts

### Stays the Same
- ✅ Source code (git repository)
- ✅ .env files and configurations
- ✅ Manual backups you created
- ✅ Git history

### Gets Created Fresh
- ✅ New Docker images
- ✅ New Docker containers
- ✅ New database (empty)
- ✅ New Redis cache (empty)
- ✅ All migrations applied
- ✅ All seed data loaded

---

## ⚡ Performance Tips

### Faster Builds
```bash
# Use BuildKit (faster builds)
$env:DOCKER_BUILDKIT=1
docker-compose build --no-cache
```

### Parallel Service Startup
```bash
# Services start simultaneously
docker-compose up -d

# Check when each is ready
docker-compose logs --follow
```

### Faster Migrations
```bash
# Run migrations with verbose output
docker-compose exec -T api alembic upgrade head -v

# Check migration status without running
docker-compose exec -T api alembic current
```

---

## 📝 Common Commands Reference

```bash
# View logs
docker-compose logs -f api              # Follow API logs
docker-compose logs postgres            # View database logs
docker-compose logs --tail=50 api       # Last 50 lines

# Database operations
docker-compose exec -T postgres psql -U msia -d msia_db
# Interactive PostgreSQL prompt

# Run one-off commands
docker-compose exec -T api python --version
docker-compose exec -T api ls -la /app

# Restart specific service
docker-compose restart api
docker-compose restart postgres

# View service status
docker-compose ps
docker ps

# Remove everything and start over
docker-compose down -v
docker system prune -a --volumes
```

---

## 🚨 Emergency Rollback

If something goes wrong after deployment:

```bash
# Quick rollback to previous state
docker-compose down

# Restore from backup
gunzip < backups/backup_20260109_143022.sql.gz | docker-compose exec -T postgres psql -U msia -d msia_db

# Restart services
docker-compose up -d

# Verify
docker-compose ps
```

---

## 📞 Need Help?

**Check logs:**
```bash
docker-compose logs [service] -f
```

**Verify database:**
```bash
docker-compose exec -T postgres psql -U msia -d msia_db -c "\dt"
```

**Run specific seed:**
```bash
docker-compose exec -T api python -m database.seeds.elements_from_pdf_seed
```

**Run tests:**
```bash
docker-compose exec -T api pytest tests/ -v
```

