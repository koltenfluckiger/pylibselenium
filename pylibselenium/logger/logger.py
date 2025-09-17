import logging
import pathlib
class Logger:
    def __init__(self, name: str, log_file: str = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(logging.StreamHandler())
        self.logger.addHandler(logging.FileHandler(pathlib.Path(log_file).parent.absolute() / f"{log_file}.log"))
        self.logger.addHandler(logging.FileHandler(pathlib.Path(log_file).parent.absolute() / f"{log_file}.log"))
    
    def info(self, message: str):
        self.logger.info(message)
    
    def warning(self, message: str):
        self.logger.warning(message)
    
    def error(self, message: str):
        self.logger.error(message)
    
    def debug(self, message: str):
        self.logger.debug(message)
    
    def critical(self, message: str):
        self.logger.critical(message)
    
    def exception(self, message: str):
        self.logger.exception(message)
    
    def get_logger(self):
        return self.logger
    


