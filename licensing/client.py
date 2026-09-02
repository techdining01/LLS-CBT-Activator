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
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


class LicenseClient:
    """Client-side license validation and management."""
    
    def __init__(self, license_server_url: str = "https://lls-cbt-activator.onrender.com"):
        """
        Initialize the license client.
        
        Args:
            license_server_url: URL of the license activation server
        """
        self.license_server_url = license_server_url
        self.license_file_path = Path.home() / ".lls_cbt_license.json"
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
        root_key_file = Path(__file__).resolve().parent.parent.parent / "license_public_key.pem"
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
        """Activate a license. Tries online first; falls back to offline (RSA-only) if unreachable."""
        # Normalise key — verify_product_key handles padding internally
        product_key = product_key.strip().replace("-", "").replace(" ", "").replace("\r", "").replace("\n", "")

        # Always verify the RSA signature locally first — works with no internet
        try:
            license_data = self.crypto.verify_product_key(product_key)
        except ValueError as e:
            return {"success": False, "message": str(e)}

        # Check key expiry from the embedded license data
        try:
            key_expiry = datetime.fromisoformat(license_data.get("expiry", ""))
            if datetime.now() > key_expiry:
                return {"success": False, "message": "This product key has expired."}
        except Exception:
            pass

        # Try online activation
        try:
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
            response = requests.post(
                f"{self.license_server_url}/api/license/activate",
                json=payload,
                timeout=15
            )
            if response.status_code == 200:
                result = response.json()
                self._save_license_locally(
                    product_key=product_key,
                    activation_id=result["activation_id"],
                    license_data=result["license_data"],
                    expiry_date=result["expiry_date"],
                    user_email=user_email,
                    user_name=user_name,
                )
                return {
                    "success": True,
                    "message": result["message"],
                    "remaining_credits": result["remaining_credits"],
                    "expiry_date": result["expiry_date"],
                }
            else:
                error_detail = response.json().get("detail", "Unknown error")
                return {"success": False, "message": f"Activation failed: {error_detail}"}

        except requests.RequestException:
            # Server unreachable — activate offline using the verified RSA key data
            expiry_date = license_data.get("expiry", (datetime.now().isoformat()))
            self._save_license_locally(
                product_key=product_key,
                activation_id=0,          # 0 = offline activation, no server record
                license_data=license_data,
                expiry_date=expiry_date,
                user_email=user_email,
                user_name=user_name,
            )
            return {
                "success": True,
                "message": "License activated offline. Connect to the internet within 120 days to sync.",
                "remaining_credits": license_data.get("credits", 0),
                "expiry_date": expiry_date,
            }

        except Exception as e:
            return {"success": False, "message": f"Activation error: {str(e)}"}
    
    def validate_license(self) -> Dict[str, Any]:
        """Validate the current license. Online when possible, offline otherwise."""
        local_license = self._load_local_license()
        if not local_license:
            return {"success": False, "message": "No license found. Please activate your product."}

        # Always verify RSA signature locally — this works with no internet
        try:
            license_data = self.crypto.verify_product_key(local_license["product_key"])
        except ValueError as e:
            return {"success": False, "message": str(e)}

        # Check expiry from the saved file
        try:
            expiry_date = datetime.fromisoformat(local_license["expiry_date"])
            if datetime.now() > expiry_date:
                return {"success": False, "message": "License has expired."}
        except Exception:
            pass

        # Offline-only activation (activation_id == 0) skips server validation entirely
        if local_license.get("activation_id", 0) == 0:
            return self._validate_offline(local_license, license_data)

        # Try online validation
        try:
            payload = {
                "product_key": local_license["product_key"],
                "machine_fingerprint": self.machine_fingerprint,
                "activation_id": local_license["activation_id"],
            }
            response = requests.post(
                f"{self.license_server_url}/api/license/validate",
                json=payload,
                timeout=10,
            )
            if response.status_code == 200:
                result = response.json()
                if result["is_valid"]:
                    # Refresh last_validated timestamp on successful online check
                    local_license["last_validated"] = datetime.now().isoformat()
                    self.license_file_path.write_text(json.dumps(local_license, indent=2))
                    return {
                        "success": True,
                        "message": "License is valid",
                        "license_data": result["license_data"],
                        "remaining_credits": result["remaining_credits"],
                    }
                return {"success": False, "message": result["message"]}
            # Non-200 from server → fall back to offline
            return self._validate_offline(local_license, license_data)

        except requests.RequestException:
            # No internet → fall back to offline
            return self._validate_offline(local_license, license_data)
            
    def _validate_offline(self, local_license: Dict[str, Any], license_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform offline license validation when server is unreachable.
        The RSA signature was already verified locally before calling this.
        Allows up to 120 days offline after last successful online validation.
        """
        expiry_date = datetime.fromisoformat(local_license["expiry_date"])
        last_validated = datetime.fromisoformat(local_license.get("last_validated", "2020-01-01T00:00:00"))
        now = datetime.now()

        # Basic clock sanity check
        if now < last_validated:
            return {
                "success": False,
                "message": "System time appears incorrect. Please check your clock."
            }

        # Check expiry
        if now > expiry_date:
            return {
                "success": False,
                "message": "License has expired"
            }

        # Allow up to 120 days offline
        days_offline = (now - last_validated).days
        if days_offline > 120:
            return {
                "success": False,
                "message": "License requires online validation (120-day offline limit reached). Please connect to the internet."
            }

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
                timeout=45
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
