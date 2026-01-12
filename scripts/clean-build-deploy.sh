#!/bin/bash

################################################################################
# Clean Build & Deployment Script for MSI-a
#
# This script performs a complete clean build and deployment:
# 1. Stops all services
# 2. Removes old containers and images
# 3. Cleans volumes (optional backup first)
# 4. Pulls latest code
# 5. Runs database migrations
# 6. Loads seed data
# 7. Starts fresh services
# 8. Verifies health
#
# Usage: ./scripts/clean-build-deploy.sh [--backup] [--dry-run]
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKUP_DIR="./backups"
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$BACKUP_DATE.sql.gz"
DRY_RUN=false
CREATE_BACKUP=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --backup)
            CREATE_BACKUP=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

execute_cmd() {
    if [ "$DRY_RUN" = true ]; then
        log_info "(DRY-RUN) $1"
    else
        log_info "Executing: $1"
        eval "$1"
    fi
}

# Main script
main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                  CLEAN BUILD & DEPLOYMENT                      ║"
    echo "║                        MSI-a Project                           ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    # Step 1: Backup database (if requested)
    if [ "$CREATE_BACKUP" = true ]; then
        backup_database
    fi

    # Step 2: Stop services
    stop_services

    # Step 3: Clean Docker
    clean_docker

    # Step 4: Pull latest code
    pull_latest_code

    # Step 5: Build fresh images
    build_images

    # Step 6: Start services
    start_services

    # Step 7: Run migrations
    run_migrations

    # Step 8: Load seed data
    load_seed_data

    # Step 9: Verify health
    verify_health

    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                   ✓ CLEAN BUILD COMPLETE!                      ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Services ready at:"
    echo "  - API:          http://localhost:8000"
    echo "  - Admin Panel:  http://localhost:3000"
    echo "  - PgAdmin:      http://localhost:5050"
    echo ""
}

# ============================================================================
# Step 1: Backup Database
# ============================================================================
backup_database() {
    log_info "Step 1: Backing up database..."

    if [ "$DRY_RUN" = true ]; then
        log_info "(DRY-RUN) Would create backup to $BACKUP_FILE"
        return
    fi

    # Create backup directory
    mkdir -p "$BACKUP_DIR"

    # Check if services are running
    if docker-compose ps postgres 2>/dev/null | grep -q "Up"; then
        log_info "Creating database backup..."
        docker-compose exec -T postgres pg_dump -U msia -d msia_db | gzip > "$BACKUP_FILE"

        if [ -f "$BACKUP_FILE" ]; then
            SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
            log_success "Database backed up: $BACKUP_FILE ($SIZE)"
        else
            log_error "Backup failed!"
            exit 1
        fi
    else
        log_warning "Database service not running, skipping backup"
    fi
}

# ============================================================================
# Step 2: Stop Services
# ============================================================================
stop_services() {
    log_info "Step 2: Stopping services..."

    execute_cmd "docker-compose down --remove-orphans"

    # Wait for services to stop
    sleep 2

    log_success "Services stopped"
}

# ============================================================================
# Step 3: Clean Docker
# ============================================================================
clean_docker() {
    log_info "Step 3: Cleaning Docker environment..."

    if [ "$DRY_RUN" = true ]; then
        log_info "(DRY-RUN) Would remove containers, images, and volumes"
        return
    fi

    # Remove old containers
    log_info "Removing containers..."
    docker-compose rm -f

    # Remove images
    log_info "Removing images..."
    docker-compose down --rmi all 2>/dev/null || true

    # Optionally clean volumes (uncomment if you want full clean)
    log_info "Cleaning volumes..."
    docker volume prune -f --filter "label!=keep" 2>/dev/null || true

    log_success "Docker cleaned"
}

# ============================================================================
# Step 4: Pull Latest Code
# ============================================================================
pull_latest_code() {
    log_info "Step 4: Pulling latest code..."

    if [ "$DRY_RUN" = true ]; then
        log_info "(DRY-RUN) Would pull latest from git"
        return
    fi

    # Check git status
    if ! command -v git &> /dev/null; then
        log_warning "Git not found, skipping code pull"
        return
    fi

    # Stash any local changes
    if [ -n "$(git status --porcelain)" ]; then
        log_warning "Local changes detected, stashing..."
        git stash
    fi

    # Pull latest
    execute_cmd "git pull origin main"

    log_success "Latest code pulled"
}

# ============================================================================
# Step 5: Build Fresh Images
# ============================================================================
build_images() {
    log_info "Step 5: Building fresh Docker images..."

    if [ "$DRY_RUN" = true ]; then
        log_info "(DRY-RUN) Would build images"
        return
    fi

    execute_cmd "docker-compose build --no-cache"

    log_success "Images built"
}

# ============================================================================
# Step 6: Start Services
# ============================================================================
start_services() {
    log_info "Step 6: Starting services..."

    if [ "$DRY_RUN" = true ]; then
        log_info "(DRY-RUN) Would start services"
        return
    fi

    execute_cmd "docker-compose up -d"

    # Wait for services to be ready
    log_info "Waiting for services to be ready..."
    sleep 10

    log_success "Services started"
}

# ============================================================================
# Step 7: Run Database Migrations
# ============================================================================
run_migrations() {
    log_info "Step 7: Running database migrations..."

    if [ "$DRY_RUN" = true ]; then
        log_info "(DRY-RUN) Would run alembic migrations"
        return
    fi

    # Wait for database to be ready
    log_info "Waiting for database to be ready..."
    for i in {1..30}; do
        if docker-compose exec -T postgres pg_isready -U msia -d msia_db &> /dev/null; then
            log_success "Database is ready"
            break
        fi
        if [ $i -eq 30 ]; then
            log_error "Database failed to start!"
            exit 1
        fi
        sleep 1
    done

    # Run migrations
    log_info "Running Alembic migrations..."
    execute_cmd "docker-compose exec -T api alembic upgrade head"

    log_success "Migrations completed"
}

# ============================================================================
# Step 8: Load Seed Data
# ============================================================================
load_seed_data() {
    log_info "Step 8: Loading seed data..."

    if [ "$DRY_RUN" = true ]; then
        log_info "(DRY-RUN) Would load seed data"
        return
    fi

    # Load category seed
    log_info "Loading category seed..."
    execute_cmd "docker-compose exec -T api python -m database.seeds.aseicars_seed"

    # Load element seed
    log_info "Loading element seed..."
    execute_cmd "docker-compose exec -T api python -m database.seeds.elements_from_pdf_seed"

    log_success "Seed data loaded"
}

# ============================================================================
# Step 9: Verify Health
# ============================================================================
verify_health() {
    log_info "Step 9: Verifying system health..."

    echo ""
    echo "Health Checks:"
    echo "───────────────────────────────────────────"

    # Check API
    if curl -s http://localhost:8000/health | grep -q "alive"; then
        log_success "API is healthy"
    else
        log_warning "Could not verify API health (may not be ready yet)"
    fi

    # Check Database
    if docker-compose exec -T postgres pg_isready -U msia -d msia_db &> /dev/null; then
        log_success "Database is healthy"
    else
        log_error "Database is not healthy!"
    fi

    # Check Redis
    if docker-compose exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
        log_success "Redis is healthy"
    else
        log_warning "Could not verify Redis health"
    fi

    # Check container statuses
    echo ""
    echo "Container Statuses:"
    echo "───────────────────────────────────────────"
    docker-compose ps

    # Verify database contents
    echo ""
    echo "Database Contents:"
    echo "───────────────────────────────────────────"
    log_info "Checking elements..."
    ELEMENT_COUNT=$(docker-compose exec -T postgres psql -U msia -d msia_db -t -c "SELECT count(*) FROM elements;" 2>/dev/null || echo "0")
    log_info "Elements in database: $ELEMENT_COUNT"

    TIER_COUNT=$(docker-compose exec -T postgres psql -U msia -d msia_db -t -c "SELECT count(*) FROM tier_element_inclusions;" 2>/dev/null || echo "0")
    log_info "Tier inclusions in database: $TIER_COUNT"

    echo ""
    log_success "Health verification complete"
}

# ============================================================================
# Error Handler
# ============================================================================
trap 'log_error "Script failed at line $LINENO"; exit 1' ERR

# ============================================================================
# Run Main
# ============================================================================
main
