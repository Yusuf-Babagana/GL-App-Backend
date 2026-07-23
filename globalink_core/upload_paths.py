import os
import uuid


def kyc_upload_path(instance, filename):
    """
    Random, non-guessable filename for sensitive KYC documents (ID scans, selfies).
    Prevents enumeration of other users' documents via predictable/original filenames.
    """
    ext = os.path.splitext(filename)[1]
    return f"kyc_docs/{uuid.uuid4().hex}{ext}"
