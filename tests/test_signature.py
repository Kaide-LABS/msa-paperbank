import hmac
import hashlib
from app.whatsapp import verify_signature

def test_signature():
    secret = "my_secret"
    body = b"hello world"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    
    # Valid
    assert verify_signature(body, sig, secret) is True
    
    # Tampered body
    assert verify_signature(b"hello worl", sig, secret) is False
    
    # Missing header
    assert verify_signature(body, "", secret) is False