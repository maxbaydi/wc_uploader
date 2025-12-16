#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Вспомогательные функции для чтения CSV с поддержкой нескольких кодировок.
"""

from typing import Callable, Iterable, Optional, Tuple

import pandas as pd

DEFAULT_ENCODINGS: Tuple[str, ...] = (
    "utf-8",
    "cp1251",
    "iso-8859-1",
    "windows-1251",
    "latin-1",
)


def read_csv_with_fallback(
    path: str,
    *,
    encodings: Iterable[str] = DEFAULT_ENCODINGS,
    log: Optional[Callable[[str], None]] = None,
    **kwargs,
) -> pd.DataFrame:
    """
    Читает CSV, последовательно пробуя список кодировок.
    Возвращает DataFrame или выбрасывает ValueError после исчерпания вариантов.
    """
    last_error: Optional[Exception] = None

    for encoding in encodings:
        try:
            df = pd.read_csv(path, encoding=encoding, **kwargs)
            if log:
                log(f"✅ CSV загружен с кодировкой: {encoding}")
            return df
        except UnicodeDecodeError as exc:
            last_error = exc
            if log:
                log(f"⚠️ Ошибка кодировки {encoding}: {exc}")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if log:
                log(f"⚠️ Ошибка чтения CSV ({encoding}): {exc}")

    raise ValueError(
        f"Не удалось прочитать CSV '{path}' с кодировками: {', '.join(encodings)}"
    ) from last_error


def read_csv_preview(
    path: str,
    *,
    nrows: int = 5,
    encodings: Iterable[str] = DEFAULT_ENCODINGS,
    log: Optional[Callable[[str], None]] = None,
    **kwargs,
) -> Optional[pd.DataFrame]:
    """
    Читает небольшой фрагмент CSV для предпросмотра, возвращает None при ошибке.
    """
    try:
        return read_csv_with_fallback(
            path,
            encodings=encodings,
            log=log,
            nrows=nrows,
            **kwargs,
        )
    except Exception as exc:  # noqa: BLE001
        if log:
            log(f"⚠️ Предпросмотр CSV не удался: {exc}")
        return None

