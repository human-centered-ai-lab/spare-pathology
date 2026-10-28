"""Tests for SQLAlchemy database models."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import DatasetImage, Study, StudyParticipant, Rating, User


class TestUser:
    """Tests for the User model."""

    def test_create_user_with_all_fields(self, db):
        user = User(
            first_name='Jane',
            last_name='Doe',
            email='jane@example.com',
            institution='General Hospital',
            role='participant',
            comments='Senior pathologist',
            is_test_user=False,
        )
        user.set_password('secret123')
        db.session.add(user)
        db.session.commit()

        assert user.id is not None
        assert user.first_name == 'Jane'
        assert user.last_name == 'Doe'
        assert user.email == 'jane@example.com'
        assert user.institution == 'General Hospital'
        assert user.role == 'participant'
        assert user.comments == 'Senior pathologist'
        assert user.is_test_user is False
        assert user.created_at is not None
        assert user.last_login is None

    def test_password_hashing(self, db):
        user = User(first_name='A', last_name='B', email='a@b.com', role='admin')
        user.set_password('mypassword')
        db.session.add(user)
        db.session.commit()

        assert user.password_hash != 'mypassword'
        assert user.check_password('mypassword') is True
        assert user.check_password('wrongpassword') is False

    def test_password_verification_after_reload(self, db):
        user = User(first_name='A', last_name='B', email='reload@test.com', role='admin')
        user.set_password('secret')
        db.session.add(user)
        db.session.commit()

        loaded = User.query.filter_by(email='reload@test.com').first()
        assert loaded.check_password('secret') is True

    def test_email_unique_constraint(self, db):
        u1 = User(first_name='A', last_name='B', email='dup@test.com', role='admin')
        u1.set_password('pass')
        u2 = User(first_name='C', last_name='D', email='dup@test.com', role='participant')
        u2.set_password('pass')
        db.session.add(u1)
        db.session.commit()

        db.session.add(u2)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_user_mixin_interface(self, db):
        user = User(first_name='A', last_name='B', email='mixin@test.com', role='admin')
        user.set_password('pass')
        db.session.add(user)
        db.session.commit()

        assert user.is_authenticated is True
        assert user.is_active is True
        assert user.is_anonymous is False
        assert user.get_id() == str(user.id)

    def test_admin_role(self, admin_user):
        assert admin_user.role == 'admin'

    def test_participant_role(self, test_user):
        assert test_user.role == 'participant'
        assert test_user.institution == 'Test Hospital'

    def test_email_accepts_plain_username(self, db):
        """Email field should accept values like 'admin' and 'test'."""
        # Default seeded users already use plain usernames 'admin' and 'test'
        user = User.query.filter_by(email='admin').first()
        assert user is not None
        assert user.email == 'admin'

    def test_is_test_user_flag(self, db):
        # Default seeded test user already has is_test_user=True
        user = User.query.filter_by(email='test').first()
        assert user is not None
        assert user.is_test_user is True


class TestStudy:
    """Tests for the Study model."""

    def test_create_study_defaults(self, db):
        study = Study(name='My Study')
        db.session.add(study)
        db.session.commit()

        assert study.id is not None
        assert study.name == 'My Study'
        assert study.status == 'draft'
        assert study.uncertainty_enabled is False
        assert study.created_at is not None
        assert study.description is None
        assert study.protocol_pdf_path is None
        assert study.session_instruction is None

    def test_study_status_values(self, db):
        for status in ('draft', 'active', 'finished'):
            s = Study(name=f'Study {status}', status=status)
            db.session.add(s)
        db.session.commit()
        assert Study.query.count() == 3

    def test_study_json_fields(self, db):
        schema = {
            'questions': [
                {'id': 'F1', 'type': 'ordinal', 'name': 'Nuclear detail', 'min': 0, 'max': 2}
            ]
        }
        study = Study(name='JSON Study', rating_schema=schema, dataset_name='test_dataset')
        db.session.add(study)
        db.session.commit()

        loaded = db.session.get(Study, study.id)
        assert loaded.rating_schema['questions'][0]['id'] == 'F1'
        assert loaded.dataset_name == 'test_dataset'

    def test_study_with_all_fields(self, db):
        study = Study(
            name='Full Study',
            description='Detailed description',
            protocol_pdf_path='/uploads/protocol.pdf',
            status='active',
            uncertainty_enabled=True,
            session_instruction='<p>Please read carefully.</p>',
            rating_schema={'questions': []},
            dataset_name='my_dataset',
        )
        db.session.add(study)
        db.session.commit()

        assert study.description == 'Detailed description'
        assert study.protocol_pdf_path == '/uploads/protocol.pdf'
        assert study.status == 'active'
        assert study.uncertainty_enabled is True
        assert study.session_instruction == '<p>Please read carefully.</p>'
        assert study.dataset_name == 'my_dataset'


class TestStudyParticipant:
    """Tests for the StudyParticipant model."""

    def test_create_study_participant(self, db, test_user, sample_study):
        sp = StudyParticipant(study_id=sample_study.id, user_id=test_user.id)
        db.session.add(sp)
        db.session.commit()

        assert sp.study_id == sample_study.id
        assert sp.user_id == test_user.id
        assert sp.submitted is False
        assert sp.submitted_at is None
        assert sp.last_viewed_image_id is None

    def test_random_seed_generation(self, db, test_user, sample_study):
        sp = StudyParticipant(study_id=sample_study.id, user_id=test_user.id)
        db.session.add(sp)
        db.session.commit()

        assert sp.random_seed is not None
        assert isinstance(sp.random_seed, int)
        assert 0 <= sp.random_seed <= 2**31 - 1

    def test_random_seed_differs_between_users(self, db, sample_study):
        """Different users should very likely get different random seeds."""
        users = []
        for i in range(5):
            u = User(first_name=f'U{i}', last_name='Test', email=f'u{i}@test.com', role='participant')
            u.set_password('pass')
            db.session.add(u)
            users.append(u)
        db.session.flush()

        seeds = set()
        for u in users:
            sp = StudyParticipant(study_id=sample_study.id, user_id=u.id)
            db.session.add(sp)
            db.session.flush()
            seeds.add(sp.random_seed)

        db.session.commit()
        # With 5 random seeds from 0 to 2^31, collision is astronomically unlikely
        assert len(seeds) == 5

    def test_composite_primary_key(self, db, test_user, sample_study):
        sp1 = StudyParticipant(study_id=sample_study.id, user_id=test_user.id)
        db.session.add(sp1)
        db.session.commit()

        sp2 = StudyParticipant(study_id=sample_study.id, user_id=test_user.id)
        db.session.add(sp2)
        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_last_viewed_image_set_null_on_delete(self, db, test_user, sample_study):
        """When a DatasetImage is deleted, last_viewed_image_id should be set to NULL."""
        img = DatasetImage(
            study_id=sample_study.id,
            image_path='model_1/mpp_0.5/1/input.png',
            attributes={'synthetic': False},
            sequence_number=1,
        )
        db.session.add(img)
        db.session.flush()

        sp = StudyParticipant(
            study_id=sample_study.id,
            user_id=test_user.id,
            last_viewed_image_id=img.id,
        )
        db.session.add(sp)
        db.session.commit()

        assert sp.last_viewed_image_id == img.id

        db.session.delete(img)
        db.session.commit()

        db.session.refresh(sp)
        assert sp.last_viewed_image_id is None


class TestDatasetImage:
    """Tests for the DatasetImage model."""

    def test_create_dataset_image(self, db, sample_study):
        img = DatasetImage(
            study_id=sample_study.id,
            image_path='model_1/mpp_0.5/1/input.png',
            attributes={
                'synthetic': False,
                'tissue_type': 'Tumor-dominant',
                'mpp_value': 0.5,
                'model_name': 'model_1',
            },
            sequence_number=1,
        )
        db.session.add(img)
        db.session.commit()

        assert img.id is not None
        assert img.study_id == sample_study.id
        assert img.image_path == 'model_1/mpp_0.5/1/input.png'
        assert img.attributes['synthetic'] is False
        assert img.attributes['tissue_type'] == 'Tumor-dominant'
        assert img.attributes['mpp_value'] == 0.5
        assert img.attributes['model_name'] == 'model_1'
        assert img.sequence_number == 1

    def test_synthetic_image(self, db, sample_study):
        img = DatasetImage(
            study_id=sample_study.id,
            image_path='model_1/mpp_0.5/1/cfg_2.5.png',
            attributes={
                'synthetic': True,
                'mpp_value': 0.5,
                'model_name': 'model_1',
            },
            sequence_number=2,
        )
        db.session.add(img)
        db.session.commit()
        assert img.attributes['synthetic'] is True
        assert img.attributes['model_name'] == 'model_1'

    def test_sequence_number_ordering(self, db, sample_study):
        for i in range(1, 6):
            img = DatasetImage(
                study_id=sample_study.id,
                image_path=f'model_1/mpp_0.5/{i}/input.png',
                attributes={'synthetic': False},
                sequence_number=i,
            )
            db.session.add(img)
        db.session.commit()

        images = DatasetImage.query.filter_by(study_id=sample_study.id).order_by(
            DatasetImage.sequence_number
        ).all()
        assert [img.sequence_number for img in images] == [1, 2, 3, 4, 5]


class TestRating:
    """Tests for the Rating model."""

    def test_create_rating_with_empty_responses(self, db, test_user, sample_study):
        img = DatasetImage(
            study_id=sample_study.id,
            image_path='model_1/mpp_0.5/1/input.png',
            attributes={'synthetic': False},
            sequence_number=1,
        )
        db.session.add(img)
        db.session.flush()

        rating = Rating(
            user_id=test_user.id,
            dataset_image_id=img.id,
            study_id=sample_study.id,
        )
        db.session.add(rating)
        db.session.commit()

        assert rating.id is not None
        assert rating.responses == {}
        assert rating.uncertainty is None
        assert rating.time_spent_seconds == 0.0
        assert rating.created_at is not None
        assert rating.updated_at is not None

    def test_rating_with_responses(self, db, test_user, sample_study):
        img = DatasetImage(
            study_id=sample_study.id,
            image_path='model_1/mpp_0.5/2/input.png',
            attributes={'synthetic': False},
            sequence_number=1,
        )
        db.session.add(img)
        db.session.flush()

        responses = {'F1': 2, 'F2': 1, 'F3': 2, 'F4': 2, 'F5': 1, 'F6': 2}
        rating = Rating(
            user_id=test_user.id,
            dataset_image_id=img.id,
            study_id=sample_study.id,
            responses=responses,
            uncertainty=False,
            time_spent_seconds=15.3,
        )
        db.session.add(rating)
        db.session.commit()

        loaded = db.session.get(Rating, rating.id)
        assert loaded.responses['F1'] == 2
        assert loaded.responses['F5'] == 1
        assert loaded.uncertainty is False
        assert loaded.time_spent_seconds == 15.3

    def test_rating_time_spent_default(self, db, test_user, sample_study):
        img = DatasetImage(
            study_id=sample_study.id,
            image_path='model_1/mpp_0.5/3/input.png',
            attributes={'synthetic': False},
            sequence_number=1,
        )
        db.session.add(img)
        db.session.flush()

        rating = Rating(
            user_id=test_user.id,
            dataset_image_id=img.id,
            study_id=sample_study.id,
        )
        db.session.add(rating)
        db.session.commit()
        assert rating.time_spent_seconds == 0.0


class TestRelationships:
    """Tests for model relationships."""

    def test_user_study_participant_relationship(self, db, test_user, sample_study):
        sp = StudyParticipant(study_id=sample_study.id, user_id=test_user.id)
        db.session.add(sp)
        db.session.commit()

        assert len(test_user.study_participants) == 1
        assert test_user.study_participants[0].study_id == sample_study.id

    def test_study_study_participant_relationship(self, db, test_user, sample_study):
        sp = StudyParticipant(study_id=sample_study.id, user_id=test_user.id)
        db.session.add(sp)
        db.session.commit()

        assert len(sample_study.study_participants) == 1
        assert sample_study.study_participants[0].user_id == test_user.id

    def test_study_participant_navigates_to_both(self, db, test_user, sample_study):
        sp = StudyParticipant(study_id=sample_study.id, user_id=test_user.id)
        db.session.add(sp)
        db.session.commit()

        assert sp.user.email == 'participant@example.com'
        assert sp.study.name == 'Test Study'

    def test_study_dataset_images_relationship(self, db, sample_study):
        for i in range(3):
            img = DatasetImage(
                study_id=sample_study.id,
                image_path=f'model_1/mpp_0.5/{i}/input.png',
                attributes={'synthetic': False},
                sequence_number=i + 1,
            )
            db.session.add(img)
        db.session.commit()

        assert len(sample_study.dataset_images) == 3

    def test_rating_dataset_image_relationship(self, db, test_user, sample_study):
        img = DatasetImage(
            study_id=sample_study.id,
            image_path='model_1/mpp_0.5/1/input.png',
            attributes={'synthetic': False},
            sequence_number=1,
        )
        db.session.add(img)
        db.session.flush()

        rating = Rating(
            user_id=test_user.id,
            dataset_image_id=img.id,
            study_id=sample_study.id,
        )
        db.session.add(rating)
        db.session.commit()

        assert rating.dataset_image.image_path == 'model_1/mpp_0.5/1/input.png'
        assert img.ratings[0].user_id == test_user.id

    def test_rating_user_relationship(self, db, test_user, sample_study):
        img = DatasetImage(
            study_id=sample_study.id,
            image_path='model_1/mpp_0.5/1/input.png',
            attributes={'synthetic': False},
            sequence_number=1,
        )
        db.session.add(img)
        db.session.flush()

        rating = Rating(
            user_id=test_user.id,
            dataset_image_id=img.id,
            study_id=sample_study.id,
        )
        db.session.add(rating)
        db.session.commit()

        assert rating.user.email == 'participant@example.com'
        assert len(test_user.ratings) == 1


class TestCascadingDeletes:
    """Tests for cascading delete behavior."""

    def test_delete_study_cascades_to_dataset_images(self, db, sample_study):
        for i in range(3):
            img = DatasetImage(
                study_id=sample_study.id,
                image_path=f'model_1/mpp_0.5/{i}/input.png',
                attributes={'synthetic': False},
                sequence_number=i + 1,
            )
            db.session.add(img)
        db.session.commit()

        assert DatasetImage.query.count() == 3
        db.session.delete(sample_study)
        db.session.commit()
        assert DatasetImage.query.count() == 0

    def test_delete_study_cascades_to_ratings(self, db, test_user, sample_study):
        img = DatasetImage(
            study_id=sample_study.id,
            image_path='model_1/mpp_0.5/1/input.png',
            attributes={'synthetic': False},
            sequence_number=1,
        )
        db.session.add(img)
        db.session.flush()

        rating = Rating(
            user_id=test_user.id,
            dataset_image_id=img.id,
            study_id=sample_study.id,
        )
        db.session.add(rating)
        db.session.commit()

        assert Rating.query.count() == 1
        db.session.delete(sample_study)
        db.session.commit()
        assert Rating.query.count() == 0

    def test_delete_dataset_image_cascades_to_ratings(self, db, test_user, sample_study):
        img = DatasetImage(
            study_id=sample_study.id,
            image_path='model_1/mpp_0.5/1/input.png',
            attributes={'synthetic': False},
            sequence_number=1,
        )
        db.session.add(img)
        db.session.flush()

        rating = Rating(
            user_id=test_user.id,
            dataset_image_id=img.id,
            study_id=sample_study.id,
        )
        db.session.add(rating)
        db.session.commit()

        assert Rating.query.count() == 1
        db.session.delete(img)
        db.session.commit()
        assert Rating.query.count() == 0

    def test_delete_study_cascades_to_study_participants(self, db, test_user, sample_study):
        sp = StudyParticipant(study_id=sample_study.id, user_id=test_user.id)
        db.session.add(sp)
        db.session.commit()

        assert StudyParticipant.query.count() == 1
        db.session.delete(sample_study)
        db.session.commit()
        assert StudyParticipant.query.count() == 0

    def test_delete_user_cascades_to_study_participants(self, db, test_user, sample_study):
        sp = StudyParticipant(study_id=sample_study.id, user_id=test_user.id)
        db.session.add(sp)
        db.session.commit()

        assert StudyParticipant.query.count() == 1
        db.session.delete(test_user)
        db.session.commit()
        assert StudyParticipant.query.count() == 0

    def test_delete_user_cascades_to_ratings(self, db, test_user, sample_study):
        img = DatasetImage(
            study_id=sample_study.id,
            image_path='model_1/mpp_0.5/1/input.png',
            attributes={'synthetic': False},
            sequence_number=1,
        )
        db.session.add(img)
        db.session.flush()

        rating = Rating(
            user_id=test_user.id,
            dataset_image_id=img.id,
            study_id=sample_study.id,
        )
        db.session.add(rating)
        db.session.commit()

        assert Rating.query.count() == 1
        db.session.delete(test_user)
        db.session.commit()
        assert Rating.query.count() == 0

    def test_full_cascade_study_to_images_to_ratings(self, db, test_user, sample_study):
        """Delete Study -> deletes DatasetImages -> deletes Ratings."""
        images = []
        for i in range(3):
            img = DatasetImage(
                study_id=sample_study.id,
                image_path=f'model_1/mpp_0.5/{i}/input.png',
                attributes={'synthetic': False},
                sequence_number=i + 1,
            )
            db.session.add(img)
            images.append(img)
        db.session.flush()

        for img in images:
            rating = Rating(
                user_id=test_user.id,
                dataset_image_id=img.id,
                study_id=sample_study.id,
            )
            db.session.add(rating)
        db.session.commit()

        assert DatasetImage.query.count() == 3
        assert Rating.query.count() == 3

        db.session.delete(sample_study)
        db.session.commit()

        assert DatasetImage.query.count() == 0
        assert Rating.query.count() == 0
        assert StudyParticipant.query.count() == 0
