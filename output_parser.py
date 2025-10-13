from typing import Dict, List

import re
import string

# These maps are based on build_semantic_dataset_from_manifest_v2.py
EMOTION_TO_TOKEN = {
    "angry": "🤬",
    "anger": "🤬",
    "sad": "😢",
    "sadness": "😢",
    "neutral": "😐",
    "happy": "😊",
    "happiness": "😊",
    "surprised": "😮",
    "surprise": "😮",
    "ps": "😮",
    "fearful": "😨",
    "fear": "😨",
    "disgust": "🤢",
    "calm": "😌"
}

EVENT_TO_TOKEN = {
    "speech": "💬",
    "music": "🎵",
    "applause": "👏",
    "clapping": "👏",
    "laughter": "😂",
    "laughing": "😂",
    "crying, sobbing": "😭",
    "crying baby": "😭",
    "sneezing": "🤧",
    "sneeze": "🤧",
    "breathing": "💨",
    "cough": "😷",
    "coughing": "😷",
}

# Create reverse mapping for parsing
# For tokens with multiple labels, we pick one representative label.
TOKEN_TO_EMOTION = {
    "🤬": "angry",
    "😢": "sad",
    "😐": "neutral",
    "😊": "happy",
    "😮": "surprised",
    "😨": "fearful",
    "🤢": "disgust",
    "😌": "calm",
    "😶": "unknown"  # As defined in the builder script for unknown emotions
}

TOKEN_TO_EVENT = {
    "💬": "speech",
    "🎵": "music",
    "👏": "clapping",
    "😂": "laughter",
    "😭": "crying",
    "🤧": "sneezing",
    "💨": "breathing",
    "😷": "cough",
    "❓": "unknown"  # As defined in the builder script for unknown events
}



def clean_repeated_patterns(text: str, threshold: int = 10, max_len: int = 30) -> str:
    """
    Remove long repeated characters or patterns from text.

    Args:
        text (str): input string to clean
        threshold (int): number of consecutive repeats to consider as noise
        max_len (int): maximum pattern length to check for repetition

    Returns:
        str: cleaned string
    """

    def fix_char_repeats(s: str, thresh: int) -> str:
        """Collapse character repeats longer than threshold."""
        res = []
        i = 0
        n = len(s)
        while i < n:
            count = 1
            while i + count < n and s[i + count] == s[i]:
                count += 1
            # 超过阈值的重复，只保留一个
            if count > thresh:
                res.append(s[i])
            else:
                res.append(s[i:i + count])
            i += count
        return ''.join(res)

    def fix_pattern_repeats(s: str, thresh: int, max_len: int) -> str:
        """Collapse repeating patterns longer than threshold."""
        n = len(s)
        min_repeat_chars = thresh * 2
        if n < min_repeat_chars:
            return s

        i = 0
        result = []
        while i <= n - min_repeat_chars:
            found = False
            for k in range(1, max_len + 1):
                if i + k * thresh > n:
                    break
                pattern = s[i:i + k]

                valid = all(
                    s[i + rep * k:i + (rep + 1) * k] == pattern
                    for rep in range(1, thresh)
                )
                if valid:
                    end_index = i + thresh * k
                    while end_index + k <= n and s[end_index:end_index + k] == pattern:
                        end_index += k
                    result.append(pattern)
                    result.append(fix_pattern_repeats(s[end_index:], thresh, max_len))
                    i = n
                    found = True
                    break
            if found:
                break
            else:
                result.append(s[i])
                i += 1
        if not found:
            result.append(s[i:])
        return ''.join(result)

    text = fix_char_repeats(text, threshold)
    return fix_pattern_repeats(text, threshold, max_len)


def clean_sequential_hallucinations(text: str, min_seq_len: int = 4) -> str:
    """
    Remove meaningless sequential or templated patterns such as:
        1 2 3 4
        one two three four
        the answer is 1, the answer is 2, ...
    while preserving original casing, punctuation, and natural spacing.
    """
    if not text:
        return text

    lower_text = text.lower()

    # --- Step 1: Remove templated numeric hallucinations
    template_pattern = re.compile(
        r"(?:\b[\w\s]{0,20}?(?:is|are|was|were)\s+)?"
        r"(?:\b(the\s+answer\s+is|the\s+result\s+is|answer\s+is)\s+)"
        r"((?:\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten)"
        r"(?:\s*,?\s*(?:the\s+answer\s+is\s+)?(?:\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten)){"
        + str(min_seq_len - 1) + r",})",
        flags=re.IGNORECASE,
    )
    mask_text = re.sub(template_pattern, "", lower_text)

    # --- Step 2: Remove sequential patterns
    alphabet = list(string.ascii_lowercase)
    number_words = [
        "zero", "one", "two", "three", "four", "five", "six",
        "seven", "eight", "nine", "ten", "eleven", "twelve",
        "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
        "eighteen", "nineteen", "twenty",
    ]
    digits = [str(i) for i in range(0, 21)]
    sequences = [alphabet, number_words, digits]

    # Split words & punctuation (保留标点)
    tokens = re.findall(r"\b\w+\b|[^\w\s]", mask_text)

    def is_seq(segment, seq):
        try:
            start = seq.index(segment[0])
        except ValueError:
            return False
        for j, t in enumerate(segment):
            if start + j >= len(seq) or seq[start + j] != t:
                return False
        return True

    keep_mask = [True] * len(tokens)
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if not re.match(r"\w+", token):
            i += 1
            continue
        matched = False
        for seq in sequences:
            for L in range(len(seq), min_seq_len - 1, -1):
                if i + L > len(tokens):
                    continue
                segment = [t for t in tokens[i:i + L] if re.match(r"\w+", t)]
                if len(segment) < L:
                    continue
                if is_seq(segment, seq):
                    for k in range(i, i + L):
                        keep_mask[k] = False
                    i += L
                    matched = True
                    break
            if matched:
                break
        if not matched:
            i += 1

    filtered_tokens = [t for t, keep in zip(tokens, keep_mask) if keep]

    # --- Step 3: Reconstruct text with natural spacing
    cleaned = ""
    prev = ""
    for t in filtered_tokens:
        # Word or number
        if re.match(r"[\w]", t):
            if prev and re.match(r"[\w\)\]\}]", prev):
                cleaned += " "
            cleaned += t
        # Opening bracket
        elif t in "([{" and prev and re.match(r"[\w\)\]\}]", prev):
            cleaned += " " + t
        # Closing bracket
        elif t in ")]}" and cleaned.endswith(" "):
            cleaned = cleaned[:-1] + t
        # Punctuation (, . ? ! :) — ensure space after if followed by word later
        elif t in ",.!?;:":
            cleaned += t
        else:
            cleaned += t
        prev = t

    # --- Step 4: fix spaces: add space after punctuation if missing before word
    cleaned = re.sub(r"([,;:!?])([^\s\w])", r"\1 \2", cleaned)
    cleaned = re.sub(r"([,;:!?])(\w)", r"\1 \2", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # --- Step 5: restore casing
    restored = ""
    j = 0
    for ch in cleaned:
        while j < len(text) and text[j].lower() != ch.lower():
            j += 1
        if j < len(text):
            restored += text[j]
            j += 1
        else:
            restored += ch
    return restored.strip()


def clean_text(text: str) -> str:
    """
    Apply all cleaning functions to the text.
    """
    text = clean_repeated_patterns(text)
    text = clean_sequential_hallucinations(text)
    return text


def parse_model_output(output_string: str) -> Dict[str, any]:
    """
    Parses the model output string to extract emotion, events, and transcript.

    Args:
        output_string: The raw output from the model.

    Returns:
        A dictionary with 'emotion', 'events', and 'transcript'.
    """
    parsed_data = {
        'raw': output_string,
        'emotion': None,
        'events': [],
        'transcript': '',
        'transcript_clean': '',
        'transcript_clean_with_event': '',
    }

    try:
        # Remove <think>...</think> block if present
        if output_string.startswith('<think>'):
            end_think_tag = '</think>'
            end_think_pos = output_string.find(end_think_tag)
            if end_think_pos != -1:
                text = output_string[end_think_pos + len(end_think_tag):].lstrip()
            else:
                text = output_string # Malformed, no closing tag
        else:
            text = output_string



        remaining_text = text
        
        # 1. Parse emotion (at most one at the beginning)
        if remaining_text:
            char = remaining_text[0]
            if char in TOKEN_TO_EMOTION:
                parsed_data['emotion'] = TOKEN_TO_EMOTION[char]
                remaining_text = remaining_text[1:]

        # 2. Parse events (zero or more, following emotion)
        while remaining_text:
            char = remaining_text[0]
            if char in TOKEN_TO_EVENT:
                parsed_data['events'].append(TOKEN_TO_EVENT[char])
                remaining_text = remaining_text[1:]
            else:
                break
        
        if '<unknown_events>' in remaining_text:
            parsed_data['events'].append('unknown')
            remaining_text = remaining_text.replace('<unknown_events>', '')

        remaining_text = remaining_text.strip()

        # 3. The rest is transcript
        if remaining_text == "🔇" or remaining_text == "<no_transcript>":
            parsed_data['transcript'] = ""
            parsed_data['transcript_clean'] = ""
        else:
            parsed_data['transcript'] = remaining_text
            parsed_data['transcript_clean'] = clean_text(remaining_text)
        
        event_text = [f'({event})' for event in parsed_data['events'] if event is not 'unknown' and event is not 'speech']
        event_text = ' '.join(event_text).strip()
        if event_text:
            parsed_data['transcript_clean_with_event'] = event_text + ' ' + parsed_data['transcript_clean'] 
        else:
            parsed_data['transcript_clean_with_event'] = parsed_data['transcript_clean'] 
        parsed_data['transcript_clean_with_event'] = parsed_data['transcript_clean_with_event'].strip()
    except Exception as e:
        print(f"Error parsing model output: {e}")
        return parsed_data

    return parsed_data  

if __name__ == '__main__':
    # Example usage and test cases
    test_outputs = [
        "<think>\n\n</think>\n\n😊💬Hello, world!",
        "<think>\n\n</think>\n\n😢",
        "<think>\n\n</think>\n\n👏😂This is funny.",
        "😐🎵",
        "Just a transcript without any tokens.",
        "🤬😷I am angry and coughing.",
        "😶❓<no_transcript>",
        "<think>\n\n</think>\n\n😐🔇",
        "This is a test 😐 with emoji in the middle",
        "💬❓"
    ]

    for output in test_outputs:
        parsed = parse_model_output(output)
        print(f"Original: '{output}'")
        print(f"Parsed  : {parsed}\n")

    # Example of a well-formed output
    print("--- Well-formed example ---")
    good_output = "<think>\n\n</think>\n\n😊👏💬Hello, how can I help you?"
    parsed_good = parse_model_output(good_output)
    print(f"Original: '{good_output}'")
    print(f"Parsed  : {parsed_good}\n")

    # Example of an output with only transcript
    print("--- Transcript only example ---")
    transcript_only = "This is a simple sentence."
    parsed_transcript = parse_model_output(transcript_only)
    print(f"Original: '{transcript_only}'")
    print(f"Parsed  : {parsed_transcript}\n")
