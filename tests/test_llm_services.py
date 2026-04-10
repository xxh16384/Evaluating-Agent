import os
import pytest
from app.services.llm_service import (
    build_virtual_reader_context,
    segment_ocr_text,
    evaluate_layer1_recognizability,
    build_semantic_graph,
    evaluate_communicative_effect
)
from app.models.schemas import VirtualReaderContext

# ==========================================
# 测试数据准备与路径配置
# ==========================================
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(TEST_DIR, "assets")
PROMPT_FILE = os.path.join(ASSETS_DIR, "sample_prompt.txt")
ESSAY_FILE = os.path.join(ASSETS_DIR, "sample_essay.md")

def read_text_file(filepath: str) -> str:
    """辅助函数：安全读取 UTF-8 文本文件"""
    assert os.path.exists(filepath), f"请先在 {filepath} 放置测试文本文件"
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

# ==========================================
# 1. 测试模块一：语境与读者建模
# ==========================================
@pytest.mark.asyncio
async def test_build_virtual_reader_context():
    print("\n[Test 1] 正在测试：语境与读者建模...")
    prompt_text = read_text_file(PROMPT_FILE)
    
    result = await build_virtual_reader_context("材料推断型", prompt_text)
    
    assert result is not None
    assert len(result.reader_identity) > 0
    print(f"✅ 成功生成读者画像: {result.reader_identity}")

# ==========================================
# 2. 测试模块二(前置)：LLM 文本切片
# ==========================================
@pytest.mark.asyncio
async def test_segment_ocr_text():
    print("\n[Test 2] 正在测试：LLM 高保真文本切片...")
    essay_text = read_text_file(ESSAY_FILE)
    
    # 为了测试速度，可以只截取前300个字符去测切片
    test_text = essay_text[:300] 
    
    result = await segment_ocr_text(test_text)
    
    assert result is not None
    assert len(result.chunks) > 0
    print(f"✅ 成功切分文本为 {len(result.chunks)} 个 Chunk。")
    print(f"   第一个 Chunk: {result.chunks[0].original_text}")

# ==========================================
# 3. 测试模块二：层级1 底层可识别性扫描
# ==========================================
@pytest.mark.asyncio
async def test_evaluate_layer1_recognizability():
    print("\n[Test 3] 正在测试：底层可识别性扫描...")
    # 模拟一份已经被切分好的纯文本列表（包含故意制造的语病）
    mock_chunks = [
        "在人生的长河中，我们都是航行者。",
        "有的人虽然很努力的划船，但是因为方向搞错的缘故，所以导致了南辕北辙的下场。", # 存在杂糅语病
        "这告诉我们一个道理。"
    ]
    
    result = await evaluate_layer1_recognizability(mock_chunks)
    
    assert result is not None
    assert len(result.evaluations) == len(mock_chunks)
    
    # 验证大模型是否抓出了第二句的错误
    errors = [e for e in result.evaluations if e.is_recognizable == 0]
    print(f"✅ 扫描完成。共发现 {len(errors)} 处底层错误。")
    if errors:
        print(f"   查错示例: Chunk {errors[0].chunk_index} -> {errors[0].deduction_reason}")

# ==========================================
# 4. 测试模块三：层级2 语义图谱建构
# ==========================================
@pytest.mark.asyncio
async def test_build_semantic_graph():
    print("\n[Test 4] 正在测试：语义图谱建构...")
    essay_text = read_text_file(ESSAY_FILE)
    
    result = await build_semantic_graph(essay_text)
    
    assert result is not None
    assert len(result.core_claim) > 0
    print(f"✅ 图谱建构成功！")
    print(f"   提取的核心论点: {result.core_claim}")
    print(f"   共提取边缘逻辑节点: {len(result.node_chains)} 个")

# ==========================================
# 5. 测试模块四：层级3 全局交际效果评估
# ==========================================
@pytest.mark.asyncio
async def test_evaluate_communicative_effect():
    print("\n[Test 5] 正在测试：全局交际效果评估...")
    
    # 手动构造一个读者画像 Mock 数据，避免依赖前面的测试
    mock_reader = VirtualReaderContext(
        task_type="材料推断型",
        reader_identity="关注青年基础教育的阅卷教师",
        prior_knowledge=["知道本手是基础，妙手是创新"],
        reader_expectation=["希望看到作者踏实筑基的价值观"]
    )
    mock_core_claim = "青年人应当拒绝浮躁，在夯实本手的基础上，去追求人生的妙手。"
    
    result = await evaluate_communicative_effect(mock_reader, mock_core_claim)
    
    assert result is not None
    print(f"✅ 交际评估完成！")
    print(f"   信息意义得分: {result.has_information_meaning}")
    print(f"   行动意义得分: {result.has_action_meaning}")
    print(f"   最终裁判分析: {result.action_analysis[:50]}...")