"""Validation of input features for the prediction API."""

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt


class PredictionRequest(BaseModel):
    """The twelve input features used by the trained model."""

    model_config = ConfigDict(extra="forbid")

    season: StrictInt = Field(ge=1, le=4)
    yr: StrictInt = Field(ge=0, le=1)
    mnth: StrictInt = Field(ge=1, le=12)
    hr: StrictInt = Field(ge=0)
    holiday: StrictInt = Field(ge=0, le=1)
    weekday: StrictInt = Field(ge=0, le=6)
    workingday: StrictInt = Field(ge=0, le=1)
    weathersit: StrictInt = Field(ge=1, le=4)

    temp: StrictFloat = Field(ge=0, le=1, allow_inf_nan=False)
    atemp: StrictFloat = Field(ge=0, le=1, allow_inf_nan=False)
    hum: StrictFloat = Field(ge=0, le=1, allow_inf_nan=False)
    windspeed: StrictFloat = Field(ge=0, le=1, allow_inf_nan=False)
