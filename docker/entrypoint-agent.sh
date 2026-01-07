#!/bin/bash
set -e

# Entrypoint script for MSI Automotive Agent Service
# This script initializes the database before starting the agent

echo "================================================"
echo "MSI Automotive Agent - Entrypoint"
echo "================================================"

# Function to run database initialization
initialize_database() {
    echo ""
    echo "Running database initialization..."

    if /app/docker/init-db.sh; then
        echo "Database initialization completed"
        return 0
    else
        echo "ERROR: Database initialization failed"
        return 1
    fi
}

# Main execution
main() {
    echo "Starting agent initialization sequence..."

    # Step 1: Initialize database
    if ! initialize_database; then
        echo ""
        echo "FATAL ERROR: Cannot start agent - database initialization failed"
        exit 1
    fi

    echo ""
    echo "================================================"
    echo "Initialization complete - Starting agent service"
    echo "================================================"
    echo ""

    # Step 2: Start the actual agent service
    # Pass all arguments to the agent
    exec "$@"
}

# Run main function with all script arguments
main "$@"
