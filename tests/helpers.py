"""Common test utilities to reduce boilerplate across test modules."""

from app.models import DatasetImage, Study, StudyParticipant, User
from app.services.schema_service import get_default_pass_fail_config, get_default_rating_schema


def login(client, email, password):
    """POST /api/auth/login and return the parsed JSON response dict."""
    resp = client.post('/api/auth/login', json={
        'email': email,
        'password': password,
    })
    return resp


def login_admin(client):
    """Log in as the default admin user (email='admin', password='adminpassword').

    Assumes the admin_user fixture has been applied so the password is 'adminpassword'.
    """
    return login(client, 'admin', 'adminpassword')


def login_participant(client, email='participant@example.com', password='testpassword'):
    """Log in as a participant user."""
    return login(client, email, password)


def create_study_with_schema(db_session):
    """Create and return a study with the default 6-question rating schema.

    The study is in 'draft' status with default stratification config.
    """
    study = Study(
        name='Test Study With Schema',
        description='A test study with full schema',
        status='draft',
        rating_schema=get_default_rating_schema(),
        pass_fail_config=get_default_pass_fail_config(),
        uncertainty_enabled=True,
    )
    db_session.session.add(study)
    db_session.session.commit()
    return study


def create_study_with_images(db_session, n=10):
    """Create and return a study with *n* dataset images (half real, half synthetic).

    Images have stratification categories assigned so the study is ready for
    activation once participants are added.
    """
    study = create_study_with_schema(db_session)
    study.name = 'Test Study With Images'
    study.dataset_name = 'test_dataset'

    categories = ['Tumor-dominant', 'Stroma-dominant']
    for i in range(1, n + 1):
        img = DatasetImage(
            study_id=study.id,
            image_path=f'test_dataset/{i:04d}.png',
            attributes={
                'synthetic': (i > n // 2),
                'mpp_value': 0.5,
                'tissue_type': categories[i % 2],
            },
            sequence_number=i,
        )
        db_session.session.add(img)

    db_session.session.commit()
    return study


def create_full_study(db_session, n_images=10, n_participants=2):
    """Create a fully configured study with schema, images, and assigned participants.

    Returns ``(study, participants)`` where *participants* is a list of User
    objects that have been assigned to the study.
    """
    study = create_study_with_images(db_session, n=n_images)
    study.name = 'Full Test Study'
    study.status = 'active'

    participants = []
    for i in range(n_participants):
        user = User(
            first_name=f'Participant{i}',
            last_name=f'User{i}',
            email=f'participant{i}@test.com',
            institution='Test Hospital',
            role='participant',
            is_test_user=False,
        )
        user.set_password('testpassword')
        db_session.session.add(user)
        db_session.session.flush()

        sp = StudyParticipant(
            study_id=study.id,
            user_id=user.id,
            random_seed=42 + i,
        )
        db_session.session.add(sp)
        participants.append(user)

    db_session.session.commit()
    return study, participants
