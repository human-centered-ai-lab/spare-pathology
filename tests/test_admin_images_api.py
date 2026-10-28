"""Tests for admin image/dataset management API endpoints.

Covers:
- GET /api/admin/images/datasets-overview
- POST /api/admin/images/check-dataset-name
- POST /api/admin/images/delete-dataset
- Path traversal prevention
- Participant access control
"""

import os
import shutil
import tempfile

import pytest

from app.models import Study, User
from app.services.schema_service import get_default_rating_schema
from tests.helpers import login_admin, login_participant


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def datasets_dir(app):
    """Create a temporary datasets directory and configure the app to use it."""
    tmpdir = tempfile.mkdtemp()
    app.config['DATASETS_DIR'] = tmpdir
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture()
def test_dataset(datasets_dir):
    """Create a test dataset with metadata.csv and dummy PNG files."""
    ds_dir = os.path.join(datasets_dir, 'test_ds')
    os.makedirs(ds_dir)

    # Write metadata.csv
    with open(os.path.join(ds_dir, 'metadata.csv'), 'w') as f:
        f.write('image_name,mpp_value,synthetic\n')
        f.write('001.png,0.5,false\n')
        f.write('002.png,0.5,true\n')

    # Create dummy PNG files
    for name in ['001.png', '002.png']:
        with open(os.path.join(ds_dir, name), 'wb') as f:
            f.write(b'\x89PNG\r\n')  # Minimal PNG-like header

    return ds_dir


@pytest.fixture()
def participant_user(db):
    """Create a participant user for access control tests."""
    user = User(
        first_name='Dataset',
        last_name='Viewer',
        email='ds_viewer@example.com',
        institution='Test Lab',
        role='participant',
        is_test_user=False,
    )
    user.set_password('viewerpass')
    db.session.add(user)
    db.session.commit()
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDatasetsOverview:

    def test_datasets_overview(self, client, admin_user, test_dataset, db):
        """GET /api/admin/images/datasets-overview returns dataset info."""
        login_admin(client)

        resp = client.get('/api/admin/images/datasets-overview')
        assert resp.status_code == 200

        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['dataset_name'] == 'test_ds'
        assert data[0]['image_count'] == 2
        assert 'mpp_value' in data[0]['attribute_names']
        assert 'synthetic' in data[0]['attribute_names']
        assert data[0]['referenced_by_studies'] == 0

    def test_datasets_overview_with_study_reference(
        self, client, admin_user, test_dataset, db
    ):
        """Datasets overview shows study reference count."""
        # Create a study referencing this dataset
        study = Study(
            name='Ref Study',
            status='draft',
            dataset_name='test_ds',
            rating_schema=get_default_rating_schema(),
        )
        db.session.add(study)
        db.session.commit()

        login_admin(client)
        resp = client.get('/api/admin/images/datasets-overview')
        data = resp.get_json()
        assert data[0]['referenced_by_studies'] == 1


class TestCheckDatasetName:

    def test_check_dataset_name_exists(self, client, admin_user, test_dataset, db):
        """POST /api/admin/images/check-dataset-name returns exists=True for existing dataset."""
        login_admin(client)

        resp = client.post('/api/admin/images/check-dataset-name', json={
            'dataset_name': 'test_ds',
        })
        assert resp.status_code == 200
        assert resp.get_json()['exists'] is True

    def test_check_dataset_name_not_exists(self, client, admin_user, datasets_dir, db):
        """POST /api/admin/images/check-dataset-name returns exists=False for non-existing dataset."""
        login_admin(client)

        resp = client.post('/api/admin/images/check-dataset-name', json={
            'dataset_name': 'nonexistent_ds',
        })
        assert resp.status_code == 200
        assert resp.get_json()['exists'] is False


class TestDeleteDataset:

    def test_delete_dataset_success(self, client, admin_user, test_dataset, datasets_dir, db):
        """POST /api/admin/images/delete-dataset removes the directory."""
        login_admin(client)

        assert os.path.isdir(test_dataset)

        resp = client.post('/api/admin/images/delete-dataset', json={
            'dataset_name': 'test_ds',
        })
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'ok'
        assert not os.path.isdir(test_dataset)

    def test_delete_dataset_blocked_by_study(
        self, client, admin_user, test_dataset, db
    ):
        """POST /api/admin/images/delete-dataset returns 409 when study references it."""
        study = Study(
            name='Blocking Study',
            status='active',
            dataset_name='test_ds',
            rating_schema=get_default_rating_schema(),
        )
        db.session.add(study)
        db.session.commit()

        login_admin(client)

        resp = client.post('/api/admin/images/delete-dataset', json={
            'dataset_name': 'test_ds',
        })
        assert resp.status_code == 409
        data = resp.get_json()
        assert 'studies' in data
        assert 'Blocking Study' in data['studies']
        # Dataset should still exist
        assert os.path.isdir(test_dataset)

    def test_delete_dataset_path_traversal(self, client, admin_user, datasets_dir, db):
        """POST /api/admin/images/delete-dataset rejects '..' in dataset_name."""
        login_admin(client)

        resp = client.post('/api/admin/images/delete-dataset', json={
            'dataset_name': '../etc',
        })
        assert resp.status_code == 400

    def test_delete_dataset_path_traversal_slash(self, client, admin_user, datasets_dir, db):
        """POST /api/admin/images/delete-dataset rejects '/' in dataset_name."""
        login_admin(client)

        resp = client.post('/api/admin/images/delete-dataset', json={
            'dataset_name': 'foo/bar',
        })
        assert resp.status_code == 400

    def test_delete_dataset_not_found(self, client, admin_user, datasets_dir, db):
        """POST /api/admin/images/delete-dataset returns 404 for missing dataset."""
        login_admin(client)

        resp = client.post('/api/admin/images/delete-dataset', json={
            'dataset_name': 'nonexistent_ds',
        })
        assert resp.status_code == 404


class TestAccessControl:

    def test_participant_cannot_access_overview(
        self, client, admin_user, participant_user, datasets_dir, db
    ):
        """Participant gets 403 on admin images endpoints."""
        login_participant(client, 'ds_viewer@example.com', 'viewerpass')

        resp = client.get('/api/admin/images/datasets-overview')
        assert resp.status_code == 403

    def test_participant_cannot_delete_dataset(
        self, client, admin_user, participant_user, datasets_dir, db
    ):
        """Participant gets 403 on delete-dataset endpoint."""
        login_participant(client, 'ds_viewer@example.com', 'viewerpass')

        resp = client.post('/api/admin/images/delete-dataset', json={
            'dataset_name': 'test_ds',
        })
        assert resp.status_code == 403

    def test_participant_cannot_check_dataset_name(
        self, client, admin_user, participant_user, datasets_dir, db
    ):
        """Participant gets 403 on check-dataset-name endpoint."""
        login_participant(client, 'ds_viewer@example.com', 'viewerpass')

        resp = client.post('/api/admin/images/check-dataset-name', json={
            'dataset_name': 'test_ds',
        })
        assert resp.status_code == 403

    def test_unauthenticated_cannot_access(self, client, datasets_dir, db):
        """Unauthenticated user gets 401 on admin images endpoints."""
        resp = client.get('/api/admin/images/datasets-overview')
        assert resp.status_code == 401
