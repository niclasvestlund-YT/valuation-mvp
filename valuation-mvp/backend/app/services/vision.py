import base64
import json
import logging
from openai import AsyncOpenAI
from ..config import settings
from ..models import VisionResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a product identification expert specializing in consumer electronics. Analyze this image and identify the EXACT product.

Respond ONLY in JSON:
{
  "product_name": "Full name with brand + exact model",
  "brand": "Brand",
  "model": "Exact model identifier (e.g. WH-1000XM4, NOT WH-1000XM5)",
  "confidence": 0.0-1.0,
  "category": "headphones|smartphone|laptop|camera|drone|tablet|smartwatch|other",
  "year_released": 2021,
  "raw_description": "Detailed description of what you see"
}

CRITICAL: Be extremely precise about model numbers. XM4 ≠ XM5. iPhone 13 ≠ iPhone 14. If you cannot determine the exact model from the image, set confidence below 0.6 and explain in raw_description what makes it ambiguous."""


async def identify_product(image_bytes_list: list[bytes]) -> VisionResult:
    """Send all images in one request so the model reasons about them jointly."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    content: list[dict] = []
    for image_bytes in image_bytes_list:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
        timeout=10,
    )
    data = json.loads(response.choices[0].message.content)
    return VisionResult(**data)
