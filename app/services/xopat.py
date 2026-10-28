"""Helpers for XOpat slide IDs and Deep Zoom tile generation."""

from __future__ import annotations

import base64
import json
import math
import os
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Any

from openslide import OpenSlide, open_slide
from openslide.deepzoom import DeepZoomGenerator
from PIL import Image


_CACHE_LOCK = Lock()
_SLIDE_CACHE: OrderedDict[tuple, Any] = OrderedDict()
_MAX_CACHED_SLIDES = 32
_RASTER_LEVEL_CACHE_SIZE = 4


class _ThreadSafeGenerator:
    def __init__(self, generator: Any):
        self._generator = generator
        self._lock = Lock()

    def get_dzi(self, image_format: str) -> str:
        with self._lock:
            return self._generator.get_dzi(image_format)

    def get_tile(self, level: int, address: tuple[int, int]) -> Image.Image:
        with self._lock:
            return self._generator.get_tile(level, address)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._generator, name)


class RasterDeepZoomGenerator:
    def __init__(
        self,
        file_path: str,
        *,
        tile_size: int = 254,
        overlap: int = 1,
        limit_bounds: bool = True,
    ):
        self._file_path = file_path
        self.tile_size = tile_size
        self.overlap = overlap
        self.limit_bounds = limit_bounds
        self._image = Image.open(file_path)
        self._image.load()
        self.width, self.height = self._image.size
        self.level_dimensions = self._build_level_dimensions(self.width, self.height)
        self.level_tiles = tuple(
            (
                math.ceil(level_width / self.tile_size),
                math.ceil(level_height / self.tile_size),
            )
            for level_width, level_height in self.level_dimensions
        )
        self.level_count = len(self.level_dimensions)
        self._level_cache: OrderedDict[int, Image.Image] = OrderedDict()

    @staticmethod
    def _build_level_dimensions(width: int, height: int) -> tuple[tuple[int, int], ...]:
        max_dimension = max(width, height)
        max_level = math.ceil(math.log2(max_dimension)) if max_dimension > 1 else 0
        dimensions: list[tuple[int, int]] = []
        for level in range(max_level + 1):
            scale = 2 ** (max_level - level)
            dimensions.append((
                max(1, math.ceil(width / scale)),
                max(1, math.ceil(height / scale)),
            ))
        return tuple(dimensions)

    def get_dzi(self, image_format: str) -> str:
        return (
            f'<Image TileSize="{self.tile_size}" Overlap="{self.overlap}" '
            f'Format="{image_format}" xmlns="http://schemas.microsoft.com/deepzoom/2008">'
            f'<Size Width="{self.width}" Height="{self.height}" /></Image>'
        )

    def _get_level_image(self, level: int) -> Image.Image:
        if level == self.level_count - 1:
            return self._image

        cached = self._level_cache.get(level)
        if cached is not None:
            self._level_cache.move_to_end(level)
            return cached

        level_size = self.level_dimensions[level]
        level_image = self._image.resize(level_size, Image.Resampling.LANCZOS)
        self._level_cache[level] = level_image
        self._level_cache.move_to_end(level)

        while len(self._level_cache) > _RASTER_LEVEL_CACHE_SIZE:
            self._level_cache.popitem(last=False)

        return level_image

    def get_tile(self, level: int, address: tuple[int, int]) -> Image.Image:
        if level < 0 or level >= self.level_count:
            raise ValueError('Invalid Deep Zoom level.')

        col, row = address
        cols, rows = self.level_tiles[level]
        if col < 0 or row < 0 or col >= cols or row >= rows:
            raise ValueError('Invalid Deep Zoom tile address.')

        level_width, level_height = self.level_dimensions[level]
        x = col * self.tile_size
        y = row * self.tile_size
        x0 = max(0, x - (self.overlap if col > 0 else 0))
        y0 = max(0, y - (self.overlap if row > 0 else 0))
        x1 = min(
            level_width,
            x + self.tile_size + (self.overlap if col + 1 < cols else 0),
        )
        y1 = min(
            level_height,
            y + self.tile_size + (self.overlap if row + 1 < rows else 0),
        )

        level_image = self._get_level_image(level)
        return level_image.crop((x0, y0, x1, y1))


def _encode_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def decode_slide_id(slide_id: str) -> dict[str, Any]:
    padded = slide_id + ('=' * (-len(slide_id) % 4))
    try:
        raw = base64.urlsafe_b64decode(padded.encode('ascii'))
        data = json.loads(raw.decode('utf-8'))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid XOpat slide identifier.') from exc
    if not isinstance(data, dict):
        raise ValueError('Invalid XOpat slide identifier.')
    return data


def make_admin_slide_id(image_path: str) -> str:
    return _encode_payload({
        'kind': 'admin_dataset',
        'image_path': image_path,
    })


def make_study_slide_id(study_id: int, dataset_image_id: int) -> str:
    return _encode_payload({
        'kind': 'study_image',
        'study_id': int(study_id),
        'dataset_image_id': int(dataset_image_id),
    })


def infer_microns(attributes: dict[str, Any] | None) -> float | None:
    attrs = attributes or {}
    for key in ('mpp', 'mpp_value', 'microns', 'microns_per_pixel'):
        value = attrs.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            if math.isfinite(value) and value > 0:
                return float(value)
            continue
        if isinstance(value, str):
            try:
                parsed = float(value.strip())
            except ValueError:
                continue
            if math.isfinite(parsed) and parsed > 0:
                return parsed
    return None


def resolve_dataset_file_path(datasets_dir: str, image_path: str) -> str:
    candidate = os.path.realpath(os.path.join(datasets_dir, image_path))
    root = os.path.realpath(datasets_dir)
    if not candidate.startswith(root + os.sep):
        raise ValueError('Invalid dataset image path.')
    if not os.path.isfile(candidate):
        raise FileNotFoundError(candidate)
    return candidate


def get_deepzoom_generator(
    slide_id: str,
    file_path: str,
    *,
    tile_size: int = 254,
    overlap: int = 1,
    limit_bounds: bool = True,
) -> Any:
    """Return a cached DeepZoomGenerator for the given slide."""
    stat = os.stat(file_path)
    key = (slide_id, os.path.realpath(file_path), stat.st_mtime_ns, stat.st_size,
           tile_size, overlap, limit_bounds)
    with _CACHE_LOCK:
        cached = _SLIDE_CACHE.get(key)
        if cached is not None:
            _SLIDE_CACHE.move_to_end(key)
            return cached

        if OpenSlide.detect_format(file_path):
            slide = open_slide(file_path)
            generator = DeepZoomGenerator(
                slide,
                tile_size=tile_size,
                overlap=overlap,
                limit_bounds=limit_bounds,
            )
        else:
            generator = RasterDeepZoomGenerator(
                file_path,
                tile_size=tile_size,
                overlap=overlap,
                limit_bounds=limit_bounds,
            )

        thread_safe_generator = _ThreadSafeGenerator(generator)
        _SLIDE_CACHE[key] = thread_safe_generator

        while len(_SLIDE_CACHE) > _MAX_CACHED_SLIDES:
            _SLIDE_CACHE.popitem(last=False)

        return thread_safe_generator


def xopat_is_available(xopat_dir: str | None) -> bool:
    if not xopat_dir:
        return False
    root = Path(xopat_dir)
    return root.is_dir() and (root / 'index.js').is_file()
