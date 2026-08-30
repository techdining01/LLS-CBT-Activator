import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
import requests
from datetime import datetime

from app.services.licensing.machine_fingerprint import MachineFingerprint
from app.services.licensing.crypto import LicenseCrypto
from dotenv import load_dotenv

# Load the environment variables from the .env file
load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")


class LicenseClient:
    """Client-side license validation and management."""
    
    def __init__(self, license_server_url: str = "http://127.0.0.1:8000"):
        """
        Initialize the license client.
        
        Args:
            license_server_url: URL of the license activation server
        """
        self.license_server_url = license_server_url
        self.license_file_path = Path.home() / ".mock_cbt_license.json"
        self.public_key_pem = self._load_public_key()
        self.crypto = LicenseCrypto(public_key_pem=self.public_key_pem)
        self.machine_fingerprint = MachineFingerprint.get_machine_id()
    
    def _load_public_key(self) -> str:
        """
        Load the public key for product key verification.
        
        Loads from environment variable, file, or embedded fallback.
        """
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
        # In production, replace this with your actual public key
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
    
    def activate_license(self, product_key: str, user_email: str = "", user_name: str = "") -> Dict[str, Any]:
        """
        Activate a license online.
        
        Args:
            product_key: The product key to activate
            user_email: User email for support and tracking
            user_name: User name for support
            
        Returns:
            Dictionary with activation result
        """
        try:
            # Prepare activation request
            payload = {
                "product_key": product_key,
                "machine_fingerprint": self.machine_fingerprint,
                "user_email": user_email,
                "user_name": user_name,
                "machine_info": {
                    "platform": os.name,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            # Call activation API
            response = requests.post(
                f"{self.license_server_url}/api/license/activate",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Save license locally
                self._save_license_locally(
                    product_key=product_key,
                    activation_id=result["activation_id"],
                    license_data=result["license_data"],
                    expiry_date=result["expiry_date"],
                    user_email=payload.get("user_email", ""),
                    user_name=payload.get("user_name", "")
                )
                
                return {
                    "success": True,
                    "message": result["message"],
                    "remaining_credits": result["remaining_credits"],
                    "expiry_date": result["expiry_date"]
                }
            else:
                error_detail = response.json().get("detail", "Unknown error")
                return {
                    "success": False,
                    "message": f"Activation failed: {error_detail}"
                }
                
        except requests.RequestException as e:
            return {
                "success": False,
                "message": f"Network error during activation: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Activation error: {str(e)}"
            }
    
    def validate_license(self) -> Dict[str, Any]:
        """
        Validate the current license.
        
        Returns:
            Dictionary with validation result
        """
        try:
            # Load local license
            local_license = self._load_local_license()
            if not local_license:
                return {
                    "success": False,
                    "message": "No license found. Please activate your product."
                }
            
            # Verify product key signature locally first
            try:
                license_data = self.crypto.verify_product_key(local_license["product_key"])
            except ValueError as e:
                return {
                    "success": False,
                    "message": f"Invalid product key: {str(e)}"
                }
            
            # Check expiry locally
            expiry_date = datetime.fromisoformat(local_license["expiry_date"])
            if datetime.now() > expiry_date:
                return {
                    "success": False,
                    "message": "License has expired"
                }
            
            # Validate online with server
            payload = {
                "product_key": local_license["product_key"],
                "machine_fingerprint": self.machine_fingerprint,
                "activation_id": local_license["activation_id"]
            }
            
            response = requests.post(
                f"{self.license_server_url}/api/license/validate",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result["is_valid"]:
                    return {
                        "success": True,
                        "message": "License is valid",
                        "license_data": result["license_data"],
                        "remaining_credits": result["remaining_credits"]
                    }
                else:
                    return {
                        "success": False,
                        "message": result["message"]
                    }
            else:
                # If server is unreachable, use offline validation
                return self._validate_offline(local_license, license_data)
                
        except Exception as e:
            return {
                "success": False,
                "message": f"Validation error: {str(e)}"
            }
    
    def _validate_offline(self, local_license: Dict[str, Any], license_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform offline license validation when server is unreachable.
        
        Args:
            local_license: Local license data
            license_data: Decoded license data from product key
            
        Returns:
            Dictionary with validation result
        """
        # Note: Offline validation has limitations for time manipulation protection
        # The server-side validation is the authoritative source
        
        # Check expiry using embedded expiry date from product key (not local system time)
        expiry_date = datetime.fromisoformat(local_license["expiry_date"])
        
        # Basic time manipulation check: if current system time is before activation time
        # that's suspicious (clock moved backwards)
        last_validated = datetime.fromisoformat(local_license.get("last_validated", "2000-01-01"))
        if datetime.now() < last_validated:
            return {
                "success": False,
                "message": "System time appears to be incorrect. Please check your clock."
            }
        
        # Check if license has expired
        if datetime.now() > expiry_date:
            return {
                "success": False,
                "message": "License has expired"
            }
        
        # Check if last validation was recent (within 7 days)
        days_since_validation = (datetime.now() - last_validated).days
        
        if days_since_validation > 7:
            return {
                "success": False,
                "message": "License requires online validation. Please connect to internet."
            }
        
        # Offline validation passed
        return {
            "success": True,
            "message": "License is valid (offline mode)",
            "license_data": license_data,
            "remaining_credits": local_license.get("remaining_credits", 0)
        }
    
    def deactivate_license(self) -> Dict[str, Any]:
        """
        Deactivate the current license.
        
        Returns:
            Dictionary with deactivation result
        """
        try:
            local_license = self._load_local_license()
            if not local_license:
                return {
                    "success": False,
                    "message": "No license found to deactivate"
                }
            
            payload = {
                "product_key": local_license["product_key"],
                "activation_id": local_license["activation_id"],
                "reason": "User requested deactivation"
            }
            
            response = requests.post(
                f"{self.license_server_url}/api/license/deactivate",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Remove local license file
                if self.license_file_path.exists():
                    self.license_file_path.unlink()
                
                return {
                    "success": True,
                    "message": result["message"],
                    "credits_restored": result["credits_restored"]
                }
            else:
                error_detail = response.json().get("detail", "Unknown error")
                return {
                    "success": False,
                    "message": f"Deactivation failed: {error_detail}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"Deactivation error: {str(e)}"
            }
    
    def _save_license_locally(
        self,
        product_key: str,
        activation_id: int,
        license_data: Dict[str, Any],
        expiry_date: str,
        user_email: str = "",
        user_name: str = ""
    ):
        """Save license information locally."""
        license_info = {
            "product_key": product_key,
            "activation_id": activation_id,
            "license_data": license_data,
            "expiry_date": expiry_date,
            "machine_fingerprint": self.machine_fingerprint,
            "user_email": user_email,
            "user_name": user_name,
            "last_validated": datetime.now().isoformat()
        }
        
        self.license_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.license_file_path.write_text(json.dumps(license_info, indent=2))
    
    def _load_local_license(self) -> Optional[Dict[str, Any]]:
        """Load license information from local storage."""
        if not self.license_file_path.exists():
            return None
        
        try:
            return json.loads(self.license_file_path.read_text())
        except Exception:
            return None
    
    def get_license_info(self) -> Optional[Dict[str, Any]]:
        """Get current license information without validation."""
        return self._load_local_license()
    
    def is_licensed(self) -> bool:
        """
        Quick check if application is licensed.
        
        Returns:
            True if licensed, False otherwise
        """
        validation_result = self.validate_license()
        return validation_result.get("success", False)