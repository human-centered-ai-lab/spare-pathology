"""Tests for dataset switching cleanup behaviour.

When a study's dataset_name is changed, all DatasetImage rows (and their
cascaded Rating rows) must be removed, StudyParticipant.last_viewed_image_id must
be nulled, and submitted users must be reverted.
"""

import pytest

from app import db
from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_default_rating_schema
from tests.helpers import login_admin


@pytest.fixture()
def study_with_ratings(db, admin_user):
    """Create a draft study with images, a test user, ratings, and a submitted user."""
    study = Study(
        name='Switch Test Study',
        status='draft',
        rating_schema=get_default_rating_schema(),
        dataset_name='dataset_a',
    )
    db.session.add(study)
    db.session.flush()

    # Add images
    images = []
    for i in range(3):
        img = DatasetImage(
            study_id=study.id,
            image_path=f'dataset_a/img_{i}.png',
            attributes={'synthetic': False},
            sequence_number=i + 1,
        )
        db.session.add(img)
        images.append(img)
    db.session.flush()

    # Add a test user assigned to the study
    test_user = User(
        first_name='Tester', last_name='Bot', email='tester@test.com',
        role='participant', is_test_user=True,
    )
    test_user.set_password('password')
    db.session.add(test_user)
    db.session.flush()

    sp = StudyParticipant(
        study_id=study.id,
        user_id=test_user.id,
        last_viewed_image_id=images[1].id,
        submitted=True,
    )
    db.session.add(sp)
    db.session.flush()

    # Add ratings from the test user
    for img in images:
        rating = Rating(
            user_id=test_user.id,
            dataset_image_id=img.id,
            study_id=study.id,
            responses={'q1': 3},
        )
        db.session.add(rating)

    db.session.commit()
    return study, images, test_user


class TestDatasetSwitch:
    """Tests for switching dataset_name via the settings endpoint."""

    def test_switch_deletes_images(self, client, admin_user, study_with_ratings):
        """Switching dataset_name deletes all DatasetImage rows."""
        study, images, _ = study_with_ratings
        login_admin(client)

        resp = client.put(f'/api/admin/studies/{study.id}/settings', json={
            'name': study.name,
            'dataset_name': 'dataset_b',
        })
        assert resp.status_code == 200

        remaining = DatasetImage.query.filter_by(study_id=study.id).count()
        assert remaining == 0

    def test_switch_cascades_to_ratings(self, client, admin_user, study_with_ratings):
        """Switching dataset_name cascade-deletes all Rating rows."""
        study, _, _ = study_with_ratings
        login_admin(client)

        # Verify ratings exist before switch
        before = Rating.query.filter_by(study_id=study.id).count()
        assert before == 3

        resp = client.put(f'/api/admin/studies/{study.id}/settings', json={
            'name': study.name,
            'dataset_name': 'dataset_b',
        })
        assert resp.status_code == 200

        after = Rating.query.filter_by(study_id=study.id).count()
        assert after == 0

    def test_switch_nulls_last_viewed_image(self, client, admin_user, study_with_ratings):
        """Switching dataset_name nulls StudyParticipant.last_viewed_image_id."""
        study, _, test_user = study_with_ratings
        login_admin(client)

        # Verify last_viewed_image_id is set
        sp = StudyParticipant.query.filter_by(
            study_id=study.id, user_id=test_user.id,
        ).first()
        assert sp.last_viewed_image_id is not None

        client.put(f'/api/admin/studies/{study.id}/settings', json={
            'name': study.name,
            'dataset_name': 'dataset_b',
        })

        db.session.refresh(sp)
        assert sp.last_viewed_image_id is None

    def test_switch_reverts_submitted_users(self, client, admin_user, study_with_ratings):
        """Switching dataset_name reverts submitted users."""
        study, _, test_user = study_with_ratings
        login_admin(client)

        sp = StudyParticipant.query.filter_by(
            study_id=study.id, user_id=test_user.id,
        ).first()
        assert sp.submitted is True

        client.put(f'/api/admin/studies/{study.id}/settings', json={
            'name': study.name,
            'dataset_name': 'dataset_b',
        })

        db.session.refresh(sp)
        assert sp.submitted is False
        assert sp.submitted_at is None

    def test_switch_updates_dataset_name(self, client, admin_user, study_with_ratings):
        """The response contains the new dataset_name."""
        study, _, _ = study_with_ratings
        login_admin(client)

        resp = client.put(f'/api/admin/studies/{study.id}/settings', json={
            'name': study.name,
            'dataset_name': 'dataset_b',
        })
        data = resp.get_json()
        assert data['dataset_name'] == 'dataset_b'

    def test_switch_returns_zero_counts(self, client, admin_user, study_with_ratings):
        """After switching, image_count and rating_count are both 0."""
        study, _, _ = study_with_ratings
        login_admin(client)

        resp = client.put(f'/api/admin/studies/{study.id}/settings', json={
            'name': study.name,
            'dataset_name': 'dataset_b',
        })
        data = resp.get_json()
        assert data['image_count'] == 0
        assert data['rating_count'] == 0

    def test_same_dataset_no_cleanup(self, client, admin_user, study_with_ratings):
        """Setting dataset_name to the same value does NOT delete images."""
        study, _, _ = study_with_ratings
        login_admin(client)

        resp = client.put(f'/api/admin/studies/{study.id}/settings', json={
            'name': study.name,
            'dataset_name': 'dataset_a',  # same as current
        })
        assert resp.status_code == 200

        remaining = DatasetImage.query.filter_by(study_id=study.id).count()
        assert remaining == 3

        ratings = Rating.query.filter_by(study_id=study.id).count()
        assert ratings == 3

    def test_switch_to_null_cleans_up(self, client, admin_user, study_with_ratings):
        """Setting dataset_name to empty/null cleans up images."""
        study, _, _ = study_with_ratings
        login_admin(client)

        resp = client.put(f'/api/admin/studies/{study.id}/settings', json={
            'name': study.name,
            'dataset_name': '',
        })
        assert resp.status_code == 200

        remaining = DatasetImage.query.filter_by(study_id=study.id).count()
        assert remaining == 0

    def test_switch_blocked_for_non_draft(self, client, admin_user, study_with_ratings):
        """Switching dataset_name is blocked when study is not in draft status."""
        study, _, _ = study_with_ratings
        study.status = 'active'
        db.session.commit()
        login_admin(client)

        resp = client.put(f'/api/admin/studies/{study.id}/settings', json={
            'name': study.name,
            'dataset_name': 'dataset_b',
        })
        assert resp.status_code == 403

        # Images should not be deleted
        remaining = DatasetImage.query.filter_by(study_id=study.id).count()
        assert remaining == 3

    def test_rating_count_in_study_detail(self, client, admin_user, study_with_ratings):
        """Study detail response includes rating_count."""
        study, _, _ = study_with_ratings
        login_admin(client)

        resp = client.get(f'/api/admin/studies/{study.id}')
        data = resp.get_json()
        assert data['rating_count'] == 3

    def test_no_images_no_cleanup(self, client, admin_user, db):
        """Switching dataset when no images exist is a clean no-op."""
        study = Study(
            name='Empty Study', status='draft',
            rating_schema={'questions': []},
            dataset_name='dataset_a',
        )
        db.session.add(study)
        db.session.commit()

        login_admin(client)
        resp = client.put(f'/api/admin/studies/{study.id}/settings', json={
            'name': study.name,
            'dataset_name': 'dataset_b',
        })
        assert resp.status_code == 200
        assert resp.get_json()['dataset_name'] == 'dataset_b'
