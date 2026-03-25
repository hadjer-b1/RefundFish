"""
Secure credential management for hotel booking sites
Uses encryption to store passwords securely
"""

import json
import os
from pathlib import Path
from cryptography.fernet import Fernet
import base64
import hashlib

CREDENTIALS_FILE = Path('data/credentials.json')
ENCRYPTION_KEY_FILE = Path('data/.encryption_key')

class CredentialsManager:
    """Manages encrypted storage of booking site credentials"""
    
    def __init__(self):
        self.credentials_file = CREDENTIALS_FILE
        self.key_file = ENCRYPTION_KEY_FILE
        self.ensure_key_exists()
        self.cipher_suite = None
        self._load_cipher()
    
    def ensure_key_exists(self):
        """Ensure encryption key exists, create if not"""
        self.key_file.parent.mkdir(exist_ok=True)
        
        if not self.key_file.exists():
            # Generate a new encryption key
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            # Secure permissions on key file
            os.chmod(self.key_file, 0o600)
    
    def _load_cipher(self):
        """Load encryption cipher from key file"""
        try:
            with open(self.key_file, 'rb') as f:
                key = f.read()
            self.cipher_suite = Fernet(key)
        except Exception as e:
            raise Exception(f"Failed to load encryption key: {e}")
    
    def encrypt_password(self, password):
        """Encrypt a password"""
        try:
            encrypted = self.cipher_suite.encrypt(password.encode())
            return encrypted.decode()
        except Exception as e:
            raise Exception(f"Encryption failed: {e}")
    
    def decrypt_password(self, encrypted_password):
        """Decrypt a password"""
        try:
            decrypted = self.cipher_suite.decrypt(encrypted_password.encode())
            return decrypted.decode()
        except Exception as e:
            raise Exception(f"Decryption failed - invalid or corrupted password: {e}")
    
    def save_credentials(self, website, username, password=None, two_fa_code=None, email=None):
        """Save credentials for a website (supports password OR 2FA code)"""
        try:
            self.credentials_file.parent.mkdir(exist_ok=True)
            
            # Load existing credentials
            creds = self._load_credentials_file()
            
            # Encrypt password if provided
            encrypted_pwd = None
            if password:
                encrypted_pwd = self.encrypt_password(password)
            
            # Encrypt 2FA code if provided
            encrypted_2fa = None
            if two_fa_code:
                encrypted_2fa = self.encrypt_password(two_fa_code)
            
            if website not in creds:
                creds[website] = {}
            
            creds[website] = {
                'username': username,
                'email': email or username,
                'password': encrypted_pwd,
                'two_fa_code': encrypted_2fa,
                'website': website,
                'saved_at': str(Path.cwd()),
                'auth_method': 'password' if password else '2fa'
            }
            
            # Save to file
            with open(self.credentials_file, 'w') as f:
                json.dump(creds, f, indent=2)
            
            # Secure permissions
            os.chmod(self.credentials_file, 0o600)
            
            return True
        except Exception as e:
            raise Exception(f"Failed to save credentials: {e}")
    
    def get_credentials(self, website):
        """Get credentials for a website (password will be encrypted)"""
        try:
            creds = self._load_credentials_file()
            if website in creds:
                cred = creds[website].copy()
                # Return encrypted password (don't decrypt on retrieve)
                return cred
            return None
        except Exception as e:
            raise Exception(f"Failed to get credentials: {e}")
    
    def get_credentials_for_agent(self, website):
        """Get decrypted credentials for agent to use (returns password OR 2FA code)"""
        try:
            creds = self._load_credentials_file()
            if website in creds:
                cred = creds[website].copy()
                # Decrypt password if exists
                if cred.get('password'):
                    cred['password'] = self.decrypt_password(cred['password'])
                # Decrypt 2FA code if exists
                if cred.get('two_fa_code'):
                    cred['two_fa_code'] = self.decrypt_password(cred['two_fa_code'])
                return cred
            return None
        except Exception as e:
            raise Exception(f"Failed to get credentials for agent: {e}")
    
    def delete_credentials(self, website):
        """Delete credentials for a website"""
        try:
            creds = self._load_credentials_file()
            if website in creds:
                del creds[website]
                with open(self.credentials_file, 'w') as f:
                    json.dump(creds, f, indent=2)
                os.chmod(self.credentials_file, 0o600)
                return True
            return False
        except Exception as e:
            raise Exception(f"Failed to delete credentials: {e}")
    
    def list_saved_websites(self):
        """List all websites with saved credentials"""
        try:
            creds = self._load_credentials_file()
            return list(creds.keys())
        except:
            return []
    
    def list_credentials_safe(self):
        """List saved credentials without passwords (for UI display)"""
        try:
            creds = self._load_credentials_file()
            safe_list = []
            
            for website, cred in creds.items():
                safe_cred = {
                    'website': website,
                    'username': cred.get('username', ''),
                    'email': cred.get('email', ''),
                    'has_password': bool(cred.get('password')),
                    'has_2fa_code': bool(cred.get('two_fa_code')),
                    'auth_method': cred.get('auth_method', 'unknown'),
                    'saved_at': cred.get('saved_at', 'unknown')
                }
                safe_list.append(safe_cred)
            
            return safe_list
        except Exception as e:
            raise Exception(f"Failed to list credentials: {e}")
    
    def _load_credentials_file(self):
        """Load credentials from file"""
        if self.credentials_file.exists():
            try:
                with open(self.credentials_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}


# Global instance
credentials_manager = CredentialsManager()
