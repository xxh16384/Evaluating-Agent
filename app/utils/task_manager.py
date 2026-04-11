import json
import base64
import redis.asyncio as redis
from typing import Optional, Dict, Any
from app.core.config import settings

# 任务状态常量
class TaskStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# 初始化异步 Redis 客户端
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
# 注意：对于二进制图片数据，我们需要一个不自动 decode 的客户端
raw_redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)

# 设置数据过期时间（例如：24小时，过期后自动清理释放内存）
TASK_EXPIRE = 86400 

async def create_task(task_type: str, prompt_text: str, image_bytes: bytes) -> str:
    """创建任务并存入 Redis"""
    import uuid
    task_id = f"eval_{uuid.uuid4().hex[:8]}"
    
    # 1. 存储元数据 (JSON 字符串)
    meta_data = {
        "task_id": task_id,
        "task_type": task_type,
        "prompt_text": prompt_text,
        "status": TaskStatus.PENDING,
        "final_result": None,
        "error_msg": None
    }
    
    # 使用 Redis 事务或 Pipeline 确保原子性
    async with redis_client.pipeline() as pipe:
        await pipe.set(f"task:{task_id}:meta", json.dumps(meta_data), ex=TASK_EXPIRE)
        # 2. 存储二进制图片 (独立 Key)
        await raw_redis_client.set(f"task:{task_id}:image", image_bytes, ex=TASK_EXPIRE)
        await pipe.execute()
        
    return task_id

async def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """从 Redis 获取任务元数据和图片"""
    meta_str = await redis_client.get(f"task:{task_id}:meta")
    if not meta_str:
        return None
    
    task_data = json.loads(meta_str)
    # 获取图片二进制
    image_bytes = await raw_redis_client.get(f"task:{task_id}:image")
    task_data["image_bytes"] = image_bytes
    return task_data

async def update_task_status(task_id: str, status: str, result: str = None, error: str = None):
    """原子化更新 Redis 中的任务状态"""
    meta_str = await redis_client.get(f"task:{task_id}:meta")
    if not meta_str:
        return
    
    meta_data = json.loads(meta_str)
    meta_data["status"] = status
    if result:
        meta_data["final_result"] = result
    if error:
        meta_data["error_msg"] = error
        
    await redis_client.set(f"task:{task_id}:meta", json.dumps(meta_data), ex=TASK_EXPIRE)

async def remove_task(task_id: str):
    """手动删除任务（通常靠 TTL 自动删除即可）"""
    await redis_client.delete(f"task:{task_id}:meta", f"task:{task_id}:image")

# 增加两个核心函数：推事件和读事件
async def push_task_event(task_id: str, event_type: str, data: Any):
    """向任务的事件流中推送一条新消息"""
    event_payload = json.dumps({"event": event_type, "data": data})
    # 使用 Redis List 存储事件序列
    await redis_client.rpush(f"task:{task_id}:events", event_payload)
    # 设置过期时间
    await redis_client.expire(f"task:{task_id}:events", TASK_EXPIRE)

async def get_task_events(task_id: str, start_index: int = 0):
    """从指定索引开始读取所有历史事件"""
    events = await redis_client.lrange(f"task:{task_id}:events", start_index, -1)
    return [json.loads(e) for e in events]