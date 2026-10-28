"""Service for scanning dataset directories and reading metadata CSV files."""

from __future__ import annotations

import csv
import math
from pathlib import Path


_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp')


def resolve_image_name(ds_path: Path, image_name: str) -> str | None:
    """Resolve an image_name to an actual file on disk.

    If the exact name exists, return it. If not (e.g. no extension), try
    appending common image extensions. Returns the resolved filename or None.
    """
    if not image_name or '\\' in image_name or '\x00' in image_name:
        return None
    candidate_path = (ds_path / image_name).resolve()
    if not candidate_path.is_relative_to(ds_path.resolve()):
        return None
    if candidate_path.is_file():
        return image_name
    # Only try extensions if the name doesn't already have one
    if not Path(image_name).suffix:
        for ext in _IMAGE_EXTENSIONS:
            candidate = image_name + ext
            if (ds_path / candidate).is_file():
                return candidate
    return None


def parse_value(raw: str):
    """Auto-detect type and parse a CSV cell value.

    Returns bool for 'true'/'false', float for numeric strings, else str.
    """
    raw = raw or ''
    lower = raw.strip().lower()
    if lower in ('true', 'false'):
        return lower == 'true'
    try:
        number = float(raw)
        return number if math.isfinite(number) else raw.strip()
    except (ValueError, TypeError):
        return raw.strip()


def scan_datasets(base_dir: str | Path) -> list[dict]:
    """List all datasets in the base directory.

    Each dataset is a subdirectory containing a metadata.csv and PNG files.

    Returns:
        List of dicts: [{name, image_count, attribute_names}, ...]
    """
    base = Path(base_dir)
    if not base.is_dir():
        return []

    results = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir() or entry.is_symlink() or entry.name.startswith('.'):
            continue
        csv_path = entry / 'metadata.csv'
        if not csv_path.is_file():
            continue

        try:
            with open(csv_path, newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                if 'image_name' not in fieldnames:
                    continue
                attribute_names = [n for n in fieldnames if n != 'image_name']
                row_count = sum(1 for row in reader if (row.get('image_name') or '').strip())
        except (UnicodeError, csv.Error, OSError):
            continue

        results.append({
            'name': entry.name,
            'image_count': row_count,
            'attribute_names': attribute_names,
        })

    return results


def scan_dataset(base_dir: str | Path, dataset_name: str) -> list[dict]:
    """Read all images and their attributes from a dataset's metadata.csv.

    Returns:
        List of dicts: [{image_name, attributes: {key: value}, missing_file?}, ...]
        Empty list if dataset not found.
    """
    ds_path = Path(base_dir) / dataset_name
    if not ds_path.resolve().is_relative_to(Path(base_dir).resolve()) or ds_path.is_symlink():
        return []
    csv_path = ds_path / 'metadata.csv'

    if not csv_path.is_file():
        return []

    images = []
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        attr_names = [n for n in fieldnames if n != 'image_name']

        for row in reader:
            image_name = (row.get('image_name') or '').strip()
            if not image_name:
                continue

            attrs = {}
            for name in attr_names:
                raw = row.get(name, '')
                attrs[name] = parse_value(raw)

            resolved = resolve_image_name(ds_path, image_name)

            entry = {
                'image_name': resolved or image_name,
                'attributes': attrs,
            }

            if resolved is None:
                entry['missing_file'] = True

            images.append(entry)

    return images


def get_attribute_schema(base_dir: str | Path, dataset_name: str) -> list[dict]:
    """Return attribute metadata: names, types, and unique values.

    Returns:
        List of dicts: [{name, type: 'boolean'|'numeric'|'string', values}, ...]
    """
    images = scan_dataset(base_dir, dataset_name)
    if not images:
        return []

    attr_names = list(images[0]['attributes'].keys())

    schema = []
    for name in attr_names:
        values = [img['attributes'].get(name) for img in images if name in img['attributes']]
        unique = sorted(set(values), key=lambda x: (isinstance(x, str), str(x)))

        # Determine type from values
        if all(isinstance(v, bool) for v in values):
            attr_type = 'boolean'
        elif all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
            attr_type = 'numeric'
        else:
            attr_type = 'string'

        schema.append({
            'name': name,
            'type': attr_type,
            'values': unique,
        })

    return schema
