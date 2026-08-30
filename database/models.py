from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database.database import Base


# ============================================================
# APP SETTINGS
# ============================================================


class AppSettings(Base):
    """
    Global application settings for the school/institution.
    These settings apply to all users and are configured by admins.
    """

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    school_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="Mock CBT Examination",
    )

    school_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    school_logo_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Path to school logo image (base64 or file path)",
    )

    theme: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="light",
        comment="Theme: light or dark",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ============================================================
# USER
# ============================================================


class User(Base):
    """
    A user of the CBT system with role-based access control.
    
    Roles:
        - admin: Full access to all features including user management
        - student: Can only take exams and view their own results
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    username: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )

    password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="student",
    )

    # Student-specific fields
    student_class: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    admission_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    exam_sessions: Mapped[list["ExamSession"]] = relationship(
        back_populates="user",
    )


# ============================================================
# SUBJECT
# ============================================================


class Subject(Base):
    """
    A subject contained in the CBT question bank.

    Examples:
        Mathematics
        English Language
        Chemistry
        Biology
        Physics
    """

    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    code: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        unique=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    questions: Mapped[list["Question"]] = relationship(
        back_populates="subject",
    )

    exam_subjects: Mapped[list["ExamSubject"]] = relationship(
        back_populates="subject",
    )


# ============================================================
# QUESTION
# ============================================================

class Question(Base):
    """
    A past examination question.

    The same subject can have questions from many years.

    Example:

        Mathematics
        2002
        Question 14
    """

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    exam_body: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="JAMB",
        server_default="JAMB",
    )

    subject_id: Mapped[int] = mapped_column(
        ForeignKey(
            "subjects.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    question_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Optional prepared explanation.
    explanation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # --------------------------------------------------------
    # Source information
    # --------------------------------------------------------

    source_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    source_page: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # --------------------------------------------------------
    # Optional image
    # --------------------------------------------------------

    images: Mapped[list["QuestionImage"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionImage.position",
    )

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    subject: Mapped["Subject"] = relationship(
        back_populates="questions",
    )

    options: Mapped[list["Option"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="Option.position",
    )

    exam_questions: Mapped[list["ExamQuestion"]] = relationship(
        back_populates="question",
    )

    # --------------------------------------------------------
    # Constraints / indexes
    # --------------------------------------------------------

    __table_args__ = (
        UniqueConstraint(
            "exam_body",
            "subject_id",
            "year",
            "question_number",
            name="uq_question_exam_year_subject_number",
        ),
        CheckConstraint(
            "year >= 1900 AND year <= 2100",
            name="ck_question_year",
        ),
        CheckConstraint(
            "question_number > 0",
            name="ck_question_number_positive",
        ),
        Index(
            "ix_questions_exam_year_subject",
            "exam_body",
            "year",
            "subject_id",
        ),
        Index(
            "ix_questions_year_subject",
            "year",
            "subject_id",
        ),
        Index(
            "ix_questions_subject",
            "subject_id",
        ),
        Index(
            "ix_questions_exam_body",
            "exam_body",
        ),
    )


 
# ============================================================
# QUESTION IMAGE
# ============================================================


class QuestionImage(Base):
    """
    An image/diagram belonging to a question.

    The actual image file is stored on disk.
    The database stores the path and metadata.
    """

    __tablename__ = "question_images"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey(
            "questions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    image_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    image_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="diagram",
    )

    source_page: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    question: Mapped["Question"] = relationship(
        back_populates="images",
    )

    __table_args__ = (
        UniqueConstraint(
            "question_id",
            "position",
            name="uq_question_image_position",
        ),
        Index(
            "ix_question_images_question",
            "question_id",
        ),
    )

# ============================================================
# OPTION
# ============================================================


class Option(Base):
    """
    An answer option belonging to a question.

    Example:

        A. ...
        B. ...
        C. ...
        D. ...
    """

    __tablename__ = "options"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey(
            "questions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    label: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
    )

    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    is_correct: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # --------------------------------------------------------
    # Relationship
    # --------------------------------------------------------

    question: Mapped["Question"] = relationship(
        back_populates="options",
    )

    # --------------------------------------------------------
    # Constraints
    # --------------------------------------------------------

    __table_args__ = (
        UniqueConstraint(
            "question_id",
            "label",
            name="uq_option_question_label",
        ),
        UniqueConstraint(
            "question_id",
            "position",
            name="uq_option_question_position",
        ),
        CheckConstraint(
            "position > 0",
            name="ck_option_position_positive",
        ),
        Index(
            "ix_options_question",
            "question_id",
        ),
    )


# ============================================================
# EXAM SESSION
# ============================================================


class ExamSession(Base):
    """
    One complete mock examination attempt.

    The entire examination uses ONE master clock.
    """

    __tablename__ = "exam_sessions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    exam_body: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="JAMB",
        server_default="JAMB",
    )

    year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    student_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    # --------------------------------------------------------
    # MASTER EXAM CLOCK
    # --------------------------------------------------------

    duration_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    user: Mapped["User"] = relationship(
        back_populates="exam_sessions",
    )

    subjects: Mapped[list["ExamSubject"]] = relationship(
        back_populates="exam_session",
        cascade="all, delete-orphan",
        order_by="ExamSubject.position",
    )

    # --------------------------------------------------------
    # Constraints
    # --------------------------------------------------------

    __table_args__ = (
        CheckConstraint(
            "duration_minutes > 0",
            name="ck_exam_session_duration",
        ),
        CheckConstraint(
            "year >= 1900 AND year <= 2100",
            name="ck_exam_session_year",
        ),
    )
# ============================================================
# EXAM SUBJECT
# ============================================================


class ExamSubject(Base):
    """
    A subject selected for a particular exam session.

    This model handles subject navigation and progress.

    It does NOT have its own timer.
    """

    __tablename__ = "exam_subjects"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    exam_session_id: Mapped[int] = mapped_column(
        ForeignKey(
            "exam_sessions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    subject_id: Mapped[int] = mapped_column(
        ForeignKey(
            "subjects.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # --------------------------------------------------------
    # Current UI position
    # --------------------------------------------------------

    current_question_position: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    exam_session: Mapped["ExamSession"] = relationship(
        back_populates="subjects",
    )

    subject: Mapped["Subject"] = relationship(
        back_populates="exam_subjects",
    )

    questions: Mapped[list["ExamQuestion"]] = relationship(
        back_populates="exam_subject",
        cascade="all, delete-orphan",
        order_by="ExamQuestion.position",
    )

    # --------------------------------------------------------
    # Constraints
    # --------------------------------------------------------

    __table_args__ = (
        UniqueConstraint(
            "exam_session_id",
            "subject_id",
            name="uq_exam_session_subject",
        ),
        UniqueConstraint(
            "exam_session_id",
            "position",
            name="uq_exam_session_subject_position",
        ),
        CheckConstraint(
            "position > 0",
            name="ck_exam_subject_position",
        ),
        CheckConstraint(
            "current_question_position >= 0",
            name="ck_exam_subject_question_position",
        ),
    )


# ============================================================
# EXAM QUESTION
# ============================================================


class ExamQuestion(Base):
    """
    A question assigned to a particular exam session.

    We create a record here rather than simply querying
    Question every time.

    This lets us preserve the exact questions selected for
    the student's exam.
    """

    __tablename__ = "exam_questions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    exam_subject_id: Mapped[int] = mapped_column(
        ForeignKey(
            "exam_subjects.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey(
            "questions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    # Question position inside this subject's exam.
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # --------------------------------------------------------
    # Relationship
    # --------------------------------------------------------

    exam_subject: Mapped["ExamSubject"] = relationship(
        back_populates="questions",
    )

    question: Mapped["Question"] = relationship(
        back_populates="exam_questions",
    )

    answer: Mapped["StudentAnswer | None"] = relationship(
        back_populates="exam_question",
        cascade="all, delete-orphan",
        uselist=False,
    )

    # --------------------------------------------------------
    # Constraints
    # --------------------------------------------------------

    __table_args__ = (
        UniqueConstraint(
            "exam_subject_id",
            "question_id",
            name="uq_exam_subject_question",
        ),
        UniqueConstraint(
            "exam_subject_id",
            "position",
            name="uq_exam_subject_question_position",
        ),
        CheckConstraint(
            "position > 0",
            name="ck_exam_question_position",
        ),
        Index(
            "ix_exam_questions_exam_subject",
            "exam_subject_id",
        ),
    )


# ============================================================
# STUDENT ANSWER
# ============================================================


class StudentAnswer(Base):
    """
    Stores the student's answer to an exam question.

    This is what gives us answer persistence.

    If the student answers Mathematics question 14 and then
    switches to Chemistry, the answer remains stored here.
    """

    __tablename__ = "student_answers"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    exam_question_id: Mapped[int] = mapped_column(
        ForeignKey(
            "exam_questions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
    )

    # The selected Option ID.
    #
    # NULL means the student has not answered the question.
    selected_option_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "options.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    exam_question: Mapped["ExamQuestion"] = relationship(
        back_populates="answer",
    )

    selected_option: Mapped["Option | None"] = relationship()

    # --------------------------------------------------------
    # Index
    # --------------------------------------------------------

    __table_args__ = (
        Index(
            "ix_student_answers_selected_option",
            "selected_option_id",
        ),
    )


# ============================================================
# LICENSING MODELS
# ============================================================


class ProductLicense(Base):
    """
    A product license key with activation credits.
    
    Tracks product keys, their metadata, and remaining activation credits.
    """

    __tablename__ = "product_licenses"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    product_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )

    product_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # Number of activation credits available
    credits: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
    )

    # License expiry date
    expiry_date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    # Additional metadata (JSON encoded)
    license_metadata: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Status tracking
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    activations: Mapped[list["LicenseActivation"]] = relationship(
        back_populates="license",
        cascade="all, delete-orphan",
    )

    # --------------------------------------------------------
    # Constraints
    # --------------------------------------------------------

    __table_args__ = (
        CheckConstraint(
            "credits >= 0",
            name="ck_product_license_credits_non_negative",
        ),
        Index(
            "ix_product_licenses_product_key",
            "product_key",
        ),
    )


class LicenseActivation(Base):
    """
    Records of license activations on specific machines.
    
    Tracks when and where a license was activated using machine fingerprinting.
    """

    __tablename__ = "license_activations"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    license_id: Mapped[int] = mapped_column(
        ForeignKey(
            "product_licenses.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    # User information for support and tracking
    user_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    user_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    # Machine fingerprint for this activation
    machine_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    # Additional machine info (optional)
    machine_info: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Activation timestamp (server-side, can't be manipulated)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    # Server-trusted timestamp for expiry calculations
    server_timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    # When this activation was last validated
    last_validated: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    # Is this activation currently valid
    is_valid: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Deactivation info (if revoked)
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    deactivation_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    license: Mapped["ProductLicense"] = relationship(
        back_populates="activations",
    )

    # --------------------------------------------------------
    # Constraints
    # --------------------------------------------------------

    __table_args__ = (
        Index(
            "ix_license_activations_license_id",
            "license_id",
        ),
        Index(
            "ix_license_activations_machine_fingerprint",
            "machine_fingerprint",
        ),
        UniqueConstraint(
            "license_id",
            "machine_fingerprint",
            name="uq_license_machine",
        ),
    )
