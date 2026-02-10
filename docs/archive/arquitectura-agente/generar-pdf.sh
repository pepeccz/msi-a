#!/bin/bash

# Script para generar el PDF de la arquitectura del agente
# Requiere: Node.js

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTML_FILE="$SCRIPT_DIR/arquitectura-agente.html"
PDF_FILE="$SCRIPT_DIR/arquitectura-agente.pdf"

echo "=============================================="
echo "  Generador de PDF - Arquitectura del Agente"
echo "=============================================="
echo ""

# Verificar que existe el archivo HTML
if [ ! -f "$HTML_FILE" ]; then
    echo "ERROR: No se encuentra el archivo HTML"
    echo "       $HTML_FILE"
    exit 1
fi

echo "Archivo HTML encontrado: $HTML_FILE"
echo ""

# Verificar Node.js
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js no esta instalado"
    echo ""
    echo "Para generar el PDF manualmente:"
    echo "  1. Abre el archivo HTML en un navegador"
    echo "  2. Haz clic en 'Guardar como PDF' o Ctrl+P"
    exit 1
fi

# Instalar puppeteer si no existe
if [ ! -d "$SCRIPT_DIR/node_modules/puppeteer" ]; then
    echo "Instalando dependencias (primera vez)..."
    cd "$SCRIPT_DIR"
    npm init -y > /dev/null 2>&1
    npm install puppeteer --silent
    echo ""
fi

echo "Generando PDF con Puppeteer..."
echo ""

# Crear script temporal de Node.js
cat > "$SCRIPT_DIR/.generate-pdf.mjs" << 'NODEJS_SCRIPT'
import puppeteer from 'puppeteer';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function generatePDF() {
    const browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    
    const page = await browser.newPage();
    
    // Cargar el HTML
    const htmlPath = join(__dirname, 'arquitectura-agente.html');
    await page.goto(`file://${htmlPath}`, {
        waitUntil: 'networkidle0',
        timeout: 60000
    });
    
    // Esperar a que Mermaid renderice los diagramas
    await page.waitForSelector('.mermaid svg', { timeout: 30000 });
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // Generar PDF
    const pdfPath = join(__dirname, 'arquitectura-agente.pdf');
    await page.pdf({
        path: pdfPath,
        format: 'A4',
        printBackground: true,
        margin: {
            top: '20mm',
            right: '15mm',
            bottom: '20mm',
            left: '15mm'
        }
    });
    
    console.log(`PDF generado: ${pdfPath}`);
    
    await browser.close();
}

generatePDF().catch(console.error);
NODEJS_SCRIPT

# Ejecutar el script
cd "$SCRIPT_DIR"
node .generate-pdf.mjs

# Limpiar script temporal
rm -f .generate-pdf.mjs

if [ -f "$PDF_FILE" ]; then
    echo ""
    echo "=============================================="
    echo "  PDF generado exitosamente!"
    echo "  $PDF_FILE"
    echo "=============================================="
    echo ""
    echo "Para limpiar dependencias de Node.js:"
    echo "  rm -rf $SCRIPT_DIR/node_modules $SCRIPT_DIR/package*.json"
else
    echo ""
    echo "ERROR: No se pudo generar el PDF"
    echo ""
    echo "Alternativa manual:"
    echo "  1. Abre el HTML en un navegador: $HTML_FILE"
    echo "  2. Haz clic en 'Guardar como PDF' o usa Ctrl+P"
fi
