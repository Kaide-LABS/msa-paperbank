import logging
import json
import sys
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage()
        }
        if hasattr(record, "extra"):
            log_record.update(record.extra)
        
        # Add any extra kwargs passed to log methods
        if hasattr(record, '__dict__'):
            for key, value in record.__dict__.items():
                if key not in ['args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
                             'funcName', 'levelname', 'levelno', 'lineno', 'module',
                             'msecs', 'message', 'msg', 'name', 'pathname', 'process',
                             'processName', 'relativeCreated', 'stack_info', 'thread',
                             'threadName', 'extra', 'taskName']:
                    log_record[key] = value

        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
            
        return json.dumps(log_record)

def setup_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())
    
    # Remove existing handlers
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        
    root_logger.addHandler(handler)