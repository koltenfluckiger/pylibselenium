import logging
import pathlib


class Logger:
    """
    A named logger with a console handler and, when ``log_file`` is given, a file handler.

    Handlers are added only once per logger name, so building the same ``Logger`` twice does not
    duplicate output. ``log_file`` is used as given (``.log`` is appended when it has no suffix)
    and its directory is created when missing.
    """

    FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    def __init__(self, name: str, log_file: str = None, level: int = logging.DEBUG):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        formatter = logging.Formatter(self.FORMAT)
        has_stream = any(
            isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
            for handler in self.logger.handlers
        )
        if not has_stream:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(stream_handler)
        self.log_file = None
        if log_file:
            path = pathlib.Path(log_file)
            if not path.suffix:
                path = path.with_suffix(".log")
            path = path.absolute()
            path.parent.mkdir(parents=True, exist_ok=True)
            has_file = any(
                isinstance(handler, logging.FileHandler) and pathlib.Path(handler.baseFilename) == path
                for handler in self.logger.handlers
            )
            if not has_file:
                file_handler = logging.FileHandler(path)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            self.log_file = path

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
