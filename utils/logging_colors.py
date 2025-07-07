from colorama import Fore, Style, init as colorama_init
import logging

colorama_init(autoreset=True)

SERVER_COLOR = Fore.BLUE
CLIENT_COLOR = Fore.CYAN
APP_COLOR = Fore.YELLOW
RESET = Style.RESET_ALL

class ColorFormatter(logging.Formatter):
    def __init__(self, color, fmt=None, datefmt=None):
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.color = color

    def format(self, record):
        message = super().format(record)
        return f"{Style.BRIGHT}{self.color}{message}{RESET}"

def setup_logger(name: str, color, fmt: str = "%(levelname)s: %(message)s") -> logging.Logger:
    """Set up a logger with colored output and proper configuration.
    
    Args:
        name: Logger name
        color: Color from colorama (e.g., SERVER_COLOR, CLIENT_COLOR)
        fmt: Log format string (default includes level and message)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter(color, fmt=fmt))
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger 