

from database.database import engine, Base

# IMPORTANT:
# Import models so SQLAlchemy knows about all tables.
from database.models import (
    Subject,
    Question,
    Option,
    QuestionImage,
    ExamSession,
    ExamSubject,
    ExamQuestion,
    StudentAnswer,
    ProductLicense,
    LicenseActivation,
)

Base.metadata.create_all(bind=engine)

print("Database tables created successfully.")
