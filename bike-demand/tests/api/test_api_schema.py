"""Tests for the prediction request schema."""

import pytest
from pydantic import ValidationError

from bike_demand.api_schema import PredictionRequest

VALID_REQUEST = {
    "season": 1,
    "yr": 0,
    "mnth": 1,
    "hr": 8,
    "holiday": 0,
    "weekday": 1,
    "workingday": 1,
    "weathersit": 1,
    "temp": 0.5,
    "atemp": 0.5,
    "hum": 0.6,
    "windspeed": 0.2,
}


def test_valid_request():
    request = PredictionRequest(**VALID_REQUEST)
    assert request.hr == 8
    assert len(request.model_dump()) == 12


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("season", 5),
        ("yr", 2),
        ("mnth", 13),
        ("hr", 30),
        ("holiday", 2),
        ("weekday", 7),
        ("workingday", 2),
        ("weathersit", 5),
        ("temp", -0.1),
        ("atemp", 1.1),
        ("hum", float("nan")),
        ("windspeed", float("inf")),
    ],
)
def test_invalid_values(field, invalid_value):
    data = VALID_REQUEST.copy()
    data[field] = invalid_value

    with pytest.raises(ValidationError):
        PredictionRequest(**data)


def test_missing_field():
    data = VALID_REQUEST.copy()
    del data["hr"]

    with pytest.raises(ValidationError):
        PredictionRequest(**data)


def test_extra_field():
    data = VALID_REQUEST.copy()
    data["cnt"] = 100

    with pytest.raises(ValidationError):
        PredictionRequest(**data)


def test_wrong_integer_type():
    data = VALID_REQUEST.copy()
    data["hr"] = "8"

    with pytest.raises(ValidationError):
        PredictionRequest(**data)


def test_wrong_float_type():
    data = VALID_REQUEST.copy()
    data["temp"] = "0.5"

    with pytest.raises(ValidationError):
        PredictionRequest(**data)
