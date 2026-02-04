"""
Script para analizar imágenes de docs/images_old/ y vincularlas a elementos de autocaravanas.

Analiza visualmente las imágenes usando Claude, identifica el elemento correspondiente,
las copia a uploads/images/ y crea registros en element_images.
"""

import asyncio
import base64
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import anthropic
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_async_session
from database.models import Element, ElementImage
from shared.config import get_settings

settings = get_settings()

# Mapeo de elementos de autocaravanas
ELEMENT_MAPPING = {
    "ESCALON_ELEC": ["escalon", "peldano", "escalera electrica"],
    "TOLDO_LAT": ["toldo", "toldo lateral", "galibo"],
    "PLACA_SOLAR": ["placa solar", "panel solar", "solar", "regulador"],
    "ANTENA_PAR": ["antena", "parabolica", "satelite"],
    "PORTABICIS": ["portabicis", "bicicleta", "bike"],
    "CLARABOYA": ["claraboya", "ventana techo", "lucernario"],
    "BACA_TECHO": ["baca", "portaequipajes", "rack"],
    "BOLA_REMOLQUE": ["bola", "remolque", "enganche", "mmr"],
    "NEVERA_COMPRESOR": ["nevera", "frigorifico", "compresor"],
    "DEPOSITO_AGUA": ["deposito", "agua", "tanque"],
    "AIRE_ACONDI": ["aire acondicionado", "climatizador", "ac"],
    "PORTAMOTOS": ["portamotos", "moto", "motocicleta"],
    "SUSP_NEUM": ["suspension", "neumatica", "air"],
    "KIT_ESTAB": ["kit elevacion", "patas", "estabilizadoras", "nivelacion"],
    "AUMENTO_MMTA": ["mmta", "masa maxima", "peso"],
    "GLP_INSTALACION": ["glp", "gas", "bombona", "deposito"],
    "AUMENTO_PLAZAS": ["plazas", "asientos"],
    "CIERRES_EXT": ["cierres", "cerraduras", "locks"],
    "FAROS_LA": ["faros", "largo alcance", "luces"],
    "DEFENSAS_DEL": ["defensas", "bullbar", "defensa delantera"],
}


class ImageAnalyzer:
    """Analiza imágenes y las vincula con elementos."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.source_dir = Path("docs/images_old")
        self.dest_dir = Path(settings.IMAGE_UPLOAD_DIR)
        self.results = []

    def encode_image(self, image_path: Path) -> str:
        """Codifica imagen en base64."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def get_image_mime_type(self, image_path: Path) -> str:
        """Detecta MIME type de imagen."""
        ext = image_path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_types.get(ext, "image/jpeg")

    async def analyze_image(self, image_path: Path) -> dict[str, Any]:
        """Analiza una imagen con Claude Vision."""
        print(f"📷 Analizando: {image_path.name}")

        image_b64 = self.encode_image(image_path)
        mime_type = self.get_image_mime_type(image_path)

        prompt = f"""Analiza esta imagen instructiva de MSI sobre elementos de autocaravanas.

ELEMENTOS POSIBLES:
{json.dumps(list(ELEMENT_MAPPING.keys()), indent=2)}

TAREA:
1. Identifica el elemento principal de la imagen
2. Extrae el título/descripción visible en la imagen
3. Determina tu nivel de confianza (high/medium/low)

RESPONDE SOLO CON JSON:
{{
    "element_code": "CODIGO_ELEMENTO",
    "confidence": "high|medium|low",
    "title": "Título extraído de la imagen",
    "description": "Breve descripción de lo que muestra",
    "text_found": ["texto1", "texto2"]
}}

Si no puedes identificar el elemento, usa "element_code": "DESCONOCIDO"
"""

        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": image_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

            # Extraer JSON de la respuesta
            content = response.content[0].text.strip()
            # Limpiar markdown si existe
            if content.startswith("```json"):
                content = content.split("```json")[1].split("```")[0].strip()
            elif content.startswith("```"):
                content = content.split("```")[1].split("```")[0].strip()

            analysis = json.loads(content)
            analysis["original_filename"] = image_path.name

            return analysis

        except Exception as e:
            print(f"❌ Error analizando {image_path.name}: {e}")
            return {
                "original_filename": image_path.name,
                "element_code": "ERROR",
                "confidence": "low",
                "title": "",
                "description": f"Error: {str(e)}",
                "text_found": [],
            }

    async def analyze_all_images(self):
        """Analiza todas las imágenes del directorio."""
        image_files = sorted(self.source_dir.glob("*.png")) + sorted(
            self.source_dir.glob("*.jpg")
        )

        print(f"\n🔍 Encontradas {len(image_files)} imágenes para analizar\n")

        for idx, image_path in enumerate(image_files, 1):
            print(f"[{idx}/{len(image_files)}] ", end="")
            analysis = await self.analyze_image(image_path)
            self.results.append(analysis)

            # Rate limiting: 50 requests/min con Sonnet
            if idx < len(image_files):
                await asyncio.sleep(1.5)

        # Guardar resultados
        output_file = Path("database/seeds/image_analysis_results.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "total_images": len(self.results),
                    "analysis": self.results,
                    "summary": self._generate_summary(),
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        print(f"\n✅ Análisis completo guardado en: {output_file}")
        return self.results

    def _generate_summary(self) -> dict:
        """Genera resumen del análisis."""
        summary = {
            "total": len(self.results),
            "by_element": {},
            "by_confidence": {"high": 0, "medium": 0, "low": 0},
            "unknown": 0,
            "errors": 0,
        }

        for result in self.results:
            element = result["element_code"]
            confidence = result.get("confidence", "low")

            if element == "DESCONOCIDO":
                summary["unknown"] += 1
            elif element == "ERROR":
                summary["errors"] += 1
            else:
                summary["by_element"][element] = (
                    summary["by_element"].get(element, 0) + 1
                )

            summary["by_confidence"][confidence] = (
                summary["by_confidence"].get(confidence, 0) + 1
            )

        return summary

    async def import_to_database(self, analysis_results: list[dict]):
        """Importa imágenes a la base de datos."""
        print("\n📦 Importando imágenes a la base de datos...")

        # Crear directorio destino si no existe
        self.dest_dir.mkdir(parents=True, exist_ok=True)

        async with get_async_session() as session:
            # Obtener elementos de aseicars-prof
            from database.models import VehicleCategory
            
            # Primero obtener la categoría
            cat_result = await session.execute(
                select(VehicleCategory).where(VehicleCategory.slug == "aseicars-prof")
            )
            category = cat_result.scalar_one_or_none()
            
            if not category:
                print("❌ Categoría 'aseicars-prof' no encontrada en la base de datos")
                return {"imported": 0, "skipped": len(analysis_results), "errors": 0}
            
            # Luego obtener elementos de esa categoría
            result = await session.execute(
                select(Element).where(Element.category_id == category.id)
            )
            elements = {elem.code: elem for elem in result.scalars().all()}
            
            print(f"📋 Encontrados {len(elements)} elementos en categoría aseicars-prof")

            stats = {"imported": 0, "skipped": 0, "errors": 0}

            for analysis in analysis_results:
                element_code = analysis["element_code"]

                if element_code in ["DESCONOCIDO", "ERROR"]:
                    stats["skipped"] += 1
                    continue

                if element_code not in elements:
                    print(
                        f"⚠️  Elemento {element_code} no encontrado en BD, omitiendo"
                    )
                    stats["skipped"] += 1
                    continue

                try:
                    # Copiar imagen a uploads/images/
                    source_path = self.source_dir / analysis["original_filename"]
                    ext = source_path.suffix
                    new_filename = f"{uuid.uuid4()}{ext}"
                    dest_path = self.dest_dir / new_filename

                    shutil.copy2(source_path, dest_path)

                    # Crear registro ElementImage
                    element = elements[element_code]
                    image_url = f"/images/{new_filename}"

                    # Obtener sort_order (siguiente disponible para este elemento)
                    max_order_result = await session.execute(
                        select(ElementImage.sort_order)
                        .where(ElementImage.element_id == element.id)
                        .order_by(ElementImage.sort_order.desc())
                        .limit(1)
                    )
                    max_order = max_order_result.scalar()
                    sort_order = (max_order or 0) + 1

                    element_image = ElementImage(
                        id=uuid.uuid4(),
                        element_id=element.id,
                        image_url=image_url,
                        image_type="example",
                        title=analysis.get("title", "")[:200],
                        description=analysis.get("description", ""),
                        sort_order=sort_order,
                        status="active",
                        is_required=False,
                    )

                    session.add(element_image)
                    stats["imported"] += 1

                    print(
                        f"✅ {element_code}: {new_filename} → {analysis.get('title', '')[:50]}"
                    )

                except Exception as e:
                    print(f"❌ Error importando {analysis['original_filename']}: {e}")
                    stats["errors"] += 1

            await session.commit()

        print(f"\n📊 Importación completada:")
        print(f"   ✅ Importadas: {stats['imported']}")
        print(f"   ⏭️  Omitidas: {stats['skipped']}")
        print(f"   ❌ Errores: {stats['errors']}")

        return stats


async def main():
    """Main execution."""
    analyzer = ImageAnalyzer()

    # Paso 1: Analizar todas las imágenes
    print("=" * 70)
    print("PASO 1: ANÁLISIS DE IMÁGENES CON CLAUDE VISION")
    print("=" * 70)

    results = await analyzer.analyze_all_images()

    # Mostrar resumen
    summary = analyzer._generate_summary()
    print("\n" + "=" * 70)
    print("RESUMEN DEL ANÁLISIS")
    print("=" * 70)
    print(f"Total imágenes analizadas: {summary['total']}")
    print(f"Desconocidas: {summary['unknown']}")
    print(f"Errores: {summary['errors']}")
    print(f"\nPor nivel de confianza:")
    print(f"  Alta: {summary['by_confidence']['high']}")
    print(f"  Media: {summary['by_confidence']['medium']}")
    print(f"  Baja: {summary['by_confidence']['low']}")
    print(f"\nPor elemento:")
    for element, count in sorted(summary["by_element"].items()):
        print(f"  {element}: {count}")

    # Paso 2: Preguntar si continuar con importación
    print("\n" + "=" * 70)
    print("PASO 2: IMPORTACIÓN A BASE DE DATOS")
    print("=" * 70)

    response = input("\n¿Continuar con la importación a la base de datos? (s/n): ")
    if response.lower() != "s":
        print("❌ Importación cancelada por el usuario")
        return

    # Paso 3: Importar a base de datos
    await analyzer.import_to_database(results)

    print("\n✅ Proceso completado exitosamente")


if __name__ == "__main__":
    asyncio.run(main())
