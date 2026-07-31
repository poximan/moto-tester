from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class CommandBody(BaseModel):
    tag: str = Field(..., description="Tag de comando, por ejemplo cB1Aut")
    value: bool | int = Field(..., description="Valor a escribir o registrar localmente")
    source: str = Field(default="web", description="Origen del comando")


class PumpCommandBody(BaseModel):
    aut: bool | None = Field(default=None, description="Valor para cB#Aut")
    mr: bool | None = Field(default=None, description="Valor para cB#Mr")
    source: str = Field(default="web", description="Origen del comando")

    @model_validator(mode="after")
    def at_least_one_value(self) -> "PumpCommandBody":
        if self.aut is None and self.mr is None:
            raise ValueError("Debe informar al menos aut o mr")
        return self


class FacadeBody(BaseModel):
    values: dict[str, bool | int | float | str] = Field(default_factory=dict)
    source: str = Field(default="web", description="Origen del pedido")


class GenericWriteBody(BaseModel):
    tag: str
    value: Any
    source: str = "web"


class WriteModeBody(BaseModel):
    mode: Literal["read_only", "write_enabled"] = Field(
        ...,
        description="Modo persistido en runtime/write_mode.txt",
    )
    source: str = Field(default="web", description="Origen del cambio")


class PollingControlBody(BaseModel):
    enabled: bool | None = Field(default=None, description="Habilita la lectura de la FC")
    sample_rate_ms: int | None = Field(
        default=None,
        ge=250,
        le=3_600_000,
        description="Intervalo entre lecturas de la FC en milisegundos",
    )
    source: str = Field(default="web", description="Origen del cambio")

    @model_validator(mode="after")
    def at_least_one_setting(self) -> "PollingControlBody":
        if self.enabled is None and self.sample_rate_ms is None:
            raise ValueError("Debe informar enabled o sample_rate_ms")
        return self


class EmulatorValveBody(BaseModel):
    inlet_open_pct: float | None = Field(default=None, ge=0, le=100)
    outlet_open_pct: float | None = Field(default=None, ge=0, le=100)
