import os
import logging
import re
import time
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

backend_dir = Path(__file__).resolve().parent.parent
dotenv_path = backend_dir / ".env"
load_dotenv(dotenv_path=dotenv_path)

from services.gemini_service import get_available_gemini_models, classify_gemini_error

logger = logging.getLogger(__name__)

def transcribe_audio(audio_bytes: bytes, mime_type: str, language_hint: str = None) -> dict:
    """
    Transcribe audio bytes using Gemini API audio understanding capabilities.
    
    Parameters
    ----------
    audio_bytes : bytes
        The raw bytes of the audio file.
    mime_type : str
        The MIME type of the audio file (e.g. audio/m4a, audio/wav, etc.)
    language_hint : str | None
        Optional language style hint.
        
    Returns
    -------
    dict with keys: success, transcript, language_hint, error_type, model_used
    """
    from services.key_manager import run_with_key_rotation

    def _execute_transcribe(api_key: str) -> dict:
        if not api_key:
            return {
                "success": False,
                "transcript": "",
                "language_hint": "unknown",
                "error_type": "missing_api_key",
                "model_used": ""
            }
            
        # Discover available models
        available_models = get_available_gemini_models(api_key)
        
        # Priority list of multimodal models supporting audio
        priority_models = [
            "models/gemini-2.5-flash",
            "models/gemini-3.6-flash",
            "models/gemini-2.0-flash",
            "models/gemini-1.5-flash",
            "models/gemini-3.5-flash",
            "gemini-2.5-flash",
            "gemini-3.6-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-3.5-flash"
        ]
        
        selected_model = None
        env_model = os.getenv("GEMINI_MODEL", "").strip()
        
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
            logger.error("No valid Gemini model available for audio transcription.")
            return {
                "success": False,
                "transcript": "",
                "language_hint": "unknown",
                "error_type": "model_not_available",
                "model_used": ""
            }

        prompt = (
            "You are FarmAI's speech-to-text processor.\n"
            "Your task is to transcribe the farmer's voice note and detect the spoken language.\n"
            "Do not answer the farming question.\n"
            "Do not give advice.\n"
            "Identify whether the spoken language is one of: Urdu, Roman Urdu, English, Punjabi, or Siraiki.\n"
            "You must return the output in the following format:\n"
            "Language: <Detected Language>\n"
            "Transcript: <Clean Transcript Text>\n\n"
            "Preserve language style:\n"
            "- If the speaker uses Urdu, return Urdu script.\n"
            "- If the speaker uses English, return English.\n"
            "- If the speaker uses Roman Urdu style, return Roman Urdu.\n"
            "- If the speaker uses Punjabi, return Punjabi meaning/script (in Shahmukhi/Urdu script).\n"
            "- If the speaker uses Siraiki, return Siraiki meaning/script (in Shahmukhi/Urdu script).\n"
            "- Keep transcript text clean, simple, and suitable for the existing analysis pipeline.\n\n"
            "Do not include markdown.\n"
            "Do not mention Gemini, backend, API, or model.\n"
            "If the audio is completely silent or unclear, reply with 'TRANSCRIPTION_FAILED'."
        )

        genai.configure(api_key=api_key)
        audio_part = {
            "mime_type": mime_type,
            "data": audio_bytes
        }

        last_stt_err_type = "unclear_audio"
        last_model_tried = ""
        last_exc = None

        for selected_model in models_to_try:
            last_model_tried = selected_model
            t_model_start = time.perf_counter()
            logger.info("[TIMING] [STT_MODEL_ATTEMPT] Trying model: %s (mime=%s, bytes=%d)", selected_model, mime_type, len(audio_bytes))
            try:
                model = genai.GenerativeModel(selected_model)
                response = model.generate_content([prompt, audio_part], request_options={"timeout": 30.0})
                t_model_end = time.perf_counter()
                raw_response = response.text.strip() if response and hasattr(response, "text") else ""

                if not raw_response or "TRANSCRIPTION_FAILED" in raw_response or len(raw_response) < 2:
                    logger.warning("[TIMING] [STT_MODEL_EMPTY] Model %s returned empty/failed transcription in %.2f s", selected_model, t_model_end - t_model_start)
                    continue

                raw_response = raw_response.replace('**', '').replace('"', '').replace("'", "").strip()

                detected_lang = "unknown"
                transcript = raw_response

                lang_match = re.search(r"Language:\s*(Urdu|Roman\s*Urdu|English|Punjabi|Siraiki)", raw_response, re.IGNORECASE)
                transcript_match = re.search(r"Transcript:\s*(.*)", raw_response, re.IGNORECASE | re.DOTALL)

                if lang_match:
                    detected_lang = lang_match.group(1).strip().lower()
                    if detected_lang == "roman urdu":
                        detected_lang = "roman_urdu"
                    elif detected_lang == "urdu":
                        detected_lang = "ur"

                if transcript_match:
                    transcript = transcript_match.group(1).strip()
                else:
                    transcript = re.sub(r"^Language:\s*\w+\s*\n?", "", raw_response, flags=re.IGNORECASE).strip()

                if not transcript or len(transcript) < 2:
                    logger.warning("[TIMING] [STT_MODEL_SHORT] Model %s returned transcript under 2 chars in %.2f s", selected_model, t_model_end - t_model_start)
                    continue

                if detected_lang == "unknown":
                    from utils.helpers import detect_language
                    lang_detected = detect_language(transcript)
                    if lang_detected in ("urdu", "ur"):
                        lang_detected = "ur"
                    detected_lang = lang_detected

                logger.info("[TIMING] [STT_MODEL_SUCCESS] Model %s succeeded in %.2f s", selected_model, t_model_end - t_model_start)
                return {
                    "success": True,
                    "transcript": transcript,
                    "language_hint": detected_lang,
                    "error_type": None,
                    "model_used": selected_model
                }
            except Exception as exc:
                t_model_end = time.perf_counter()
                err_type, err_msg = classify_gemini_error(exc)
                logger.warning("[TIMING] [STT_MODEL_FAILED] Model %s failed in %.2f s with error (%s): %s", selected_model, t_model_end - t_model_start, err_type, err_msg)
                last_exc = exc
                last_stt_err_type = err_type
                if err_type == "invalid_api_key":
                    raise exc

        if last_exc:
            err_type, err_msg = classify_gemini_error(last_exc)
            if err_type in ("quota_or_rate_limit", "invalid_api_key"):
                raise last_exc

        return {
            "success": False,
            "transcript": "",
            "language_hint": "unknown",
            "error_type": last_stt_err_type,
            "model_used": last_model_tried
        }

    # Execute with key rotation using the STT pool
    rotation_res = run_with_key_rotation("STT", _execute_transcribe)
    
    if rotation_res.get("success"):
        return rotation_res["result"]
    else:
        return {
            "success": False,
            "transcript": "",
            "language_hint": "unknown",
            "error_type": rotation_res.get("error_type", "transcription_failed"),
            "model_used": ""
        }
