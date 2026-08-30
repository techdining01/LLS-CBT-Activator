import hashlib
import platform
import subprocess
import uuid
from typing import Optional


class MachineFingerprint:
    """Generates a stable machine fingerprint for licensing."""
    
    @staticmethod
    def get_machine_id() -> str:
        """Generate a unique machine identifier based on hardware."""
        try:
            # Collect multiple hardware identifiers
            identifiers = []
            
            # 1. MAC address (first network adapter)
            mac = MachineFingerprint._get_mac_address()
            if mac:
                identifiers.append(f"MAC:{mac}")
            
            # 2. Motherboard serial number
            motherboard_serial = MachineFingerprint._get_motherboard_serial()
            if motherboard_serial:
                identifiers.append(f"MB:{motherboard_serial}")
            
            # 3. CPU ID
            cpu_id = MachineFingerprint._get_cpu_id()
            if cpu_id:
                identifiers.append(f"CPU:{cpu_id}")
            
            # 4. Disk serial
            disk_serial = MachineFingerprint._get_disk_serial()
            if disk_serial:
                identifiers.append(f"DISK:{disk_serial}")
            
            # 5. Windows Product ID (stable across reinstalls if OEM)
            if platform.system() == "Windows":
                product_id = MachineFingerprint._get_windows_product_id()
                if product_id:
                    identifiers.append(f"WIN:{product_id}")
            
            # If we couldn't get hardware IDs, fall back to UUID
            if not identifiers:
                identifiers.append(f"UUID:{uuid.getnode()}")
            
            # Create a stable hash from all identifiers
            fingerprint_data = "|".join(sorted(identifiers))
            fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()
            
            return fingerprint[:32]  # Return first 32 chars for readability
            
        except Exception as e:
            # Fallback to simple MAC-based fingerprint
            print(f"Error generating machine fingerprint: {e}")
            return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:32]
    
    @staticmethod
    def _get_mac_address() -> Optional[str]:
        """Get the MAC address of the first network adapter."""
        try:
            if platform.system() == "Windows":
                # Use wmic to get MAC address
                result = subprocess.run(
                    ['wmic', 'nic', 'where', 'netenabled=true', 'get', 'macaddress'],
                    capture_output=True, text=True, timeout=10
                )
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # Skip header
                    mac = line.strip()
                    if mac and mac != "":
                        return mac
            else:
                # Linux/Mac
                import netifaces
                interfaces = netifaces.interfaces()
                for interface in interfaces:
                    if interface != 'lo':
                        addrs = netifaces.ifaddresses(interface)
                        if netifaces.AF_LINK in addrs:
                            return addrs[netifaces.AF_LINK][0]['addr']
        except Exception:
            pass
        return None
    
    @staticmethod
    def _get_motherboard_serial() -> Optional[str]:
        """Get motherboard serial number using WMI."""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ['wmic', 'baseboard', 'get', 'serialnumber'],
                    capture_output=True, text=True, timeout=10
                )
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # Skip header
                    serial = line.strip()
                    if serial and serial.lower() not in ['to be filled by o.e.m.', '']:
                        return serial
        except Exception:
            pass
        return None
    
    @staticmethod
    def _get_cpu_id() -> Optional[str]:
        """Get CPU processor ID."""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ['wmic', 'cpu', 'get', 'processorid'],
                    capture_output=True, text=True, timeout=10
                )
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # Skip header
                    cpu_id = line.strip()
                    if cpu_id:
                        return cpu_id
        except Exception:
            pass
        return None
    
    @staticmethod
    def _get_disk_serial() -> Optional[str]:
        """Get disk serial number."""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ['wmic', 'diskdrive', 'get', 'serialnumber'],
                    capture_output=True, text=True, timeout=10
                )
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # Skip header
                    serial = line.strip()
                    if serial:
                        return serial
        except Exception:
            pass
        return None
    
    @staticmethod
    def _get_windows_product_id() -> Optional[str]:
        """Get Windows Product ID from registry."""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
            )
            product_id, _ = winreg.QueryValueEx(key, "ProductId")
            winreg.CloseKey(key)
            return product_id
        except Exception:
            pass
        return None
    
    @staticmethod
    def is_same_machine(fingerprint1: str, fingerprint2: str) -> bool:
        """Check if two fingerprints are from the same machine."""
        # Allow small variations (e.g., network card change)
        return fingerprint1 == fingerprint2