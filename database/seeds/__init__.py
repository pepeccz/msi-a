"""
MSI Automotive - Database Seed Scripts.

New architecture (2026-01-11):
- Categories now have client_type (particular/professional)
- Tiers no longer have client_type
- Slugs include type suffix: motos-part, motos-prof, aseicars-part, aseicars-prof

Available seeds:
- motos_particular_seed: Motocicletas for particulars (motos-part)
- aseicars_professional_seed: Autocaravanas for professionals (aseicars-prof)
- run_all_seeds: Execute all seeds at once

Run all seeds:
    python -m database.seeds.run_all_seeds
"""
