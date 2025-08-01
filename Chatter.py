import random
import numpy as np
import torch
import os
import re
import datetime
import torchaudio
import gradio as gr
import spaces
import subprocess
from pydub import AudioSegment
import ffmpeg
import librosa
import string
import difflib
import time
import gc
from chatterbox.src.chatterbox.tts import ChatterboxTTS
from concurrent.futures import ThreadPoolExecutor, as_completed
import whisper
import nltk
from nltk.tokenize import sent_tokenize
from faster_whisper import WhisperModel as FasterWhisperModel
import json
import csv
import soundfile as sf
from chatterbox.src.chatterbox.vc import ChatterboxVC
import markdown
SETTINGS_PATH = "settings.json"
#THIS IS THE START
def load_settings():
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                d = default_settings()
                d.update(data)
                return d
            except Exception:
                return default_settings()
    else:
        return default_settings()

def save_settings(mapping):
    # Ensure "whisper_model_dropdown" is always saved as the label, not code
    whisper_model_map = {
        "tiny (~1 GB VRAM OpenAI / ~0.5 GB faster-whisper)": "tiny",
        "base (~1.2–2 GB OpenAI / ~0.7–1 GB faster-whisper)": "base",
        "small (~2–3 GB OpenAI / ~1.2–1.7 GB faster-whisper)": "small",
        "medium (~5–8 GB OpenAI / ~2.5–4.5 GB faster-whisper)": "medium",
        "large (~10–13 GB OpenAI / ~4.5–6.5 GB faster-whisper)": "large"
    }
    v = mapping.get("whisper_model_dropdown", "")
    if v not in whisper_model_map:
        label = next((k for k, code in whisper_model_map.items() if code == v), v)
        mapping["whisper_model_dropdown"] = label

    # --- Add the extra "per-generation" fields for full compatibility ---
    if "input_basename" not in mapping:
        mapping["input_basename"] = "text_input_"
    if "audio_prompt_path_input" not in mapping:
        mapping["audio_prompt_path_input"] = None
    if "generation_time" not in mapping:
        import datetime
        mapping["generation_time"] = datetime.datetime.now().isoformat()
    if "output_audio_files" not in mapping:
        mapping["output_audio_files"] = []

    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
        
def save_settings_csv(settings_dict, output_audio_files, csv_path):
    """
    Save a dict of settings and a list of output audio files to a one-row CSV.
    """
    # Prepare a flattened settings dict for CSV
    flat_settings = {}
    for k, v in settings_dict.items():
        if isinstance(v, (list, tuple)):
            flat_settings[k] = '|'.join(map(str, v))
        else:
            flat_settings[k] = v
    flat_settings['output_audio_files'] = '|'.join(output_audio_files)
    with open(csv_path, "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(flat_settings.keys()))
        writer.writeheader()
        writer.writerow(flat_settings)

def save_settings_json(settings_dict, json_path):
    """
    Save the settings dict as a JSON file.
    """
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(settings_dict, f, indent=2, ensure_ascii=False)
        
        
# === VC TAB (NEW) ===
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
VC_MODEL = None

def get_or_load_vc_model():
    global VC_MODEL
    if VC_MODEL is None:
        VC_MODEL = ChatterboxVC.from_pretrained(DEVICE)
    return VC_MODEL



def voice_conversion(input_audio_path, target_voice_audio_path, chunk_sec=60, overlap_sec=0.1, disable_watermark=True, pitch_shift=0):
    import soundfile as sf
    import librosa
    vc_model = get_or_load_vc_model()
    model_sr = vc_model.sr

    wav, sr = sf.read(input_audio_path)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != model_sr:
        wav = librosa.resample(wav, orig_sr=sr, target_sr=model_sr)
        sr = model_sr

    total_sec = len(wav) / model_sr

    if total_sec <= chunk_sec:
        wav_out = vc_model.generate(
            input_audio_path,
            target_voice_path=target_voice_audio_path,
            apply_watermark=not disable_watermark,
            pitch_shift=pitch_shift
        )
        out_wav = wav_out.squeeze(0).numpy()
        return model_sr, out_wav

    # chunking logic for long files
    chunk_samples = int(chunk_sec * model_sr)
    overlap_samples = int(overlap_sec * model_sr)
    step_samples = chunk_samples - overlap_samples

    out_chunks = []
    for start in range(0, len(wav), step_samples):
        end = min(start + chunk_samples, len(wav))
        chunk = wav[start:end]
        temp_chunk_path = f"temp_vc_chunk_{start}_{end}.wav"
        sf.write(temp_chunk_path, chunk, model_sr)
        out_chunk = vc_model.generate(
            temp_chunk_path,
            target_voice_path=target_voice_audio_path,
            apply_watermark=not disable_watermark,
            pitch_shift=pitch_shift
        )
        out_chunk_np = out_chunk.squeeze(0).numpy()
        out_chunks.append(out_chunk_np)
        os.remove(temp_chunk_path)

    # Crossfade join as before...
    result = out_chunks[0]
    for i in range(1, len(out_chunks)):
        overlap = min(overlap_samples, len(out_chunks[i]), len(result))
        if overlap > 0:
            fade_out = np.linspace(1, 0, overlap)
            fade_in = np.linspace(0, 1, overlap)
            result[-overlap:] = result[-overlap:] * fade_out + out_chunks[i][:overlap] * fade_in
            result = np.concatenate([result, out_chunks[i][overlap:]])
        else:
            result = np.concatenate([result, out_chunks[i]])
    return model_sr, result

def default_settings():
    return {
        "text_input": """Three Rings for the Elven-kings under the sky,

Seven for the Dwarf-lords in their halls of stone,

Nine for Mortal Men doomed to die,

One for the Dark Lord on his dark throne

In the Land of Mordor where the Shadows lie.

One Ring to rule them all, One Ring to find them,

One Ring to bring them all and in the darkness bind them

In the Land of Mordor where the Shadows lie.""",
        "separate_files_checkbox": False,
        "export_format_checkboxes": ["flac", "mp3"],
        "disable_watermark_checkbox": True,
        "num_generations_input": 1,
        "num_candidates_slider": 3,
        "max_attempts_slider": 3,
        "bypass_whisper_checkbox": False,
        "whisper_model_dropdown": "medium (~5–8 GB OpenAI / ~2.5–4.5 GB faster-whisper)",
        "use_faster_whisper_checkbox": True,
        "enable_parallel_checkbox": True,
        "use_longest_transcript_on_fail_checkbox": True,
        "num_parallel_workers_slider": 4,
        "exaggeration_slider": 0.5,
        "cfg_weight_slider": 1.0,
        "temp_slider": 0.75,
        "seed_input": 0,
        "enable_batching_checkbox": False,
        "smart_batch_short_sentences_checkbox": True,
        "to_lowercase_checkbox": True,
        "normalize_spacing_checkbox": True,
        "fix_dot_letters_checkbox": True,
        "remove_reference_numbers_checkbox": True,
        "use_auto_editor_checkbox": False,
        "keep_original_checkbox": False,
        "threshold_slider": 0.06,
        "margin_slider": 0.2,
        "normalize_audio_checkbox": False,
        "normalize_method_dropdown": "ebu",
        "normalize_level_slider": -24,
        "normalize_tp_slider": -2,
        "normalize_lra_slider": 7,
        "sound_words_field": "",
    }
        
settings = load_settings()        
# Download both punkt and punkt_tab if missing
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab')

os.environ["CUDA_LAUNCH_BLOCKING"] = "0"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🚀 Running on device: {DEVICE}")

# Global model management
MODEL = None
WHISPER_MODEL = None  # Global persistent Whisper model
WHISPER_MODEL_CONFIG = {"model_key": None, "use_faster_whisper": None, "device": None}

def get_or_load_whisper_model(model_key, use_faster_whisper, device):
    """
    Get or load Whisper model globally to prevent repeated load/unload cycles that cause segfaults.
    """
    global WHISPER_MODEL, WHISPER_MODEL_CONFIG
    
    # Check if we need to load a new model (config changed)
    current_config = {"model_key": model_key, "use_faster_whisper": use_faster_whisper, "device": device}
    
    if WHISPER_MODEL is None or WHISPER_MODEL_CONFIG != current_config:
        print(f"[DEBUG] Loading/reloading Whisper model: {model_key} (faster-whisper: {use_faster_whisper})")
        
        # If we have an existing model, try to clean it up safely
        if WHISPER_MODEL is not None:
            try:
                print("[DEBUG] Safely cleaning up previous Whisper model...")
                torch.cuda.empty_cache()
                gc.collect()
                time.sleep(0.1)  # Give GC time to work
            except Exception as e:
                print(f"[WARNING] Error during Whisper model cleanup: {e}")
        
        # Load new model
        try:
            WHISPER_MODEL = load_whisper_backend(model_key, use_faster_whisper, device)
            WHISPER_MODEL_CONFIG = current_config
            print(f"[DEBUG] Whisper model loaded successfully: {model_key}")
        except Exception as e:
            print(f"[ERROR] Failed to load Whisper model {model_key}: {e}")
            WHISPER_MODEL = None
            WHISPER_MODEL_CONFIG = {"model_key": None, "use_faster_whisper": None, "device": None}
            raise
    else:
        print(f"[DEBUG] Using existing Whisper model: {model_key}")
    
    return WHISPER_MODEL

def load_whisper_backend(model_name, use_faster_whisper, device):
    """Load Whisper backend with enhanced error handling."""
    try:
        if use_faster_whisper:
            print(f"[DEBUG] Loading faster-whisper model: {model_name}")
            return FasterWhisperModel(model_name, device=device, compute_type="float16" if device=="cuda" else "float32")
        else:
            import whisper
            print(f"[DEBUG] Loading openai-whisper model: {model_name}")
            return whisper.load_model(model_name, device=device)
    except Exception as e:
        print(f"[ERROR] Failed to load Whisper backend {model_name}: {e}")
        # Clean up any partial state
        torch.cuda.empty_cache()
        gc.collect()
        raise

def get_or_load_model():
    global MODEL
    if MODEL is None:
        print("Model not loaded, initializing...")
        MODEL = ChatterboxTTS.from_pretrained(DEVICE)
        if hasattr(MODEL, 'to') and str(MODEL.device) != DEVICE:
            MODEL.to(DEVICE)
        print(f"Model loaded on device: {getattr(MODEL, 'device', 'unknown')}")
    return MODEL

try:
    get_or_load_model()
except Exception as e:
    print(f"CRITICAL: Failed to load model. Error: {e}")

def set_seed(seed: int):
    torch.manual_seed(seed)
    if DEVICE == "cuda":
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    random.seed(seed)
    np.random.seed(seed)

def normalize_whitespace(text: str) -> str:
    return re.sub(r'\s{2,}', ' ', text.strip())

def replace_letter_period_sequences(text: str) -> str:
    def replacer(match):
        cleaned = match.group(0).rstrip('.')
        letters = cleaned.split('.')
        return ' '.join(letters)
    return re.sub(r'\b(?:[A-Za-z]\.){2,}', replacer, text)
    
def remove_inline_reference_numbers(text):
    # Remove reference numbers after sentence-ending punctuation, but keep the punctuation
    pattern = r'([.!?,\"\'")\]])(\d+)(?=\s|$)'
    return re.sub(pattern, r'\1', text)


def split_into_sentences(text):
    # NLTK's Punkt tokenizer handles abbreviations and common English quirks
    return sent_tokenize(text)

def split_long_sentence(sentence, max_len=300, seps=None):
    """
    Recursively split a sentence into chunks of <= max_len using a sequence of separators.
    Tries each separator in order, splitting further as needed.
    """
    if seps is None:
        seps = [';', ':', '-', ',', ' ']

    sentence = sentence.strip()
    if len(sentence) <= max_len:
        return [sentence]

    if not seps:
        # Fallback: force split every max_len chars
        return [sentence[i:i+max_len].strip() for i in range(0, len(sentence), max_len)]

    sep = seps[0]
    parts = sentence.split(sep)

    if len(parts) == 1:
        # Separator not found, try next separator
        return split_long_sentence(sentence, max_len, seps=seps[1:])

    # Now recursively process each part, joining separator back except for the first
    chunks = []
    current = parts[0].strip()
    for part in parts[1:]:
        candidate = (current + sep + part).strip()
        if len(candidate) > max_len:
            # Split current chunk further with the next separator
            chunks.extend(split_long_sentence(current.strip(), max_len, seps=seps[1:]))
            current = part.strip()
        else:
            current = candidate
    # Process the last current
    if current:
        if len(current) > max_len:
            chunks.extend(split_long_sentence(current.strip(), max_len, seps=seps[1:]))
        else:
            chunks.append(current.strip())

    return chunks

    # Fallback: force split every max_len chars
    #return [sentence[i:i+max_len].strip() for i in range(0, len(sentence), max_len)]

def group_sentences(sentences, max_chars=300):
    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        if not sentence:
            print(f"\033[32m[DEBUG] Skipping empty sentence\033[0m")
            continue
        sentence = sentence.strip()
        sentence_len = len(sentence)

        print(f"\033[32m[DEBUG] Processing sentence: len={sentence_len}, content='\033[33m{sentence}...'\033[0m")

        if sentence_len > 300:
            print(f"\033[32m[DEBUG] Splitting overlong sentence of {sentence_len} chars\033[0m")
            for chunk in split_long_sentence(sentence, 300):
                if len(chunk) > max_chars:
                    # For extremely long non-breakable segments, just chunk them
                    for i in range(0, len(chunk), max_chars):
                        chunks.append(chunk[i:i+max_chars])
                else:
                    chunks.append(chunk)
            current_chunk = []
            current_length = 0
            continue  # Skip the rest of the loop for this sentence

        if sentence_len > max_chars:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                print(f"\033[32m[DEBUG] Finalized chunk: {' '.join(current_chunk)}...\033[0m")
            chunks.append(sentence)
            print(f"\033[32m[DEBUG] Added long sentence as chunk: {sentence}...\033[0m")
            current_chunk = []
            current_length = 0
        elif current_length + sentence_len + (1 if current_chunk else 0) <= max_chars:
            current_chunk.append(sentence)
            current_length += sentence_len + (1 if current_chunk else 0)
            print(f"\033[32m[DEBUG] Adding sentence to chunk: {sentence}...\033[0m")
        else:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                print(f"\033[32m[DEBUG] Finalized chunk: {' '.join(current_chunk)}...\033[0m")
            current_chunk = [sentence]
            current_length = sentence_len
            print(f"\033[32m[DEBUG] Starting new chunk with: {sentence}...\033[0m")

    if current_chunk:
        chunks.append(" ".join(current_chunk))
        print(f"\033[32m[DEBUG] Finalized final chunk: {' '.join(current_chunk)}...\033[0m")

    print(f"\033[32m[DEBUG] Total chunks created: {len(chunks)}\033[0m")
    for i, chunk in enumerate(chunks):
        print(f"\033[32m[DEBUG] Chunk {i}: len={len(chunk)}, content='\033[33m{chunk}...'\033[0m")

    return chunks

def smart_append_short_sentences(sentences, max_chars=300):
    new_groups = []
    i = 0
    while i < len(sentences):
        current = sentences[i].strip()
        if len(current) >= 20:
            new_groups.append(current)
            i += 1
        else:
            appended = False
            if i + 1 < len(sentences):
                next_sentence = sentences[i + 1].strip()
                if len(current + " " + next_sentence) <= max_chars:
                    new_groups.append(current + " " + next_sentence)
                    i += 2
                    appended = True
            if not appended and new_groups:
                if len(new_groups[-1] + " " + current) <= max_chars:
                    new_groups[-1] += " " + current
                    i += 1
                    appended = True
            if not appended:
                new_groups.append(current)
                i += 1
    return new_groups

def normalize_with_ffmpeg(input_wav, output_wav, method="ebu", i=-24, tp=-2, lra=7):
    if method == "ebu":
        loudnorm = f"loudnorm=I={i}:TP={tp}:LRA={lra}"
        (
            ffmpeg
            .input(input_wav)
            .output(output_wav, af=loudnorm)
            .overwrite_output()
            .run(quiet=True)
        )
    elif method == "peak":
        (
            ffmpeg
            .input(input_wav)
            .output(output_wav, af="dynaudnorm")
            .overwrite_output()
            .run(quiet=True)
        )
    else:
        raise ValueError("Unknown normalization method.")
    os.replace(output_wav, input_wav)

def get_wav_duration(path):
    try:
        return librosa.get_duration(filename=path)
    except Exception as e:
        print(f"[ERROR] librosa.get_duration failed: {e}")
        return float('inf')

def normalize_for_compare_all_punct(text):
    text = re.sub(r'[–—-]', ' ', text)
    text = re.sub(rf"[{re.escape(string.punctuation)}]", '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.lower().strip()

def fuzzy_match(text1, text2, threshold=1.0):
    t1 = normalize_for_compare_all_punct(text1)
    t2 = normalize_for_compare_all_punct(text2)
    seq = difflib.SequenceMatcher(None, t1, t2)
    return seq.ratio() >= threshold

def parse_sound_word_field(user_input):
    # Accepts comma or newline separated, allows 'sound=>replacement'
    lines = [l.strip() for l in user_input.split('\n') if l.strip()]
    result = []
    for line in lines:
        if '=>' in line:
            pattern, replacement = line.split('=>', 1)
            result.append((pattern.strip(), replacement.strip()))
        else:
            result.append((line, ''))  # Remove (replace with empty string)
    return result

def smart_remove_sound_words(text, sound_words):
    for pattern, replacement in sound_words:
        if replacement:
            # 1. Handle possessive: "Baggins's" or "Baggins'" (optionally with s or S after apostrophe)
            text = re.sub(
                r'(?i)(%s)([’\']s?)' % re.escape(pattern),
                lambda m: replacement + "'s" if m.group(2) else replacement,
                text
            )
            # 2. Replace word in quotes
            text = re.sub(
                r'(["\'])%s(["\'])' % re.escape(pattern),
                lambda m: f"{m.group(1)}{replacement}{m.group(2)}",
                text,
                flags=re.IGNORECASE
            )
            # If pattern is a punctuation character (like dash), replace all
            if all(char in "-–—" for char in pattern.strip()):
                text = re.sub(re.escape(pattern), replacement, text)
            else:
                # 3. Replace as whole word (not in quotes)
                text = re.sub(
                    r'\b%s\b' % re.escape(pattern),
                    replacement,
                    text,
                    flags=re.IGNORECASE
                )
        else:
            # Remove only the pattern itself, not adjacent spaces
            text = re.sub(
                r'%s' % re.escape(pattern),
                '',
                text,
                flags=re.IGNORECASE
            )

    # --- Fix accidental joining of words caused by quote removal ---
    # Add a space if a letter is next to a letter and was separated by removed quote
    #text = re.sub(r'(\w)([’\'"")(\w)', r'\1 \3', text)
    # Add a space between lowercase and uppercase, likely joined words (e.g., rainbowPride)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    # --- Clean up doubled-up commas and extra spaces ---
    text = re.sub(r'([,\s]+,)+', ',', text)
    text = re.sub(r',\s*,+', ',', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'(\s+,|,\s+)', ', ', text)
    text = re.sub(r'(^|[\.!\?]\s*),+', r'\1', text)
    text = re.sub(r',+\s*([\.!\?])', r'\1', text)
    return text.strip()


def convert_markdown_to_text(markdown_content: str) -> str:
    """
    Convert markdown content to plain text by removing markdown formatting.
    This function handles common markdown elements like headers, bold, italic, links, etc.
    """
    # Convert markdown to HTML first
    html = markdown.markdown(markdown_content)
    
    # Remove HTML tags to get plain text
    import re
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', html)
    # Decode HTML entities
    import html
    text = html.unescape(text)
    # Clean up extra whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text


def generate_clean_filename(input_basename: str, export_format: str, gen_index: int = 0, num_generations: int = 1) -> str:
    """
    Generate a clean filename based on the input file name.
    If multiple generations, append generation number.
    """
    # Clean the basename (remove special characters, keep only alphanumeric, spaces, and common punctuation)
    import re
    clean_basename = re.sub(r'[^a-zA-Z0-9\s\-_\.]', '', input_basename)
    clean_basename = re.sub(r'\s+', '_', clean_basename.strip())
    
    # If multiple generations, add generation number
    if num_generations > 1:
        filename = f"{clean_basename}_gen{gen_index+1}.{export_format}"
    else:
        filename = f"{clean_basename}.{export_format}"
    
    return filename


def whisper_check_mp(candidate_path, target_text, whisper_model, use_faster_whisper=False):
    import difflib
    import re
    import string
    import os

    def normalize_for_compare_all_punct(text):
        text = re.sub(r'[–—-]', ' ', text)
        text = re.sub(rf"[{re.escape(string.punctuation)}]", '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.lower().strip()

    try:
        print(f"\033[32m[DEBUG] Whisper checking: {candidate_path}\033[0m")
        if use_faster_whisper:
            segments, info = whisper_model.transcribe(candidate_path)
            transcribed = "".join([seg.text for seg in segments]).strip().lower()
        else:
            result = whisper_model.transcribe(candidate_path)
            transcribed = result['text'].strip().lower()
        print(f"\033[32m[DEBUG] Whisper transcription: '\033[33m{transcribed}' for candidate '{os.path.basename(candidate_path)}'\033[0m")
        score = difflib.SequenceMatcher(
            None,
            normalize_for_compare_all_punct(transcribed),
            normalize_for_compare_all_punct(target_text.strip().lower())
        ).ratio()
        print(f"\033[32m[DEBUG] Score: {score:.3f} (target: '\033[33m{target_text}')\033[0m")
        return (candidate_path, score, transcribed)
    except Exception as e:
        print(f"[ERROR] Whisper transcription failed for {candidate_path}: {e}")
        return (candidate_path, 0.0, f"ERROR: {e}")
        
        
def process_one_chunk(
    model, sentence_group, idx, gen_index, this_seed,
    audio_prompt_path_input, exaggeration_input, temperature_input, cfgw_input,
    disable_watermark, num_candidates_per_chunk, max_attempts_per_candidate,
    bypass_whisper_checking,
    retry_attempt_number=1
):
    candidates = []
    try:
        if not sentence_group.strip():
            print(f"\033[32m[DEBUG] Skipping empty sentence group at index {idx}\033[0m")
            return (idx, candidates)
        if len(sentence_group) > 300:
            print(f"\033[33m[WARNING] Very long sentence group at index {idx} (len={len(sentence_group)}); proceeding anyway.\033[0m")

        print(f"\033[32m[DEBUG] Processing group {idx}: len={len(sentence_group)}:\033[33m {sentence_group}\033[0m")

        for cand_idx in range(num_candidates_per_chunk):
            for attempt in range(max_attempts_per_candidate):
                if cand_idx == 0 and attempt == 0:
                    candidate_seed = this_seed
                else:
                    candidate_seed = random.randint(1, 2**32-1)
                set_seed(candidate_seed)
                try:
                    print(f"\033[32m[DEBUG] Generating candidate {cand_idx+1} attempt {attempt+1} for chunk {idx}...\033[0m")
#                    print(f"[TTS DEBUG] audio_prompt_path passed: {audio_prompt_path_input!r}")
                    wav = model.generate(
                        sentence_group,
                        audio_prompt_path=audio_prompt_path_input,
                        exaggeration=min(exaggeration_input, 1.0),
                        temperature=temperature_input,
                        cfg_weight=cfgw_input,
                        apply_watermark=not disable_watermark
                    )
                    

                    candidate_path = f"temp/gen{gen_index+1}_chunk_{idx:03d}_cand_{cand_idx+1}_try{retry_attempt_number}_seed{candidate_seed}.wav"
                    torchaudio.save(candidate_path, wav, model.sr)
                    for _ in range(10):
                        if os.path.exists(candidate_path) and os.path.getsize(candidate_path) > 1024:
                            break
                        time.sleep(0.05)
                    duration = get_wav_duration(candidate_path)
                    print(f"\033[32m[DEBUG] Saved candidate {cand_idx+1}, attempt {attempt+1}, duration={duration:.3f}s: {candidate_path}\033[0m")
                    candidates.append({
                        'path': candidate_path,
                        'duration': duration,
                        'sentence_group': sentence_group,
                        'cand_idx': cand_idx,
                        'attempt': attempt,
                    })
                    break
                except Exception as e:
                    print(f"[ERROR] Candidate {cand_idx+1} generation attempt {attempt+1} failed: {e}")
    except Exception as exc:
        print(f"[ERROR] Exception in chunk {idx}: {exc}")
    return (idx, candidates)

def generate_and_preview(*args):
    try:
        print("[INFO] 🚀 Starting TTS generation...")
        output_paths = generate_batch_tts(*args)
        audio_files = [p for p in output_paths if os.path.splitext(p)[1].lower() in [".wav", ".mp3", ".flac"]]
        dropdown_value = audio_files[0] if audio_files else None
        
        if output_paths:
            print(f"[INFO] ✅ Generation completed successfully! Generated {len(output_paths)} file(s).")
            print("[INFO] 🎵 Ready for next generation. Interface remains open.")
        else:
            print("[WARNING] ⚠️ No output files generated. Please check your settings.")
            
        return output_paths, gr.Dropdown(choices=audio_files, value=dropdown_value), dropdown_value
    except Exception as e:
        print(f"[ERROR] ❌ Generation failed: {e}")
        print("[INFO] 🔄 Interface remains open. You can try again.")
        return [], gr.Dropdown(choices=[], value=None), None
    

def update_audio_preview(selected_path):
    return selected_path

@spaces.GPU
def generate_batch_tts(
    text: str,
    text_file,
    audio_prompt_path_input,
    exaggeration_input: float,
    temperature_input: float,
    seed_num_input: int,
    cfgw_input: float,
    use_auto_editor: bool,
    ae_threshold: float,
    ae_margin: float,
    export_formats: list,
    enable_batching: bool,
    to_lowercase: bool,
    normalize_spacing: bool,
    fix_dot_letters: bool,
    remove_reference_numbers: bool,
    keep_original_wav: bool,
    smart_batch_short_sentences: bool,
    disable_watermark: bool,
    num_generations: int,
    normalize_audio: bool,
    normalize_method: str,
    normalize_level: float,
    normalize_tp: float,
    normalize_lra: float,
    num_candidates_per_chunk: int,
    max_attempts_per_candidate: int,
    bypass_whisper_checking: bool,
    whisper_model_name: str,
    enable_parallel: bool = True,
    num_parallel_workers: int = 4,
    use_longest_transcript_on_fail: bool = False,
    sound_words_field: str = "",
    use_faster_whisper: bool = False,
    generate_separate_audio_files: bool = False,
) -> str:
    print(f"[DEBUG] Received audio_prompt_path_input: {audio_prompt_path_input!r}")

    if not audio_prompt_path_input or (isinstance(audio_prompt_path_input, str) and not os.path.isfile(audio_prompt_path_input)):
        audio_prompt_path_input = None
    model = get_or_load_model()

    # PATCH: Get file basename (to prepend) if a text file was uploaded
    # Support for multiple file uploads
    # PATCH: Get file basename (to prepend) if a text file was uploaded
    # Support for multiple file uploads
    input_basename = ""

    # Robust handling for Gradio's file input (can be None, False, or list containing such)
    files = []
    if text_file:
        files = text_file if isinstance(text_file, list) else [text_file]
        # Remove any entry that's not a file-like object with a .name attribute (filters out None, False, bool)
        files = [f for f in files if hasattr(f, "name") and isinstance(getattr(f, "name", None), str)]

    if files:
        # If generating separate audio files per text file:
        if generate_separate_audio_files:
            all_jobs = []
            for fobj in files:
                try:
                    fname = os.path.basename(fobj.name)
                    base = os.path.splitext(fname)[0]
                    # Keep original filename for cleaner output naming
                    original_base = base
                    base = re.sub(r'[^a-zA-Z0-9_\-]', '_', base)
                    with open(fobj.name, "r", encoding="utf-8") as f:
                        file_text = f.read()
                    
                    # Convert markdown to plain text if it's a .md file
                    if fname.lower().endswith('.md'):
                        file_text = convert_markdown_to_text(file_text)
                        print(f"[INFO] Converted markdown file: {fname}")
                    
                    all_jobs.append((file_text, original_base))
                except Exception as e:
                    print(f"[ERROR] Failed to read file: {getattr(fobj, 'name', repr(fobj))} | {e}")
            # Now process each file separately and collect outputs
            all_outputs = []
            for job_text, base in all_jobs:
                print(f"[DEBUG] Starting TTS for file: {base}")
                try:
                    output_paths = process_text_for_tts(
                        job_text, base,
                        audio_prompt_path_input,
                        exaggeration_input, temperature_input, seed_num_input, cfgw_input,
                        use_auto_editor, ae_threshold, ae_margin, export_formats, enable_batching,
                        to_lowercase, normalize_spacing, fix_dot_letters, remove_reference_numbers, keep_original_wav,
                        smart_batch_short_sentences, disable_watermark, num_generations,
                        normalize_audio, normalize_method, normalize_level, normalize_tp,
                        normalize_lra, num_candidates_per_chunk, max_attempts_per_candidate,
                        bypass_whisper_checking, whisper_model_name, enable_parallel,
                        num_parallel_workers, use_longest_transcript_on_fail, sound_words_field, use_faster_whisper
                    )
                    print(f"[DEBUG] process_text_for_tts returned: {type(output_paths)} with {len(output_paths) if hasattr(output_paths, '__len__') else 'unknown'} items")
                    
                    # Ensure output_paths is a list before extending
                    if output_paths is None:
                        output_paths = []
                    elif not isinstance(output_paths, (list, tuple)):
                        output_paths = [output_paths]
                    
                    all_outputs.extend(output_paths)
                    print(f"[DEBUG] Completed TTS for file: {base}, generated {len(output_paths)} files")
                    
                    # Add memory management between files
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    print("[DEBUG] Cleared memory after file")
                except Exception as e:
                    print(f"[ERROR] Failed TTS for file {base}: {e}")
                    import traceback
                    traceback.print_exc()
            return all_outputs  # Return list of output files

        # ELSE (default: join all text files as one, as before)
        all_text = []
        basenames = []
        for fobj in files:
            try:
                fname = os.path.basename(fobj.name)
                base = os.path.splitext(fname)[0]
                # Keep original filename for cleaner output naming
                original_base = base
                base = re.sub(r'[^a-zA-Z0-9_\-]', '_', base)
                basenames.append(original_base)
                with open(fobj.name, "r", encoding="utf-8") as f:
                    file_content = f.read()
                
                # Convert markdown to plain text if it's a .md file
                if fname.lower().endswith('.md'):
                    file_content = convert_markdown_to_text(file_content)
                    print(f"[INFO] Converted markdown file: {fname}")
                
                all_text.append(file_content)
            except Exception as e:
                print(f"[ERROR] Failed to read file: {getattr(fobj, 'name', repr(fobj))} | {e}")
        text = "\n\n".join(all_text)
        # Use the first filename as the base, or combine if multiple files
        if len(basenames) == 1:
            input_basename = basenames[0]
        else:
            input_basename = "_".join(basenames)

        return process_text_for_tts(
            text, input_basename, audio_prompt_path_input,
            exaggeration_input, temperature_input, seed_num_input, cfgw_input,
            use_auto_editor, ae_threshold, ae_margin, export_formats, enable_batching,
            to_lowercase, normalize_spacing, fix_dot_letters, remove_reference_numbers, keep_original_wav,
            smart_batch_short_sentences, disable_watermark, num_generations,
            normalize_audio, normalize_method, normalize_level, normalize_tp,
            normalize_lra, num_candidates_per_chunk, max_attempts_per_candidate,
            bypass_whisper_checking, whisper_model_name, enable_parallel,
            num_parallel_workers, use_longest_transcript_on_fail, sound_words_field, use_faster_whisper
        )
    else:
        # No text file: just process the Text Input box as one job
        input_basename = "text_input_"
        return process_text_for_tts(
            text, input_basename, audio_prompt_path_input,
            exaggeration_input, temperature_input, seed_num_input, cfgw_input,
            use_auto_editor, ae_threshold, ae_margin, export_formats, enable_batching,
            to_lowercase, normalize_spacing, fix_dot_letters, remove_reference_numbers, keep_original_wav,
            smart_batch_short_sentences, disable_watermark, num_generations,
            normalize_audio, normalize_method, normalize_level, normalize_tp,
            normalize_lra, num_candidates_per_chunk, max_attempts_per_candidate,
            bypass_whisper_checking, whisper_model_name, enable_parallel,
            num_parallel_workers, use_longest_transcript_on_fail, sound_words_field, use_faster_whisper
        )

def process_text_for_tts(
    text,
    input_basename,
    audio_prompt_path_input,
    exaggeration_input,
    temperature_input,
    seed_num_input,
    cfgw_input,
    use_auto_editor,
    ae_threshold,
    ae_margin,
    export_formats,
    enable_batching,
    to_lowercase,
    normalize_spacing,
    fix_dot_letters,
    remove_reference_numbers,
    keep_original_wav,
    smart_batch_short_sentences,
    disable_watermark,
    num_generations,
    normalize_audio,
    normalize_method,
    normalize_level,
    normalize_tp,
    normalize_lra,
    num_candidates_per_chunk,
    max_attempts_per_candidate,
    bypass_whisper_checking,
    whisper_model_name,
    enable_parallel,
    num_parallel_workers,
    use_longest_transcript_on_fail,
    sound_words_field,
    use_faster_whisper=False,
):

    

    model = get_or_load_model()
    whisper_model = None
    if not text or len(text.strip()) == 0:
        raise ValueError("No text provided.")
    
    # ---- NEW: Apply sound word removals/replacements ----
    if sound_words_field and sound_words_field.strip():
        sound_words = parse_sound_word_field(sound_words_field)
        if sound_words:
            text = smart_remove_sound_words(text, sound_words)

    if to_lowercase:
        text = text.lower()
    if normalize_spacing:
        text = normalize_whitespace(text)
    if fix_dot_letters:
        text = replace_letter_period_sequences(text)
    if remove_reference_numbers:
        text = remove_inline_reference_numbers(text)

    print("[DEBUG] After reference number removal:", repr(text))  # <--- ADD THIS LINE HERE

    os.makedirs("temp", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    for f in os.listdir("temp"):
        os.remove(os.path.join("temp", f))

    sentences = split_into_sentences(text)
    print(f"\033[32m[DEBUG] Split text into {len(sentences)} sentences.\033[0m")

    def enforce_min_chunk_length(chunks, min_len=20, max_len=300):
        out = []
        i = 0
        while i < len(chunks):
            current = chunks[i].strip()
            if len(current) >= min_len or i == len(chunks) - 1:
                out.append(current)
                i += 1
            else:
                # Try to merge with the next chunk if possible
                if i + 1 < len(chunks):
                    merged = current + " " + chunks[i + 1]
                    if len(merged) <= max_len:
                        out.append(merged)
                        i += 2
                    else:
                        out.append(current)
                        i += 1
                else:
                    out.append(current)
                    i += 1
        return out

    # Add memory management and safety checks
    def check_memory_usage():
        """Check available GPU memory and warn if running low"""
        try:
            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / 1024**3
                reserved = torch.cuda.memory_reserved() / 1024**3
                total = torch.cuda.get_device_properties(0).total_memory / 1024**3
                free = total - reserved
                
                print(f"\033[33m[MEMORY] GPU: {allocated:.1f}GB allocated, {reserved:.1f}GB reserved, {free:.1f}GB free\033[0m")
                
                if free < 2.0:  # Less than 2GB free
                    print(f"\033[31m[WARNING] Low GPU memory! Only {free:.1f}GB free. Consider reducing batch size or text length.\033[0m")
                    return False
                return True
        except Exception as e:
            print(f"[WARNING] Could not check GPU memory: {e}")
            return True

    def safe_process_chunk(chunk_text, chunk_index, max_retries=3):
        """Safely process a chunk with error handling and memory management"""
        for attempt in range(max_retries):
            try:
                # Check memory before processing
                if not check_memory_usage():
                    print(f"\033[31m[ERROR] Insufficient memory for chunk {chunk_index}. Skipping.\033[0m")
                    return None
                
                # Force garbage collection
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                
                return chunk_text
            except Exception as e:
                print(f"\033[31m[ERROR] Failed to process chunk {chunk_index} (attempt {attempt + 1}): {e}\033[0m")
                if attempt == max_retries - 1:
                    print(f"\033[31m[ERROR] Giving up on chunk {chunk_index} after {max_retries} attempts\033[0m")
                    return None
                time.sleep(1)  # Wait before retry
        return None

    sentence_groups = None
    if enable_batching:
        sentence_groups = group_sentences(sentences, max_chars=300)
        if smart_batch_short_sentences:  # NEW: now works as post-processing!
            sentence_groups = enforce_min_chunk_length(sentence_groups)
    elif smart_batch_short_sentences:
        sentence_groups = smart_append_short_sentences(sentences)
        sentence_groups = enforce_min_chunk_length(sentence_groups)
    else:
        sentence_groups = sentences

    # Add safety check for extremely long chunks
    max_safe_chunk_length = 500  # Maximum safe chunk length
    filtered_groups = []
    for i, group in enumerate(sentence_groups):
        if len(group) > max_safe_chunk_length:
            print(f"\033[31m[WARNING] Chunk {i} is too long ({len(group)} chars). Splitting into smaller chunks.\033[0m")
            # Split long chunks into smaller pieces
            words = group.split()
            current_chunk = ""
            for word in words:
                if len(current_chunk + " " + word) <= max_safe_chunk_length:
                    current_chunk += (" " + word) if current_chunk else word
                else:
                    if current_chunk:
                        filtered_groups.append(current_chunk.strip())
                    current_chunk = word
            if current_chunk:
                filtered_groups.append(current_chunk.strip())
        else:
            filtered_groups.append(group)
    
    sentence_groups = filtered_groups
    print(f"\033[32m[DEBUG] Final sentence groups: {len(sentence_groups)} chunks\033[0m")

    output_paths = []
    for gen_index in range(num_generations):
        if seed_num_input == 0:
            this_seed = random.randint(1, 2**32 - 1)
        else:
            this_seed = int(seed_num_input) + gen_index
        set_seed(this_seed)

        print(f"\033[43m[DEBUG] Starting generation {gen_index+1}/{num_generations} with seed {this_seed}\033[0m")

        chunk_candidate_map = {}
        waveform_list = []  # Initialize waveform_list here to ensure it's defined

        # -------- CHUNK GENERATION --------
        if enable_parallel:
            total_chunks = len(sentence_groups)
            completed = 0
            failed_chunks = 0
            
            with ThreadPoolExecutor(max_workers=num_parallel_workers) as executor:
                futures = [
                    executor.submit(
                        process_one_chunk,
                        model, group, idx, gen_index, this_seed,
                        audio_prompt_path_input, exaggeration_input, temperature_input, cfgw_input,
                        disable_watermark, num_candidates_per_chunk, max_attempts_per_candidate, bypass_whisper_checking
                    )
                    for idx, group in enumerate(sentence_groups)
                ]
                
                for future in as_completed(futures):
                    try:
                        idx, candidates = future.result()
                        chunk_candidate_map[idx] = candidates
                        completed += 1
                        percent = int(100 * completed / total_chunks)
                        print(f"\033[36m[PROGRESS] Generated chunk {completed}/{total_chunks} ({percent}%)\033[0m")
                    except Exception as e:
                        failed_chunks += 1
                        print(f"\033[31m[ERROR] Failed to process chunk: {e}\033[0m")
                        if failed_chunks > total_chunks // 2:  # If more than half fail
                            print(f"\033[31m[CRITICAL] Too many chunks failed ({failed_chunks}/{total_chunks}). Stopping generation.\033[0m")
                            break
        else:
            # Sequential mode: Process chunks one by one
            failed_chunks = 0
            for idx, group in enumerate(sentence_groups):
                try:
                    idx, candidates = process_one_chunk(
                        model, group, idx, gen_index, this_seed,
                        audio_prompt_path_input, exaggeration_input, temperature_input, cfgw_input,
                        disable_watermark, num_candidates_per_chunk, max_attempts_per_candidate, bypass_whisper_checking
                    )
                    chunk_candidate_map[idx] = candidates
                    print(f"\033[36m[PROGRESS] Generated chunk {idx+1}/{len(sentence_groups)}\033[0m")
                except Exception as e:
                    failed_chunks += 1
                    print(f"\033[31m[ERROR] Failed to process chunk {idx}: {e}\033[0m")
                    if failed_chunks > len(sentence_groups) // 2:  # If more than half fail
                        print(f"\033[31m[CRITICAL] Too many chunks failed ({failed_chunks}/{len(sentence_groups)}). Stopping generation.\033[0m")
                        break

        # -------- WHISPER VALIDATION --------
        if not bypass_whisper_checking:
            print(f"\033[32m[DEBUG] Validating all candidates with Whisper for all chunks (sequentially)...\033[0m")
            model_key = whisper_model_map.get(whisper_model_name, "medium")
            whisper_model = get_or_load_whisper_model(model_key, use_faster_whisper, DEVICE)
            # Load model once
            try:
                all_candidates = []
                for chunk_idx, candidates in chunk_candidate_map.items():
                    for cand in candidates:
                        all_candidates.append((chunk_idx, cand))

                chunk_validations = {chunk_idx: [] for chunk_idx in chunk_candidate_map}
                chunk_failed_candidates = {chunk_idx: [] for chunk_idx in chunk_candidate_map}

                # Initial sequential Whisper validation
                for chunk_idx, cand in all_candidates:
                    candidate_path = cand['path']
                    sentence_group = cand['sentence_group']
                    try:
                        if not os.path.exists(candidate_path) or os.path.getsize(candidate_path) < 1024:
                            print(f"[ERROR] Candidate file missing or too small: {candidate_path}")
                            chunk_failed_candidates[chunk_idx].append((0.0, candidate_path, ""))
                            continue
                        path, score, transcribed = whisper_check_mp(candidate_path, sentence_group, whisper_model, use_faster_whisper)
                        print(f"\033[32m[DEBUG] [Chunk {chunk_idx}] {os.path.basename(candidate_path)}: score={score:.3f}, transcript=\033[33m'{transcribed}'\033[0m")
                        if score >= 0.90:  # Lowered from 0.95 for better legal text handling
                            chunk_validations[chunk_idx].append((cand['duration'], cand['path']))
                        else:
                            chunk_failed_candidates[chunk_idx].append((score, cand['path'], transcribed))
                    except Exception as e:
                        print(f"[ERROR] Whisper transcription failed for {candidate_path}: {e}")
                        chunk_failed_candidates[chunk_idx].append((0.0, candidate_path, ""))

                # Retry block for failed chunks
                retry_queue = [chunk_idx for chunk_idx in sorted(chunk_candidate_map.keys()) if not chunk_validations[chunk_idx]]
                chunk_attempts = {chunk_idx: 1 for chunk_idx in retry_queue}

                while retry_queue:
                    still_need_retry = [
                        chunk_idx for chunk_idx in retry_queue
                        if chunk_attempts[chunk_idx] < max_attempts_per_candidate
                    ]
                    if not still_need_retry:
                        break

                    print(f"\033[33m[RETRY] Retrying {len(still_need_retry)} chunks, attempt {chunk_attempts[still_need_retry[0]]+1} of {max_attempts_per_candidate}\033[0m")

                    retry_candidate_map = {}
                    with ThreadPoolExecutor(max_workers=num_parallel_workers) as executor:
                        futures = [
                            executor.submit(
                                process_one_chunk,
                                model,
                                chunk_candidate_map[chunk_idx][0]['sentence_group'] if chunk_candidate_map[chunk_idx] else sentence_groups[chunk_idx],
                                chunk_idx,
                                gen_index,
                                random.randint(1, 2**32-1),
                                audio_prompt_path_input, exaggeration_input, temperature_input, cfgw_input,
                                disable_watermark, num_candidates_per_chunk, 1,
                                bypass_whisper_checking,
                                chunk_attempts[chunk_idx] + 1
                            )
                            for chunk_idx in still_need_retry
                        ]
                        for future in as_completed(futures):
                            idx, candidates = future.result()
                            retry_candidate_map[idx] = candidates

                    for chunk_idx, candidates in retry_candidate_map.items():
                        for cand in candidates:
                            candidate_path = cand['path']
                            sentence_group = cand['sentence_group']
                            try:
                                if not os.path.exists(candidate_path) or os.path.getsize(candidate_path) < 1024:
                                    print(f"[ERROR] Retry candidate file missing or too small: {candidate_path}")
                                    chunk_failed_candidates[chunk_idx].append((0.0, candidate_path, ""))
                                    continue
                                path, score, transcribed = whisper_check_mp(candidate_path, sentence_group, whisper_model, use_faster_whisper)
                                print(f"\033[32m[DEBUG] [Chunk {chunk_idx}] RETRY {os.path.basename(candidate_path)}: score={score:.3f}, transcript=\033[33m'{transcribed}'\033[0m")
                                if score >= 0.90:  # Lowered from 0.95 for better legal text handling
                                    chunk_validations[chunk_idx].append((cand['duration'], cand['path']))
                                else:
                                    chunk_failed_candidates[chunk_idx].append((score, cand['path'], transcribed))
                            except Exception as e:
                                print(f"[ERROR] Whisper transcription failed for retry {candidate_path}: {e}")
                                chunk_failed_candidates[chunk_idx].append((0.0, candidate_path, ""))

                    retry_queue = [chunk_idx for chunk_idx in still_need_retry if not chunk_validations[chunk_idx]]
                    for chunk_idx in still_need_retry:
                        chunk_attempts[chunk_idx] += 1

                # Assemble waveform list
                for chunk_idx in sorted(chunk_candidate_map.keys()):
                    if chunk_validations[chunk_idx]:
                        best_path = sorted(chunk_validations[chunk_idx], key=lambda x: x[0])[0][1]
                        print(f"\033[32m[DEBUG] Selected {best_path} as best candidate for chunk {chunk_idx} \033[1;33m(PASSED Whisper check)\033[0m")
                        try:
                            waveform, sr = torchaudio.load(best_path)
                            print(f"[DEBUG] Loaded waveform for chunk {chunk_idx}: shape={waveform.shape}, sr={sr}")
                            
                            # Normalize to mono (1, N)
                            if waveform.ndim == 1:
                                waveform = waveform.unsqueeze(0)  # (N,) -> (1, N)
                            if waveform.shape[0] > 1:
                                waveform = waveform.mean(dim=0, keepdim=True)  # Stereo/multi -> mono
                            
                            waveform_list.append(waveform)
                        except Exception as e:
                            print(f"[ERROR] Failed to load waveform for chunk {chunk_idx} ({best_path}): {e}")
                    elif chunk_failed_candidates[chunk_idx]:
                        if use_longest_transcript_on_fail:
                            best_failed = max(chunk_failed_candidates[chunk_idx], key=lambda x: len(x[2]))
                            print(f"\033[33m[WARNING] No candidate passed for chunk {chunk_idx}. Using failed candidate with longest transcript: {best_failed[1]} (len={len(best_failed[2])})\033[0m")
                        else:
                            best_failed = max(chunk_failed_candidates[chunk_idx], key=lambda x: x[0])
                            print(f"\033[33m[WARNING] No candidate passed for chunk {chunk_idx}. Using failed candidate with highest score: {best_failed[1]} (score={best_failed[0]:.3f})\033[0m")
                        try:
                            waveform, sr = torchaudio.load(best_failed[1])
                            print(f"[DEBUG] Loaded waveform for chunk {chunk_idx}: shape={waveform.shape}, sr={sr}")
                            
                            # Normalize to mono (1, N)
                            if waveform.ndim == 1:
                                waveform = waveform.unsqueeze(0)  # (N,) -> (1, N)
                            if waveform.shape[0] > 1:
                                waveform = waveform.mean(dim=0, keepdim=True)  # Stereo/multi -> mono
                            
                            waveform_list.append(waveform)
                        except Exception as e:
                            print(f"[ERROR] Failed to load waveform for chunk {chunk_idx} ({best_failed[1]}): {e}")
                    else:
                        print(f"[ERROR] No candidates were generated for chunk {chunk_idx}.")
            finally:
                # Safe cleanup - only clear cache, don't unload the global model
                try:
                    print("[DEBUG] Clearing VRAM cache after Whisper validation (keeping model loaded)...")
                    torch.cuda.empty_cache()
                    gc.collect()
                    print("\033[32m[DEBUG] VRAM cache cleared after Whisper validation. Model remains loaded for next use.\033[0m")
                except Exception as e:
                    print(f"\033[31m[ERROR] Failed during post-Whisper cache cleanup: {e}\033[0m")
        else:
            # Bypass Whisper: pick shortest duration per chunk
            for chunk_idx in sorted(chunk_candidate_map.keys()):
                candidates = chunk_candidate_map[chunk_idx]
                # Only consider candidates whose files exist and are > 1024 bytes
                valid_candidates = [c for c in candidates if os.path.exists(c['path']) and os.path.getsize(c['path']) > 1024]
                if valid_candidates:
                    best = min(valid_candidates, key=lambda c: c['duration'])
                    print(f"\033[32m[DEBUG] [Bypass Whisper] Selected {best['path']} as shortest candidate for chunk {chunk_idx}\033[0m")
                    try:
                        waveform, sr = torchaudio.load(best['path'])
                        print(f"[DEBUG] Loaded waveform for chunk {chunk_idx}: shape={waveform.shape}, sr={sr}")
                        
                        # Normalize to mono (1, N)
                        if waveform.ndim == 1:
                            waveform = waveform.unsqueeze(0)  # (N,) -> (1, N)
                        if waveform.shape[0] > 1:
                            waveform = waveform.mean(dim=0, keepdim=True)  # Stereo/multi -> mono
                        
                        waveform_list.append(waveform)
                    except Exception as e:
                        print(f"[ERROR] Failed to load waveform for chunk {chunk_idx} ({best['path']}): {e}")
                else:
                    print(f"\033[33m[WARNING] No valid candidates found for chunk {chunk_idx} (all generations failed)\033[0m")
                    

        if not waveform_list:
            print(f"\033[33m[WARNING] No audio generated in generation {gen_index+1} (empty waveform_list)\033[0m")
            continue

        try:
            print(f"[DEBUG] Concatenating {len(waveform_list)} waveforms...")
            
            # Validate all waveforms before concatenation
            for i, w in enumerate(waveform_list):
                if w is None:
                    raise ValueError(f"Waveform {i} is None")
                if w.numel() == 0:
                    raise ValueError(f"Waveform {i} is empty")
                if w.shape[0] != 1:
                    print(f"[WARNING] Waveform {i} has unexpected channels: {w.shape[0]}, converting to mono")
                    w = w.mean(dim=0, keepdim=True)
                    waveform_list[i] = w
            
            # Safe concatenation
            full_audio = torch.cat(waveform_list, dim=1)
            print(f"[DEBUG] Full audio shape: {full_audio.shape}")
            
            # Validate output
            if full_audio.numel() == 0:
                raise ValueError("Concatenated audio is empty")
                
        except Exception as e:
            print(f"[ERROR] Failed to concatenate waveforms: {e}")
            print("Waveform details:")
            for i, w in enumerate(waveform_list):
                if w is not None:
                    print(f"  Chunk {i}: shape={w.shape}, dtype={w.dtype}, device={w.device}")
                else:
                    print(f"  Chunk {i}: None")
            continue  # Skip save if cat fails
        
        # Generate clean filename based on input file name
        clean_filename = generate_clean_filename(input_basename, "wav", gen_index, num_generations)
        wav_output = f"output/{clean_filename}"
        
        try:
            torchaudio.save(wav_output, full_audio, model.sr)
            print(f"[DEBUG] Saved WAV: {wav_output}")
        except Exception as e:
            print(f"[ERROR] Failed to save WAV {wav_output}: {e}")
            continue  # Skip rest of processing if save fails
        
        print(f"\33[104m[DEBUG] \33[5mFinal audio concatenated, output file: {wav_output}\033[0m")

        if use_auto_editor:
            try:
                # Use clean naming for auto-editor files
                clean_filename = generate_clean_filename(input_basename, "wav", gen_index, num_generations)
                cleaned_output = f"output/{clean_filename.replace('.wav', '_cleaned.wav')}"
                if keep_original_wav:
                    backup_path = f"output/{clean_filename.replace('.wav', '_original.wav')}"
                    os.rename(wav_output, backup_path)
                    auto_editor_input = backup_path
                else:
                    auto_editor_input = wav_output

                auto_editor_cmd = [
                    "auto-editor",
                    "--edit", f"audio:threshold={ae_threshold}",
                    "--margin", f"{ae_margin}s",
                    "--export", "audio",
                    auto_editor_input,
                    "-o", cleaned_output
                ]

                # Use safe subprocess with timeout to prevent hangs/crashes
                auto_editor_success = safe_subprocess_run(auto_editor_cmd, timeout=300)
                if not auto_editor_success:
                    print("[INFO] Auto-editor failed or timed out. Continuing without auto-editor processing...")
                else:
                    print(f"[DEBUG] Auto-editor completed successfully")

                if os.path.exists(cleaned_output):
                    os.replace(cleaned_output, wav_output)
                    print(f"\033[32m[DEBUG] Post-processed with auto-editor: {wav_output}\033[0m")
            except Exception as e:
                print(f"[ERROR] Auto-editor post-processing failed: {e}")

        if normalize_audio:
            try:
                # Use clean naming for normalization files
                clean_filename = generate_clean_filename(input_basename, "wav", gen_index, num_generations)
                norm_temp = f"output/{clean_filename.replace('.wav', '_norm.wav')}"
                normalize_with_ffmpeg(
                    wav_output,
                    norm_temp,
                    method=normalize_method,
                    i=normalize_level,
                    tp=normalize_tp,
                    lra=normalize_lra,
                )
                print(f"\033[32m[DEBUG] Post-processed with ffmpeg normalization: {wav_output}\033[0m")
            except Exception as e:
                print(f"[ERROR] ffmpeg normalization failed: {e}")

        gen_outputs = []
        for export_format in export_formats:
            if export_format.lower() == "wav":
                gen_outputs.append(wav_output)
            else:
                audio = AudioSegment.from_wav(wav_output)
                # Generate clean filename for each export format
                clean_filename = generate_clean_filename(input_basename, export_format, gen_index, num_generations)
                final_output = f"output/{clean_filename}"
                export_kwargs = {}
                if export_format.lower() == "mp3":
                    export_kwargs["bitrate"] = "320k"
                audio.export(final_output, format=export_format, **export_kwargs)
                gen_outputs.append(final_output)

        output_paths.extend(gen_outputs)

        if "wav" not in [fmt.lower() for fmt in export_formats]:
            try:
                os.remove(wav_output)
            except Exception as e:
                print(f"[ERROR] Could not remove temp wav file: {e}")
                
            # === Save settings CSV and JSON for this generation ===
        # Only include relevant fields and NOT the raw text_input
        settings_to_save = {
            "text_input": "",  # Intentionally blank for privacy
            "exaggeration_slider": exaggeration_input,
            "temp_slider": temperature_input,
            "seed_input": this_seed,
            "cfg_weight_slider": cfgw_input,
            "use_auto_editor_checkbox": use_auto_editor,
            "threshold_slider": ae_threshold,
            "margin_slider": ae_margin,
            "export_format_checkboxes": export_formats,
            "enable_batching_checkbox": enable_batching,
            "to_lowercase_checkbox": to_lowercase,
            "normalize_spacing_checkbox": normalize_spacing,
            "fix_dot_letters_checkbox": fix_dot_letters,
            "remove_reference_numbers_checkbox": remove_reference_numbers,
            "keep_original_checkbox": keep_original_wav,
            "smart_batch_short_sentences_checkbox": smart_batch_short_sentences,
            "disable_watermark_checkbox": disable_watermark,
            "num_generations_input": num_generations,
            "normalize_audio_checkbox": normalize_audio,
            "normalize_method_dropdown": normalize_method,
            "normalize_level_slider": normalize_level,
            "normalize_tp_slider": normalize_tp,
            "normalize_lra_slider": normalize_lra,
            "num_candidates_slider": num_candidates_per_chunk,
            "max_attempts_slider": max_attempts_per_candidate,
            "bypass_whisper_checkbox": bypass_whisper_checking,
            "whisper_model_dropdown": next((k for k, v in whisper_model_map.items() if v == whisper_model_name), whisper_model_name),
            "enable_parallel_checkbox": enable_parallel,
            "num_parallel_workers_slider": num_parallel_workers,
            "use_longest_transcript_on_fail_checkbox": use_longest_transcript_on_fail,
            "sound_words_field": sound_words_field,
            "use_faster_whisper_checkbox": use_faster_whisper,
            "separate_files_checkbox": False,  # Or True, if that option was used for this job
            "input_basename": input_basename,  # Additional info, optional
            "audio_prompt_path_input": audio_prompt_path_input,  # Additional info, optional
            "generation_time": datetime.datetime.now().isoformat(),
            #"output_audio_files": gen_outputs,  # Add this so each settings.json also points to its outputs!
        }

        # Name settings file after the first output audio file (base)
        base_out = gen_outputs[0].rsplit('.', 1)[0]  # E.g., output/audiofile_gen1_seedXXXXX
        csv_path = base_out + ".settings.csv"
        json_path = base_out + ".settings.json"

        # Save CSV (no output_audio_files in dict)
        save_settings_csv(settings_to_save, gen_outputs, csv_path)

        # Save JSON (add output_audio_files to dict)
        settings_for_json = settings_to_save.copy()
        settings_for_json["output_audio_files"] = gen_outputs
        save_settings_json(settings_for_json, json_path)

    print(f"\033[1;36m[DEBUG] \33[6;4;3;34;102mALL GENERATIONS COMPLETE. Outputs:\033[0m\n" + "\n".join(output_paths))
    return output_paths

# ----- UI SECTION -----
whisper_model_choices = [
    "tiny (~1 GB VRAM OpenAI / ~0.5 GB faster-whisper)",
    "base (~1.2–2 GB OpenAI / ~0.7–1 GB faster-whisper)",
    "small (~2–3 GB OpenAI / ~1.2–1.7 GB faster-whisper)",
    "medium (~5–8 GB OpenAI / ~2.5–4.5 GB faster-whisper)",
    "large (~10–13 GB OpenAI / ~4.5–6.5 GB faster-whisper)",
]

whisper_model_map = {
    "tiny (~1 GB VRAM OpenAI / ~0.5 GB faster-whisper)": "tiny",
    "base (~1.2–2 GB OpenAI / ~0.7–1 GB faster-whisper)": "base",
    "small (~2–3 GB OpenAI / ~1.2–1.7 GB faster-whisper)": "small",
    "medium (~5–8 GB OpenAI / ~2.5–4.5 GB faster-whisper)": "medium",
    "large (~10–13 GB OpenAI / ~4.5–6.5 GB faster-whisper)": "large"
}


def apply_settings_json(settings_json):
    import json
    if not settings_json:
        return [gr.update() for _ in range(35)]
    try:
        with open(settings_json.name, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        # This order must match the order of your Gradio inputs!
        return [
            loaded.get("text_input", ""),
            None,  # text_file_input: cannot load a file from JSON
            loaded.get("separate_files_checkbox", False),
            loaded.get("audio_prompt_path_input", ""),
            loaded.get("export_format_checkboxes", ["wav"]),
            loaded.get("disable_watermark_checkbox", False),
            loaded.get("num_generations_input", 1),
            loaded.get("num_candidates_slider", 3),
            loaded.get("max_attempts_slider", 3),
            loaded.get("bypass_whisper_checkbox", False),
            loaded.get("whisper_model_dropdown", "medium (~5–8 GB OpenAI / ~2.5–4.5 GB faster-whisper)"),
            loaded.get("use_faster_whisper_checkbox", True),
            loaded.get("enable_parallel_checkbox", True),
            loaded.get("use_longest_transcript_on_fail_checkbox", True),
            loaded.get("num_parallel_workers_slider", 4),
            loaded.get("exaggeration_slider", 0.5),
            loaded.get("cfg_weight_slider", 1.0),
            loaded.get("temp_slider", 0.75),
            loaded.get("seed_input", 0),
            loaded.get("enable_batching_checkbox", False),
            loaded.get("smart_batch_short_sentences_checkbox", True),
            loaded.get("to_lowercase_checkbox", True),
            loaded.get("normalize_spacing_checkbox", True),
            loaded.get("fix_dot_letters_checkbox", True),
            loaded.get("remove_reference_numbers_checkbox", True),
            loaded.get("use_auto_editor_checkbox", False),
            loaded.get("keep_original_checkbox", False),
            loaded.get("threshold_slider", 0.06),
            loaded.get("margin_slider", 0.2),
            loaded.get("normalize_audio_checkbox", False),
            loaded.get("normalize_method_dropdown", "ebu"),
            loaded.get("normalize_level_slider", -24),
            loaded.get("normalize_tp_slider", -2),
            loaded.get("normalize_lra_slider", 7),
            loaded.get("sound_words_field", ""),
        ]
    except Exception as e:
        print(f"[ERROR] Failed to load settings JSON: {e}")
        return [gr.update() for _ in range(35)]





def main():
    with gr.Blocks(title="Chatterbox TTS Extended", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🎧 Chatterbox TTS Extended")
        gr.Markdown("**💡 Tip:** This interface will stay open after processing. You can continue to use it for multiple generations!")
        with gr.Tabs():
            # TTS Tab (your original interface)
            with gr.Tab("TTS & Multi-Gen"):
                with gr.Row():
                    with gr.Column():
                        text_input = gr.Textbox(label="Text Input", lines=6, value=settings["text_input"])
                        text_file_input = gr.File(label="Text File(s) (.txt, .md)", file_types=[".txt", ".md"], file_count="multiple")
                        separate_files_checkbox = gr.Checkbox(label="Generate separate audio files per text file", value=settings["separate_files_checkbox"])
                        ref_audio_input = gr.Audio(sources=["upload", "microphone"], type="filepath", label="Reference Audio (Optional)")
                        export_format_checkboxes = gr.CheckboxGroup(
                            choices=["wav", "mp3", "flac"],
                            value=settings["export_format_checkboxes"],  # default selection
                            label="Export Format(s): Select one or more"
                        )
                        disable_watermark_checkbox = gr.Checkbox(label="Disable Perth Watermark", value=settings["disable_watermark_checkbox"], visible=False)
                        num_generations_input = gr.Number(value=settings["num_generations_input"], precision=0, label="Number of Generations")
                        num_candidates_slider = gr.Slider(1, 10, value=settings["num_candidates_slider"], step=1, label="Number of Candidates Per Chunk (after batching) - [reduces the chance of artifacts and hallucinations]")
                        max_attempts_slider = gr.Slider(1, 10, value=settings["max_attempts_slider"], step=1, label="Max Attempts Per Candidate (Whisper check retries)")
                        bypass_whisper_checkbox = gr.Checkbox(label="Bypass Whisper Checking (pick shortest candidate regardless of transcription)", value=settings["bypass_whisper_checkbox"])
                        whisper_model_dropdown = gr.Dropdown(
                            choices=whisper_model_choices,
                            value=settings["whisper_model_dropdown"],
                            label="Whisper Sync Model (with VRAM requirements)",
                            info="Select a Whisper model for sync/transcription; smaller models use less VRAM but are less accurate."
                        )
                        use_faster_whisper_checkbox = gr.Checkbox(
                            label="Use faster-whisper (SYSTRAN) backend for Whisper validation (much faster, less VRAM, almost as accurate)",
                            value=settings["use_faster_whisper_checkbox"]
                        )
                        enable_parallel_checkbox = gr.Checkbox(label="Enable Parallel Chunk Processing", value=settings["enable_parallel_checkbox"], visible=False)
                        use_longest_transcript_on_fail_checkbox = gr.Checkbox(
                        label="When all candidates fail Whisper check, pick candidate with longest transcript (not highest fuzzy match score)",
                        value=settings["use_longest_transcript_on_fail_checkbox"]
                        )
                        num_parallel_workers_slider = gr.Slider(1, 8, value=settings["num_parallel_workers_slider"], step=1, label="Parallel Workers - set to 1 for sequential processing")
                        load_settings_file = gr.File(label="Load Settings (.json)", file_types=[".json"])

                        run_button = gr.Button("Generate")
                    with gr.Column():
                        exaggeration_slider = gr.Slider(0.0, 2.0, value=settings["exaggeration_slider"], step=0.1, label="Emotion Exaggeration")
                        cfg_weight_slider = gr.Slider(0.1, 1.0, value=settings["cfg_weight_slider"], step=0.01, label="CFG Weight/Pace")
                        temp_slider = gr.Slider(0.01, 5.0, value=settings["temp_slider"], step=0.05, label="Temperature")
                        seed_input = gr.Number(value=settings["seed_input"], label="Random Seed (0 for random)")
                        enable_batching_checkbox = gr.Checkbox(label="Enable Sentence Batching (Max 300 chars)", value=settings["enable_batching_checkbox"])
                        smart_batch_short_sentences_checkbox = gr.Checkbox(label="Smart-append short sentences (if batching is off)", value=settings["smart_batch_short_sentences_checkbox"])
                        to_lowercase_checkbox = gr.Checkbox(label="Convert input text to lowercase", value=settings["to_lowercase_checkbox"])
                        normalize_spacing_checkbox = gr.Checkbox(label="Normalize spacing (remove extra newlines and spaces)", value=settings["normalize_spacing_checkbox"])
                        fix_dot_letters_checkbox = gr.Checkbox(label="Convert 'J.R.R.' style input to 'J R R'", value=settings["fix_dot_letters_checkbox"])
                        remove_reference_numbers_checkbox = gr.Checkbox(
                            label="Remove inline reference numbers after sentences (e.g., '.188', '.3')",
                            value=settings.get("remove_reference_numbers_checkbox", True)
                        )
                        
                        use_auto_editor_checkbox = gr.Checkbox(label="Post-process with Auto-Editor", value=settings["use_auto_editor_checkbox"])
                        keep_original_checkbox = gr.Checkbox(label="Keep original WAV (before Auto-Editor)", value=settings["keep_original_checkbox"])
                        threshold_slider = gr.Slider(0.01, 0.5, value=settings["threshold_slider"], step=0.01, label="Auto-Editor Volume Threshold")
                        margin_slider = gr.Slider(0.0, 2.0, value=settings["margin_slider"], step=0.1, label="Auto-Editor Margin (seconds)")

                        normalize_audio_checkbox = gr.Checkbox(label="Normalize with ffmpeg (loudness/peak)", value=settings["normalize_audio_checkbox"])
                        normalize_method_dropdown = gr.Dropdown(
                            choices=["ebu", "peak"], value=settings["normalize_method_dropdown"], label="Normalization Method"
                        )
                        normalize_level_slider = gr.Slider(
                            -70, -5, value=settings["normalize_level_slider"], step=1, label="EBU Target Integrated Loudness (I, dB, ebu only)"
                        )
                        normalize_tp_slider = gr.Slider(
                            -9, 0, value=settings["normalize_tp_slider"], step=1, label="EBU True Peak (TP, dB, ebu only)"
                        )
                        normalize_lra_slider = gr.Slider(
                            1, 50, value=settings["normalize_lra_slider"], step=1, label="EBU Loudness Range (LRA, ebu only)"
                        )


                        sound_words_field = gr.Textbox(
                            label="Remove/Replace Words/Sounds (newline separated or 'sound=>replacement')",
                            lines=2,
                            info="Examples: sss, ss, ahh=>um, hmm (removes/replace as standalone or quoted; not in words)",
                            value=settings["sound_words_field"]
                        )
                        # === LOAD SETTINGS FROM JSON FEATURE ===
                        load_settings_file.change(
                            fn=apply_settings_json,
                            inputs=[load_settings_file],
                            outputs=[
                                text_input,                          # 0
                                text_file_input,                     # 1
                                separate_files_checkbox,             # 2
                                ref_audio_input,                     # 3
                                export_format_checkboxes,            # 4
                                disable_watermark_checkbox,          # 5
                                num_generations_input,               # 6
                                num_candidates_slider,               # 7
                                max_attempts_slider,                 # 8
                                bypass_whisper_checkbox,             # 9
                                whisper_model_dropdown,              # 10
                                use_faster_whisper_checkbox,         # 11
                                enable_parallel_checkbox,            # 12
                                use_longest_transcript_on_fail_checkbox, # 13
                                num_parallel_workers_slider,         # 14
                                exaggeration_slider,                 # 15
                                cfg_weight_slider,                   # 16
                                temp_slider,                         # 17
                                seed_input,                          # 18
                                enable_batching_checkbox,            # 19
                                smart_batch_short_sentences_checkbox,# 20
                                to_lowercase_checkbox,               # 21
                                normalize_spacing_checkbox,          # 22
                                fix_dot_letters_checkbox,            # 23
                                remove_reference_numbers_checkbox,   # 24
                                use_auto_editor_checkbox,            # 25
                                keep_original_checkbox,              # 26
                                threshold_slider,                    # 27
                                margin_slider,                       # 28
                                normalize_audio_checkbox,            # 29
                                normalize_method_dropdown,           # 30
                                normalize_level_slider,              # 31
                                normalize_tp_slider,                 # 32
                                normalize_lra_slider,                # 33
                                sound_words_field,                   # 34
                            ]
                        )

                        
                        

                        output_audio = gr.Files(label="Download Final Audio File(s)")
                        audio_dropdown = gr.Dropdown(label="Click to Preview Any Generated File")
                        audio_preview = gr.Audio(label="Audio Preview", interactive=True)
                        audio_dropdown.change(fn=update_audio_preview, inputs=audio_dropdown, outputs=audio_preview)

            def collect_ui_settings(*vals):
                keys = [
                    "text_input",
                    "exaggeration_slider",
                    "temp_slider",
                    "seed_input",
                    "cfg_weight_slider",
                    "use_auto_editor_checkbox",
                    "threshold_slider",
                    "margin_slider",
                    "export_format_checkboxes",
                    "enable_batching_checkbox",
                    "to_lowercase_checkbox",
                    "normalize_spacing_checkbox",
                    "fix_dot_letters_checkbox",
                    "remove_reference_numbers_checkbox",
                    "keep_original_checkbox",
                    "smart_batch_short_sentences_checkbox",
                    "disable_watermark_checkbox",
                    "num_generations_input",
                    "normalize_audio_checkbox",
                    "normalize_method_dropdown",
                    "normalize_level_slider",
                    "normalize_tp_slider",
                    "normalize_lra_slider",
                    "num_candidates_slider",
                    "max_attempts_slider",
                    "bypass_whisper_checkbox",
                    "whisper_model_dropdown",
                    "enable_parallel_checkbox",
                    "num_parallel_workers_slider",
                    "use_longest_transcript_on_fail_checkbox",
                    "sound_words_field",
                    "use_faster_whisper_checkbox",
                    "separate_files_checkbox",
                ]
                if len(keys) != len(vals):
                    raise ValueError(f"[SETTINGS ERROR] collect_ui_settings: Number of values ({len(vals)}) does not match keys ({len(keys)})!")
                mapping = dict(zip(keys, vals))
                save_settings(mapping)
                return
             
            

            run_button.click(
                fn=lambda *args: (
                    collect_ui_settings(*([args[0]] + list(args[3:]))),  # text_input + rest of option fields (skipping file/audio)
                    generate_and_preview(*args)
                )[1],
                inputs=[
                    text_input,                   # 0
                    text_file_input,              # 1
                    ref_audio_input,              # 2
                    exaggeration_slider,          # 3
                    temp_slider,                  # 4
                    seed_input,                   # 5
                    cfg_weight_slider,            # 6
                    use_auto_editor_checkbox,     # 7
                    threshold_slider,             # 8
                    margin_slider,                # 9
                    export_format_checkboxes,     #10
                    enable_batching_checkbox,     #11
                    to_lowercase_checkbox,        #12
                    normalize_spacing_checkbox,   #13
                    fix_dot_letters_checkbox,     #14
                    remove_reference_numbers_checkbox,   #15
                    keep_original_checkbox,       #16
                    smart_batch_short_sentences_checkbox,#17
                    disable_watermark_checkbox,   #18
                    num_generations_input,        #19
                    normalize_audio_checkbox,     #20
                    normalize_method_dropdown,    #21
                    normalize_level_slider,       #22
                    normalize_tp_slider,          #23
                    normalize_lra_slider,         #24
                    num_candidates_slider,        #25
                    max_attempts_slider,          #26
                    bypass_whisper_checkbox,      #27
                    whisper_model_dropdown,       #28
                    enable_parallel_checkbox,     #29
                    num_parallel_workers_slider,  #30
                    use_longest_transcript_on_fail_checkbox, #31
                    sound_words_field,            #32
                    use_faster_whisper_checkbox,  #33
                    separate_files_checkbox       #34
                ],
                outputs=[output_audio, audio_dropdown, audio_preview],
            )


            # === VC TAB: Voice Conversion Tab ===
            with gr.Tab("Voice Conversion (VC)"):
                gr.Markdown("## Voice Conversion\nConvert one speaker's voice to sound like another speaker using a target/reference voice audio.")
                with gr.Row():
                    vc_input_audio = gr.Audio(sources=["upload", "microphone"], type="filepath", label="Input Audio (to convert)")
                    vc_target_audio = gr.Audio(sources=["upload", "microphone"], type="filepath", label="Target Voice Audio")
                vc_pitch_shift = gr.Number(value=0, label="Pitch", step=0.5, interactive=True)
                vc_convert_btn = gr.Button("Run Voice Conversion")
                vc_output_files = gr.Files(label="Converted VC Audio File(s)")
                vc_output_audio = gr.Audio(label="VC Output Preview", interactive=True)

                def _vc_wrapper(input_audio_path, target_voice_audio_path, disable_watermark, pitch_shift):
                    # Defensive: None means Gradio didn't get file yet
                    if not input_audio_path or not os.path.exists(input_audio_path):
                        raise gr.Error("Please upload or record an input audio file.")
                    if not target_voice_audio_path or not os.path.exists(target_voice_audio_path):
                        raise gr.Error("Please upload or record a target/reference voice audio file.")

                    sr, out_wav = voice_conversion(
                        input_audio_path,
                        target_voice_audio_path,
                        disable_watermark=disable_watermark,
                        pitch_shift=pitch_shift
                    )
                    os.makedirs("output", exist_ok=True)
                    base = os.path.splitext(os.path.basename(input_audio_path))[0]
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")[:-3]
                    out_path = f"output/{base}_vc_{timestamp}.wav"
                    sf.write(out_path, out_wav, sr)
                    return [out_path], out_path  # Files and preview

                vc_convert_btn.click(
                    fn=_vc_wrapper,
                    inputs=[vc_input_audio, vc_target_audio, disable_watermark_checkbox, vc_pitch_shift],
                    outputs=[vc_output_files, vc_output_audio],
                )

        with gr.Accordion("Show Help / Instructions", open=False):
            gr.Markdown(
            """
            **What do all the main sliders and settings do?**
            ---

            ### **Text & Reference Input**
            - **Text Input:**  
              Enter the text you want to convert to speech. This can be any length, but for best results, keep sentences concise.  
            - **Text File(s) (.txt):**  
              Upload one or more plain text files. If files are uploaded, their contents override the text box input.  
              - *Tip: You can drag-and-drop multiple `.txt` files. If you do, you can choose to generate either one combined audio file, or separate audio files for each text file (see below).*
            - **Generate Separate Audio Files Per Text File:**  
              If checked, each uploaded text file will result in a separate audio file.  
              If unchecked, all text files are merged (in alphabetical order) and a single audio file is generated.
            - **Reference Audio:**  
              (Optional) Upload or record a sample of the target voice or style. The model will attempt to mimic this reference in generated speech.

            ---

            ### **TTS Voice/Emotion Controls**
            - **Emotion Exaggeration:**  
              Controls how dramatically emotions (like excitement, sadness, etc.) are expressed.  
              - *Low values* = more monotone/neutral  
              - *1.0* = model's default expressiveness  
              - *Above 1.0* = extra dramatic
            - **CFG Weight (Classifier-Free Guidance):**  
              Governs how strictly the output should follow the input text vs. being natural and expressive.  
              - *Higher values* = more literal, less expressive  
              - *Lower values* = more natural, possibly less faithful to the input
            - **Temperature:**  
              Adds randomness/variety to speech.  
              - *Low (0.1–0.5)* = more predictable, less expressive  
              - *High (0.7–1.2)* = more variety and unpredictability in speech patterns

            - **Random Seed (0 for random):**  
              Sets the base for the random number generator.  
              - *0* = pick a new random seed each time (unique results)  
              - *Any other number* = repeatable generations (for reproducibility/debugging)

            ---

            ### **Text Processing Options**
            - **Enable Sentence Batching (Max 300 chars):**  
              Chunks the input into groups of sentences, up to the specified maximum character length per batch.  
              - *Improves natural phrasing and makes TTS more efficient.*
            - **Smart-Append Short Sentences (if batching is off):**  
              If sentence batching is disabled, this option intelligently merges very short sentences together for smoother prosody.
            - **Convert Input Text to Lowercase:**  
              Automatically lowercases the input before synthesis.  
              - *May improve consistency in pronunciation for some models.*
            - **Normalize Spacing:**  
              Removes redundant spaces and blank lines, creating cleaner input for the model.
            - **Convert 'J.R.R.' to 'J R R':**  
              Automatically converts abbreviations written with periods to a spaced-out format (improves pronunciation of initials/names).

            ---

            ### **Audio Post-Processing**
            - **Post-process with Auto-Editor:**  
              Uses [auto-editor](https://github.com/WyattBlue/auto-editor) to automatically trim silences and clean up the audio, reducing stutters and small TTS artifacts.
            - **Auto-Editor Volume Threshold:**  
              Sets the loudness level below which audio is considered silence and removed.  
              - *Higher values = more aggressive trimming.*
            - **Auto-Editor Margin (seconds):**  
              Adds a buffer before and after detected audio to avoid cutting words or breaths.
            - **Keep Original WAV (before Auto-Editor):**  
              If enabled, the unprocessed audio is also saved, alongside the cleaned-up version.
            - **Normalize with ffmpeg (loudness/peak):**  
              Uses `ffmpeg` to adjust output volume.  
              - *Loudness normalization* matches the volume across different audio files.  
              - *Peak normalization* ensures audio doesn't exceed a certain volume.
            - **Normalization Method:**  
              - *ebu*: Broadcast-standard loudness normalization (good for consistent perceived loudness).  
              - *peak*: Simple normalization so the loudest part is at a fixed level.
            - **EBU Target Integrated Loudness (I, dB, ebu only):**  
              Target average loudness in decibels (usually -24 dB for TV, -16 dB for podcasts).
            - **EBU True Peak (TP, dB, ebu only):**  
              Maximum peak volume in dB (e.g., -2 dB to avoid digital clipping).
            - **EBU Loudness Range (LRA, ebu only):**  
              Controls the dynamic range of the output.  
              - *Lower values* = more compressed sound; *higher values* = more dynamic range.

            ---

            ### **Output & Export Options**
            - **Export Format:**  
              Choose one or more audio formats for export:  
              - *WAV*: Uncompressed, highest quality  
              - *MP3*: Compressed, smaller files, near-universal support  
              - *FLAC*: Lossless compression, smaller than WAV but no loss in quality  
              - *Tip: You can select multiple formats to export all at once.*
            - **Disable Perth Watermark:**  
              If enabled, disables the PerthNet audio watermarking (if the model applies it by default).  
              - *Recommended for privacy or when watermarking is not needed.*

            ---

            ### **Generation Controls**
            - **Number of Generations:**  
              Produces multiple unique audio outputs in one click (for variety or "takes").  
              - *All generations will have different random seeds (unless a fixed seed is set).*
            - **Number of Candidates Per Chunk:**  
              For each chunk, generate this many TTS variants and pick the best one (based on Whisper check or duration).  
              - *More candidates can reduce artifacts, but increases processing time and VRAM use.*
            - **Max Attempts Per Candidate (Whisper check retries):**  
              How many times to retry each candidate if the Whisper sync check fails.  
              - Will keep trying new variations up to this number per candidate when failing Whisper Sync validation.  
            - **Bypass Whisper Checking:**  
              If enabled, skips speech-to-text validation (faster but riskier—may allow more TTS mistakes).  
              - *When off, each candidate is checked using Whisper for accuracy.*

            ---

            ### **Whisper Sync Options**
            - **Whisper Sync Model (with VRAM requirements):**  
              Choose which Whisper model to use for automatic speech-to-text checking (to validate each TTS chunk and reduce artifacts). There are **two different backends** you can select:

              **1. OpenAI Whisper (official, more VRAM required):**
                - *OpenAI's original Whisper models offer high accuracy, but use more VRAM, especially at larger sizes.*
                - **VRAM usage (approximate, CUDA/float16):**
                    - tiny: ~1 GB
                    - base: ~1.2–2 GB
                    - small: ~2–3 GB
                    - medium: ~5–8 GB
                    - large: ~10–13 GB
                - *medium* (~5–8 GB VRAM) is a good compromise between speed and accuracy for most users.
                - **Use this if:**  
                  - You want the "classic" Whisper experience, or your GPU has ample VRAM.

              **2. faster-whisper (SYSTRAN, highly optimized):**
                - *This is a fast, memory-efficient reimplementation of Whisper. It is nearly as accurate as the official version, but uses far less VRAM and runs significantly faster, especially on modern NVIDIA GPUs.*
                - **VRAM usage (approximate, CUDA/float16):**
                    - tiny: ~0.5 GB
                    - base: ~0.7–1.0 GB
                    - small: ~1.2–1.7 GB
                    - medium: ~2.5–4.5 GB
                    - large: ~4.5–6.5 GB
                - *Even "large" can run comfortably on a 6 GB GPU!*
                - **Use this if:**  
                  - You want faster processing and/or have limited VRAM.

            - **Accuracy/Speed Tips:**
                - **tiny**/**base** are fastest but less accurate (good for quick checks, not critical applications).
                - **small**/**medium** are a good balance for most TTS validation use-cases.
                - **large** offers best accuracy, but is only practical on powerful GPUs.

            - **Which backend should I choose?**
                - **faster-whisper** is highly recommended for most users.  
                  It will check the "Use faster-whisper (SYSTRAN) backend" box.  
                  It is typically 2× faster and uses 30–60% less VRAM than official Whisper.
                - If you experience VRAM errors with OpenAI Whisper, switch to faster-whisper or a smaller model.
                - If you want to exactly match results from the original Whisper repo, use the OpenAI Whisper backend.

            - **Note:**  
                - Model size can affect TTS generation time and GPU memory use. If you get CUDA out-of-memory errors, try a smaller model or enable "faster-whisper".

            ---

            **Summary Table: Whisper Model VRAM Usage**

            | Model   | OpenAI Whisper VRAM | faster-whisper VRAM |
            |---------|---------------------|--------------------|
            | tiny    | ~1 GB               | ~0.5 GB            |
            | base    | ~1.2–2 GB           | ~0.7–1.0 GB        |
            | small   | ~2–3 GB             | ~1.2–1.7 GB        |
            | medium  | ~5–8 GB             | ~2.5–4.5 GB        |
            | large   | ~10–13 GB           | ~4.5–6.5 GB        |

            ---

            ### **Parallel Processing & Performance**
            - **Enable Parallel Chunk Processing:**  
              Speeds up synthesis by generating multiple audio chunks at the same time.  
              - *Uses more VRAM; can speed up batch synthesis a lot on powerful GPUs.*
            - **Parallel Workers:**  
              How many chunks to process in parallel.  
              - *Set to 1 for full sequential processing (lower VRAM, slower).*
              - *Higher = more speed, but may hit VRAM limits on consumer GPUs.*

            ---

            ### **How Candidate Selection Works**
            - For each chunk, the model creates the specified number of candidate audio variations.
            - If Whisper checking is enabled:  
              - Each candidate is transcribed, and the one with the closest match to the input text is chosen.
            - If Whisper is bypassed:  
              - The shortest-duration candidate is chosen (assumed best).
            - If all candidates fail validation after retries:  
              - The candidate with the highest Whisper score is used, or the one with the most text characters, depending on user settings.

            ---

            ### **Sound Words / Replacement (Advanced)**
            - **Sound Word List:**  
              (Advanced) Supply a list of word replacements in the provided format to automatically substitute or remove problematic words during synthesis.
              - *Format: "original=>replacement, nextword=>newword"*  
              - Can be used to fix tricky pronunciations or remove unwanted sound cues from the text.

            ---

            ### **Tips & Troubleshooting**
            - If you experience **slow Whisper checking or VRAM errors**, try:
              - Reducing the number of parallel workers
              - Switching to a smaller Whisper model
              - Reducing the number of candidates per chunk
            - If audio sounds choppy or cut off, try **raising the Auto-Editor margin**, or lowering the volume threshold.

            ---

            **Still have questions?**  
            This interface aims to expose every option for maximum control, but if you're unsure, try using defaults for most sliders and options.
            """,
            elem_classes=["gr-text-center"]

            )

        try:
            print("[INFO] 🌐 Starting web server on http://127.0.0.1:7860")
            demo.launch(
                server_name="127.0.0.1",
                server_port=7860,
                inbrowser=True,
                share=False,
                debug=False,
                prevent_thread_lock=False,
                show_error=True,
                quiet=False
            )
        except KeyboardInterrupt:
            print("\n[INFO] 🛑 Server stopped by user (Ctrl+C)")
            cleanup_models()
        except Exception as e:
            print(f"[ERROR] 💥 Server error: {e}")
            print("[INFO] 🔄 Attempting to restart server...")
            import traceback
            traceback.print_exc()
            
            # Clean up models before restart attempt
            cleanup_models()
            time.sleep(1)
            
            # Try to restart the server
            try:
                demo.launch(
                    server_name="127.0.0.1",
                    server_port=7861,  # Try different port in case of conflict
                    inbrowser=False,
                    share=False,
                    debug=False,
                    prevent_thread_lock=False,
                    show_error=True,
                    quiet=False
                )
            except Exception as e2:
                print(f"[ERROR] 💥 Failed to restart server: {e2}")
                print("[INFO] ℹ️ Please restart the application manually.")
                cleanup_models()

def cleanup_models():
    """Safely cleanup all loaded models at application shutdown."""
    global MODEL, WHISPER_MODEL
    
    print("[INFO] 🧹 Cleaning up models for shutdown...")
    
    # Clean up Whisper model safely
    if WHISPER_MODEL is not None:
        try:
            print("[DEBUG] Safely unloading Whisper model...")
            WHISPER_MODEL = None
            torch.cuda.empty_cache()
            gc.collect()
            time.sleep(0.2)  # Give more time for cleanup
            print("[DEBUG] Whisper model cleaned up successfully")
        except Exception as e:
            print(f"[WARNING] Error during Whisper model cleanup: {e}")
    
    # Clean up TTS model
    if MODEL is not None:
        try:
            print("[DEBUG] Cleaning up TTS model...")
            MODEL = None
            torch.cuda.empty_cache()
            gc.collect()
            print("[DEBUG] TTS model cleaned up successfully")
        except Exception as e:
            print(f"[WARNING] Error during TTS model cleanup: {e}")
    
    print("[INFO] ✅ Model cleanup completed")

def safe_subprocess_run(cmd, timeout=300, **kwargs):
    """Run subprocess with timeout and enhanced error handling."""
    try:
        print(f"[DEBUG] Running command with {timeout}s timeout: {' '.join(cmd)}")
        result = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True, **kwargs)
        
        if result.returncode != 0:
            print(f"[WARNING] Command returned non-zero exit code: {result.returncode}")
            print(f"[WARNING] stderr: {result.stderr}")
            return False
        
        print(f"[DEBUG] Command completed successfully")
        return True
        
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Command timed out after {timeout} seconds")
        return False
    except Exception as e:
        print(f"[ERROR] Command failed: {e}")
        return False

if __name__ == "__main__":
    try:
        print("[INFO] 🎧 Starting Chatterbox TTS Extended...")
        print("[INFO] 🔄 Interface will remain open after processing for multiple generations.")
        main()
    except KeyboardInterrupt:
        print("\n[INFO] 👋 Application stopped by user (Ctrl+C)")
    except Exception as e:
        print(f"[ERROR] 💥 Application error: {e}")
        print("[INFO] 🔄 Please restart the application.")
        import traceback
        traceback.print_exc()
    finally:
        print("[INFO] 🏁 Application ended.")
        cleanup_models()
