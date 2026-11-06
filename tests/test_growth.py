from octodesk.growth import (MOON_KM, compound_series, doubling_ladder,
                             fold_distance_km, steps_to_target)


def test_steps_to_target_boundary():
    assert steps_to_target(1, 1_000_000) == 20
    assert steps_to_target(1, 1024) == 10
    assert steps_to_target(1, 1025) == 11
    assert steps_to_target(5, 5) == 0


def test_fold_to_the_moon():
    assert fold_distance_km(42) > MOON_KM
    assert fold_distance_km(41) < MOON_KM
    assert abs(fold_distance_km(42) - 439804.65) < 1.0


def test_compound_series_last_value():
    series = compound_series(100.0, 0.07, 52)
    assert len(series) == 53
    assert abs(series[-1] - 100.0 * 1.07 ** 52) < 1e-6


def test_doubling_ladder():
    assert doubling_ladder(1, 4) == [1, 2, 4, 8, 16]
    assert doubling_ladder(1, 20)[-1] == 1_048_576
