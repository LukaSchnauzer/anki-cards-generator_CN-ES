"""Azure Cognitive Services TTS Engine implementation."""

import os
import time
import random
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class AzureTTSEngine:
    """Azure Cognitive Services Text-to-Speech engine."""
    
    # Available Chinese voices with variety
    CHINESE_VOICES = [
        # Female voices
        "zh-CN-XiaoxiaoNeural",      # Young female, warm
        "zh-CN-XiaohanNeural",        # Young female, friendly
        "zh-CN-XiaomengNeural",       # Young female, cute
        "zh-CN-XiaomoNeural",         # Young female, gentle
        "zh-CN-XiaoqiuNeural",        # Young female, professional
        "zh-CN-XiaoruiNeural",        # Young female, energetic
        "zh-CN-XiaoshuangNeural",     # Young female, clear
        "zh-CN-XiaoxuanNeural",       # Young female, sweet
        "zh-CN-XiaoyanNeural",        # Young female, standard
        "zh-CN-XiaoyiNeural",         # Young female, natural
        "zh-CN-XiaoyouNeural",        # Child female
        "zh-CN-XiaozhenNeural",       # Young female, soft
        
        # Male voices
        "zh-CN-YunxiNeural",          # Young male, energetic
        "zh-CN-YunyangNeural",        # Young male, professional
        "zh-CN-YunjianNeural",        # Young male, sports
        "zh-CN-YunxiaNeural",         # Young male, calm
        "zh-CN-YunfengNeural",        # Mature male, authoritative
        "zh-CN-YunhaoNeural",         # Young male, friendly
        "zh-CN-YunyeNeural",          # Mature male, professional
    ]
    
    def __init__(self, voice: str = None, speed: float = 1.0, random_voice: bool = False):
        """Initialize Azure TTS engine.
        
        Args:
            voice: Voice to use (default: random from CHINESE_VOICES if random_voice=True)
            speed: Speech rate (0.5 = 50% slower, 1.0 = normal, 2.0 = 2x faster)
            random_voice: If True, use random voice for each audio generation
        """
        self.default_voice = voice or "zh-CN-XiaoxiaoNeural"
        self.speed = speed
        self.random_voice = random_voice
        self.name = "Azure TTS"
        
        # Load credentials from environment
        self.subscription_key = os.getenv("AZURE_TTS_KEY")
        self.region = os.getenv("AZURE_TTS_REGION", "eastus")
        
        if not self.subscription_key:
            raise ValueError(
                "Azure TTS requires AZURE_TTS_KEY in .env file. "
                "Get your key from: https://portal.azure.com"
            )
        
        # Build endpoint URL
        self.endpoint = f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"
    
    def get_voice(self) -> str:
        """Get voice to use for this generation.
        
        Returns:
            Voice name (random if random_voice is True)
        """
        if self.random_voice:
            return random.choice(self.CHINESE_VOICES)
        return self.default_voice
    
    def generate_audio(self, text: str, output_path: str, max_retries: int = 5) -> bool:
        """Generate audio file from text using Azure TTS with retry logic.
        
        Args:
            text: Text to convert to speech
            output_path: Path where audio file will be saved
            max_retries: Maximum number of retry attempts (default: 5)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Prepare headers
            headers = {
                'Ocp-Apim-Subscription-Key': self.subscription_key,
                'Content-Type': 'application/ssml+xml',
                'X-Microsoft-OutputFormat': 'audio-16khz-128kbitrate-mono-mp3',
                'User-Agent': 'ChinoSRS'
            }
            
            # Get voice for this generation
            voice = self.get_voice()
            
            # Prepare SSML body with speed control
            # Speed: 0.5 = 50% slower, 1.0 = normal, 1.5 = 50% faster, 2.0 = 2x faster
            speed_percent = f"{int((self.speed - 1.0) * 100):+d}%"  # Convert to percentage
            
            ssml = f"""<speak version='1.0' xml:lang='zh-CN'>
                <voice xml:lang='zh-CN' name='{voice}'>
                    <prosody rate='{speed_percent}'>
                        {text}
                    </prosody>
                </voice>
            </speak>"""
            
            # Retry logic with exponential backoff
            for attempt in range(max_retries):
                # Make request
                response = requests.post(self.endpoint, headers=headers, data=ssml.encode('utf-8'))
                
                if response.status_code == 200:
                    # Save audio file
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                    
                    # Small delay to respect rate limits (20 requests/min for free tier)
                    time.sleep(0.15)  # 150ms delay between requests
                    
                    # Verify file was created
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        return True
                    else:
                        return False
                        
                elif response.status_code == 429:
                    # Rate limited - exponential backoff
                    wait_time = min(2 ** attempt, 30)  # Max 30 seconds
                    if attempt < max_retries - 1:
                        print(f"  ⚠️  Rate limit alcanzado (intento {attempt + 1}/{max_retries}), esperando {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        print(f"  ❌ Rate limit: Máximo de reintentos alcanzado")
                        return False
                        
                else:
                    # Other HTTP errors
                    print(f"  ERROR Azure TTS: HTTP {response.status_code} - {response.text}")
                    return False
            
            return False
                
        except Exception as e:
            print(f"  ERROR Azure TTS: {e}")
            return False
    
    def is_available(self) -> bool:
        """Check if Azure TTS is available.
        
        Returns:
            True if the engine can be used
        """
        return self.subscription_key is not None
