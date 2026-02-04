"""
Script simplificado para análisis manual de imágenes basándose en texto visible.
Extrae el texto de las imágenes con OCR y lo vincula con elementos.
"""

import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import select

from database.connection import get_async_session
from database.models import Element, ElementImage, VehicleCategory

# Mapeo manual basado en las imágenes que ya vimos
MANUAL_MAPPING = {
    # Imágenes de suspensión/amortiguación
    "0638b4b5-eb4b-490d-8626-443a9d445ff6.png": ("SUSP_NEUM", "Foto con medida desde el tanque - Sistema de amortiguación"),
    
    # Imágenes de toldo lateral
    "0a1ee7bb-b00d-453f-9069-f00ca56c4bd3.png": ("TOLDO_LAT", "Foto de instalación - Toldo lateral Dometic con luz de galibo"),
    
    # Imágenes de vistas laterales (documentación general)
    "0b1c7c33-021b-4d7e-8e03-4e7cc41b79a5.png": ("GENERAL", "4 fotos de las vistas laterales"),
    
    # Imágenes de galibo/toldo
    "0f7b7594-b834-4f5d-ac64-bbd7608abdb0.png": ("TOLDO_LAT", "Fotos de toldo y marcado de galibo"),
    
    # Placas solares
    "1694e135-736f-41cb-adb5-ed6fc8110589.png": ("PLACA_SOLAR", "Placa solar con regulador - Fotos necesarias"),
}


class ManualImageImporter:
    """Importador manual de imágenes."""
    
    def __init__(self):
        base_dir = Path("/app")
        self.source_dir = base_dir / "uploads" / "images_old"
        self.dest_dir = base_dir / "uploads" / "images"
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        
    async def import_images(self):
        """Importa imágenes manualmente mapeadas."""
        print("=" * 70)
        print("IMPORTADOR MANUAL DE IMÁGENES")
        print("=" * 70)
        
        image_files = sorted(self.source_dir.glob("*.png")) + sorted(
            self.source_dir.glob("*.jpg")
        )
        
        print(f"\n📂 Encontradas {len(image_files)} imágenes")
        print(f"📋 Mapeo manual disponible para {len(MANUAL_MAPPING)} imágenes\n")
        
        async with get_async_session() as session:
            # Obtener categoría
            cat_result = await session.execute(
                select(VehicleCategory).where(VehicleCategory.slug == "aseicars-prof")
            )
            category = cat_result.scalar_one_or_none()
            
            if not category:
                print("❌ Categoría 'aseicars-prof' no encontrada")
                return
            
            # Obtener elementos
            result = await session.execute(
                select(Element).where(Element.category_id == category.id)
            )
            elements = {elem.code: elem for elem in result.scalars().all()}
            
            print(f"✅ Categoría encontrada: {category.name}")
            print(f"✅ {len(elements)} elementos disponibles\n")
            
            stats = {"imported": 0, "skipped": 0, "general": 0}
            
            for image_path in image_files:
                filename = image_path.name
                
                if filename not in MANUAL_MAPPING:
                    # Intentar identificar por nombre si tiene patron reconocible
                    element_code, description = self._guess_from_filename(filename)
                else:
                    element_code, description = MANUAL_MAPPING[filename]
                
                if element_code == "GENERAL" or element_code is None:
                    print(f"⏭️  {filename}: General/No identificado")
                    stats["general"] += 1
                    continue
                
                if element_code not in elements:
                    print(f"⚠️  {filename}: Elemento {element_code} no encontrado")
                    stats["skipped"] += 1
                    continue
                
                # Copiar imagen
                ext = image_path.suffix
                new_filename = f"{uuid.uuid4()}{ext}"
                dest_path = self.dest_dir / new_filename
                shutil.copy2(image_path, dest_path)
                
                # Crear registro
                element = elements[element_code]
                image_url = f"/images/{new_filename}"
                
                # Obtener sort_order
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
                    title=description[:200] if description else f"Imagen {sort_order}",
                    description=description,
                    sort_order=sort_order,
                    status="active",
                    is_required=False,
                )
                
                session.add(element_image)
                stats["imported"] += 1
                
                print(f"✅ {element_code}: {description[:60]}...")
            
            await session.commit()
        
        print("\n" + "=" * 70)
        print("RESUMEN")
        print("=" * 70)
        print(f"✅ Importadas: {stats['imported']}")
        print(f"📄 Generales: {stats['general']}")
        print(f"⏭️  Omitidas: {stats['skipped']}")
        print(f"\n✅ Proceso completado")
    
    def _guess_from_filename(self, filename: str) -> tuple[str | None, str]:
        """Intenta adivinar el elemento por el nombre del archivo."""
        # Por ahora retornamos None - se puede mejorar después
        return None, f"Imagen {filename}"


async def main():
    """Main execution."""
    importer = ManualImageImporter()
    await importer.import_images()


if __name__ == "__main__":
    asyncio.run(main())
