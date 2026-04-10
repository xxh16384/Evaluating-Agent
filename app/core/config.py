from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    全局配置类：自动从环境变量或 .env 文件中读取配置
    """
    # 项目基础配置
    PROJECT_NAME: str = "Essay Grading Agent API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # OCR 服务配置
    OCR_API_URL: str
    OCR_API_TOKEN: str

    # 大模型服务配置
    LLM_API_URL: str
    LLM_API_KEY: str
    LLM_MODEL_NAME: str
    
    # 评测结果存储配置（Redis）
    REDIS_URL: str = "redis://localhost:6379/0"

    # 指定去哪里找 .env 文件
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # 如果环境变量中有同名字段，以环境变量为准
        env_nested_delimiter="__", 
        extra="ignore"
    )

# 实例化配置对象，整个项目只需要导入这个 settings 即可
settings = Settings()