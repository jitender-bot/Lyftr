import os
from typing import List

class Settings:
    # Keys
    LLM_API_KEYS_RAW: str = os.getenv("LLM_API_KEYS", "dummy_key_1,dummy_key_2")
    
    @property
    def LLM_API_KEYS(self) -> List[str]:
        keys = [k.strip() for k in self.LLM_API_KEYS_RAW.split(",") if k.strip()]
        return keys if keys else ["dummy_key_1", "dummy_key_2"]
    
    # Model
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini/gemini-flash-lite-latest")
    LLM_MODELS_RAW: str = os.getenv("LLM_MODELS", "")

    @property
    def LLM_MODELS(self) -> List[str]:
        models = [m.strip() for m in self.LLM_MODELS_RAW.split(",") if m.strip()]
        return models

    DEFAULT_SYSTEM_PROMPT: str = os.getenv(
        "DEFAULT_SYSTEM_PROMPT", "You are a helpful and concise AI assistant."
    )
    
    # Database URL
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    
    # CORS
    ALLOWED_ORIGINS_RAW: str = os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,*"
    )
    
    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        origins = [o.strip() for o in self.ALLOWED_ORIGINS_RAW.split(",") if o.strip()]
        return origins if origins else ["*"]
        
    # Failure Simulation
    @property
    def ENABLE_FAILURE_SIMULATION(self) -> bool:
        val = os.getenv("ENABLE_FAILURE_SIMULATION", "true").lower().strip()
        return val in ("true", "1", "yes")

settings = Settings()
