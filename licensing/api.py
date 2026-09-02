import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import ProductLicense, LicenseActivation
from app.services.licensing.crypto import LicenseCrypto


router = APIRouter(prefix="/api/license", tags=["licensing"])


# ============================================================
# Request/Response Models
# ============================================================


class ActivationRequest(BaseModel):
    """Request model for license activation."""
    product_key: str = Field(..., description="The product key to activate")
    machine_fingerprint: str = Field(..., description="Machine fingerprint hash")
    user_email: str = Field(default="", description="User email for support and tracking")
    user_name: str = Field(default="", description="User name for support")
    machine_info: Dict[str, Any] = Field(default_factory=dict, description="Additional machine info")


class ActivationResponse(BaseModel):
    """Response model for successful activation."""
    success: bool
    message: str
    license_data: Dict[str, Any]
    remaining_credits: int
    expiry_date: str
    activation_id: int


class ValidationRequest(BaseModel):
    """Request model for license validation."""
    product_key: str = Field(..., description="The product key to validate")
    machine_fingerprint: str = Field(..., description="Current machine fingerprint")
    activation_id: int = Field(..., description="Previous activation ID")


class ValidationResponse(BaseModel):
    """Response model for license validation."""
    success: bool
    message: str
    is_valid: bool
    license_data: Optional[Dict[str, Any]] = None
    remaining_credits: Optional[int] = None


class DeactivationRequest(BaseModel):
    """Request model for license deactivation."""
    product_key: str = Field(..., description="The product key to deactivate")
    activation_id: int = Field(..., description="Activation ID to deactivate")
    reason: str = Field(default="User requested deactivation", description="Reason for deactivation")


class DeactivationResponse(BaseModel):
    """Response model for deactivation."""
    success: bool
    message: str
    credits_restored: int


class RegisterLicenseRequest(BaseModel):
    """Request model for registering a new license key."""
    product_key: str = Field(..., description="The product key to register")
    product_name: str = Field(default="LLS CBT", description="Product name")
    version: str = Field(default="1.0.0", description="Product version")
    credits: int = Field(default=2, description="Number of activation credits")
    expiry_days: int = Field(default=365, description="Days until expiry")
    admin_secret: str = Field(default="", description="Admin secret for authorization")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RegisterLicenseResponse(BaseModel):
    """Response model for license registration."""
    success: bool
    message: str
    license_id: Optional[int] = None


# ============================================================
# Helper Functions
# ============================================================


def _clean_product_key(product_key: str) -> str:
    """Strip dashes, whitespace, and ensure proper Base64 padding."""
    clean = product_key.strip().replace("-", "").replace(" ", "").replace("\r", "").replace("\n", "")
    missing = len(clean) % 4
    if missing:
        clean += "=" * (4 - missing)
    return clean


def _get_public_key() -> str:
    """Get the RSA public key for product key verification."""
    public_key = os.getenv("LICENSE_PUBLIC_KEY")
    if public_key:
        return public_key

    key_file = Path(__file__).parent / "public_key.pem"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8")

    root_key_file = Path(__file__).resolve().parent.parent.parent.parent / "license_public_key.pem"
    if root_key_file.exists():
        return root_key_file.read_text(encoding="utf-8")

    embedded_key = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwq/XMIVF9N3D6QKfnac/
00ku5pidy2/a14YSRiJ1StEEusplVAjVgJo1C85uQm5aBTItDrPu6x0C79BzZF9w
IW7NS1FjxmgoF1aNUI0B0WP2RUoN5CHotw0j36+1zP047AKT6ghAzJq5L02w7QAL
KK/T4wJzqncRA6czhznKhcW0VBisIuplaXlvwS/k6Gx/bZP8mesYawFM8kjZCTeO
FJuUlYcnlGgKQ3oiemc25OS8uJO51UtDcsggl185TQ1EIyMw07uxO14t6ppgkkBd
wF058X6/y5WAgZc/EKd4dlb8YfLy8SJIGOWEudF6Ij4m8/KVvAwHNkA+JnqSDCVv
EwIDAQAB
-----END PUBLIC KEY-----"""
    return embedded_key


# ============================================================
# API Endpoints
# ============================================================


@router.post("/activate", response_model=ActivationResponse)
async def activate_license(
    request: ActivationRequest,
    db: Session = Depends(get_db)
):
    """
    Activate a product key on a specific machine.
    
    1. Verifies RSA-2048 cryptographic signature on the product key.
    2. Auto-provisions the license in the server database if valid and not yet stored.
    3. Checks license expiration and activation credits.
    4. Handles machine fingerprint binding and deduction of credits.
    """
    clean_key = _clean_product_key(request.product_key)

    try:
        public_key_pem = _get_public_key()
        crypto = LicenseCrypto(public_key_pem=public_key_pem)

        # Cryptographically verify the product key
        try:
            license_data = crypto.verify_product_key(clean_key)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid product key: {str(e)}")

        # Check if license exists in database
        license_record = db.query(ProductLicense).filter(
            ProductLicense.product_key == clean_key
        ).first()

        # If not present in database, auto-provision from cryptographically verified key data
        if not license_record:
            try:
                expiry_dt = datetime.fromisoformat(license_data["expiry"])
            except Exception:
                expiry_dt = datetime.now() + timedelta(days=365)

            initial_credits = int(license_data.get("credits", 2))
            license_record = ProductLicense(
                product_key=clean_key,
                product_name=license_data.get("product", "LLS CBT"),
                version=license_data.get("version", "1.0.0"),
                credits=initial_credits,
                expiry_date=expiry_dt,
                license_metadata=json.dumps(license_data.get("metadata", {})) if license_data.get("metadata") else None,
                is_active=True
            )
            db.add(license_record)
            db.commit()
            db.refresh(license_record)

        # Check if license is active
        if not license_record.is_active:
            raise HTTPException(status_code=403, detail="License has been deactivated")

        # Check expiration (using server time)
        server_now = datetime.now()
        if license_record.expiry_date < server_now:
            raise HTTPException(
                status_code=403,
                detail=f"License has expired on {license_record.expiry_date.isoformat()}"
            )

        # Check if this machine already has an active activation
        existing_activation = db.query(LicenseActivation).filter(
            LicenseActivation.license_id == license_record.id,
            LicenseActivation.machine_fingerprint == request.machine_fingerprint,
            LicenseActivation.is_valid == True
        ).first()

        if existing_activation:
            existing_activation.last_validated = datetime.now()
            existing_activation.is_valid = True
            existing_activation.deactivated_at = None
            existing_activation.deactivation_reason = None
            db.commit()

            return ActivationResponse(
                success=True,
                message="License reactivated successfully on this machine",
                license_data=license_data,
                remaining_credits=license_record.credits,
                expiry_date=license_record.expiry_date.isoformat(),
                activation_id=existing_activation.id
            )

        # Check allowed machines vs total activations
        max_allowed = int(license_data.get("credits", 2))
        active_machine_count = db.query(LicenseActivation).filter(
            LicenseActivation.license_id == license_record.id,
            LicenseActivation.is_valid == True
        ).count()

        if active_machine_count >= max_allowed:
            raise HTTPException(
                status_code=403,
                detail=f"License already activated on {active_machine_count} machine(s). Maximum allowed: {max_allowed}"
            )

        if license_record.credits <= 0:
            raise HTTPException(status_code=403, detail="No activation credits remaining for this license")

        # Consume one credit for new machine activation
        license_record.credits -= 1

        new_activation = LicenseActivation(
            license_id=license_record.id,
            machine_fingerprint=request.machine_fingerprint,
            user_email=request.user_email,
            user_name=request.user_name,
            machine_info=json.dumps(request.machine_info) if request.machine_info else None,
            is_valid=True
        )

        db.add(new_activation)
        db.commit()
        db.refresh(new_activation)

        return ActivationResponse(
            success=True,
            message="License activated successfully",
            license_data=license_data,
            remaining_credits=license_record.credits,
            expiry_date=license_record.expiry_date.isoformat(),
            activation_id=new_activation.id
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Activation failed: {str(e)}")


@router.post("/validate", response_model=ValidationResponse)
async def validate_license(
    request: ValidationRequest,
    db: Session = Depends(get_db)
):
    """Validate an existing license activation."""
    clean_key = _clean_product_key(request.product_key)

    try:
        public_key_pem = _get_public_key()
        crypto = LicenseCrypto(public_key_pem=public_key_pem)

        try:
            license_data = crypto.verify_product_key(clean_key)
        except ValueError as e:
            return ValidationResponse(
                success=False,
                message=f"Invalid product key: {str(e)}",
                is_valid=False
            )

        license_record = db.query(ProductLicense).filter(
            ProductLicense.product_key == clean_key
        ).first()

        if not license_record or not license_record.is_active:
            return ValidationResponse(
                success=False,
                message="License not found or deactivated",
                is_valid=False
            )

        server_now = datetime.now()
        if license_record.expiry_date < server_now:
            return ValidationResponse(
                success=False,
                message=f"License expired on {license_record.expiry_date.isoformat()}",
                is_valid=False
            )

        activation = db.query(LicenseActivation).filter(
            LicenseActivation.id == request.activation_id,
            LicenseActivation.license_id == license_record.id
        ).first()

        if not activation or not activation.is_valid:
            return ValidationResponse(
                success=False,
                message="Activation record not found or inactive",
                is_valid=False
            )

        if activation.machine_fingerprint != request.machine_fingerprint:
            return ValidationResponse(
                success=False,
                message="Machine fingerprint mismatch",
                is_valid=False
            )

        activation.last_validated = server_now
        db.commit()

        return ValidationResponse(
            success=True,
            message="License is valid",
            is_valid=True,
            license_data=license_data,
            remaining_credits=license_record.credits
        )

    except Exception as e:
        return ValidationResponse(
            success=False,
            message=f"Validation failed: {str(e)}",
            is_valid=False
        )


@router.post("/deactivate", response_model=DeactivationResponse)
async def deactivate_license(
    request: DeactivationRequest,
    db: Session = Depends(get_db)
):
    """Deactivate a license on this machine and restore credit."""
    clean_key = _clean_product_key(request.product_key)

    try:
        license_record = db.query(ProductLicense).filter(
            ProductLicense.product_key == clean_key
        ).first()

        if not license_record:
            raise HTTPException(status_code=404, detail="License not found")

        activation = db.query(LicenseActivation).filter(
            LicenseActivation.id == request.activation_id,
            LicenseActivation.license_id == license_record.id
        ).first()

        if not activation:
            raise HTTPException(status_code=404, detail="Activation not found")

        if not activation.is_valid:
            raise HTTPException(status_code=400, detail="Activation is already deactivated")

        activation.is_valid = False
        activation.deactivated_at = datetime.now()
        activation.deactivation_reason = request.reason

        license_record.credits += 1
        db.commit()

        return DeactivationResponse(
            success=True,
            message="License deactivated successfully",
            credits_restored=1
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Deactivation failed: {str(e)}")


@router.post("/register", response_model=RegisterLicenseResponse)
async def register_license(
    request: RegisterLicenseRequest,
    db: Session = Depends(get_db)
):
    """Admin endpoint to pre-register a product key."""
    clean_key = _clean_product_key(request.product_key)

    expected_secret = os.getenv("LICENSE_ADMIN_SECRET", "")
    if expected_secret and request.admin_secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    try:
        public_key_pem = _get_public_key()
        crypto = LicenseCrypto(public_key_pem=public_key_pem)
        license_data = crypto.verify_product_key(clean_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid product key signature: {str(e)}")

    existing = db.query(ProductLicense).filter(
        ProductLicense.product_key == clean_key
    ).first()

    if existing:
        return RegisterLicenseResponse(
            success=True,
            message="License already registered",
            license_id=existing.id
        )

    try:
        try:
            expiry_dt = datetime.fromisoformat(license_data.get("expiry", ""))
        except Exception:
            expiry_dt = datetime.now() + timedelta(days=request.expiry_days)

        license_record = ProductLicense(
            product_key=clean_key,
            product_name=request.product_name,
            version=request.version,
            credits=request.credits,
            expiry_date=expiry_dt,
            license_metadata=json.dumps(request.metadata) if request.metadata else None,
            is_active=True
        )
        db.add(license_record)
        db.commit()
        db.refresh(license_record)

        return RegisterLicenseResponse(
            success=True,
            message="License registered successfully",
            license_id=license_record.id
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")
