import os
from scripts import weekly_digest

def test_digest_render(session, tmp_path):
    # Seed minimal data
    from app.db import RequestLog
    from datetime import datetime, timezone
    
    session.add(RequestLog(
        wa_message_id="m1", wa_from="2348123456789", user_text="hi", 
        outcome="sent", flash_input_tokens=100, flash_output_tokens=50,
        received_at=datetime.now(timezone.utc)
    ))
    session.commit()
    
    out_file = tmp_path / "digest.md"
    # Mock health to avoid subprocess
    weekly_digest.get_health_json = lambda: {"overall": "MOCK_PASS"}
    
    weekly_digest.run_digest(days=7, out_path=str(out_file))
    
    assert out_file.exists()
    content = out_file.read_text()
    assert "# Weekly Digest" in content
    assert "23481234XXXX" in content # masked
    assert "MOCK_PASS" in content
