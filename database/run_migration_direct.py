#!/usr/bin/env python3
"""
Script para ejecutar la migración 035 directamente contra PostgreSQL en Docker.
"""
import sys
sys.path.insert(0, '/home/autohomologacion/msi-a')

from database.alembic.versions.import_035_restructure_motos_elements import upgrade, downgrade
import psycopg
from datetime import datetime

# Conexión directa a PostgreSQL (fuera de Docker)
DATABASE_URL = "postgresql://msia:Msi4ut0m0t1v3_2024!@localhost:5432/msia_db"

def run_migration():
    print("=" * 70)
    print("🚀 Ejecutando migración: 035_restructure_motos_elements")
    print("=" * 70)
    print()
    
    # Conectar
    try:
        conn = psycopg.connect(DATABASE_URL)
        print("✅ Conexión a PostgreSQL establecida")
    except Exception as e:
        print(f"❌ Error conectando a PostgreSQL: {e}")
        print("\n💡 Asegúrate de que PostgreSQL está corriendo y accesible en localhost:5432")
        return 1
    
    try:
        with conn.cursor() as cur:
            # Verificar versión actual
            cur.execute("SELECT version_num FROM alembic_version")
            current_version = cur.fetchone()[0]
            print(f"📌 Versión actual: {current_version}")
            
            if current_version != "7dc32f4a106a":
                print(f"⚠️  Versión actual ({current_version}) no es la esperada (7dc32f4a106a)")
                print("   La migración puede fallar.")
                response = input("\n¿Continuar de todos modos? (s/N): ")
                if response.lower() != 's':
                    print("❌ Migración cancelada")
                    return 1
            
            print()
            print("🔧 Aplicando migración...")
            
            # Ejecutar upgrade()
            upgrade()
            
            # Actualizar alembic_version
            cur.execute(
                "UPDATE alembic_version SET version_num = '035_restructure_motos_elements'"
            )
            
            conn.commit()
            
            print()
            print("=" * 70)
            print("✅ Migración aplicada exitosamente")
            print("=" * 70)
            print()
            print("📊 Próximo paso: Ejecutar verificación")
            print("   python3 database/seeds/verify_restructure.py")
            
            return 0
            
    except Exception as e:
        conn.rollback()
        print()
        print("=" * 70)
        print(f"❌ Error aplicando migración: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        conn.close()

if __name__ == "__main__":
    sys.exit(run_migration())
