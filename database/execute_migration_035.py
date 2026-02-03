#!/usr/bin/env python3
"""
Ejecuta la migración 035 directamente conectándose a PostgreSQL en Docker.
"""
import sys
import psycopg

# Importar las funciones de la migración
sys.path.insert(0, '/home/autohomologacion/msi-a')
from database.alembic.versions import migration_035_restructure_motos_elements as migration

# Conexión a PostgreSQL (dentro de Docker, accesible por puerto 5432)
DATABASE_URL = "host=localhost port=5432 dbname=msia_db user=msia password=Msi4ut0m0t1v3_2024!"

def main():
    print("=" * 80)
    print("🚀 Ejecutando Migración 035: Motorcycle Seeds Restructuring")
    print("=" * 80)
    print()
    
    # Conectar
    try:
        conn = psycopg.connect(DATABASE_URL, autocommit=False)
        print("✅ Conexión a PostgreSQL establecida")
    except Exception as e:
        print(f"❌ Error conectando: {e}")
        return 1
    
    cursor = conn.cursor()
    
    try:
        # Verificar versión actual
        cursor.execute("SELECT version_num FROM alembic_version")
        current_version = cursor.fetchone()[0]
        print(f"📌 Versión actual: {current_version}")
        print()
        
        if current_version != "7dc32f4a106a":
            print(f"⚠️  Versión inesperada. Esperada: 7dc32f4a106a, encontrada: {current_version}")
            response = input("¿Continuar de todos modos? (s/N): ")
            if response.lower() != 's':
                return 1
        
        print("🔧 Aplicando migración...")
        print()
        
        # Ejecutar upgrade() pasando el cursor
        migration.upgrade()
        
        # Actualizar alembic_version
        print("📝 Actualizando alembic_version...")
        cursor.execute(
            "UPDATE alembic_version SET version_num = %s",
            ("035_restructure_motos_elements",)
        )
        
        # Commit
        conn.commit()
        print()
        print("=" * 80)
        print("✅ ¡MIGRACIÓN APLICADA EXITOSAMENTE!")
        print("=" * 80)
        print()
        
        # Verificar versión final
        cursor.execute("SELECT version_num FROM alembic_version")
        final_version = cursor.fetchone()[0]
        print(f"📌 Versión final: {final_version}")
        print()
        print("📊 Próximo paso: Verificar con script")
        print("   $ python3 database/seeds/verify_restructure.py")
        print()
        
        return 0
        
    except Exception as e:
        conn.rollback()
        print()
        print("=" * 80)
        print(f"❌ ERROR APLICANDO MIGRACIÓN")
        print("=" * 80)
        print()
        print(f"Error: {e}")
        print()
        import traceback
        traceback.print_exc()
        print()
        print("💡 La base de datos se revirtió al estado anterior (rollback)")
        return 1
        
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    sys.exit(main())
