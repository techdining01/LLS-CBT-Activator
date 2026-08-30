from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# ============================================================
# DATABASE LOCATION
import sys

# Project root:
# Supports both standard python execution and frozen standalone executables (Nuitka / PyInstaller)
if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

DATABASE_PATH = DATA_DIR / "cbt.sqlite3"


# ============================================================
# DATABASE URL
# ============================================================

DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


# ============================================================
# SQLALCHEMY ENGINE
# ============================================================

engine = create_engine(
    DATABASE_URL,
    # SQLite desktop application.
    connect_args={
        "check_same_thread": False,
    },
    # Useful during development.
    echo=False,
)


# ============================================================
# SQLITE FOREIGN KEY SUPPORT
# ============================================================


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """
    SQLite does not enable foreign-key enforcement by default.

    This turns it on for every connection.
    """

    cursor = dbapi_connection.cursor()

    cursor.execute("PRAGMA foreign_keys=ON")

    cursor.close()


# ============================================================
# BASE MODEL
# ============================================================


class Base(DeclarativeBase):
    """
    Base class inherited by every SQLAlchemy model.
    """

    pass


# ============================================================
# SESSION FACTORY
# ============================================================

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================


def init_database() -> None:
    """
    Create all database tables if they do not already exist.
    Also ensures reports directory, default app settings, and default admin user exist.
    """
    # Import models here so SQLAlchemy knows about them before
    # create_all() is called.
    from app.database import models  # noqa: F401

    # 1. Create all tables defined in models.py
    Base.metadata.create_all(
        bind=engine,
    )

    # 1b. Auto-migrate existing SQLite database if exam_body column or constraint needs upgrade
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            # Check questions table
            q_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(questions)")).fetchall()]
            if len(q_cols) > 0:
                table_sql_row = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='questions'")).fetchone()
                table_sql = table_sql_row[0] if table_sql_row else ""

                if "exam_body" not in q_cols:
                    conn.execute(text("ALTER TABLE questions ADD COLUMN exam_body VARCHAR(50) DEFAULT 'JAMB' NOT NULL"))
                    conn.commit()
                    print("Migrated questions table: added exam_body column.")

                # If old unique constraint (subject_id, year, question_number) without exam_body exists, rebuild table
                if "UNIQUE (subject_id, year, question_number)" in table_sql or "uq_question_year_subject_number" in table_sql:
                    print("Upgrading questions table schema with composite unique constraint (exam_body, subject_id, year, question_number)...")
                    conn.execute(text("PRAGMA foreign_keys=off;"))
                    conn.execute(text("ALTER TABLE questions RENAME TO _questions_old;"))
                    conn.execute(text("""
                        CREATE TABLE questions (
                            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                            exam_body VARCHAR(32) DEFAULT 'JAMB' NOT NULL,
                            subject_id INTEGER NOT NULL,
                            year INTEGER NOT NULL,
                            question_number INTEGER NOT NULL,
                            text TEXT NOT NULL,
                            explanation TEXT,
                            source_reference VARCHAR(255),
                            source_page INTEGER,
                            is_active BOOLEAN NOT NULL DEFAULT 1,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                            CONSTRAINT uq_question_exam_year_subject_number UNIQUE (exam_body, subject_id, year, question_number),
                            FOREIGN KEY(subject_id) REFERENCES subjects (id) ON DELETE RESTRICT
                        );
                    """))
                    conn.execute(text("""
                        INSERT INTO questions (id, exam_body, subject_id, year, question_number, text, explanation, source_reference, source_page, is_active, created_at, updated_at)
                        SELECT id, COALESCE(exam_body, 'JAMB'), subject_id, year, question_number, text, explanation, source_reference, source_page, is_active, created_at, updated_at
                        FROM _questions_old;
                    """))
                    conn.execute(text("DROP TABLE _questions_old;"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_question_exam_body ON questions (exam_body);"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_question_exam_year_subject ON questions (exam_body, year, subject_id);"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_question_subject_year ON questions (subject_id, year);"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_question_year ON questions (year);"))
                    conn.execute(text("PRAGMA foreign_keys=on;"))
                    conn.commit()
                    print("Questions table schema successfully upgraded.")

            # Check options table foreign key integrity
            opt_sql_row = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='options'")).fetchone()
            if opt_sql_row and "_questions_old" in opt_sql_row[0]:
                conn.execute(text("PRAGMA foreign_keys=off;"))
                conn.execute(text("ALTER TABLE options RENAME TO _options_old;"))
                conn.execute(text("""
                    CREATE TABLE options (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        question_id INTEGER NOT NULL,
                        label VARCHAR(10) NOT NULL,
                        position INTEGER NOT NULL,
                        text TEXT NOT NULL,
                        is_correct BOOLEAN NOT NULL,
                        CONSTRAINT uq_option_question_label UNIQUE (question_id, label),
                        CONSTRAINT uq_option_question_position UNIQUE (question_id, position),
                        FOREIGN KEY(question_id) REFERENCES questions (id) ON DELETE CASCADE
                    );
                """))
                conn.execute(text("""
                    INSERT INTO options (id, question_id, label, position, text, is_correct)
                    SELECT id, question_id, label, position, text, is_correct
                    FROM _options_old;
                """))
                conn.execute(text("DROP TABLE _options_old;"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_option_question_label ON options (question_id, label);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_option_question_id ON options (question_id);"))
                conn.execute(text("PRAGMA foreign_keys=on;"))
                conn.commit()
                print("Repaired options table foreign key reference.")

            # Check question_images table foreign key integrity
            qimg_sql_row = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='question_images'")).fetchone()
            if qimg_sql_row and "_questions_old" in qimg_sql_row[0]:
                conn.execute(text("PRAGMA foreign_keys=off;"))
                conn.execute(text("ALTER TABLE question_images RENAME TO _question_images_old;"))
                conn.execute(text("""
                    CREATE TABLE question_images (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        question_id INTEGER NOT NULL,
                        image_path VARCHAR(500) NOT NULL,
                        position INTEGER NOT NULL,
                        image_type VARCHAR(50) NOT NULL,
                        source_page INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        CONSTRAINT uq_question_image_position UNIQUE (question_id, position),
                        FOREIGN KEY(question_id) REFERENCES questions (id) ON DELETE CASCADE
                    );
                """))
                conn.execute(text("""
                    INSERT INTO question_images (id, question_id, image_path, position, image_type, source_page, created_at)
                    SELECT id, question_id, image_path, position, image_type, source_page, created_at
                    FROM _question_images_old;
                """))
                conn.execute(text("DROP TABLE _question_images_old;"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_question_images_question_id ON question_images (question_id);"))
                conn.execute(text("PRAGMA foreign_keys=on;"))
                conn.commit()
                print("Repaired question_images table foreign key reference.")

            # Check exam_questions table foreign key integrity
            eq_sql_row = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='exam_questions'")).fetchone()
            if eq_sql_row and "_questions_old" in eq_sql_row[0]:
                conn.execute(text("PRAGMA foreign_keys=off;"))
                conn.execute(text("ALTER TABLE exam_questions RENAME TO _exam_questions_old;"))
                conn.execute(text("""
                    CREATE TABLE exam_questions (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        exam_subject_id INTEGER NOT NULL,
                        question_id INTEGER NOT NULL,
                        position INTEGER NOT NULL,
                        CONSTRAINT uq_exam_subject_question UNIQUE (exam_subject_id, question_id),
                        CONSTRAINT uq_exam_subject_question_position UNIQUE (exam_subject_id, position),
                        CONSTRAINT ck_exam_question_position CHECK (position > 0),
                        FOREIGN KEY(exam_subject_id) REFERENCES exam_subjects (id) ON DELETE CASCADE,
                        FOREIGN KEY(question_id) REFERENCES questions (id) ON DELETE RESTRICT
                    );
                """))
                conn.execute(text("""
                    INSERT INTO exam_questions (id, exam_subject_id, question_id, position)
                    SELECT id, exam_subject_id, question_id, position
                    FROM _exam_questions_old;
                """))
                conn.execute(text("DROP TABLE _exam_questions_old;"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_exam_question_subject_id ON exam_questions (exam_subject_id);"))
            # Check student_answers table foreign key integrity
            sa_sql_row = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='student_answers'")).fetchone()
            if sa_sql_row and ("_exam_questions_old" in sa_sql_row[0] or "_options_old" in sa_sql_row[0]):
                conn.execute(text("PRAGMA foreign_keys=off;"))
                conn.execute(text("ALTER TABLE student_answers RENAME TO _student_answers_old;"))
                conn.execute(text("""
                    CREATE TABLE student_answers (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        exam_question_id INTEGER NOT NULL,
                        selected_option_id INTEGER,
                        answered_at DATETIME,
                        UNIQUE (exam_question_id),
                        FOREIGN KEY(exam_question_id) REFERENCES exam_questions (id) ON DELETE CASCADE,
                        FOREIGN KEY(selected_option_id) REFERENCES options (id) ON DELETE SET NULL
                    );
                """))
                conn.execute(text("""
                    INSERT INTO student_answers (id, exam_question_id, selected_option_id, answered_at)
                    SELECT id, exam_question_id, selected_option_id, answered_at
                    FROM _student_answers_old;
                """))
                conn.execute(text("DROP TABLE _student_answers_old;"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_student_answer_exam_question_id ON student_answers (exam_question_id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_student_answer_selected_option_id ON student_answers (selected_option_id);"))
                conn.execute(text("PRAGMA foreign_keys=on;"))
                conn.commit()
                print("Repaired student_answers table foreign key reference.")

            # Check exam_sessions table
            e_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(exam_sessions)")).fetchall()]
            if "exam_body" not in e_cols and len(e_cols) > 0:
                conn.execute(text("ALTER TABLE exam_sessions ADD COLUMN exam_body VARCHAR(50) DEFAULT 'JAMB' NOT NULL"))
                conn.commit()
                print("Migrated exam_sessions table: added exam_body column.")
    except Exception as m_err:
        print("Schema migration check:", m_err)

    # 2. Ensure reports directory exists for generated PDF transcripts
    reports_dir = DATA_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 3. Seed default settings and initial admin account on fresh installation
    try:
        from sqlalchemy import select
        from app.services.settings_service import SettingsService
        from app.services.auth_service import AuthService

        with SessionLocal() as db:
            # Ensure default settings row exists
            settings_service = SettingsService(db)
            settings_service.get_settings()

            # Ensure default admin exists
            admin_user = db.scalar(
                select(models.User).where(models.User.role == "admin").limit(1)
            )
            if not admin_user:
                auth_service = AuthService(db)
                auth_service.create_user(
                    username="admin",
                    password="admin",
                    full_name="Administrator",
                    role="admin",
                )
                db.commit()
                print("Initialized default admin user (admin / admin)")
    except Exception as err:
        print("Database bootstrap notice:", err)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI to get database sessions.

    Yields a database session and ensures it's closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
