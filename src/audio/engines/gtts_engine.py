"""Google TTS Engine implementation."""

import os
from gtts import gTTS


class GTTSEngine:
    """Google Text-to-Speech engine."""
    
    def __init__(self, lang: str = "zh-CN"):
        """Initialize Google TTS engine.
        
        Args:
            lang: Language code (default: zh-CN for Mandarin Chinese)
        """
        self.lang = lang
        self.name = "Google TTS"
    
    def generate_audio(self, text: str, output_path: str) -> bool:
        """Generate audio file from text using Google TTS.
        
        Args:
            text: Text to convert to speech
            output_path: Path where audio file will be saved
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Generate audio
            tts = gTTS(text=text, lang=self.lang)
            tts.save(output_path)
            
            # Verify file was created
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
            else:
                return False
        except Exception as e:
            print(f"  ERROR Google TTS: {e}")
            return False
    
    def is_available(self) -> bool:
        """Check if Google TTS is available.
        
        Returns:
            True if the engine can be used
        """
        try:
            from gtts import gTTS
            return True
        except ImportError:
            return False
