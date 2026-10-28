"""Tests for evaluation API: image list, randomization, blinding, ratings, sidebar status."""

import random

import pytest

from app.models import DatasetImage, Study, StudyParticipant, Rating, User
from app.services.schema_service import get_default_rating_schema


# ---------------------------------------------------------------------------
# Helper: log in as a participant via API
# ---------------------------------------------------------------------------

def _login(client, email, password):
    return client.post('/api/auth/login', json={
        'email': email,
        'password': password,
    })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def eval_study(db):
    """Create a study configured for evaluation with rating schema and images."""
    schema = get_default_rating_schema()
    # visible_attributes is empty by default -- no attributes visible to participants
    study = Study(
        name='Eval Study',
        description='Study for evaluation tests',
        status='active',
        rating_schema=schema,
        uncertainty_enabled=True,
        session_instruction='<p>Please rate each image carefully.</p>',
    )
    db.session.add(study)
    db.session.flush()

    # Add 5 dataset images
    for i in range(1, 6):
        img = DatasetImage(
            study_id=study.id,
            image_path=f'test_dataset/image_{i}.png',
            attributes={
                'synthetic': (i % 2 == 0),
                'tissue_type': 'Tumor-dominant' if i <= 3 else 'Stroma-dominant',
                'mpp_value': 0.5,
                'model_name': 'ModelA' if i % 2 == 0 else None,
            },
            sequence_number=i,
        )
        db.session.add(img)

    db.session.commit()
    return study


@pytest.fixture()
def eval_study_visible_attrs(db):
    """Create a study with some attributes visible to participants."""
    schema = get_default_rating_schema()
    schema['visible_attributes'] = ['tissue_type']
    study = Study(
        name='Visible Attrs Study',
        description='Study with visible attributes',
        status='active',
        rating_schema=schema,
        uncertainty_enabled=False,
    )
    db.session.add(study)
    db.session.flush()

    for i in range(1, 4):
        img = DatasetImage(
            study_id=study.id,
            image_path=f'strat_dataset/image_{i}.png',
            attributes={
                'synthetic': False,
                'tissue_type': 'Tumor-dominant' if i == 1 else 'Stroma-dominant',
            },
            sequence_number=i,
        )
        db.session.add(img)

    db.session.commit()
    return study


@pytest.fixture()
def assigned_user(db, test_user, eval_study):
    """Assign test_user to eval_study with a fixed seed."""
    sp = StudyParticipant(
        study_id=eval_study.id,
        user_id=test_user.id,
        random_seed=42,
    )
    db.session.add(sp)
    db.session.commit()
    return test_user


@pytest.fixture()
def second_user(db, eval_study):
    """Create a second participant with a different seed."""
    user = User(
        first_name='Second',
        last_name='User',
        email='second@example.com',
        role='participant',
        is_test_user=False,
    )
    user.set_password('secondpass')
    db.session.add(user)
    db.session.flush()

    sp = StudyParticipant(
        study_id=eval_study.id,
        user_id=user.id,
        random_seed=999,
    )
    db.session.add(sp)
    db.session.commit()
    return user


# ===========================================================================
# Test: Randomization
# ===========================================================================

class TestRandomization:

    def test_randomization_deterministic_per_user(self, client, assigned_user, eval_study, db):
        """Same seed produces the same image order every time."""
        _login(client, 'participant@example.com', 'testpassword')

        resp1 = client.get(f'/api/studies/{eval_study.id}/images')
        data1 = resp1.get_json()

        resp2 = client.get(f'/api/studies/{eval_study.id}/images')
        data2 = resp2.get_json()

        ids1 = [item['dataset_image_id'] for item in data1]
        ids2 = [item['dataset_image_id'] for item in data2]
        assert ids1 == ids2

    def test_randomization_different_per_user(self, client, assigned_user, second_user, eval_study, db):
        """Different seeds produce different image orders."""
        # Get order for first user (seed=42)
        _login(client, 'participant@example.com', 'testpassword')
        resp1 = client.get(f'/api/studies/{eval_study.id}/images')
        data1 = resp1.get_json()
        ids1 = [item['dataset_image_id'] for item in data1]
        client.post('/api/auth/logout')

        # Get order for second user (seed=999)
        _login(client, 'second@example.com', 'secondpass')
        resp2 = client.get(f'/api/studies/{eval_study.id}/images')
        data2 = resp2.get_json()
        ids2 = [item['dataset_image_id'] for item in data2]

        # With different seeds and 5 images, the orders should differ
        assert ids1 != ids2

    def test_position_based_numbering(self, client, assigned_user, eval_study, db):
        """Image positions are 1-based and sequential in user's randomized order."""
        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/images')
        data = resp.get_json()

        positions = [item['position'] for item in data]
        assert positions == [1, 2, 3, 4, 5]

    def test_position_not_sequence_number(self, client, assigned_user, eval_study, db):
        """Position is the user's randomized position, not the original sequence_number."""
        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/images')
        data = resp.get_json()

        # Get the image IDs by position
        images = DatasetImage.query.filter_by(study_id=eval_study.id).order_by(DatasetImage.id).all()
        original_order = [img.id for img in images]

        # The shuffled order (seed=42) should differ from the original order
        shuffled_ids = [item['dataset_image_id'] for item in data]

        # Verify positions are sequential
        for i, item in enumerate(data):
            assert item['position'] == i + 1

        # Verify the order is shuffled (not same as original sequence_number order)
        rng = random.Random(42)
        expected_ids = list(original_order)
        rng.shuffle(expected_ids)
        assert shuffled_ids == expected_ids


# ===========================================================================
# Test: Image sidebar status indicators
# ===========================================================================

class TestImageSidebarStatus:

    def test_all_images_not_opened_initially(self, client, assigned_user, eval_study, db):
        """All images show not_opened status when no ratings exist."""
        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/images')
        data = resp.get_json()

        for item in data:
            assert item['status'] == 'not_opened'

    def test_opened_status_after_opening_rating(self, client, assigned_user, eval_study, db):
        """Image shows 'opened' status after rating row is created with empty responses."""
        _login(client, 'participant@example.com', 'testpassword')

        # Get first image
        resp = client.get(f'/api/studies/{eval_study.id}/images')
        data = resp.get_json()
        first_image_id = data[0]['dataset_image_id']

        # Open rating
        client.post('/api/ratings/open', json={
            'study_id': eval_study.id,
            'dataset_image_id': first_image_id,
        })

        # Check status
        resp = client.get(f'/api/studies/{eval_study.id}/images')
        data = resp.get_json()
        assert data[0]['status'] == 'opened'

    def test_partial_status_with_some_answers(self, client, assigned_user, eval_study, db):
        """Image shows 'partial' when some ordinal questions answered."""
        _login(client, 'participant@example.com', 'testpassword')

        # Get first image
        resp = client.get(f'/api/studies/{eval_study.id}/images')
        first_image_id = resp.get_json()[0]['dataset_image_id']

        # Create rating with partial responses
        rating = Rating(
            user_id=assigned_user.id,
            dataset_image_id=first_image_id,
            study_id=eval_study.id,
            responses={'F1': 2, 'F2': 1},  # Only 2 of 6 ordinal questions
        )
        db.session.add(rating)
        db.session.commit()

        resp = client.get(f'/api/studies/{eval_study.id}/images')
        data = resp.get_json()
        assert data[0]['status'] == 'partial'

    def test_complete_status_with_all_answers(self, client, assigned_user, eval_study, db):
        """Image shows 'complete' when all ordinal questions answered."""
        _login(client, 'participant@example.com', 'testpassword')

        resp = client.get(f'/api/studies/{eval_study.id}/images')
        first_image_id = resp.get_json()[0]['dataset_image_id']

        # Create rating with all ordinal answers
        rating = Rating(
            user_id=assigned_user.id,
            dataset_image_id=first_image_id,
            study_id=eval_study.id,
            responses={'F1': 2, 'F2': 1, 'F3': 2, 'F4': 1, 'F5': 2, 'F6': 2},
        )
        db.session.add(rating)
        db.session.commit()

        resp = client.get(f'/api/studies/{eval_study.id}/images')
        data = resp.get_json()
        assert data[0]['status'] == 'complete'


# ===========================================================================
# Test: Rating API -- open
# ===========================================================================

class TestRatingOpen:

    def test_open_creates_rating_row(self, client, assigned_user, eval_study, db):
        """POST /api/ratings/open creates a new Rating with empty responses."""
        _login(client, 'participant@example.com', 'testpassword')

        images = DatasetImage.query.filter_by(study_id=eval_study.id).all()
        image_id = images[0].id

        resp = client.post('/api/ratings/open', json={
            'study_id': eval_study.id,
            'dataset_image_id': image_id,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['responses'] == {}
        assert data['dataset_image_id'] == image_id

        # Verify in database
        rating = Rating.query.filter_by(
            user_id=assigned_user.id,
            dataset_image_id=image_id,
        ).first()
        assert rating is not None
        assert rating.responses == {}

    def test_open_returns_existing_rating(self, client, assigned_user, eval_study, db):
        """Opening an already-opened image returns the existing rating."""
        _login(client, 'participant@example.com', 'testpassword')

        images = DatasetImage.query.filter_by(study_id=eval_study.id).all()
        image_id = images[0].id

        # First open
        resp1 = client.post('/api/ratings/open', json={
            'study_id': eval_study.id,
            'dataset_image_id': image_id,
        })
        assert resp1.status_code == 201

        # Second open
        resp2 = client.post('/api/ratings/open', json={
            'study_id': eval_study.id,
            'dataset_image_id': image_id,
        })
        assert resp2.status_code == 200
        assert resp2.get_json()['id'] == resp1.get_json()['id']

    def test_open_updates_last_viewed_image(self, client, assigned_user, eval_study, db):
        """Opening a rating updates StudyParticipant.last_viewed_image_id."""
        _login(client, 'participant@example.com', 'testpassword')

        images = DatasetImage.query.filter_by(study_id=eval_study.id).all()
        image_id = images[0].id

        client.post('/api/ratings/open', json={
            'study_id': eval_study.id,
            'dataset_image_id': image_id,
        })

        sp = StudyParticipant.query.filter_by(
            study_id=eval_study.id,
            user_id=assigned_user.id,
        ).first()
        assert sp.last_viewed_image_id == image_id

    def test_viewing_image_updates_last_viewed_image(self, client, assigned_user, eval_study, db):
        """Loading image data updates StudyParticipant.last_viewed_image_id for resume."""
        _login(client, 'participant@example.com', 'testpassword')

        resp = client.get(f'/api/studies/{eval_study.id}/image/1')
        assert resp.status_code == 200
        image_id = resp.get_json()['dataset_image_id']

        sp = StudyParticipant.query.filter_by(
            study_id=eval_study.id,
            user_id=assigned_user.id,
        ).first()
        assert sp.last_viewed_image_id == image_id

    def test_prefetch_image_does_not_update_last_viewed_image(self, client, assigned_user, eval_study, db):
        """Non-tracking image fetches must not clobber resume state."""
        _login(client, 'participant@example.com', 'testpassword')

        images = DatasetImage.query.filter_by(study_id=eval_study.id).order_by(DatasetImage.id).all()
        sp = StudyParticipant.query.filter_by(
            study_id=eval_study.id,
            user_id=assigned_user.id,
        ).first()
        sp.last_viewed_image_id = images[-1].id
        db.session.commit()

        resp = client.get(f'/api/studies/{eval_study.id}/image/1?track=0')
        assert resp.status_code == 200

        db.session.refresh(sp)
        assert sp.last_viewed_image_id == images[-1].id

    def test_open_rating_missing_fields(self, client, assigned_user, eval_study, db):
        """POST /api/ratings/open returns 400 if fields are missing."""
        _login(client, 'participant@example.com', 'testpassword')

        resp = client.post('/api/ratings/open', json={'study_id': eval_study.id})
        assert resp.status_code == 400

    def test_open_rating_wrong_study(self, client, assigned_user, eval_study, db):
        """POST /api/ratings/open returns 404 for image not in study."""
        _login(client, 'participant@example.com', 'testpassword')

        # Create another study with an image
        other = Study(name='Other', status='active', rating_schema={'questions': []})
        db.session.add(other)
        db.session.flush()
        other_img = DatasetImage(
            study_id=other.id,
            image_path='other/img.png',
            sequence_number=1,
        )
        db.session.add(other_img)
        db.session.commit()

        resp = client.post('/api/ratings/open', json={
            'study_id': eval_study.id,
            'dataset_image_id': other_img.id,
        })
        assert resp.status_code == 404


# ===========================================================================
# Test: Blinding -- no metadata visible to participant
# ===========================================================================

class TestBlinding:

    def test_image_data_no_metadata(self, client, assigned_user, eval_study, db):
        """Image data endpoint does not expose attributes or image_path."""
        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/image/1')
        assert resp.status_code == 200
        data = resp.get_json()

        # Verify blinding: no metadata fields
        assert 'attributes' not in data
        assert 'image_path' not in data

        # Position should be there
        assert 'position' in data
        assert 'dataset_image_id' in data

    def test_image_list_no_metadata(self, client, assigned_user, eval_study, db):
        """Image list endpoint does not expose metadata."""
        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/images')
        data = resp.get_json()

        for item in data:
            assert 'attributes' not in item
            assert 'image_path' not in item


# ===========================================================================
# Test: Stratification visibility
# ===========================================================================

class TestVisibleAttributes:

    def test_no_visible_attributes_when_empty(self, client, assigned_user, eval_study, db):
        """No visible_attributes field when schema has empty visible_attributes list."""
        _login(client, 'participant@example.com', 'testpassword')

        resp = client.get(f'/api/studies/{eval_study.id}/images')
        data = resp.get_json()

        for item in data:
            assert 'visible_attributes' not in item

    def test_no_visible_attributes_in_image_data_when_empty(self, client, assigned_user, eval_study, db):
        """No visible_attributes in image data when schema has empty list."""
        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/image/1')
        data = resp.get_json()
        assert 'visible_attributes' not in data
        assert 'question_attributes' not in data

    def test_visible_attributes_shown_when_configured(self, client, test_user, eval_study_visible_attrs, db):
        """Visible attributes shown when listed in schema.visible_attributes."""
        # Assign user to this study
        sp = StudyParticipant(
            study_id=eval_study_visible_attrs.id,
            user_id=test_user.id,
            random_seed=42,
        )
        db.session.add(sp)
        db.session.commit()

        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study_visible_attrs.id}/images')
        data = resp.get_json()

        # At least one item should have visible_attributes with tissue_type
        items_with_attrs = [item for item in data if 'visible_attributes' in item]
        assert len(items_with_attrs) > 0
        tissue_types = [item['visible_attributes']['tissue_type'] for item in items_with_attrs]
        assert 'Tumor-dominant' in tissue_types or 'Stroma-dominant' in tissue_types

    def test_visible_attributes_shown_in_image_data(self, client, test_user, eval_study_visible_attrs, db):
        """Image data includes visible_attributes when configured."""
        sp = StudyParticipant(
            study_id=eval_study_visible_attrs.id,
            user_id=test_user.id,
            random_seed=42,
        )
        db.session.add(sp)
        db.session.commit()

        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study_visible_attrs.id}/image/1')
        data = resp.get_json()
        assert 'visible_attributes' in data
        assert 'tissue_type' in data['visible_attributes']


# ===========================================================================
# Test: Question placeholder attributes
# ===========================================================================

class TestQuestionAttributes:

    def test_question_attributes_shown_when_placeholders_are_used(
        self, client, assigned_user, eval_study, db
    ):
        """Image data includes only the attributes referenced in question text."""
        schema = {
            **eval_study.rating_schema,
            'questions': [
            {
                'id': 'label_check',
                'type': 'ordinal',
                'name': 'Does this image show {{tissue_type}}?',
                'description': 'Synthetic: {{synthetic}}',
                'min': 0,
                'max': 1,
                'labels': {'0': 'No', '1': 'Yes'},
            },
            ],
        }
        eval_study.rating_schema = schema
        db.session.commit()

        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/image/1')
        data = resp.get_json()

        assert 'question_attributes' in data
        assert set(data['question_attributes'].keys()) == {'tissue_type', 'synthetic'}
        assert 'model_name' not in data['question_attributes']
        assert 'mpp_value' not in data['question_attributes']

    def test_question_attributes_ignore_unknown_placeholders(
        self, client, assigned_user, eval_study, db
    ):
        """Unknown placeholders do not leak unrelated dataset attributes."""
        schema = {
            **eval_study.rating_schema,
            'questions': [
            {
                'id': 'label_check',
                'type': 'ordinal',
                'name': 'Does this image show {{unknown_attr}}?',
                'min': 0,
                'max': 1,
                'labels': {'0': 'No', '1': 'Yes'},
            },
            ],
        }
        eval_study.rating_schema = schema
        db.session.commit()

        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/image/1')
        data = resp.get_json()

        assert 'question_attributes' not in data


# ===========================================================================
# Test: Image data endpoint
# ===========================================================================

class TestImageDataEndpoint:

    def test_image_data_returns_correct_position(self, client, assigned_user, eval_study, db):
        """Image data endpoint returns the correct image for the given position."""
        _login(client, 'participant@example.com', 'testpassword')

        # Get the expected image at position 1
        resp_list = client.get(f'/api/studies/{eval_study.id}/images')
        expected_id = resp_list.get_json()[0]['dataset_image_id']

        resp = client.get(f'/api/studies/{eval_study.id}/image/1')
        data = resp.get_json()
        assert data['dataset_image_id'] == expected_id
        assert data['position'] == 1
        assert data['total_images'] == 5

    def test_image_data_includes_image_url(self, client, assigned_user, eval_study, db):
        """Image data includes a URL for serving the image."""
        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/image/1')
        data = resp.get_json()
        assert 'image_url' in data
        assert '/api/studies/images/' in data['image_url']

    def test_image_data_includes_rating_when_exists(self, client, assigned_user, eval_study, db):
        """Image data includes existing rating when present."""
        _login(client, 'participant@example.com', 'testpassword')

        # Get first image id
        resp_list = client.get(f'/api/studies/{eval_study.id}/images')
        image_id = resp_list.get_json()[0]['dataset_image_id']

        # Create a rating
        rating = Rating(
            user_id=assigned_user.id,
            dataset_image_id=image_id,
            study_id=eval_study.id,
            responses={'F1': 2, 'F2': 1},
        )
        db.session.add(rating)
        db.session.commit()

        resp = client.get(f'/api/studies/{eval_study.id}/image/1')
        data = resp.get_json()
        assert data['rating'] is not None
        assert data['rating']['responses'] == {'F1': 2, 'F2': 1}

    def test_image_data_creates_one_empty_rating(self, client, assigned_user, eval_study, db):
        """Opening an editable image creates a rating once, ready for autosave."""
        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/image/1')
        data = resp.get_json()
        assert data['rating']['responses'] == {}
        again = client.get(f'/api/studies/{eval_study.id}/image/1').get_json()
        assert again['rating']['id'] == data['rating']['id']
        assert Rating.query.filter_by(user_id=assigned_user.id).count() == 1

    def test_image_data_invalid_position(self, client, assigned_user, eval_study, db):
        """Image data returns 404 for invalid position."""
        _login(client, 'participant@example.com', 'testpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/image/0')
        assert resp.status_code == 404
        resp = client.get(f'/api/studies/{eval_study.id}/image/99')
        assert resp.status_code == 404


# ===========================================================================
# Test: Admin cannot access participant API endpoints
# ===========================================================================

class TestAdminBlocked:

    def test_admin_cannot_access_image_list(self, client, admin_user, eval_study, db):
        """Admin user gets 403 on image list."""
        _login(client, 'admin', 'adminpassword')
        resp = client.get(f'/api/studies/{eval_study.id}/images')
        assert resp.status_code == 403

    def test_admin_cannot_open_rating(self, client, admin_user, eval_study, db):
        """Admin user gets 403 on rating API."""
        _login(client, 'admin', 'adminpassword')
        images = DatasetImage.query.filter_by(study_id=eval_study.id).all()
        resp = client.post('/api/ratings/open', json={
            'study_id': eval_study.id,
            'dataset_image_id': images[0].id,
        })
        assert resp.status_code == 403
