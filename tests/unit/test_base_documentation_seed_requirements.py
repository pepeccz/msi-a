"""Seed contract tests for base documentation wording and order."""

import pytest


@pytest.mark.unit
@pytest.mark.parametrize(
    ("module_path", "expected_vehicle_term"),
    [
        ("database.seeds.data.common", "vehiculo"),
        ("database.seeds.data.motos_part", "moto"),
        ("database.seeds.data.aseicars_prof", "vehiculo"),
        ("database.seeds.data.aseicars_part", "vehiculo"),
    ],
)
def test_base_documentation_has_required_codes_order_and_photo_wording(
    module_path: str,
    expected_vehicle_term: str,
) -> None:
    module = __import__(module_path, fromlist=["BASE_DOCUMENTATION"])
    docs = module.BASE_DOCUMENTATION_COMMON if module_path.endswith("common") else module.BASE_DOCUMENTATION

    assert [doc["code"] for doc in docs] == [
        "ficha_tecnica",
        "permiso_circulacion",
        "dni_titular",
        "fotos_vehiculo",
    ]
    assert [doc["sort_order"] for doc in docs] == [1, 2, 3, 4]

    descriptions = [doc["description"].lower() for doc in docs]
    assert "foto" in descriptions[0]
    assert "foto" in descriptions[1]
    assert "foto" in descriptions[2]
    assert "dni/nie" in descriptions[2]
    assert "foto" in descriptions[3]
    assert expected_vehicle_term in descriptions[3]
