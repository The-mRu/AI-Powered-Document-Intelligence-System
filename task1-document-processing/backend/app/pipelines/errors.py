"""Typed errors. `code` is persisted on the document row so the UI/API can
show a precise reason instead of a generic "processing failed"."""


class ProcessingError(Exception):
    code = "processing_error"


class UnsupportedFileError(ProcessingError):
    code = "unsupported_file"


class CorruptedFileError(ProcessingError):
    code = "corrupted_file"


class EncryptedFileError(ProcessingError):
    code = "encrypted_file"


class FileTooLargeError(ProcessingError):
    code = "file_too_large"
