"""
MSI Automotive - Database Seed Scripts.

Refactored architecture (2026-01):
- data/: Seed data definitions (constants only)
- seeders/: Reusable seeding logic

Available categories:
- motos-part: Motocicletas for particulars (39 elements)
- aseicars-prof: Autocaravanas for professionals (~30 elements)

Run all seeds:
    python -m database.seeds.run_all_seeds

Validate seeds:
    python -m database.seeds.validate_elements_seed

Adding a new category:
    1. Create data/nueva_categoria.py with CATEGORY, TIERS, ELEMENTS, etc.
    2. Import in run_all_seeds.py and add call to seed_category()
    3. No modifications needed to seeders
"""

from database.seeds.run_all_seeds import run_all_seeds, seed_category

__all__ = [
    "run_all_seeds",
    "seed_category",
]
