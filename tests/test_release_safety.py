"""Regression tests for deployment, uploads, and data integrity."""

import csv
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image

from app import create_app
from app.config import TestConfig, _load_secret_key
from app.models import Rating, Study, StudyParticipant, User
from app.services.export_service import generate_csv
from app.services.image_scanner import parse_value, resolve_image_name, scan_dataset
from app.services.xopat import get_deepzoom_generator, make_study_slide_id
from tests.helpers import create_study_with_images, login_admin, login_participant


def test_empty_database_requires_private_password(tmp_path):
    class ReleaseConfig(TestConfig):
        ADMIN_PASSWORD = ''
        CREATE_TEST_USER = False
        UPLOADS_DIR = str(tmp_path / 'uploads')
        DATASETS_DIR = str(tmp_path / 'datasets')

    with pytest.raises(RuntimeError, match='ADMIN_PASSWORD'):
        create_app(ReleaseConfig)


def test_bootstrap_is_private_and_preserves_renamed_admin(tmp_path):
    class ReleaseConfig(TestConfig):
        ADMIN_PASSWORD = 'private-initial-password'
        CREATE_TEST_USER = False
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{tmp_path / "app.db"}'
        UPLOADS_DIR = str(tmp_path / 'uploads')
        DATASETS_DIR = str(tmp_path / 'datasets')

    from app import db
    app = create_app(ReleaseConfig)
    with app.app_context():
        assert User.query.count() == 1
        assert Study.query.count() == 0
        admin = User.query.one()
        assert admin.check_password(ReleaseConfig.ADMIN_PASSWORD)
        admin.email = 'renamed@example.com'
        db.session.commit()
    restarted = create_app(ReleaseConfig)
    with restarted.app_context():
        assert User.query.count() == 1
        assert User.query.one().email == 'renamed@example.com'


def test_concurrent_initial_secret_key_is_shared(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = list(pool.map(lambda _: _load_secret_key(tmp_path, {}), range(16)))
    assert len(set(keys)) == 1


@pytest.mark.parametrize('body', [[], [1], 'text', 12, None])
def test_invalid_json_shape_returns_400(client, body):
    response = client.post('/api/auth/login', data=__import__('json').dumps(body),
                           content_type='application/json')
    assert response.status_code == 400


def test_cross_origin_mutations_are_rejected(client, admin_user):
    response = client.post('/api/auth/login', json={'email': 'admin', 'password': 'adminpassword'},
                           headers={'Origin': 'https://untrusted.example'})
    assert response.status_code == 403
    response = client.post('/api/auth/login', json={'email': 'admin', 'password': 'adminpassword'},
                           headers={'Origin': 'http://localhost'})
    assert response.status_code == 200
    assert 'SameSite=Lax' in response.headers['Set-Cookie']


def _chunk(client, index=0, total=2, name='sample', path='image.png', content=b'part'):
    return client.post('/api/admin/images/upload-chunk', data={
        'upload_id': 'release-upload', 'dataset_name': name, 'file_path': path,
        'chunk_index': str(index), 'total_chunks': str(total),
        'chunk': (io.BytesIO(content), 'chunk'),
    })


def test_upload_missing_chunks_can_be_retried(client, admin_user, app):
    login_admin(client)
    assert _chunk(client).status_code == 200
    completion = {'upload_id': 'release-upload', 'dataset_name': 'sample'}
    assert client.post('/api/admin/images/upload-complete', json=completion).status_code == 409
    target = Path(app.config['DATASETS_DIR']) / 'sample'
    assert not target.exists()
    assert _chunk(client, index=1).status_code == 200
    assert client.post('/api/admin/images/upload-complete', json=completion).status_code == 200
    assert (target / 'image.png').read_bytes() == b'partpart'


@pytest.mark.parametrize('index,total,path', [(-1, 2, 'image.png'), (2, 2, 'image.png'),
                                             (0, 0, 'image.png'), (0, 1, '../escape.png'),
                                             (0, 1, '/escape.png'), (0, 1, 'a\\b.png')])
def test_invalid_upload_chunks_are_rejected(client, admin_user, index, total, path):
    login_admin(client)
    assert _chunk(client, index, total, path=path).status_code == 400


def test_upload_cannot_change_dataset_or_chunk_count(client, admin_user):
    login_admin(client)
    assert _chunk(client).status_code == 200
    assert _chunk(client, name='different').status_code == 409
    assert _chunk(client, total=3).status_code == 409
    assert client.post('/api/admin/images/upload-complete', json={
        'upload_id': 'release-upload', 'dataset_name': 'different',
    }).status_code == 409


def test_csv_missing_cells_bom_and_unsafe_paths(tmp_path):
    dataset = tmp_path / 'sample'
    dataset.mkdir()
    (tmp_path / 'private.png').write_bytes(b'private')
    (dataset / 'image.png').write_bytes(b'image')
    (dataset / 'escape.png').symlink_to(tmp_path / 'private.png')
    (dataset / 'metadata.csv').write_text('\ufeffimage_name,score\nimage.png\n', encoding='utf-8')
    assert scan_dataset(tmp_path, 'sample')[0]['attributes'] == {'score': ''}
    assert resolve_image_name(dataset, '../private.png') is None
    assert resolve_image_name(dataset, 'escape.png') is None
    assert parse_value('NaN') == 'NaN'
    assert parse_value('Infinity') == 'Infinity'


@pytest.fixture()
def active_rating(client, db, test_user):
    study = create_study_with_images(db, n=1)
    study.status = 'active'
    db.session.add(StudyParticipant(study_id=study.id, user_id=test_user.id))
    db.session.commit()
    login_participant(client)
    response = client.get(f'/api/studies/{study.id}/image/1')
    return study, db.session.get(Rating, response.json['rating']['id'])


@pytest.mark.parametrize('value', [True, 1.5, float('nan'), float('inf')])
def test_ordinal_rejects_non_integer_values(client, active_rating, value):
    _, rating = active_rating
    assert client.put(f'/api/ratings/{rating.id}/response',
                      json={'question_id': 'F1', 'value': value}).status_code == 400


@pytest.mark.parametrize('elapsed', [True, float('inf'), float('nan'), -1])
def test_elapsed_time_must_be_finite(client, active_rating, elapsed):
    _, rating = active_rating
    assert client.put(f'/api/ratings/{rating.id}/time', json={'elapsed': elapsed}).status_code == 400


def test_closed_study_cannot_be_modified(client, db, active_rating):
    study, rating = active_rating
    study.status = 'finished'
    db.session.commit()
    assert client.put(f'/api/ratings/{rating.id}/response',
                      json={'question_id': 'F1', 'value': 2}).status_code == 403
    assert client.post(f'/api/studies/{study.id}/submit').status_code == 403


def test_free_text_and_column_names_are_safe_in_csv(client, db, active_rating):
    study, rating = active_rating
    study.rating_schema = {'questions': [{'id': '=column', 'type': 'free_text', 'label': 'Notes'}]}
    rating.responses = {'=column': '=HYPERLINK("https://example.com")'}
    db.session.commit()
    rows = list(csv.reader(io.StringIO(generate_csv(study.id)[0])))
    column = rows[0].index("'=column")
    assert rows[1][column].startswith("'=")


def test_tile_cache_does_not_reuse_another_file(tmp_path):
    first, second = tmp_path / 'first.png', tmp_path / 'second.png'
    Image.new('RGB', (4, 4), 'red').save(first)
    Image.new('RGB', (4, 4), 'blue').save(second)
    slide_id = make_study_slide_id(1, 1)
    a = get_deepzoom_generator(slide_id, str(first))
    b = get_deepzoom_generator(slide_id, str(second))
    assert a.get_tile(2, (0, 0)).getpixel((0, 0)) != b.get_tile(2, (0, 0)).getpixel((0, 0))


def test_disabled_notebook_returns_explicit_status(client, admin_user, sample_study, app):
    login_admin(client)
    app.config['ENABLE_JUPYTER'] = False
    url = f'/api/admin/studies/{sample_study.id}/notebook'
    assert client.get(url).json['enabled'] is False
    assert client.post(url).status_code == 503


def test_health_reports_release_version(client):
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.json == {'status': 'ok', 'version': '1.0.0'}


@pytest.mark.parametrize('schema', [[], {'questions': [{'id': [], 'type': 'ordinal', 'name': 'Bad'}]},
                                    {'questions': [{'id': 'F1', 'type': 'ordinal', 'name': 'Bad', 'min': False, 'max': 2}]}])
def test_malformed_schema_returns_400(client, admin_user, sample_study, schema):
    login_admin(client)
    response = client.put(f'/api/admin/studies/{sample_study.id}/schema', json={'schema': schema})
    assert response.status_code == 400


def test_notebook_uses_configured_storage(client, admin_user, sample_study, app, tmp_path):
    pytest.importorskip('nbformat')
    login_admin(client)
    app.config.update(ENABLE_JUPYTER=True, NOTEBOOKS_DIR=str(tmp_path / 'analysis'),
                      JUPYTER_TOKEN='private+token&value')
    response = client.post(f'/api/admin/studies/{sample_study.id}/notebook')
    assert response.status_code == 200
    assert 'private%2Btoken%26value' in response.json['url']
    assert (tmp_path / 'analysis' / response.json['filename']).is_file()
    assert (tmp_path / 'analysis' / f'study_{sample_study.id}.csv').is_file()


def test_statistics_cache_includes_pass_fail_configuration(monkeypatch):
    import pandas as pd
    from app.services import statistics

    seen = []

    def prepare(study_id, **kwargs):
        seen.append(kwargs['pass_fail_config'])
        return pd.DataFrame()

    monkeypatch.setattr(statistics, 'prepare_ratings_dataframe', prepare)
    statistics.invalidate_stats_cache()
    schema = {'questions': []}
    first = {'total_score_questions': [], 'conditions': []}
    second = {'total_score_questions': [], 'conditions': [{'field': 'S_total', 'operator': '>', 'value': 1}]}
    statistics.compute_all(987, schema=schema, pass_fail_config=first)
    statistics.compute_all(987, schema=schema, pass_fail_config=second)
    assert seen == [first, second]
    statistics.invalidate_stats_cache()
