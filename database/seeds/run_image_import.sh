#!/bin/bash
# Script para ejecutar el importador de imágenes dentro del contenedor API

echo "🚀 Ejecutando importador de imágenes en contenedor API..."
echo ""

docker-compose exec -T api python -m database.seeds.analyze_and_import_images

echo ""
echo "✅ Script completado"
