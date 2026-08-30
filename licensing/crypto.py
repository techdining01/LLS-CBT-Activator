import base64
import json
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
from typing import Dict, Any


class LicenseCrypto:
    """Handles cryptographic operations for licensing."""
    
    def __init__(self, private_key_pem: str = None, public_key_pem: str = None):
        """
        Initialize with either private key (server) or public key (client).
        
        Args:
            private_key_pem: PEM-formatted private key (server only)
            public_key_pem: PEM-formatted public key (client only)
        """
        self.private_key = None
        self.public_key = None
        
        if private_key_pem:
            self.private_key = serialization.load_pem_private_key(
                private_key_pem.encode(),
                password=None,
                backend=default_backend()
            )
            self.public_key = self.private_key.public_key()
        
        if public_key_pem:
            self.public_key = serialization.load_pem_public_key(
                public_key_pem.encode(),
                backend=default_backend()
            )
    
    @staticmethod
    def generate_key_pair() -> tuple[str, str]:
        """
        Generate RSA-2048 key pair.
        
        Returns:
            Tuple of (private_key_pem, public_key_pem)
        """
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()
        
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
        
        return private_pem, public_pem
    
    def sign_product_key(self, license_data: Dict[str, Any]) -> str:
        """
        Sign license data to create a product key.
        
        Args:
            license_data: Dictionary containing license metadata
            
        Returns:
            Base64-encoded product key (signature + data)
        """
        if not self.private_key:
            raise ValueError("Private key required for signing")
        
        # Serialize license data
        data_json = json.dumps(license_data, sort_keys=True)
        data_bytes = data_json.encode()
        
        # Sign the data
        signature = self.private_key.sign(
            data_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        # Combine signature and data
        combined = {
            "sig": base64.b64encode(signature).decode(),
            "data": base64.b64encode(data_bytes).decode()
        }
        
        # Encode as base64 for product key
        product_key = base64.b64encode(json.dumps(combined).encode()).decode()
        
        # Format as XXXX-XXXX-XXXX-XXXX for readability
        formatted_key = self._format_product_key(product_key)
        
        return formatted_key
    
    def verify_product_key(self, product_key: str) -> Dict[str, Any]:
        """
        Verify and decode a product key.
        
        Args:
            product_key: Formatted product key string
            
        Returns:
            Dictionary containing license data if valid
            
        Raises:
            ValueError: If signature is invalid or key is malformed
        """
        if not self.public_key:
            raise ValueError("Public key required for verification")
        
        try:
            # Remove formatting, whitespace, and newlines
            raw_key = product_key.strip().replace("-", "").replace(" ", "").replace("\r", "").replace("\n", "")
            
            # Add missing base64 padding if needed
            missing_padding = len(raw_key) % 4
            if missing_padding:
                raw_key += "=" * (4 - missing_padding)
            
            # Decode base64
            decoded_json = base64.b64decode(raw_key.encode()).decode("utf-8")
            combined = json.loads(decoded_json)
            
            # Extract signature and data
            signature = base64.b64decode(combined["sig"])
            data_bytes = base64.b64decode(combined["data"])
            
            # Verify signature
            self.public_key.verify(
                signature,
                data_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # Decode and return license data
            license_data = json.loads(data_bytes.decode("utf-8"))
            return license_data
            
        except Exception as e:
            raise ValueError(f"Invalid product key: {str(e)}")
    
    @staticmethod
    def _format_product_key(key: str) -> str:
        """Format a base64 key as XXXX-XXXX-XXXX-XXXX... (case-sensitive)"""
        # Remove any existing formatting
        clean_key = key.replace("-", "").replace(" ", "").strip()
        
        # Split into groups of 4
        groups = [clean_key[i:i+4] for i in range(0, len(clean_key), 4)]
        
        # Join with hyphens, preserving Base64 case
        return "-".join(groups)
    
    @staticmethod
    def generate_license_data(
        product_name: str,
        version: str,
        credits: int = 2,
        expiry_days: int = 365,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Generate license data structure.
        
        Args:
            product_name: Name of the product
            version: Product version
            credits: Number of activation credits
            expiry_days: Days until licence expires
            metadata: Additional metadata
            
        Returns:
            Dictionary with license data
        """
        from datetime import datetime, timedelta
        
        expiry_date = (datetime.now() + timedelta(days=expiry_days)).isoformat()
        
        license_data = {
            "product": product_name,
            "version": version,
            "credits": credits,
            "expiry": expiry_date,
            "issued": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        return license_data