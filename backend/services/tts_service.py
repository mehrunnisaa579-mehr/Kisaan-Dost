import os
import re
import uuid
import wave
import io
import json
import logging
import time
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

backend_dir = Path(__file__).resolve().parent.parent
dotenv_path = backend_dir / ".env"
load_dotenv(dotenv_path=dotenv_path)

from services.gemini_service import get_available_gemini_models, classify_gemini_error

logger = logging.getLogger(__name__)

# Constants
STATIC_AUDIO_DIR = backend_dir / "static" / "audio"
DEFAULT_VOICE = "Aoede" # Puck, Charon, Fenrir, Kore, Aoede

def clean_text_for_tts(text: str) -> str:
    """
    Cleans markdown formatting, list indicators, and raw JSON blocks 
    before sending text to the TTS engine.
    """
    if not text:
        return ""
    
    # 1. Clean JSON if accidentally present
    trimmed = text.strip()
    if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
        try:
            data = json.loads(trimmed)
            if isinstance(data, dict):
                # Try common keys for message response
                for key in ["farmer_response", "text", "message", "response"]:
                    if key in data and data[key]:
                        return clean_text_for_tts(str(data[key]))
        except Exception:
            pass

    # Remove inline JSON-like strings
    text = re.sub(r'\{[^{}]*\}', '', text)
    
    # 2. Clean markdown bold/italic/code markers
    text = text.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
    text = text.replace("```", "")
    
    # Remove header markers (e.g., "# Heading" -> "Heading")
    text = re.sub(r'#+\s*', '', text)
    
    # Remove bullet/list markers at the beginning of lines
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
    
    # Remove excessive newlines
    text = re.sub(r'\n+', '\n', text)
    return text.strip()


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    """Converts raw 16-bit linear PCM bytes into standard WAV bytes."""
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        wav_file.setnchannels(1)       # Mono
        wav_file.setsampwidth(2)      # 16-bit (2 bytes per sample)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return wav_io.getvalue()


def extract_audio_bytes(response) -> bytes | None:
    """Extract audio bytes from various candidate Gemini API response shapes."""
    if not response or not hasattr(response, "candidates") or not response.candidates:
        return None
    
    try:
        candidate = response.candidates[0]
        if not candidate.content or not hasattr(candidate.content, "parts") or not candidate.content.parts:
            return None
            
        for part in candidate.content.parts:
            # 1. Attribute inline_data
            inline_data = getattr(part, "inline_data", None)
            if inline_data:
                data = getattr(inline_data, "data", None)
                if data:
                    if isinstance(data, bytes):
                        return data
                    elif isinstance(data, str):
                        import base64
                        try:
                            return base64.b64decode(data)
                        except Exception:
                            pass
            
            # 2. Dictionary style inline_data or inlineData
            if isinstance(part, dict):
                inline_data = part.get("inline_data") or part.get("inlineData")
                if inline_data:
                    data = inline_data.get("data")
                    if data:
                        if isinstance(data, bytes):
                            return data
                        elif isinstance(data, str):
                            import base64
                            try:
                                return base64.b64decode(data)
                            except Exception:
                                pass
                                
            # 3. Direct dictionary access on part object attributes
            try:
                # Check for inlineData attribute
                inline_data = getattr(part, "inlineData", None)
                if inline_data:
                    data = getattr(inline_data, "data", None)
                    if data:
                        if isinstance(data, bytes):
                            return data
                        elif isinstance(data, str):
                            import base64
                            try:
                                return base64.b64decode(data)
                            except Exception:
                                pass
            except Exception:
                pass
    except Exception as e:
        logger.warning("Error during audio bytes extraction: %s", e)
        
    return None


def generate_tts_audio(text: str, language_hint: str = None) -> dict:
    """
    Generates TTS audio from input text using Gemini API.
    Saves file under static/audio/ and returns a status dict.
    """
    # Clean input text
    cleaned_text = clean_text_for_tts(text)
    if not cleaned_text:
        return {
            "success": False,
            "error_type": "empty_input",
            "message": "آواز بنانے کے لیے متن موجود نہیں۔"
        }

    # Trim to reasonable length if excessively long (e.g. limit to 2000 chars to avoid timeout/quota overload)
    if len(cleaned_text) > 2000:
        cleaned_text = cleaned_text[:2000] + "..."

    from services.key_manager import run_with_key_rotation

    def _execute_tts(api_key: str) -> dict:
        if not api_key:
            return {
                "success": False,
                "error_type": "missing_api_key",
                "message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔"
            }

        # 1. Model Selection
        env_model = os.getenv("GEMINI_TTS_MODEL", "").strip()
        selected_model = None

        available_models = get_available_gemini_models(api_key)
        # Priority list of TTS models
        priority_models = [
            "models/gemini-2.5-flash-preview-tts",
            "models/gemini-2.5-flash",
            "models/gemini-3.1-flash-tts-preview",
            "models/gemini-2.5-pro-preview-tts",
            "models/gemini-2.0-flash",
            "gemini-2.5-flash-preview-tts",
            "gemini-2.5-flash",
            "gemini-3.1-flash-tts-preview",
            "gemini-2.5-pro-preview-tts",
            "gemini-2.0-flash"
        ]
        
        # Clean model names to find matches
        def clean_name(n: str) -> str:
            return n[7:] if n.startswith("models/") else n
            
        normalized_available = {clean_name(m): m for m in available_models}

        models_to_try = []
        for p in priority_models:
            p_clean = clean_name(p)
            if p_clean in normalized_available:
                m_full = normalized_available[p_clean]
                if m_full not in models_to_try:
                    models_to_try.append(m_full)

        if env_model and clean_name(env_model) in normalized_available:
            m_env = normalized_available[clean_name(env_model)]
            if m_env not in models_to_try:
                models_to_try.append(m_env)

        if not models_to_try and available_models:
            models_to_try = [available_models[0]]

        if not models_to_try:
            logger.error("No valid Gemini model available for TTS generation.")
            return {
                "success": False,
                "error_type": "model_not_available",
                "message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔"
            }

        # 2. Build instructions prompt based on language_hint or detected language
        active_lang = language_hint
        if not active_lang:
            from utils.helpers import detect_language
            active_lang = detect_language(cleaned_text)

        lang_lower = str(active_lang).lower().strip()
        if lang_lower in ("ur", "urdu", "punjabi", "siraiki"):
            lang_instruction = "Read it with natural Urdu pronunciation."
        elif lang_lower == "roman_urdu":
            lang_instruction = "Read it in Pakistani Roman Urdu style, not English pronunciation."
        elif lang_lower in ("en", "english"):
            lang_instruction = "Read it in natural English pronunciation."
        else:
            lang_instruction = "Transition pronunciation smoothly based on the script used in text."

        system_prompt = (
            "You are a high-quality, natural Text-to-Speech engine.\n"
            "Your only task is to read the provided text aloud clearly, naturally, and fluently.\n"
            "Return audio only. Do not generate any written text.\n"
            "Do not answer the user or add extra commentary.\n"
            "Only speak the provided text exactly as given.\n\n"
            "Voice style:\n"
            "* Friendly, calm, supportive, and clear.\n"
            "* Suitable for Pakistani farmers.\n\n"
            "Language pronunciation:\n"
            f"* {lang_instruction}\n\n"
            "Formatting cleanup:\n"
            "* Do not read markdown symbols, asterisks, hashtags, or formatting markers."
        )

        full_prompt = f"{system_prompt}\n\nText: {cleaned_text}"

        # 3. Call API
        genai.configure(api_key=api_key)
        config = {
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {
                        "voice_name": DEFAULT_VOICE
                    }
                }
            }
        }

        last_tts_err_type = "empty_response"
        last_exc = None

        for selected_model in models_to_try:
            t_model_start = time.perf_counter()
            logger.info("[TIMING] [TTS_MODEL_ATTEMPT] Trying model: %s (lang=%s, text_len=%d)", selected_model, active_lang, len(cleaned_text))
            try:
                model = genai.GenerativeModel(selected_model)
                response = model.generate_content(
                    full_prompt,
                    generation_config=config,
                    request_options={"timeout": 30.0}
                )
                t_model_end = time.perf_counter()

                pcm_bytes = extract_audio_bytes(response)
                if not pcm_bytes:
                    logger.warning("[TIMING] [TTS_MODEL_NO_BYTES] Model %s returned no valid inline audio bytes in %.2f s, trying next candidate.", selected_model, t_model_end - t_model_start)
                    continue

                wav_bytes = pcm_to_wav(pcm_bytes)
                os.makedirs(STATIC_AUDIO_DIR, exist_ok=True)
                filename = f"tts_{uuid.uuid4().hex}.wav"
                file_path = os.path.join(STATIC_AUDIO_DIR, filename)
                with open(file_path, "wb") as f:
                    f.write(wav_bytes)

                logger.info("Saved generated TTS audio: %s", file_path)
                logger.info("[TIMING] [TTS_MODEL_SUCCESS] Model %s succeeded in %.2f s", selected_model, t_model_end - t_model_start)
                return {
                    "success": True,
                    "filename": filename,
                    "tts_status": {
                        "success": True,
                        "model_used": selected_model
                    }
                }
            except Exception as exc:
                t_model_end = time.perf_counter()
                err_type, err_msg = classify_gemini_error(exc)
                logger.warning("[TIMING] [TTS_MODEL_FAILED] Model %s failed in %.2f s with error (%s): %s", selected_model, t_model_end - t_model_start, err_type, err_msg)
                last_exc = exc
                last_tts_err_type = err_type
                if err_type == "invalid_api_key":
                    raise exc

        if last_exc:
            err_type, err_msg = classify_gemini_error(last_exc)
            if err_type in ("quota_or_rate_limit", "invalid_api_key"):
                raise last_exc

        return {
            "success": False,
            "error_type": last_tts_err_type,
            "message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔",
            "tts_status": {
                "success": False,
                "error_type": last_tts_err_type
            }
        }

    # Execute with key rotation using the TTS pool
    rotation_res = run_with_key_rotation("TTS", _execute_tts)
    
    if rotation_res.get("success"):
        res = rotation_res["result"]
        # Add rotation tracking to tts_status
        res["tts_status"]["pool"] = rotation_res.get("pool")
        res["tts_status"]["attempts"] = rotation_res.get("attempts")
        res["tts_status"]["key_index_used"] = rotation_res.get("key_index_used")
        return res
    else:
        # Rotation failed completely (all keys exhausted or pool empty)
        return {
            "success": False,
            "error_type": rotation_res.get("error_type", "tts_failed"),
            "message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔",
            "tts_status": {
                "success": False,
                "pool": rotation_res.get("pool"),
                "error_type": rotation_res.get("error_type", "tts_failed"),
                "attempts": rotation_res.get("attempts", []),
                "key_index_used": rotation_res.get("key_index_used", 0)
            }
        }
