"""Seed data service for demo/test database initialization.

Creates a demo evaluation study with balanced images,
seed participants, and plausible ratings on first server start.
Idempotent: skips seeding if the demo study already exists.
"""

import csv
import os
import random
import secrets
import struct
import zlib
from datetime import datetime, timezone, timedelta

from flask import current_app

from app import db
from app.models import User, Study, StudyParticipant, DatasetImage, Rating
from app.services.schema_service import (
    get_default_rating_schema,
    get_default_pass_fail_config,
    evaluate_condition,
)

STUDY_NAME = "Demo Evaluation Study"

# Seed participants: (first_name, institution)
SEED_PARTICIPANTS = [
    ("Amara", "University Hospital Zurich"),
    ("Carlos", "Stanford Pathology Lab"),
    ("Yuki", "Tokyo Medical Center"),
    ("Eleanor", "Oxford Institute of Pathology"),
]

# MPP levels used for image generation
MPP_LEVELS = [0.5, 1.0, 1.5, 2.0]

# Per-rater bias offsets (applied to base mean for score generation)
# Positive = more lenient, negative = stricter
RATER_BIASES = [0.1, -0.15, 0.05, -0.1]


def _make_png(width, height, r, g, b):
    """Generate a minimal valid PNG file as bytes using only stdlib.

    Creates a solid-color image of the given dimensions and RGB values.
    """
    def _chunk(chunk_type, data):
        raw = chunk_type + data
        return struct.pack('>I', len(data)) + raw + struct.pack('>I', zlib.crc32(raw) & 0xFFFFFFFF)

    # PNG signature
    signature = b'\x89PNG\r\n\x1a\n'

    # IHDR: width, height, bit depth 8, color type 2 (RGB)
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    ihdr = _chunk(b'IHDR', ihdr_data)

    # IDAT: raw pixel data (filter byte 0 + RGB for each row)
    row = b'\x00' + bytes([r, g, b]) * width
    raw_data = row * height
    compressed = zlib.compress(raw_data)
    idat = _chunk(b'IDAT', compressed)

    # IEND
    iend = _chunk(b'IEND', b'')

    return signature + ihdr + idat + iend


def seed_database():
    """Seed the database with demo data if not already present.

    Creates:
    - A demo study with default Tier-2 schema and dataset_name
    - 80 dataset images (40 real + 40 synthetic), balanced across MPP levels
    - Placeholder PNG files and metadata.csv in uploads/datasets/demo_dataset/
    - 4 seed participant users with plausible ratings on all images
    - Test user assignment to the study (not submitted)

    Uses random.Random(42) for reproducible data generation.
    """
    # Idempotency check
    existing = Study.query.filter_by(name=STUDY_NAME).first()
    if existing is not None:
        return

    rng = random.Random(42)

    # Create the demo study
    schema = get_default_rating_schema()

    study = Study(
        name=STUDY_NAME,
        description="A demonstration reader study for evaluating synthetic histopathology images.",
        status="active",
        rating_schema=schema,
        pass_fail_config=get_default_pass_fail_config(),
        dataset_name="demo_dataset",
    )
    db.session.add(study)
    db.session.flush()  # Get study.id

    # Create 80 dataset images: 40 real + 40 synthetic
    # 10 real + 10 synthetic per MPP level
    images = _create_images(study)
    db.session.flush()  # Get image IDs

    # Create 4 seed participants
    participants = _create_participants()
    db.session.flush()  # Get user IDs

    # Create StudyParticipant entries for seed participants (all submitted)
    base_time = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    for i, user in enumerate(participants):
        pu = StudyParticipant(
            study_id=study.id,
            user_id=user.id,
            submitted=True,
            submitted_at=base_time + timedelta(hours=i * 3, minutes=rng.randint(0, 59)),
            random_seed=rng.randint(0, 2**31 - 1),
        )
        db.session.add(pu)

    # Assign existing test user to the study (not submitted)
    test_user = User.query.filter_by(email="test").first()
    if test_user:
        pu_test = StudyParticipant(
            study_id=study.id,
            user_id=test_user.id,
            submitted=False,
            random_seed=rng.randint(0, 2**31 - 1),
        )
        db.session.add(pu_test)

    # Generate ratings for all participants on all images
    _create_ratings(study, participants, images, schema, rng)

    db.session.commit()


# RGB tints per MPP level: green tints for real, purple tints for synthetic
_MPP_COLORS = {
    0.5:  {"real": (100, 180, 100), "synth": (160, 100, 180)},
    1.0:  {"real": (80,  200, 80),  "synth": (180, 80,  200)},
    1.5:  {"real": (60,  160, 60),  "synth": (140, 60,  160)},
    2.0:  {"real": (40,  140, 40),  "synth": (120, 40,  140)},
}


def _create_images(study):
    """Create 80 balanced dataset images for the study.

    Writes placeholder PNG files and metadata.csv to the demo_dataset directory.
    Returns a list of DatasetImage objects (40 real + 40 synthetic).
    """
    datasets_dir = current_app.config.get('DATASETS_DIR', os.path.join('uploads', 'datasets'))
    dataset_dir = os.path.join(datasets_dir, 'demo_dataset')

    # Collect image info for metadata.csv
    csv_rows = []
    images = []
    seq = 1

    for mpp in MPP_LEVELS:
        # 10 real images per MPP level
        for i in range(10):
            filename = f"mpp_{mpp}_{i}_input.png"

            csv_rows.append({
                "image_name": filename,
                "mpp_value": mpp,
                "synthetic": False,
            })

            img = DatasetImage(
                study_id=study.id,
                image_path=f"demo_dataset/{filename}",
                attributes={"mpp_value": mpp, "synthetic": False},
                sequence_number=seq,
            )
            db.session.add(img)
            images.append(img)
            seq += 1

        # 10 synthetic images per MPP level
        for i in range(10):
            filename = f"mpp_{mpp}_{i}_cfg_2.5.png"

            csv_rows.append({
                "image_name": filename,
                "mpp_value": mpp,
                "synthetic": True,
            })

            img = DatasetImage(
                study_id=study.id,
                image_path=f"demo_dataset/{filename}",
                attributes={"mpp_value": mpp, "synthetic": True},
                sequence_number=seq,
            )
            db.session.add(img)
            images.append(img)
            seq += 1

    # Write files to disk (idempotent: skip if directory already exists)
    if not os.path.isdir(dataset_dir):
        os.makedirs(dataset_dir, exist_ok=True)

        # Write PNG files
        for row in csv_rows:
            mpp = row["mpp_value"]
            is_synth = row["synthetic"]
            colors = _MPP_COLORS[mpp]
            r, g, b = colors["synth"] if is_synth else colors["real"]
            png_bytes = _make_png(64, 64, r, g, b)
            filepath = os.path.join(dataset_dir, row["image_name"])
            with open(filepath, 'wb') as f:
                f.write(png_bytes)

        # Write metadata.csv
        csv_path = os.path.join(dataset_dir, 'metadata.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['image_name', 'mpp_value', 'synthetic'])
            writer.writeheader()
            for row in csv_rows:
                writer.writerow({
                    'image_name': row['image_name'],
                    'mpp_value': row['mpp_value'],
                    'synthetic': str(row['synthetic']).lower(),
                })

    return images


def _create_participants():
    """Create 4 seed participant users.

    Returns a list of User objects.
    """
    participants = []
    for first_name, institution in SEED_PARTICIPANTS:
        email = f"{first_name.lower()}.test@example.com"
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(
                first_name=first_name,
                last_name="Test",
                email=email,
                institution=institution,
                role="participant",
                is_test_user=False,
            )
            user.set_password(current_app.config.get('DEMO_PASSWORD') or secrets.token_urlsafe(24))
            db.session.add(user)
        participants.append(user)
    return participants


def _generate_score(rng, mean, bias):
    """Generate a single ordinal score (0, 1, or 2) with given mean and bias.

    Uses a simple approach: draw from a distribution centered on mean+bias,
    then clamp to [0, 2].
    """
    # Effective mean with rater bias
    effective_mean = mean + bias
    # Add noise
    raw = effective_mean + rng.gauss(0, 0.5)
    # Round and clamp to valid range
    score = max(0, min(2, round(raw)))
    return score


def _create_ratings(study, participants, images, schema, rng):
    """Create plausible ratings for all participants on all images.

    Real images get higher base scores (mean ~1.5).
    Synthetic images get slightly lower base scores (mean ~1.2).
    Per-rater biases add individual variation.
    """
    failure_condition = schema.get("failure_reason", {}).get("condition", {})
    failure_options = schema.get("failure_reason", {}).get("options", [])
    question_ids = [q["id"] for q in schema["questions"] if q["type"] == "ordinal"]

    for rater_idx, user in enumerate(participants):
        bias = RATER_BIASES[rater_idx]

        for img in images:
            is_synthetic = (img.attributes or {}).get("synthetic", False)
            base_mean = 1.5 if not is_synthetic else 1.2

            # Generate responses for each question
            responses = {}
            for qid in question_ids:
                responses[qid] = _generate_score(rng, base_mean, bias)

            # If any score is 0, add a failure_reason
            has_failure = evaluate_condition(failure_condition, responses, schema)
            if has_failure and failure_options:
                # Pick a plausible failure reason based on which question scored 0
                reason = None
                for i, qid in enumerate(question_ids):
                    if responses[qid] == 0 and i < len(failure_options):
                        reason = failure_options[i]
                        break
                if reason is None:
                    reason = failure_options[-1]  # "Other"
                responses["failure_reason"] = reason

            # Uncertainty flag: ~10% chance
            uncertainty = rng.random() < 0.10

            # Realistic time spent: 5-30 seconds
            time_spent = round(rng.uniform(5.0, 30.0), 1)

            rating = Rating(
                user_id=user.id,
                dataset_image_id=img.id,
                study_id=study.id,
                responses=responses,
                uncertainty=uncertainty,
                time_spent_seconds=time_spent,
            )
            db.session.add(rating)
