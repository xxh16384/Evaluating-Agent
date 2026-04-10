import json
import logging
import asyncio
from app.utils.task_manager import (
    get_task, 
    update_task_status, 
    push_task_event, 
    get_task_events, 
    TaskStatus
)
from app.services.ocr_service import parse_image_to_markdown
from app.services.llm_service import (
    build_virtual_reader_context,
    segment_ocr_text,
    evaluate_layer1_recognizability,
    build_semantic_graph,
    evaluate_communicative_effect,
    infer_task_type
)
from app.models.schemas import FinalEvaluationResult

logger = logging.getLogger(__name__)

async def execute_evaluation_task(task_id: str):
    """
    【后台执行引擎】：受 asyncio.create_task 管理，独立于 HTTP 连接运行。
    负责运行 AI 逻辑并将结果推送到 Redis 事件流。
    """
    task_data = await get_task(task_id)
    if not task_data or task_data["status"] == TaskStatus.PROCESSING:
        return

    try:
        # 1. 标记状态并开始
        await update_task_status(task_id, TaskStatus.PROCESSING)
        
        image_bytes = task_data["image_bytes"]
        task_type = task_data["task_type"]
        prompt_text = task_data["prompt_text"]

        # ==========================================
        # 节点 0: OCR 识别
        # ==========================================
        logger.info(f"Task {task_id} - [1/7] 正在执行 OCR...")
        ocr_markdown = await parse_image_to_markdown(image_bytes)
        if not ocr_markdown:
            raise Exception("未能从图片中提取到任何有效文字。")
        await push_task_event(task_id, "ocr_completed", {"markdown": ocr_markdown})

        # ==========================================
        # 自动判定任务类型
        # ==========================================
        if task_type == "自动判定":
            logger.info(f"Task {task_id} - 自动判定任务类型...")
            task_type = await infer_task_type(prompt_text)
            await push_task_event(task_id, "task_type_inferred", {"inferred_type": task_type})

        # ==========================================
        # 节点 1: 语境与读者建模
        # ==========================================
        logger.info(f"Task {task_id} - [2/7] 构建虚拟读者画像...")
        reader_context = await build_virtual_reader_context(task_type, prompt_text)
        await push_task_event(task_id, "context_built", reader_context.model_dump())

        # ==========================================
        # 节点 2: LLM 高保真文本切片
        # ==========================================
        logger.info(f"Task {task_id} - [3/7] 文本语义切片...")
        document_chunks = await segment_ocr_text(ocr_markdown)
        chunk_texts = [chunk.original_text for chunk in document_chunks.chunks]
        await push_task_event(task_id, "text_segmented", document_chunks.model_dump())

        # ==========================================
        # 节点 3: 层级1扫描
        # ==========================================
        logger.info(f"Task {task_id} - [4/7] 层级1扫描...")
        layer1_report = await evaluate_layer1_recognizability(chunk_texts)
        await push_task_event(task_id, "layer1_scanned", layer1_report.model_dump())

        # ==========================================
        # 节点 4: 语义图谱建构
        # ==========================================
        logger.info(f"Task {task_id} - [5/7] 建构语义图谱...")
        semantic_graph = await build_semantic_graph(ocr_markdown)
        await push_task_event(task_id, "layer2_graphed", semantic_graph.model_dump())

        # ==========================================
        # 节点 5: 全局交际效果评估
        # ==========================================
        logger.info(f"Task {task_id} - [6/7] 评估交际效果...")
        comm_effect = await evaluate_communicative_effect(reader_context, semantic_graph.core_claim)
        await push_task_event(task_id, "layer3_evaluated", comm_effect.model_dump())

        # ==========================================
        # 节点 6: 最终算法结算 (完全保留用户原始算法逻辑)
        # ==========================================
        logger.info(f"Task {task_id} - [7/7] 最终统分结算...")
        base_rate = 1.0
        diagnostic_lines = []

        for eval_chunk in layer1_report.evaluations:
            if eval_chunk.is_recognizable == 0:
                base_rate -= 0.05
                diagnostic_lines.append(f"- 表达障碍：{eval_chunk.deduction_reason} (第{eval_chunk.chunk_index}句)")
            if eval_chunk.has_coherence == 0:
                base_rate -= 0.05
                diagnostic_lines.append(f"- 衔接断裂：{eval_chunk.deduction_reason} (第{eval_chunk.chunk_index}句)")

        for node in semantic_graph.node_chains:
            if node.is_isolated == 1:
                base_rate -= 0.1
                diagnostic_lines.append(f"- 游离废话：节点 '{node.edge_node}' 属于孤岛节点。")
            elif node.intermediary_count < 1 or node.intermediary_count > 5:
                base_rate -= 0.05
                diagnostic_lines.append(f"- 逻辑层级异常：节点 '{node.edge_node}' 推导层级异常。")

        base_rate = max(0.0, min(1.0, base_rate))
        if comm_effect.has_information_meaning == 0 or comm_effect.has_action_meaning == 0:
            base_rate *= 0.6

        final_score = round(base_rate * 60.0, 1)
        report_text = f"### 得分判定：{final_score}分 / 60分\n\n"
        # ... (此处省略部分 report_text 拼接代码，实际运行时请保留你原有的完整逻辑)
        report_text += f"**【交际效果判定】**\n信息意义：{'✅' if comm_effect.has_information_meaning else '❌'} | 行动意义：{'✅' if comm_effect.has_action_meaning else '❌'}\n\n"
        if diagnostic_lines:
            report_text += "**【扣分明细】**\n" + "\n".join(diagnostic_lines)

        final_result = FinalEvaluationResult(
            total_score=final_score,
            diagnostic_report=report_text,
            layer1_recognizability=layer1_report.evaluations,
            layer2_focus=semantic_graph,
            layer3_cooperation=comm_effect
        )

        # 最终归档：存入结果并推送完成事件
        final_json = final_result.model_dump_json()
        await update_task_status(task_id, TaskStatus.COMPLETED, result=final_json)
        await push_task_event(task_id, "task_finished", final_result.model_dump())

    except Exception as e:
        logger.error(f"Task {task_id} 运行失败: {e}")
        await update_task_status(task_id, TaskStatus.FAILED, error=str(e))
        await push_task_event(task_id, "error", {"msg": str(e)})


async def stream_task_monitor(task_id: str):
    """
    【前台监看引擎】：SSE 接口直接调用的函数。
    负责从 Redis 实时读取事件流并推送给前端。
    """
    current_idx = 0
    
    while True:
        # 1. 获取从 current_idx 开始的新事件
        events = await get_task_events(task_id, start_index=current_idx)
        
        for event in events:
            # 这里的 event 是字典：{"event": "...", "data": {...}}
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
            current_idx += 1
            
            # 如果读到了终点事件，直接安全退出
            if event['event'] in ["task_finished", "error"]:
                return

        # 2. 如果任务已经由于某些原因结束了，但队列里没写结束事件（兜底逻辑）
        task_data = await get_task(task_id)
        if not task_data:
            yield f"event: error\ndata: {json.dumps({'msg': '任务数据丢失'})}\n\n"
            return
            
        if task_data["status"] == TaskStatus.FAILED and not events:
            yield f"event: error\ndata: {json.dumps({'msg': task_data.get('error_msg') or '后台任务异常中断'})}\n\n"
            return

        # 3. 没读到新事件，稍微睡一下再看，避免 CPU 空转
        await asyncio.sleep(1)