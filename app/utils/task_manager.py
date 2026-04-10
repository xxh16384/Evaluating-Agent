import uuid
from typing import Dict, Any

# 内存中的任务暂存区（全局字典）
# 【重要提示】：在目前的开发和本地测试阶段，使用内存字典是最快、最轻量的方案。
# 但是到了未来的生产环境，如果你的 FastAPI 启动了多个 Worker（多进程），
# 内存字典是无法跨进程共享的，到时候你需要把这个字典替换为 Redis 存储。
_TASK_STORE: Dict[str, Any] = {}

def create_task(task_type: str, prompt_text: str, image_bytes: bytes) -> str:
    """
    创建一个新任务，生成唯一的 task_id，并将数据暂存到内存中。
    """
    # 生成一个类似 eval_a1b2c3d4 的短ID
    task_id = f"eval_{uuid.uuid4().hex[:8]}"
    
    _TASK_STORE[task_id] = {
        "task_type": task_type,
        "prompt_text": prompt_text,
        "image_bytes": image_bytes,
        "status": "pending"
    }
    
    return task_id

def get_task(task_id: str) -> dict | None:
    """
    根据 task_id 获取任务的具体数据。如果任务不存在则返回 None。
    """
    return _TASK_STORE.get(task_id)

def remove_task(task_id: str):
    """
    任务执行完毕或发生致命错误后，务必调用此方法清理内存。
    如果不清理，随着评改作文越来越多，服务器内存会被撑爆。
    """
    if task_id in _TASK_STORE:
        del _TASK_STORE[task_id]