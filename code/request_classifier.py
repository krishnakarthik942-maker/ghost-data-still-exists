import re

NON_DELETION_PHRASES = [
    'leave the account',
    'not asking for deletion',
    'keep the account',
    'do not close',
    'without removing any of my records',
    'marketing lists only',
    'not a request to erase',
    'leave my profile',
    'continue using the service',
    "don't delete",
    "dont delete",
    'misspelled',
    'correct it',
    'copy of last year',
    'copy of the information held'
]

def classify_request(request_text: str) -> str:
    """
    Classifies a privacy request based on the request text.
    Returns 'NOT_APPLICABLE' if the request explicitly asks to keep the account,
    rectify details, export data without deletion, or opt out of marketing only.
    Otherwise returns 'APPLICABLE' (a genuine deletion request).
    """
    text_lower = request_text.lower()
    for phrase in NON_DELETION_PHRASES:
        if phrase in text_lower:
            return 'NOT_APPLICABLE'
    return 'APPLICABLE'
