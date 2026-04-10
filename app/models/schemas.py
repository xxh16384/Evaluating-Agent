from pydantic import BaseModel, Field
from typing import List, Literal, Optional

# ==========================================
# 0. 前后端交互基础结构
# ==========================================
# 将 task_type 设为可空，给后端自动判定的空间
class TaskSubmitRequest(BaseModel):
    # 增加 "自动判定" 选项，并设为默认
    task_type: Literal["材料推断型", "明确对象型", "自动判定"] = Field(
        default="自动判定", 
        description="写作任务类型，若不确定请选择自动判定"
    )
    prompt_text: str = Field(..., description="作文题目具体要求")

class TaskSubmitResponse(BaseModel):
    code: int = 200
    msg: str = "任务已受理"
    task_id: str

# ==========================================
# 1. 模块一：语境与读者建模（层级 0 前置设定）
# ==========================================
class VirtualReaderContext(BaseModel):
    task_type: Literal["材料推断型", "明确对象型"] = Field(..., description="根据题目判断的写作任务类型")
    reader_identity: str = Field(..., description="虚拟读者的具体身份或形象刻画")
    prior_knowledge: List[str] = Field(..., description="读者对当前话题的既有认知、事实或潜在偏见")
    reader_expectation: List[str] = Field(..., description="读者在阅读此文时的核心诉求或期望")

# ==========================================
# 1.5 模块二（前置）：LLM 高保真文本切片
# ==========================================
class TextChunk(BaseModel):
    chunk_index: int = Field(..., description="片段的顺序编号，从 1 开始")
    original_text: str = Field(..., description="切分出来的原文片段，必须一字不差地保留原样")

class DocumentChunks(BaseModel):
    chunks: List[TextChunk] = Field(..., description="按照原文顺序切分好的文本片段列表")

# ==========================================
# 2. 模块二：流式解析与可识别性判定（层级 1）
# ==========================================
class ChunkEvaluation(BaseModel):
    chunk_index: int = Field(..., description="段落/句群的原始序号")
    is_recognizable: int = Field(..., description="字词句是否规范可解。是=1，否=0")
    has_coherence: int = Field(..., description="与上一段落/句子是否有逻辑衔接。是=1，否=0")
    deduction_reason: str = Field(..., description="如果上述任意一项为0，说明具体扣分原因；如果全为1，填'无'")

class Layer1Report(BaseModel):
    evaluations: List[ChunkEvaluation] = Field(..., description="所有文本块的底层评估记录列表")

# ==========================================
# 3. 模块三：语义图谱建构（层级 2 聚焦性）
# ==========================================
class NodeChain(BaseModel):
    edge_node: str = Field(..., description="边缘节点（论据/分论点）内容概括")
    intermediary_count: int = Field(..., description="推导至中心节点跨越的中介逻辑层级数")
    is_isolated: int = Field(..., description="是否为孤岛节点（游离于中心论点之外）。是=1，否=0")
    logic_strength: Literal["演绎", "归纳", "相关", "隐喻", "无效"] = Field(..., description="连接有效性分类")

class SemanticGraph(BaseModel):
    core_claim: str = Field(..., description="全篇的中心思想/总论点")
    node_chains: List[NodeChain] = Field(..., description="边缘节点到中心节点的推导链条集合")

# ==========================================
# 4. 模块四：全局交际效果评估（层级 3 合作性）
# ==========================================
class CommunicativeEffect(BaseModel):
    has_information_meaning: int = Field(..., description="信息意义：是否更新了读者的既有认知。是=1，否=0")
    information_analysis: str = Field(..., description="解释说明如何更新（或为何未更新）了读者认知")
    has_action_meaning: int = Field(..., description="行动意义：是否正面回应了读者的期望。是=1，否=0")
    action_analysis: str = Field(..., description="解释说明如何回应（或为何未回应）了读者期望")

# ==========================================
# 5. 模块五：最终前端渲染聚合数据模型
# ==========================================
class FinalEvaluationResult(BaseModel):
    total_score: float = Field(..., description="最终得分（满分60）")
    diagnostic_report: str = Field(..., description="包含改进建议的完整文本评语")
    layer1_recognizability: List[ChunkEvaluation] = Field(..., description="用于前端划线报错的底层扣分明细")
    layer2_focus: SemanticGraph = Field(..., description="用于前端渲染思维导图的图谱数据")
    layer3_cooperation: CommunicativeEffect = Field(..., description="高层级交际达成分析结果")