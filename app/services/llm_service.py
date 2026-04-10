import logging
from openai import AsyncOpenAI
from app.core.config import settings
from app.models.schemas import (
    VirtualReaderContext,
    Layer1Report,
    SemanticGraph,
    CommunicativeEffect,
    DocumentChunks
)

logger = logging.getLogger(__name__)

# 初始化全局异步 OpenAI 客户端
# 注意：即使你用的是国内模型或代理，只要接口兼容 OpenAI 标准，就可以这样连
client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_API_URL,
    max_retries=2 # 增加默认重试次数以提高稳定性
)

async def build_virtual_reader_context(task_type: str, prompt_text: str) -> VirtualReaderContext:
    """
    模块一：语境与读者建模。根据题目设定虚拟读者画像。
    """
    # 【更新】增加极其严格的 JSON 格式示例约束
    system_prompt = """你是一个高级教育心理学与语用学分析引擎。
你需要阅读用户提供的作文题目或材料，并为其构建“虚拟读者”的认知语境。
1. 若为“材料推断型”，从材料的矛盾中反向推断隐藏受众。
2. 若为“明确对象型”，直接提取并丰满该对象形象。

【最高指令：输出格式约束】
由于系统架构要求，你必须且只能输出一个合法的 JSON 对象。绝对不要输出任何额外的解释性文本（如“好的”、“解析如下”等）。
你的 JSON 必须完全包含以下字段，严禁更改字段名称，严禁增减字段：
{
  "task_type": "材料推断型", // 或 明确对象型
  "reader_identity": "这里填写具体身份描述，例如：关注青年成长的学者",
  "prior_knowledge": [
    "既有认知1", 
    "既有认知2"
  ],
  "reader_expectation": [
    "期望1", 
    "期望2"
  ]
}"""

    user_prompt = f"任务类型：{task_type}\n题目/材料内容：\n{prompt_text}"

    try:
        completion = await client.beta.chat.completions.parse(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format=VirtualReaderContext,
            temperature=0.1 # 把温度进一步调低到0.1，让它不要乱发散
        )
        return completion.choices[0].message.parsed
    except Exception as e:
        logger.error(f"模块一 (读者建模) LLM 调用失败: {e}")
        raise

async def segment_ocr_text(ocr_markdown: str) -> DocumentChunks:
    """
    模块二（前置）：高保真语义切片。将 OCR 文本按语义边界切分为短句群。
    """
    system_prompt = """你是一个高精度的“文本语义切片引擎”。
你的唯一任务是将用户输入的 OCR 识别文本，按照合理的“语义完整性”切分为连续的独立句子或短句群。

【最高指令：输出格式约束】
你必须且只能输出一个合法的 JSON 对象。
1. 绝对保真：你必须【逐字逐句】保留原文的所有字符。严禁进行任何错别字纠正或语病润色。
2. 无缝拼接：所有 original_text 按顺序拼接后，必须与原文 100% 完全相等。
3. JSON 格式示例：
{
  "chunks": [
    {"chunk_index": 1, "original_text": "这是第一句话。"},
    {"chunk_index": 2, "original_text": "这是第二句话，存在语病但不能改。"}
  ]
}"""

    try:
        completion = await client.beta.chat.completions.parse(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": ocr_markdown}
            ],
            response_format=DocumentChunks,
            temperature=0.0 # 切片任务要求绝对确定性
        )
        return completion.choices[0].message.parsed
    except Exception as e:
        logger.error(f"文本切片 LLM 调用失败: {e}")
        raise

async def evaluate_layer1_recognizability(markdown_blocks: list[str]) -> Layer1Report:
    """
    模块二：层级 1 判定。底层可识别性与连贯性扫描。
    """
    system_prompt = """你是智能体底层阅读引擎。请遍历输入的文本块列表，模拟人类顺序阅读。
针对每一个文本块，进行以下严格的二元判定（1/0）：
1. 可识别性：是否存在生僻词、生造词、严重语病？（无=1，有=0）
2. 语篇连贯性：该文本块与上文是否有同义替换、逻辑连词、代词等形式上的衔接手段？（有=1，无=0，首段默认为1）
必须记录所有判定为 0 的具体原句及扣分原因。

【最高指令：输出格式约束】
你必须且只能输出一个合法的 JSON 对象，严禁输出任何额外文本。
你的 JSON 必须完全符合以下结构和字段名：
{
  "evaluations": [
    {
      "chunk_index": 1,
      "is_recognizable": 1,
      "has_coherence": 1,
      "deduction_reason": "无"
    },
    {
      "chunk_index": 2,
      "is_recognizable": 0,
      "has_coherence": 1,
      "deduction_reason": "存在严重语病：'XX'词语搭配不当"
    }
  ]
}"""

    formatted_blocks = "\n".join([f"[{i+1}] {block}" for i, block in enumerate(markdown_blocks)])

    try:
        completion = await client.beta.chat.completions.parse(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请逐段分析以下文本：\n{formatted_blocks}"}
            ],
            response_format=Layer1Report,
            temperature=0.1
        )
        return completion.choices[0].message.parsed
    except Exception as e:
        logger.error(f"模块二 (层级1扫描) LLM 调用失败: {e}")
        raise

async def build_semantic_graph(full_markdown: str) -> SemanticGraph:
    """
    模块三：语义图谱建构。提取中心论点及逻辑推导链。
    """
    system_prompt = """请将输入的文章解构为一个“中心-边缘”的语义网络图谱。
1. 提炼出文章唯一的“核心论点”。
2. 梳理所有的边缘节点（论据、分论点），统计它们推导至中心节点所需的中介节点数量。
3. 若某段内容与核心论点毫无逻辑关联，标记为孤岛节点(is_isolated=1)。
4. 评估逻辑连接强度(演绎、归纳、相关、隐喻、无效)。

【最高指令：输出格式约束】
你必须且只能输出一个合法的 JSON 对象，严禁输出任何额外文本。
你的 JSON 必须完全符合以下结构和字段名，logic_strength 只能是 [演绎, 归纳, 相关, 隐喻, 无效] 中的一个：
{
  "core_claim": "这里是全篇的核心论点",
  "node_chains": [
    {
      "edge_node": "第一段的论据A概括",
      "intermediary_count": 2,
      "is_isolated": 0,
      "logic_strength": "演绎"
    },
    {
      "edge_node": "完全跑题的废话段落概括",
      "intermediary_count": 0,
      "is_isolated": 1,
      "logic_strength": "无效"
    }
  ]
}"""

    try:
        completion = await client.beta.chat.completions.parse(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_markdown}
            ],
            response_format=SemanticGraph,
            temperature=0.2
        )
        return completion.choices[0].message.parsed
    except Exception as e:
        logger.error(f"模块三 (语义图谱) LLM 调用失败: {e}")
        raise

async def evaluate_communicative_effect(reader_context: VirtualReaderContext, core_claim: str) -> CommunicativeEffect:
    """
    模块四：全局交际效果评估。用核心论点去碰撞读者期望。
    """
    system_prompt = """你是交际效果终审法官。请根据提供的【虚拟读者画像】，评估作者的【核心论点】是否达成了有效交际。
1. 信息意义评估：论点是否为该读者增加了新信息、削弱了旧偏见？
2. 行动意义评估：论点是否解决了读者的矛盾、消除了迷误或回应了诉求？
给出 1/0 判定及深度分析。

【最高指令：输出格式约束】
你必须且只能输出一个合法的 JSON 对象，严禁输出任何额外文本。
你的 JSON 必须完全符合以下结构和字段名：
{
  "has_information_meaning": 1,
  "information_analysis": "详细解释为什么增加了信息意义...",
  "has_action_meaning": 0,
  "action_analysis": "详细解释为什么没有达成行动意义..."
}"""

    user_prompt = f"""
【虚拟读者画像】
身份：{reader_context.reader_identity}
既有认知：{reader_context.prior_knowledge}
核心期望：{reader_context.reader_expectation}

【作者核心论点】
{core_claim}
"""

    try:
        completion = await client.beta.chat.completions.parse(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format=CommunicativeEffect,
            temperature=0.4
        )
        return completion.choices[0].message.parsed
    except Exception as e:
        logger.error(f"模块四 (交际效果) LLM 调用失败: {e}")
        raise

async def infer_task_type(prompt_text: str) -> str:
    """
    新增服务：根据题目内容自动判定属于哪种交际范式。
    """
    system_prompt = """你是一个作文题目分类专家。
请判断该题目属于以下哪种类型：
1. 材料推断型：题目只提供了背景材料，没有明确要求写给谁（如：结合材料写感悟）。
2. 明确对象型：题目明确要求了写作对象（如：给XX的一封信、对XX的演讲稿、建议书等）。

【最高指令：输出格式约束】
你必须且只能输出这五个字中的一个：'材料推断型' 或 '明确对象型'。绝对不要输出任何额外文字。"""

    try:
        completion = await client.chat.completions.create( # 这种简单判定无需用 .parse
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text}
            ],
            temperature=0.0
        )
        prediction = completion.choices[0].message.content.strip()
        # 兜底逻辑：防止模型吐出多余字符
        return "明确对象型" if "明确对象" in prediction else "材料推断型"
    except Exception as e:
        logger.error(f"任务类型推断失败: {e}")
        return "材料推断型" # 发生错误时默认为最常见的类型