"""
Script simple para importar imágenes de docs/images_old/ a uploads/images/
y crear registros en UploadedImage para que se puedan asignar desde el admin panel.
"""

import asyncio
import shutil
import uuid
from pathlib import Path
from PIL import Image

from sqlalchemy import select
from database.connection import get_async_session
from database.models import UploadedImage


async def import_images():
    """Importa todas las imágenes como uploaded_images."""
    
    print("=" * 70)
    print("IMPORTADOR SIMPLE DE IMÁGENES")
    print("=" * 70)
    
    source_dir = Path("/app/uploads/images_old")
    dest_dir = Path("/app/uploads/images")
    
    # Crear directorio destino si no existe
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Obtener todas las imágenes
    image_files = sorted(source_dir.glob("*.png")) + sorted(source_dir.glob("*.jpg"))
    
    print(f"\n📂 Directorio fuente: {source_dir}")
    print(f"📂 Directorio destino: {dest_dir}")
    print(f"📸 Total de imágenes encontradas: {len(image_files)}\n")
    
    stats = {"imported": 0, "skipped": 0, "errors": 0}
    
    async with get_async_session() as session:
        for idx, image_path in enumerate(image_files, 1):
            try:
                # Obtener info de la imagen
                with Image.open(image_path) as img:
                    width, height = img.size
                    mime_type = f"image/{img.format.lower()}"
                
                # Generar nuevo nombre
                ext = image_path.suffix
                new_filename = f"{uuid.uuid4()}{ext}"
                dest_path = dest_dir / new_filename
                
                # Copiar imagen
                shutil.copy2(image_path, dest_path)
                
                # Crear registro en DB
                uploaded_image = UploadedImage(
                    id=uuid.uuid4(),
                    filename=image_path.name,
                    stored_filename=new_filename,
                    mime_type=mime_type,
                    file_size=image_path.stat().st_size,
                    width=width,
                    height=height,
                    uploaded_by="system",
                    category="aseicars-prof",
                )
                
                session.add(uploaded_image)
                stats["imported"] += 1
                
                print(f"[{idx}/{len(image_files)}] ✅ {new_filename} ({width}x{height})")
                
            except Exception as e:
                print(f"[{idx}/{len(image_files)}] ❌ Error con {image_path.name}: {e}")
                stats["errors"] += 1
        
        # Commit todas las imágenes
        await session.commit()
    
    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"✅ Importadas: {stats['imported']}")
    print(f"❌ Errores: {stats['errors']}")
    print(f"\n✅ Proceso completado")
    print(f"\n💡 Las imágenes están ahora en:")
    print(f"   - Base de datos: tabla 'uploaded_images'")
    print(f"   - Filesystem: {dest_dir}")
    print(f"\n📝 Puedes asignarlas a elementos desde el admin panel en:")
    print(f"   /admin/elements → Editar elemento → Agregar imágenes")


async def main():
    """Main execution."""
    await import_images()


if __name__ == "__main__":
    asyncio.run(main())
