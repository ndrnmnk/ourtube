import yaml

class Config:
    _instance = None

    def __new__(cls, path="config.yaml"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config(path)
        return cls._instance

    def _load_config(self, path):
        with open(path, "r") as file:
            self._config = yaml.safe_load(file)

    def get(self, key, default=None):
        return self._config.get(key, default)

    def all(self):
        return self._config

config_instance = Config()