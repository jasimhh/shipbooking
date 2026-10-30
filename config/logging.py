import json
import logging


class JsonFormatter(logging.Formatter):
    """One JSON object per line: easy to search in any log service."""

    def format(self, record):
        entry = {"time": self.formatTime(record), "level": record.levelname, "logger": record.name, "message": record.getMessage()}
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)
