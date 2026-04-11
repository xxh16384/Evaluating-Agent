import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse

# 导入我们的模型和工具
from app.models.schemas import TaskSubmitResponse
from app.utils.task_manager import create_task
# 注意：这里导入的是拆分后的两个核心函数
from app.services.agent_workflow import execute_evaluation_task, stream_task_monitor

# 创建路由对象
router = APIRouter()

@router.post("/upload", response_model=TaskSubmitResponse)
async def upload_task(
    image: UploadFile = File(...),
    task_type: str = Form("自动判定"), 
    prompt_text: str = Form(...)
):
    """
    【第一阶段：提交】
    接收前端上传数据，存入 Redis，并立即触发后台异步批改任务。
    """
    # 1. 基础校验
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传有效的图片文件")
    
    # 2. 读取图片二进制流
    image_bytes = await image.read()
    
    # 3. 在 Redis 中创建任务，拿到 task_id
    task_id = await create_task(task_type, prompt_text, image_bytes)
    
    # 4. 【核心改动】触发后台异步任务（不等待其执行结果，直接向下运行）
    # asyncio.create_task 会将协程丢进 FastAPI 的事件循环后台运行
    asyncio.create_task(execute_evaluation_task(task_id))
    
    # 5. 立即给前端返回 task_id，让前端去连接 SSE
    return TaskSubmitResponse(task_id=task_id)


@router.get("/stream/{task_id}")
async def stream_evaluation(task_id: str):
    """
    【第二阶段：监看】
    SSE 流式接口。前端通过 task_id 连接此接口。
    该接口只负责从 Redis 队列中读取并转发事件，不参与实际的 AI 计算。
    """
    # 返回 StreamingResponse，调用监看者函数 stream_task_monitor
    # 媒体类型必须是 text/event-stream
    return StreamingResponse(
        stream_task_monitor(task_id), 
        media_type="text/event-stream"
    )