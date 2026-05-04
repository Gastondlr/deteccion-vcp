"""Dataclasses de datos para el pipeline de deteccion de VCP.

Cada dataclass representa la salida de un paso del pipeline:

- SwingPoint: salida del Paso 1 (deteccion de swing points).
- Contraction: salida del Paso 2 (calculo de contracciones HIGH->LOW).
- DecreasingSequence: salida del Paso 3 (secuencia decreciente + filtros de calidad).
- ATRCompressionResult: salida del Paso 4 (verificacion de compresion de ATR).
- VolumeContractionResult: salida del Paso 5 (verificacion de contraccion de volumen).
- PivotInfo: informacion del pivote identificado en el Paso 6.
- VCPSignal: salida final del Paso 6 (senal de compra confirmada).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from models.enums import SwingType


@dataclass(frozen=True)
class SwingPoint:
    """Un swing point (maximo o minimo local) detectado en una serie de precios.

    Attributes:
        date: Fecha del extremo (el high o low real en la serie).
        price: Precio del extremo (high si type=HIGH, low si type=LOW).
        type: SwingType.HIGH o SwingType.LOW.
        confirmed_at: Fecha en la cual el swing fue confirmado por el detector.
            Para ATR ZigZag, esto es posterior a ``date`` (confirmacion causal).
        metadata: Dict opcional con info especifica del detector.
    """

    date: pd.Timestamp
    price: float
    type: SwingType
    confirmed_at: pd.Timestamp
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Contraction:
    """Una contraccion de precio entre un swing high y el swing low siguiente.

    Representa la caida porcentual desde un pico hasta el valle inmediato.
    Es la unidad de medida basica del patron VCP.

    Attributes:
        high_swing: SwingPoint de tipo HIGH (inicio de la contraccion).
        low_swing: SwingPoint de tipo LOW (fin de la contraccion).
        depth_pct: Caida porcentual: (high - low) / high. Siempre positivo.
            Expresado como fraccion (0.05 = 5%).
        depth_abs: Caida absoluta en unidades del precio.
        duration_bars: Numero de bars entre high y low.
        confirmed_at: Fecha de confirmacion completa de la contraccion.
    """

    high_swing: SwingPoint
    low_swing: SwingPoint
    depth_pct: float
    depth_abs: float
    duration_bars: int
    confirmed_at: pd.Timestamp


@dataclass(frozen=True)
class DecreasingSequence:
    """Secuencia de contracciones decrecientes (patron VCP candidato).

    Una serie de N contracciones consecutivas donde cada una es menor que
    la anterior segun el metodo de monotonia configurado.

    Attributes:
        contractions: Lista ordenada cronologicamente de Contraction.
        evaluation_date: Fecha en la cual se evaluo la secuencia.
        method: Nombre del metodo de monotonia aplicado.
        method_metrics: Metricas especificas del metodo.
        n_contractions: Cantidad de contracciones en la secuencia.
        depths_pct: Lista de depth_pct en orden cronologico.
    """

    contractions: list[Contraction]
    evaluation_date: pd.Timestamp
    method: str
    method_metrics: dict
    n_contractions: int
    depths_pct: list[float]


@dataclass(frozen=True)
class ATRCompressionResult:
    """Resultado de evaluar la compresion de ATR a lo largo de un patron.

    Attributes:
        passes: True si el patron cumple el criterio de compresion.
        method: Metodo aplicado ("ratio", "trend", "ratio_normalized").
        atr_start: Valor de ATR al inicio del patron.
        atr_end: Valor de ATR al final del patron.
        start_date: Fecha de inicio (primer high de la secuencia).
        end_date: Fecha de fin (ultimo low de la secuencia).
        atr_period: Periodo usado para calcular el ATR.
        method_metrics: Metricas especificas del metodo.
    """

    passes: bool
    method: str
    atr_start: float
    atr_end: float
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    atr_period: int
    method_metrics: dict


@dataclass(frozen=True)
class VolumeContractionResult:
    """Resultado de evaluar la contraccion de volumen durante la formacion.

    Attributes:
        passes: True si el volumen se contrae segun el criterio configurado.
        method: Metodo aplicado ("per_contraction", "trend", "ratio").
        volume_column: Columna usada como proxy de volumen.
        avg_volumes: Volumen promedio por contraccion en orden cronologico.
        start_date: Fecha de inicio (primer high de la secuencia).
        end_date: Fecha de fin (ultimo low de la secuencia).
        method_metrics: Metricas especificas del metodo.
    """

    passes: bool
    method: str
    volume_column: str
    avg_volumes: list[float]
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    method_metrics: dict


@dataclass(frozen=True)
class PivotInfo:
    """Informacion del pivote identificado a partir de una DecreasingSequence.

    Attributes:
        price: Precio del pivote (high del ultimo par HIGH->LOW).
        date: Fecha del high del pivote.
        last_low_price: Precio del ultimo low (nivel de stop-loss natural).
        last_low_date: Fecha del ultimo low.
        sequence: Referencia a la DecreasingSequence de origen.
    """

    price: float
    date: pd.Timestamp
    last_low_price: float
    last_low_date: pd.Timestamp
    sequence: DecreasingSequence


@dataclass(frozen=True)
class VCPSignal:
    """Senal de compra confirmada por el detector heuristico de VCP.

    Salida final del pipeline — contiene toda la informacion necesaria
    para tomar una decision de trading.

    Attributes:
        signal_date: Fecha del breakout.
        entry_price: Precio sugerido de entrada (close del dia de senal).
        pivot_price: Precio del pivote superado.
        suggested_stop: Stop loss sugerido (ultimo low del patron).
        suggested_stop_distance_pct: Distancia entry-stop como fraccion.
        pivot_info: PivotInfo completo.
        atr_compression: ATRCompressionResult que valido la compresion.
        volume_confirmation: Info del filtro de volumen en breakout.
        volume_contraction: Resultado de contraccion de volumen en la base.
        metadata: Info adicional para debugging y analisis.
    """

    signal_date: pd.Timestamp
    entry_price: float
    pivot_price: float
    suggested_stop: float
    suggested_stop_distance_pct: float
    pivot_info: PivotInfo
    atr_compression: ATRCompressionResult
    volume_confirmation: dict
    volume_contraction: VolumeContractionResult | None = None
    metadata: dict = field(default_factory=dict)
