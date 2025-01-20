import logging
import sys

def setup_logging():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Debug imports
    logger.info(f"Python path: {sys.path}")
    logger.info(f"Python version: {sys.version}")
    
    return logger 