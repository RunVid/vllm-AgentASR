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


def clean_sequential_hallucinations(text: str, min_seq_len: int = 10) -> str:
    """
    Remove meaningless sequential or templated patterns such as:
        1 2 3 4
        one two three four
        the answer is 1, the answer is 2, ...
    while preserving original casing, punctuation, and natural spacing.
    """
    try:
        if not text:
            return text

        original_text = text

        # --- Step 1: Remove templated numeric hallucinations (大小写无关)
        template_pattern = re.compile(
            r"(?:\b[\w\s]{0,20}?(?:is|are|was|were)\s+)?"
            r"(?:\b(the\s+answer\s+is|the\s+result\s+is|answer\s+is)\s+)"
            r"((?:\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten)"
            r"(?:\s*,?\s*(?:the\s+answer\s+is\s+|answer\s+is\s+)?(?:\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten)){"
            + str(min_seq_len - 1) + r",})",
            flags=re.IGNORECASE,
        )
        lower_text = text.lower()
        mask_text = re.sub(template_pattern, "", lower_text)
        templated_removed = mask_text != lower_text

        # --- Step 2: Tokenize 原文 + 小写版
        tokens_orig = re.findall(r"\b\w+\b|[^\w\s]", text)
        tokens_lower = [t.lower() for t in tokens_orig]

        alphabet = list(string.ascii_lowercase)
        number_words = [
            "zero", "one", "two", "three", "four", "five", "six",
            "seven", "eight", "nine", "ten", "eleven", "twelve",
            "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
            "eighteen", "nineteen", "twenty",
        ]
        digits = [str(i) for i in range(0, 21)]
        sequences = [alphabet, number_words, digits]

        def is_seq(segment, seq):
            try:
                start = seq.index(segment[0])
            except ValueError:
                return False
            for j, t in enumerate(segment):
                if start + j >= len(seq) or seq[start + j] != t:
                    return False
            return True

        keep_mask = [True] * len(tokens_lower)
        hallucination_found = False
        i = 0
        while i < len(tokens_lower):
            token = tokens_lower[i]
            if not re.match(r"\w+", token):
                i += 1
                continue
            matched = False
            for seq in sequences:
                for L in range(len(seq), min_seq_len - 1, -1):
                    if i + L > len(tokens_lower):
                        continue
                    segment = [t for t in tokens_lower[i:i + L] if re.match(r"\w+", t)]
                    if len(segment) < L:
                        continue
                    if is_seq(segment, seq):
                        for k in range(i, i + L):
                            keep_mask[k] = False
                        i += L
                        matched = True
                        hallucination_found = True
                        break
                if matched:
                    break
            if not matched:
                i += 1

        # --- Step 3: 若无幻觉 & 无模板匹配 → 返回原文
        if not hallucination_found and not templated_removed:
            return original_text

        # --- Step 4: 重构文本（带空格 & 小数点保护）
        cleaned = ""
        prev = ""
        for i, t in enumerate(tokens_orig):
            if not keep_mask[i]:
                continue
            if re.match(r"[\w]", t):
                if prev and re.match(r"[\w\)\]\}]", prev):
                    cleaned += " "
                cleaned += t
            elif t in "([{" and prev and re.match(r"[\w\)\]\}]", prev):
                cleaned += " " + t
            elif t in ")]}" and cleaned.endswith(" "):
                cleaned = cleaned[:-1] + t
            elif t in ",.!?;:":
                # 小数点不加空格
                if t == "." and re.match(r"\d", prev) and i + 1 < len(tokens_orig) and re.match(r"\d", tokens_orig[i + 1]):
                    cleaned += t
                else:
                    cleaned += t + " "
            else:
                cleaned += t
            prev = t

        # 清理多余空格、孤立标点
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        cleaned = re.sub(r"([,.;:!?])\s+([,.;:!?])", r"\1 \2", cleaned)
        cleaned = re.sub(r"\s*\.\s*\.", ".", cleaned)
        cleaned = re.sub(r"\s*\.\s*$", "", cleaned)  # 去掉末尾孤立句号
        return cleaned.strip()
    except Exception as e:
        print(f"Error cleaning sequential hallucinations: {e}")
        return text

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
        
        event_text = [f'({event})' for event in parsed_data['events'] if event != 'unknown' and event != 'speech']
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
