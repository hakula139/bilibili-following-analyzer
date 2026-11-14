"""Read and validate local analysis configuration."""

from __future__ import annotations

import math
import tomllib
from pathlib import Path
from typing import Any


DEFAULTS: dict[str, Any] = {
    'mid': None,
    'allow_list': [],
    'delay': 0.3,
    'output': None,
    'filters': [],
    'filter_expr': None,
    'filter_mode': 'and',
    'num_videos': 10,
    'num_dynamics': 20,
}


def load_config(path: Path, *, required: bool) -> dict[str, Any]:
    """Read known settings without exposing values in errors.

    Parameters
    ----------
    path : Path
        Configuration file to read.
    required : bool
        Whether a missing file is an error. Optional missing files return no
        settings, while unreadable files and malformed TOML always fail.

    Returns
    -------
    dict[str, Any]
        Known settings, before CLI overrides and value validation.

    Raises
    ------
    ValueError
        If the file cannot be read or contains malformed TOML or unknown keys.
    """
    try:
        with path.open('rb') as handle:
            config = tomllib.load(handle)
    except FileNotFoundError:
        if not required:
            return {}
        raise ValueError(f'Configuration file not found: {path}') from None
    except tomllib.TOMLDecodeError:
        raise ValueError(f'Invalid TOML in configuration file: {path}') from None
    except OSError as error:
        raise ValueError(f'Cannot read configuration file: {path}') from error

    unknown = config.keys() - DEFAULTS.keys()
    if unknown:
        names = ', '.join(sorted(unknown))
        raise ValueError(f'Unknown configuration keys in {path}: {names}')
    return config


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate merged settings and normalize the output path.

    Parameters
    ----------
    config : dict[str, Any]
        Complete settings after defaults, file values, and CLI overrides merge.

    Returns
    -------
    dict[str, Any]
        The same dictionary with output converted to a Path. Relative paths
        retain their current working directory semantics.

    Raises
    ------
    ValueError
        If an effective setting has the wrong type or range. Messages name
        settings without including their values.
    """
    mid = config['mid']
    if mid is not None and (type(mid) is not int or mid <= 0):
        raise ValueError('mid must be a positive integer')

    allow_list = config['allow_list']
    if not isinstance(allow_list, list) or any(
        type(uid) is not int or uid <= 0 for uid in allow_list
    ):
        raise ValueError('allow_list must be an array of positive integer UIDs')

    delay = config['delay']
    if type(delay) not in (int, float) or not math.isfinite(delay) or delay < 0:
        raise ValueError('delay must be a finite nonnegative number')

    output = config['output']
    if output is not None:
        if not isinstance(output, (str, Path)) or not str(output):
            raise ValueError('output must be a nonempty file path')
        config['output'] = Path(output)

    filters = config['filters']
    if not isinstance(filters, list) or any(
        not isinstance(spec, str) for spec in filters
    ):
        raise ValueError('filters must be an array of strings')

    expression = config['filter_expr']
    if expression is not None and not isinstance(expression, str):
        raise ValueError('filter_expr must be a string')
    if config['filter_mode'] not in ('and', 'or'):
        raise ValueError('filter_mode must be and or or')

    for name in ('num_videos', 'num_dynamics'):
        value = config[name]
        if type(value) is not int or value < 0:
            raise ValueError(f'{name} must be a nonnegative integer')
    return config
