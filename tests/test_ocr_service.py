import os
import pytest
from app.services.ocr_service import parse_image_to_markdown

# 获取当前测试文件所在的目录
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
# 拼接测试图片的绝对路径 (确保你在 tests/assets/ 下放了一张名为 sample_essay.jpg 的图片)
TEST_IMAGE_PATH = os.path.join(TEST_DIR, "assets", "sample_essay.jpg")

@pytest.mark.asyncio
async def test_parse_image_to_markdown_success():
    """
    测试 OCR 服务能否成功将图片解析为 Markdown
    """
    # 1. 准备测试数据
    assert os.path.exists(TEST_IMAGE_PATH), f"请先在 {TEST_IMAGE_PATH} 放置一张测试图片"
    
    with open(TEST_IMAGE_PATH, "rb") as f:
        image_bytes = f.read()

    # 2. 调用服务
    print("\n[Test] 正在请求远端 OCR 接口，请稍候...")
    markdown_result = await parse_image_to_markdown(image_bytes)

    # 3. 断言与验证
    assert markdown_result is not None
    assert isinstance(markdown_result, str)
    assert len(markdown_result) > 0, "返回的 Markdown 文本为空"

    # 打印部分结果看看效果
    print("\n========== OCR 解析结果预览 ==========")
    print(markdown_result[:500] + "..." if len(markdown_result) > 500 else markdown_result)
    print("======================================")