from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from app.models.schemas import TaskSubmitResponse
from app.utils.task_manager import create_task
from app.services.agent_workflow import run_evaluation_pipeline

# 创建路由对象
router = APIRouter()

@router.post("/upload", response_model=TaskSubmitResponse)
async def upload_task(
    image: UploadFile = File(...),
    # 将默认值改为 "自动判定"
    task_type: str = Form("自动判定"), 
    prompt_text: str = Form(...)
):
    """
    接收前端上传数据。task_type 可选: 材料推断型, 明确对象型, 自动判定。
    """
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传有效的图片文件")
    
    image_bytes = await image.read()
    
    # 将包含 "自动判定" 的参数存入任务管理器
    task_id = create_task(task_type, prompt_text, image_bytes)
    
    return TaskSubmitResponse(task_id=task_id)

@router.get("/stream/{task_id}")
async def stream_evaluation(task_id: str):
    """
    SSE 流式接口。前端拿到 task_id 后请求此接口，
    后端将异步推送 OCR、切片、各层级评分以及最终报告。
    """
    # 返回 StreamingResponse，媒体类型必须是 text/event-stream
    return StreamingResponse(
        run_evaluation_pipeline(task_id), 
        media_type="text/event-stream"
    )