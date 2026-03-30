import json
import os
import threading
import logging
from pydantic import BaseModel, Field

class SecuritySettings(BaseModel):
    secret_key: str = Field(default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7", description="Secret key for JWT")
    algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(default=60*24*3, description="Access token expiration in minutes")

class TaskSettings(BaseModel):
    max_concurrent_tasks: int = Field(default=10, description="Maximum number of concurrent tasks")

class SystemSettings(BaseModel):
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    task: TaskSettings = Field(default_factory=TaskSettings)

class SystemConfigManager:
    _instance = None
    _lock = threading.RLock()
    _config_path = './data/system_config.json'

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(SystemConfigManager, cls).__new__(cls)
                    cls._instance._load()
        return cls._instance

    def _load(self):
        self.config = SystemSettings()
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.config = SystemSettings(**data)
            except Exception as e:
                logging.error(f"Failed to load system config: {e}")
        else:
            self.save()

    def save(self):
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
                with open(self._config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.config.model_dump(), f, indent=4, ensure_ascii=False)
            except Exception as e:
                logging.error(f"Failed to save system config: {e}")

system_config = SystemConfigManager()
