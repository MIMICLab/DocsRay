# src/utils/text_cleaning.py

import re

def basic_clean_text(text: str) -> str:
    """
    Basic text normalizer.

    1. Replace tab and newline characters with a single space.  
    2. Collapse multiple consecutive whitespace characters into one space.  
    3. Strip leading and trailing whitespace.

    Parameters
    ----------
    text : str
        Raw input text.

    Returns
    -------
    str
        Cleaned text string.
    """
    # Replace tabs and newlines with a space
    text = text.replace('\t', ' ').replace('\n', ' ')

    # Collapse multiple spaces into a single space
    text = re.sub(r'\s+', ' ', text)

    return text.strip()