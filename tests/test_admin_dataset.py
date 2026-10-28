"""Tests for admin dataset management API: browse, toggle, remove, assign category, list, stats."""


import pytest
from PIL import Image as PILImage

from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_default_rating_schema
from tests.helpers import create_study_with_images, login_admin, login_participant


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def dataset_study(db):
    """Create a study with images for dataset tests."""
    return create_study_with_images(db, n=6)


@pytest.fixture()
def active_dataset_study(db):
    """Create an active study (structurally frozen — dataset edits are blocked)."""
    study = create_study_with_images(db, n=2)
    study.status = 'active'
    db.session.commit()
    return study


# ===========================================================================
# Test: Dataset List & Stats
# ===========================================================================

class TestDatasetList:

    def test_list_dataset_images(self, client, admin_user, dataset_study):
        """GET /api/admin/studies/:id/dataset/list returns paginated images."""
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{dataset_study.id}/dataset/list')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] == 6
        assert len(data['items']) == 6
        assert data['page'] == 1

    def test_list_dataset_images_sorted(self, client, admin_user, dataset_study):
        """GET /api/admin/studies/:id/dataset/list respects sort_by and sort_dir."""
        login_admin(client)
        resp = client.get(
            f'/api/admin/studies/{dataset_study.id}/dataset/list?sort_by=sequence_number&sort_dir=desc'
        )
        assert resp.status_code == 200
        data = resp.get_json()
        seqs = [item['sequence_number'] for item in data['items']]
        assert seqs == sorted(seqs, reverse=True)

    def test_list_dataset_images_paginated(self, client, admin_user, dataset_study):
        """Pagination returns correct subsets."""
        login_admin(client)
        resp = client.get(
            f'/api/admin/studies/{dataset_study.id}/dataset/list?page=1&per_page=2'
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['items']) == 2
        assert data['total'] == 6
        assert data['total_pages'] == 3


class TestDatasetStats:

    def test_get_dataset_stats(self, client, admin_user, dataset_study):
        """GET /api/admin/studies/:id/dataset/stats returns composition breakdown."""
        login_admin(client)
        resp = client.get(f'/api/admin/studies/{dataset_study.id}/dataset/stats')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] == 6
        assert 'by_attribute' in data
        # Should have attribute breakdowns for synthetic, mpp_value, tissue_type
        assert 'synthetic' in data['by_attribute']
        assert 'mpp_value' in data['by_attribute']
        assert 'tissue_type' in data['by_attribute']


# ===========================================================================
# Test: Toggle Image
# ===========================================================================

class TestToggleImage:

    def test_toggle_image_into_dataset(self, client, admin_user, db):
        """POST /api/admin/studies/:id/dataset/toggle adds an image."""
        study = Study(
            name='Toggle Test',
            status='draft',
            rating_schema=get_default_rating_schema(),
        )
        db.session.add(study)
        db.session.commit()

        login_admin(client)
        resp = client.post(f'/api/admin/studies/{study.id}/dataset/toggle', json={
            'image_path': 'model/0.5/0001/input.png',
            'attributes': {
                'synthetic': False,
                'mpp_value': 0.5,
            },
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'added'
        assert data['in_dataset'] is True
        assert data['dataset_image_id'] is not None

    def test_toggle_image_out_of_dataset(self, client, admin_user, dataset_study, db):
        """POST /api/admin/studies/:id/dataset/toggle removes an existing image."""
        img = DatasetImage.query.filter_by(study_id=dataset_study.id).first()
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{dataset_study.id}/dataset/toggle', json={
            'image_path': img.image_path,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'removed'
        assert data['in_dataset'] is False

    def test_toggle_on_active_study_forbidden(self, client, admin_user, active_dataset_study):
        """POST /api/admin/studies/:id/dataset/toggle returns 403 when study is active."""
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{active_dataset_study.id}/dataset/toggle', json={
            'image_path': 'new/image.png',
        })
        assert resp.status_code == 403


# ===========================================================================
# Test: Remove Images
# ===========================================================================

class TestRemoveImages:

    def test_remove_image_cascades_ratings(self, client, admin_user, db):
        """POST /api/admin/studies/:id/dataset/remove cascade-deletes ratings."""
        study = create_study_with_images(db, n=2)

        # Create a test user with ratings
        user = User(
            first_name='Rate', last_name='User', email='rater@test.com',
            institution='Test', role='participant', is_test_user=True,
        )
        user.set_password('testpass')
        db.session.add(user)
        db.session.flush()

        sp = StudyParticipant(study_id=study.id, user_id=user.id, random_seed=42)
        db.session.add(sp)

        img = DatasetImage.query.filter_by(study_id=study.id).first()
        rating = Rating(
            user_id=user.id, dataset_image_id=img.id,
            study_id=study.id, responses={'F1': 1},
        )
        db.session.add(rating)
        db.session.commit()

        login_admin(client)
        resp = client.post(f'/api/admin/studies/{study.id}/dataset/remove', json={
            'image_ids': [img.id],
        })
        assert resp.status_code == 200
        assert resp.get_json()['removed'] == 1

        # Rating should be gone too
        assert Rating.query.filter_by(dataset_image_id=img.id).count() == 0

    def test_remove_on_active_study_forbidden(self, client, admin_user, active_dataset_study):
        """POST /api/admin/studies/:id/dataset/remove returns 403 when study is active."""
        img = DatasetImage.query.filter_by(study_id=active_dataset_study.id).first()
        login_admin(client)
        resp = client.post(f'/api/admin/studies/{active_dataset_study.id}/dataset/remove', json={
            'image_ids': [img.id],
        })
        assert resp.status_code == 403


# ===========================================================================
# Test: Access Control
# ===========================================================================

class TestDatasetAccessControl:

    def test_participant_cannot_list_dataset(self, client, test_user, dataset_study):
        """Participant gets 403 on dataset list endpoint."""
        login_participant(client)
        resp = client.get(f'/api/admin/studies/{dataset_study.id}/dataset/list')
        assert resp.status_code == 403


# ===========================================================================
# Test: GET /api/admin/datasets and /api/admin/datasets/<name>/images
# ===========================================================================

class TestBrowseImages:
    """Tests for the dataset browsing endpoints."""

    @pytest.fixture()
    def datasets_dir(self, tmp_path):
        """Create a mock filesystem structure with a CSV-driven dataset."""
        import csv

        dataset_dir = tmp_path / 'TestDataset'
        dataset_dir.mkdir()

        # Create images
        for name in ['img_001.png', 'img_002.png', 'img_003.png']:
            img = PILImage.new('RGB', (1, 1), color='blue')
            img.save(str(dataset_dir / name))

        # Create metadata.csv
        with open(str(dataset_dir / 'metadata.csv'), 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['image_name', 'synthetic', 'mpp_value'])
            writer.writeheader()
            writer.writerow({'image_name': 'img_001.png', 'synthetic': 'false', 'mpp_value': '0.5'})
            writer.writerow({'image_name': 'img_002.png', 'synthetic': 'true', 'mpp_value': '0.5'})
            writer.writerow({'image_name': 'img_003.png', 'synthetic': 'false', 'mpp_value': '1.0'})

        return tmp_path

    @pytest.fixture()
    def browse_app(self, app, datasets_dir):
        """Configure app with datasets dir."""
        with app.app_context():
            app.config['DATASETS_DIR'] = str(datasets_dir)
        return app

    def test_browse_returns_images(self, client, admin_user, browse_app):
        """Returns scanned images for dataset."""
        login_admin(client)
        resp = client.get('/api/admin/datasets/TestDataset/images')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] == 3

    def test_browse_pagination(self, client, admin_user, browse_app):
        """page + per_page return correct slice."""
        login_admin(client)
        resp = client.get('/api/admin/datasets/TestDataset/images?per_page=2&page=1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['items']) == 2
        assert data['total'] == 3
        assert data['total_pages'] == 2

    def test_browse_all_returns_complete_dataset(self, client, admin_user, browse_app):
        """all=true returns the full scanned dataset instead of acting as a filter."""
        login_admin(client)
        resp = client.get('/api/admin/datasets/TestDataset/images?all=true')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['items']) == 3
        assert data['total'] == 3
        assert data['page'] == 1
        assert data['total_pages'] == 1

    def test_browse_as_participant(self, client, test_user, browse_app):
        """403 for non-admin."""
        login_participant(client)
        resp = client.get('/api/admin/datasets/TestDataset/images')
        assert resp.status_code == 403

    def test_list_datasets(self, client, admin_user, browse_app):
        """GET /api/admin/datasets returns available datasets."""
        login_admin(client)
        resp = client.get('/api/admin/datasets')
        assert resp.status_code == 200
        data = resp.get_json()
        names = [d['name'] for d in data]
        assert 'TestDataset' in names
