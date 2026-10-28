import csv
import os
import tempfile

import pytest

from app.services.image_scanner import (
    scan_datasets,
    scan_dataset,
    get_attribute_schema,
    parse_value,
)


@pytest.fixture()
def dataset_dir():
    """Create a temporary dataset directory with metadata.csv and PNGs."""
    with tempfile.TemporaryDirectory() as base:
        ds_dir = os.path.join(base, 'dataset_1')
        os.makedirs(ds_dir)

        # Create dummy PNGs
        for name in ['img_a.png', 'img_b.png', 'img_c.png']:
            open(os.path.join(ds_dir, name), 'wb').close()

        # Create metadata.csv
        with open(os.path.join(ds_dir, 'metadata.csv'), 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['image_name', 'mpp_value', 'synthetic'])
            writer.writerow(['img_a.png', '0.5', 'false'])
            writer.writerow(['img_b.png', '1.0', 'true'])
            writer.writerow(['img_c.png', '0.5', 'true'])

        yield base


class TestParseValue:
    def test_boolean_true(self):
        assert parse_value('true') is True
        assert parse_value('True') is True
        assert parse_value('TRUE') is True

    def test_boolean_false(self):
        assert parse_value('false') is False
        assert parse_value('False') is False

    def test_numeric(self):
        assert parse_value('0.5') == 0.5
        assert parse_value('42') == 42.0

    def test_string(self):
        assert parse_value('hello') == 'hello'
        assert parse_value('  spaced  ') == 'spaced'


class TestScanDatasets:
    def test_lists_datasets(self, dataset_dir):
        result = scan_datasets(dataset_dir)
        assert len(result) == 1
        assert result[0]['name'] == 'dataset_1'
        assert result[0]['image_count'] == 3
        assert set(result[0]['attribute_names']) == {'mpp_value', 'synthetic'}

    def test_empty_dir(self, tmp_path):
        result = scan_datasets(str(tmp_path))
        assert result == []

    def test_missing_dir(self):
        result = scan_datasets('/nonexistent/path')
        assert result == []

    def test_skips_dirs_without_csv(self, dataset_dir):
        os.makedirs(os.path.join(dataset_dir, 'no_csv_dir'))
        result = scan_datasets(dataset_dir)
        assert len(result) == 1  # only dataset_1


class TestScanDataset:
    def test_returns_images_with_attributes(self, dataset_dir):
        images = scan_dataset(dataset_dir, 'dataset_1')
        assert len(images) == 3
        img_a = next(i for i in images if i['image_name'] == 'img_a.png')
        assert img_a['attributes']['mpp_value'] == 0.5
        assert img_a['attributes']['synthetic'] is False

    def test_type_detection_numeric(self, dataset_dir):
        images = scan_dataset(dataset_dir, 'dataset_1')
        img_b = next(i for i in images if i['image_name'] == 'img_b.png')
        assert isinstance(img_b['attributes']['mpp_value'], float)

    def test_type_detection_boolean(self, dataset_dir):
        images = scan_dataset(dataset_dir, 'dataset_1')
        img_b = next(i for i in images if i['image_name'] == 'img_b.png')
        assert img_b['attributes']['synthetic'] is True

    def test_nonexistent_dataset(self, dataset_dir):
        images = scan_dataset(dataset_dir, 'no_such_dataset')
        assert images == []

    def test_flags_missing_png(self, dataset_dir):
        csv_path = os.path.join(dataset_dir, 'dataset_1', 'metadata.csv')
        with open(csv_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['ghost.png', '2.0', 'false'])
        images = scan_dataset(dataset_dir, 'dataset_1')
        ghost = next(i for i in images if i['image_name'] == 'ghost.png')
        assert ghost.get('missing_file') is True

    def test_existing_files_not_flagged(self, dataset_dir):
        images = scan_dataset(dataset_dir, 'dataset_1')
        img_a = next(i for i in images if i['image_name'] == 'img_a.png')
        assert 'missing_file' not in img_a


class TestGetAttributeSchema:
    def test_returns_attribute_types(self, dataset_dir):
        schema = get_attribute_schema(dataset_dir, 'dataset_1')
        assert len(schema) == 2

        mpp_attr = next(a for a in schema if a['name'] == 'mpp_value')
        assert mpp_attr['type'] == 'numeric'
        assert set(mpp_attr['values']) == {0.5, 1.0}

        synth_attr = next(a for a in schema if a['name'] == 'synthetic')
        assert synth_attr['type'] == 'boolean'
        assert set(synth_attr['values']) == {True, False}

    def test_nonexistent_dataset(self, dataset_dir):
        schema = get_attribute_schema(dataset_dir, 'nonexistent')
        assert schema == []
