import random
from datetime import datetime, timezone

from flask_login import UserMixin

from app import bcrypt, db, login_manager


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (ValueError, TypeError):
        return None


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    institution = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='participant')
    comments = db.Column(db.Text, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    is_test_user = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    study_participants = db.relationship('StudyParticipant', back_populates='user', cascade='all, delete-orphan')
    ratings = db.relationship('Rating', back_populates='user', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        if not isinstance(password, str) or len(password.encode('utf-8')) > 72:
            return False
        return bcrypt.check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'


class Study(db.Model):
    __tablename__ = 'studies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    protocol_pdf_path = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='draft')
    uncertainty_enabled = db.Column(db.Boolean, default=False, nullable=False)
    session_instruction = db.Column(db.Text, nullable=True)
    rating_schema = db.Column(db.JSON, nullable=True)
    pass_fail_config = db.Column(db.JSON, nullable=True)
    dataset_name = db.Column(db.String(255), nullable=True)
    default_image_viewer = db.Column(db.String(20), nullable=False, default='native')

    # Relationships
    study_participants = db.relationship('StudyParticipant', back_populates='study', cascade='all, delete-orphan')
    dataset_images = db.relationship('DatasetImage', back_populates='study', cascade='all, delete-orphan')
    ratings = db.relationship('Rating', back_populates='study', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Study {self.name}>'


class StudyParticipant(db.Model):
    __tablename__ = 'study_participants'

    study_id = db.Column(db.Integer, db.ForeignKey('studies.id', ondelete='CASCADE'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    submitted = db.Column(db.Boolean, default=False, nullable=False)
    submitted_at = db.Column(db.DateTime, nullable=True)
    random_seed = db.Column(db.Integer, nullable=False, default=lambda: random.randint(0, 2**31 - 1))
    last_viewed_image_id = db.Column(
        db.Integer,
        db.ForeignKey('dataset_images.id', ondelete='SET NULL'),
        nullable=True,
    )

    # Relationships
    study = db.relationship('Study', back_populates='study_participants')
    user = db.relationship('User', back_populates='study_participants')
    last_viewed_image = db.relationship('DatasetImage', foreign_keys=[last_viewed_image_id])

    def __repr__(self):
        return f'<StudyParticipant study={self.study_id} user={self.user_id}>'


class DatasetImage(db.Model):
    __tablename__ = 'dataset_images'
    __table_args__ = (
        db.UniqueConstraint('study_id', 'image_path', name='uq_study_image_path'),
    )

    id = db.Column(db.Integer, primary_key=True)
    study_id = db.Column(db.Integer, db.ForeignKey('studies.id', ondelete='CASCADE'), nullable=False)
    image_path = db.Column(db.String(500), nullable=False)
    attributes = db.Column(db.JSON, nullable=False, default=dict)
    sequence_number = db.Column(db.Integer, nullable=False)

    # Relationships
    study = db.relationship('Study', back_populates='dataset_images')
    ratings = db.relationship('Rating', back_populates='dataset_image', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<DatasetImage {self.image_path}>'


class Rating(db.Model):
    __tablename__ = 'ratings'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'dataset_image_id', name='uq_rating_user_image'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    dataset_image_id = db.Column(db.Integer, db.ForeignKey('dataset_images.id', ondelete='CASCADE'), nullable=False)
    study_id = db.Column(db.Integer, db.ForeignKey('studies.id', ondelete='CASCADE'), nullable=False)
    responses = db.Column(db.JSON, nullable=False, default=dict)
    uncertainty = db.Column(db.Boolean, nullable=True)
    time_spent_seconds = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = db.relationship('User', back_populates='ratings')
    dataset_image = db.relationship('DatasetImage', back_populates='ratings')
    study = db.relationship('Study', back_populates='ratings')

    def __repr__(self):
        return f'<Rating user={self.user_id} image={self.dataset_image_id}>'
