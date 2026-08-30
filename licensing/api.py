from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import ProductLicense, LicenseActivation
from app.services.licensing.machine_fingerprint import MachineFingerprint
from app.services.licensing.crypto import LicenseCrypto


router = APIRouter(prefix="/api/license", tags=["licensing"])


# ============================================================
# Request/Response Models
# ============================================================


class ActivationRequest(BaseModel):
    """Request model for license activation."""
    
    product_key: str = Field(..., description="The product key to activate")
    machine_fingerprint: str = Field(..., description="Machine fingerprint hash")
    user_email: str = Field(..., description="User email for support and tracking")
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
    license_data: Dict[str, Any] | None = None
    remaining_credits: int | None = None


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
    
    This endpoint:
    1. Verifies the product key signature
    2. Checks if license exists and has credits
    3. Checks if this machine already has an activation
    4. Creates a new activation or reactivates existing one
    5. Consumes one credit for new activations
    """
    try:
        # Load public key for verification (in production, load from secure config)
        # For now, we'll create a temporary crypto instance
        # In production, you should have the public key stored securely
        public_key_pem = _get_public_key()
        crypto = LicenseCrypto(public_key_pem=public_key_pem)
        
        # Verify and decode product key
        try:
            license_data = crypto.verify_product_key(request.product_key)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid product key: {str(e)}")
        
        # Check if license exists in database
        license_record = db.query(ProductLicense).filter(
            ProductLicense.product_key == request.product_key
        ).first()
        
        if not license_record:
            raise HTTPException(status_code=404, detail="License not found in database")
        
        # Check if license is active
        if not license_record.is_active:
            raise HTTPException(status_code=403, detail="License has been deactivated")
        
        # Check if license has expired (using server time, not client time)
        # This prevents time manipulation attacks
        server_now = datetime.now()
        if license_record.expiry_date < server_now:
            raise HTTPException(
                status_code=403, 
                detail=f"License has expired on {license_record.expiry_date.isoformat()}"
            )
        
        # Additional time manipulation protection:
        # If the license was activated more than (expiry_days + 30) days ago, it's suspicious
        days_since_creation = (server_now - license_record.created_at).days
        if days_since_creation > 400:  # ~1 year + buffer
            raise HTTPException(
                status_code=403,
                detail="License validity period exceeded. Please contact support."
            )
        
        # Check if license has credits
        if license_record.credits <= 0:
            raise HTTPException(status_code=403, detail="No activation credits remaining")
        
        # Check if this machine already has an activation
        existing_activation = db.query(LicenseActivation).filter(
            LicenseActivation.license_id == license_record.id,
            LicenseActivation.machine_fingerprint == request.machine_fingerprint,
            LicenseActivation.is_valid == True
        ).first()
        
        if existing_activation:
            # Reactivate existing activation (no credit consumed)
            existing_activation.last_validated = datetime.now()
            existing_activation.is_valid = True
            existing_activation.deactivated_at = None
            existing_activation.deactivation_reason = None
            db.commit()
            
            return ActivationResponse(
                success=True,
                message="License reactivated successfully on same machine",
                license_data=license_data,
                remaining_credits=license_record.credits,
                expiry_date=license_record.expiry_date.isoformat(),
                activation_id=existing_activation.id
            )
        
        # Check if this key has been activated on too many different machines
        activation_count = db.query(LicenseActivation).filter(
            LicenseActivation.license_id == license_record.id,
            LicenseActivation.is_valid == True
        ).count()
        
        if activation_count >= 2:  # Allow activation on up to 2 different machines
            raise HTTPException(
                status_code=403, 
                detail=f"License already activated on {activation_count} different machines. Maximum allowed: 2"
            )
        
        # Create new activation
        new_activation = LicenseActivation(
            license_id=license_record.id,
            user_email=request.user_email,
            user_name=request.user_name,
            machine_fingerprint=request.machine_fingerprint,
            machine_info=str(request.machine_info),
            activated_at=datetime.now(),
            server_timestamp=datetime.now(),  # Server-trusted timestamp
            last_validated=datetime.now(),
            is_valid=True
        )
        
        # Consume one credit
        license_record.credits -= 1
        
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
    """
    Validate an existing license activation.
    
    This endpoint:
    1. Verifies the product key signature
    2. Checks if the activation exists and is valid
    3. Updates last_validated timestamp
    4. Returns license status
    5. Uses server time for all expiry checks (prevents time manipulation)
    """
    try:
        # Load public key for verification
        public_key_pem = _get_public_key()
        crypto = LicenseCrypto(public_key_pem=public_key_pem)
        
        # Verify and decode product key
        try:
            license_data = crypto.verify_product_key(request.product_key)
        except ValueError as e:
            return ValidationResponse(
                success=False,
                message=f"Invalid product key: {str(e)}",
                is_valid=False
            )
        
        # Get license record
        license_record = db.query(ProductLicense).filter(
            ProductLicense.product_key == request.product_key
        ).first()
        
        if not license_record:
            return ValidationResponse(
                success=False,
                message="License not found",
                is_valid=False
            )
        
        # Get activation record
        activation = db.query(LicenseActivation).filter(
            LicenseActivation.id == request.activation_id,
            LicenseActivation.license_id == license_record.id
        ).first()
        
        if not activation:
            return ValidationResponse(
                success=False,
                message="Activation not found",
                is_valid=False
            )
        
        # Check if activation is valid
        if not activation.is_valid:
            return ValidationResponse(
                success=False,
                message="Activation has been deactivated",
                is_valid=False
            )
        
        # Check if machine fingerprint matches
        if activation.machine_fingerprint != request.machine_fingerprint:
            return ValidationResponse(
                success=False,
                message="Machine fingerprint mismatch",
                is_valid=False
            )
        
        # Check if license is still active
        if not license_record.is_active:
            return ValidationResponse(
                success=False,
                message="License has been deactivated",
                is_valid=False
            )
        
        # Check if license has expired (using server time only)
        server_now = datetime.now()
        if license_record.expiry_date < server_now:
            return ValidationResponse(
                success=False,
                message=f"License has expired on {license_record.expiry_date.isoformat()}",
                is_valid=False
            )
        
        # Time manipulation protection: Check if server_timestamp shows excessive time
        # Calculate actual elapsed time based on server timestamps
        elapsed_days = (server_now - activation.server_timestamp).days
        if elapsed_days > 400:  # More than ~1 year + buffer
            return ValidationResponse(
                success=False,
                message="License validity period exceeded. Please contact support.",
                is_valid=False
            )
        
        # Update last validated timestamp (server time)
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
    """
    Deactivate a license activation.
    
    This endpoint:
    1. Verifies the product key
    2. Deactivates the specified activation
    3. Restores one credit to the license
    """
    try:
        # Get license record
        license_record = db.query(ProductLicense).filter(
            ProductLicense.product_key == request.product_key
        ).first()
        
        if not license_record:
            raise HTTPException(status_code=404, detail="License not found")
        
        # Get activation record
        activation = db.query(LicenseActivation).filter(
            LicenseActivation.id == request.activation_id,
            LicenseActivation.license_id == license_record.id
        ).first()
        
        if not activation:
            raise HTTPException(status_code=404, detail="Activation not found")
        
        if not activation.is_valid:
            raise HTTPException(status_code=400, detail="Activation is already deactivated")
        
        # Deactivate the activation
        activation.is_valid = False
        activation.deactivated_at = datetime.now()
        activation.deactivation_reason = request.reason
        
        # Restore one credit
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


# ============================================================
# Helper Functions
# ============================================================


def _get_public_key() -> str:
    """
    Get the public key for product key verification.
    
    Loads from environment variable or falls back to embedded key.
    """
    import os
    
    # Try environment variable first
    public_key = os.getenv("LICENSE_PUBLIC_KEY")
    if public_key:
        return public_key
    
    # Try to load from file in the licensing directory
    key_file = Path(__file__).parent / "public_key.pem"
    if key_file.exists():
        return key_file.read_text()
        
    # Try to load from project root
    root_key_file = Path(__file__).resolve().parent.parent.parent.parent / "license_public_key.pem"
    if root_key_file.exists():
        return root_key_file.read_text()
    
    # Embedded fallback public key (for client distribution)
    # In production, this should be your actual public key
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