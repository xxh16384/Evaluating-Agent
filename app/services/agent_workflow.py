import json
import logging
import asyncio
from app.utils.task_manager import get_task, remove_task
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

async def run_evaluation_pipeline(task_id: str):
    """
    核心工作流：按照交际语境范式，串行调度所有的 AI 模块，并通过 yield 返回 SSE 事件流。
    """
    task_data = get_task(task_id)
    if not task_data:
        yield f"event: error\ndata: {json.dumps({'msg': '未找到对应的任务数据，请重新上传'})}\n\n"
        return

    try:
        # 获取前端传来的原始参数
        image_bytes = task_data["image_bytes"]
        task_type = task_data["task_type"]
        prompt_text = task_data["prompt_text"]

        # ==========================================
        # 节点 0: OCR 识别图像到 Markdown
        # ==========================================
        logger.info(f"Task {task_id} - [1/6] 正在执行 OCR...")
        ocr_markdown = await parse_image_to_markdown(image_bytes)
        if not ocr_markdown:
            raise Exception("未能从图片中提取到任何有效文字。")
        # 推送给前端展示
        yield f"event: ocr_completed\ndata: {json.dumps({'markdown': ocr_markdown})}\n\n"
        
        if task_type == "自动判定":
            logger.info(f"Task {task_id} - 正在自动判定任务类型...")
            # 调用我们在 llm_services.py 中准备好的推断服务
            task_type = await infer_task_type(prompt_text)
            
            # 推送给前端，让用户知道智能体“思考”出了什么类型
            yield f"event: task_type_inferred\ndata: {json.dumps({'inferred_type': task_type})}\n\n"

        # ==========================================
        # 节点 1: 语境与读者建模 (模块一)
        # ==========================================
        # 接下来的模块一将使用判定好的 task_type
        logger.info(f"Task {task_id} - [2/6] 正在构建虚拟读者画像...")
        reader_context = await build_virtual_reader_context(task_type, prompt_text)
        yield f"event: context_built\ndata: {reader_context.model_dump_json()}\n\n"

        # ==========================================
        # 节点 2: LLM 高保真文本切片 (模块二 前置)
        # ==========================================
        logger.info(f"Task {task_id} - [3/6] 正在进行文本语义切片...")
        document_chunks = await segment_ocr_text(ocr_markdown)
        # 提取纯文本列表供下一环使用
        chunk_texts = [chunk.original_text for chunk in document_chunks.chunks]
        
        # 可选：如果你希望前端看到切片过程，可以推一个事件（前端不展示也可以静默接收）
        yield f"event: text_segmented\ndata: {document_chunks.model_dump_json()}\n\n"

        # ==========================================
        # 节点 3: 底层可识别性扫描 (模块二)
        # ==========================================
        logger.info(f"Task {task_id} - [4/6] 正在进行层级1扫描...")
        layer1_report = await evaluate_layer1_recognizability(chunk_texts)
        yield f"event: layer1_scanned\ndata: {layer1_report.model_dump_json()}\n\n"

        # ==========================================
        # 节点 4: 语义图谱建构 (模块三)
        # ==========================================
        logger.info(f"Task {task_id} - [5/6] 正在建构语义图谱...")
        semantic_graph = await build_semantic_graph(ocr_markdown)
        yield f"event: layer2_graphed\ndata: {semantic_graph.model_dump_json()}\n\n"

        # ==========================================
        # 节点 5: 全局交际效果评估 (模块四)
        # ==========================================
        logger.info(f"Task {task_id} - [6/6] 正在评估交际效果...")
        comm_effect = await evaluate_communicative_effect(reader_context, semantic_graph.core_claim)
        yield f"event: layer3_evaluated\ndata: {comm_effect.model_dump_json()}\n\n"

        # ==========================================
        # 节点 6: 最终算法结算与评语生成 (模块五)
        # ==========================================
        logger.info(f"Task {task_id} - 正在进行最终统分结算...")
        
        # 1. 黑盒算法计分（严格按照文档逻辑）
        base_rate = 1.0
        diagnostic_lines = [] # 收集扣分明细用于生成评语

        # -- 层级 1 扣分（可识别性、衔接）
        for eval_chunk in layer1_report.evaluations:
            if eval_chunk.is_recognizable == 0:
                base_rate -= 0.05
                diagnostic_lines.append(f"- 表达障碍：{eval_chunk.deduction_reason} (第{eval_chunk.chunk_index}句)")
            if eval_chunk.has_coherence == 0:
                base_rate -= 0.05
                diagnostic_lines.append(f"- 衔接断裂：{eval_chunk.deduction_reason} (第{eval_chunk.chunk_index}句)")

        # -- 层级 2 扣分（聚焦性、孤岛节点）
        for node in semantic_graph.node_chains:
            if node.is_isolated == 1:
                base_rate -= 0.1  # 孤岛节点属于严重跑题，扣分更重
                diagnostic_lines.append(f"- 游离废话：节点 '{node.edge_node}' 属于孤岛节点，未能指向核心论点。")
            elif node.intermediary_count < 1 or node.intermediary_count > 5:
                base_rate -= 0.05
                diagnostic_lines.append(f"- 逻辑层级异常：节点 '{node.edge_node}' 的中介推导层级（{node.intermediary_count}）超出了合理认知负荷。")

        # 将基础达成率限制在 [0.0, 1.0] 之间
        base_rate = max(0.0, min(1.0, base_rate))

        # -- 层级 3 扣分（一票否决级/降维打击）
        if comm_effect.has_information_meaning == 0 or comm_effect.has_action_meaning == 0:
            base_rate *= 0.6  # 核心交际未达成，直接折算最高只能拿及格分

        final_score = round(base_rate * 60.0, 1)

        # 2. 组装诊断性评语
        report_text = f"### 得分判定：{final_score}分 / 60分\n\n"
        report_text += f"**【交际效果判定】**\n"
        report_text += f"信息意义更新：{'✅ 达成' if comm_effect.has_information_meaning else '❌ 未达成'}。{comm_effect.information_analysis}\n"
        report_text += f"行动期望回应：{'✅ 达成' if comm_effect.has_action_meaning else '❌ 未达成'}。{comm_effect.action_analysis}\n\n"
        
        if diagnostic_lines:
            report_text += "**【阅读阻碍/扣分明细】**\n" + "\n".join(diagnostic_lines) + "\n\n"
        else:
            report_text += "**【阅读阻碍/扣分明细】**\n全文表达顺畅，逻辑聚焦，无明显阻碍。\n\n"

        # 3. 构造最终聚合数据并推送
        final_result = FinalEvaluationResult(
            total_score=final_score,
            diagnostic_report=report_text,
            layer1_recognizability=layer1_report.evaluations,
            layer2_focus=semantic_graph,
            layer3_cooperation=comm_effect
        )

        yield f"event: task_finished\ndata: {final_result.model_dump_json()}\n\n"
        logger.info(f"Task {task_id} - 全流程执行完毕，已推送完成事件。")

    except Exception as e:
        logger.error(f"Task {task_id} - 运行中发生错误: {e}")
        # 如果出错了，立刻推给前端报错，前端好停止 loading 状态
        yield f"event: error\ndata: {json.dumps({'msg': str(e)})}\n\n"
    
    finally:
        # 清理内存，防止积压
        remove_task(task_id)