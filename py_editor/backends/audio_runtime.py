"""Audio manager for NodeCanvas runtime using pygame.mixer"""
import os
from typing import Dict, Optional

# Try to use pygame for audio, fall back to simpler solutions
try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    print("Warning: pygame not available. Audio playback disabled.")
    print("Install with: pip install pygame")


# Channel name to index mapping
CHANNEL_MAP = {
    "Music": 0,
    "Effect": 1,
    "Voice": 2,
    "UI": 3,
    "Ambient": 4,
    "Custom1": 5,
    "Custom2": 6,
    "Custom3": 7,
    "All": -1,  # Special: all channels
}


class AudioManager:
    """Manages audio playback with named channels"""
    
    _instance: Optional['AudioManager'] = None
    
    def __init__(self):
        self.channels: Dict[str, pygame.mixer.Channel] = {}
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        
        if PYGAME_AVAILABLE:
            # Pre-allocate 8 channels
            pygame.mixer.set_num_channels(8)
            for name, idx in CHANNEL_MAP.items():
                if idx >= 0:
                    self.channels[name] = pygame.mixer.Channel(idx)
    
    @classmethod
    def get_instance(cls) -> 'AudioManager':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = AudioManager()
        return cls._instance
    
    def play_sound(self, file_path: str, channel: str = "Effect", loop: bool = False) -> bool:
        """
        Play a sound file on the specified channel.
        
        Args:
            file_path: Path to audio file (.wav, .mp3, .ogg)
            channel: Channel name (Music, Effect, Voice, UI, Ambient, Custom1-3)
            loop: Whether to loop the sound
            
        Returns:
            True if playback started, False otherwise
        """
        if not PYGAME_AVAILABLE:
            print(f"[Audio] pygame not available, cannot play: {file_path}")
            return False
        
        if not file_path or not os.path.exists(file_path):
            print(f"[Audio] File not found: {file_path}")
            return False
        
        try:
            # Load sound if not cached
            if file_path not in self.sounds:
                self.sounds[file_path] = pygame.mixer.Sound(file_path)
            
            sound = self.sounds[file_path]
            
            # Get channel
            ch = self.channels.get(channel)
            if ch is None:
                ch = self.channels.get("Effect")  # Fallback
            
            # Play the sound
            loops = -1 if loop else 0  # -1 = infinite loop in pygame
            ch.play(sound, loops=loops)
            
            print(f"[Audio] Playing '{os.path.basename(file_path)}' on channel '{channel}' (loop={loop})")
            return True
            
        except Exception as e:
            print(f"[Audio] Error playing {file_path}: {e}")
            return False
    
    def stop_sound(self, channel: str = "All"):
        """
        Stop sound on a channel.
        
        Args:
            channel: Channel name, or "All" to stop all channels
        """
        if not PYGAME_AVAILABLE:
            return
        
        if channel == "All":
            pygame.mixer.stop()
            print("[Audio] Stopped all channels")
        else:
            ch = self.channels.get(channel)
            if ch:
                ch.stop()
                print(f"[Audio] Stopped channel '{channel}'")
    
    def set_volume(self, channel: str, volume: float):
        """Set volume for a channel (0.0 to 1.0)"""
        if not PYGAME_AVAILABLE:
            return
        
        volume = max(0.0, min(1.0, volume))
        
        if channel == "All":
            for ch in self.channels.values():
                ch.set_volume(volume)
        else:
            ch = self.channels.get(channel)
            if ch:
                ch.set_volume(volume)
    
    def cleanup(self):
        """Clean up audio resources"""
        if PYGAME_AVAILABLE:
            pygame.mixer.stop()
            self.sounds.clear()


# Global instance for easy access
def play_sound(file_path: str, channel: str = "Effect", loop: bool = False) -> bool:
    """Convenience function to play a sound"""
    return AudioManager.get_instance().play_sound(file_path, channel, loop)


def stop_sound(channel: str = "All"):
    """Convenience function to stop sound"""
    AudioManager.get_instance().stop_sound(channel)
