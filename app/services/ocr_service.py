import base64
import logging
import httpx
from app.core.config import settings

# 配置简单的日志记录
logger = logging.getLogger(__name__)

async def parse_image_to_markdown(image_bytes: bytes) -> str:
    """
    调用远端 OCR (Layout Parsing) API，将二进制图片转换为 Markdown 文本。
    """
    # 将二进制图片数据编码为 base64 字符串
    file_data = base64.b64encode(image_bytes).decode("ascii")

    headers = {
        "Authorization": f"token {settings.OCR_API_TOKEN}",
        "Content-Type": "application/json"
    }

    # 根据示例，图片类型的 fileType 设为 1
    required_payload = {
        "file": file_data,
        "fileType": 1, 
    }

    optional_payload = {
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useChartRecognition": False,
    }
    
    payload = {**required_payload, **optional_payload}

    # 使用 httpx.AsyncClient 发起异步请求
    # 设置 timeout=30.0 因为 OCR 处理图片可能需要几秒到十几秒的时间
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                settings.OCR_API_URL, 
                json=payload, 
                headers=headers
            )
            # 检查 HTTP 状态码，如果不是 2xx 则抛出异常
            response.raise_for_status()
            
            result = response.json().get("result", {})
            layout_results = result.get("layoutParsingResults", [])
            
            if not layout_results:
                logger.warning("OCR 接口返回成功，但未能解析出任何布局内容。")
                return ""

            # 遍历解析结果，提取纯文本 Markdown
            markdown_texts = []
            for res in layout_results:
                md_text = res.get("markdown", {}).get("text", "")
                if md_text:
                    markdown_texts.append(md_text)
            
            # 将多块内容拼接成一个完整的 Markdown 字符串并返回
            final_markdown = "\n\n".join(markdown_texts)
            return final_markdown

        except httpx.TimeoutException:
            logger.error("OCR API 请求超时。")
            raise Exception("OCR 识别服务超时，请稍后重试。")
        except httpx.HTTPStatusError as e:
            logger.error(f"OCR API 请求失败，状态码: {e.response.status_code}")
            raise Exception(f"OCR 服务端异常，状态码: {e.response.status_code}")
        except Exception as e:
            logger.error(f"OCR 服务调用发生未知错误: {str(e)}")
            raise Exception(f"无法连接到 OCR 服务或解析失败: {str(e)}")