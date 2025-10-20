import logging
import yaml
from pathlib import Path

# Cache for configuration to avoid repeated file reads
_config_cache = None

# Define custom ANALYTICS logging level
ANALYTICS_LEVEL = 25  # Between INFO (20) and WARNING (30)
logging.addLevelName(ANALYTICS_LEVEL, "ANALYTICS")


def analytics(self, message, *args, **kwargs):
    """Custom logging method for analytics events."""
    if self.isEnabledFor(ANALYTICS_LEVEL):
        self._log(ANALYTICS_LEVEL, message, args, **kwargs)


# Add the analytics method to the Logger class
logging.Logger.analytics = analytics


def load_config():
    """Load configuration from config.yaml file.
    
    Uses a singleton pattern to cache the configuration and avoid
    repeated file reads during the application lifecycle.
    """
    global _config_cache
    if _config_cache is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f)
    return _config_cache


def get_custom_logger(name="chainlit_logger", log_file=None):
    if log_file is None:
        config = load_config()
        log_file = config["logging"]["log_file"]
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid adding multiple handlers if already set
    if not logger.handlers:
        # Create a file handler
        file_handler = logging.FileHandler(log_file, mode="a")
        file_handler.setLevel(logging.INFO)  # Will capture INFO and above, including ANALYTICS (25)

        # Create and set a formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)

        # Add the handler to the logger
        logger.addHandler(file_handler)

        # Prevent it from propagating to the root logger (used by the framework)
        logger.propagate = False

    return logger