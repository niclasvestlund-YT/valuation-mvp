import base64
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpg",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/avif",
    "image/heic",
    "image/heif",
}
HEIC_IMAGE_MIME_TYPES = {
    "image/heic",
    "image/heif",
}
OUTPUT_IMAGE_MIME_TYPE = "image/jpeg"
MAX_LONGEST_SIDE = 1600
JPEG_QUALITY = 82

_HEIC_SUPPORT_REGISTERED = False


class ImagePreprocessError(ValueError):
    pass


@dataclass(frozen=True)
class PreprocessedImage:
    data_url: str
    output_bytes: bytes
    source_mime_type: str
    output_mime_type: str
    width: int
    height: int


def normalize_mime_type(mime_type: str) -> str:
    return mime_type.lower().strip()


def split_data_url(data_url: str) -> tuple[str, bytes]:
    if not data_url.startswith("data:") or ";base64," not in data_url:
        raise ImagePreprocessError("Image must be a base64 data URL.")

    header, encoded = data_url.split(",", 1)
    mime_type = normalize_mime_type(header[5:].split(";")[0])

    try:
        decoded = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ImagePreprocessError("Invalid base64 image payload.") from exc

    return mime_type, decoded


def has_heic_support() -> bool:
    global _HEIC_SUPPORT_REGISTERED

    if _HEIC_SUPPORT_REGISTERED:
        return True

    try:
        # Optional dependency for HEIC/HEIF decoding with Pillow.
        from pillow_heif import register_heif_opener
    except ImportError:
        return False

    register_heif_opener()
    _HEIC_SUPPORT_REGISTERED = True
    return True


def is_supported_mime_type(mime_type: str) -> bool:
    return normalize_mime_type(mime_type) in SUPPORTED_IMAGE_MIME_TYPES


def ensure_decoder_support(source_mime_type: str) -> None:
    normalized = normalize_mime_type(source_mime_type)

    if normalized not in SUPPORTED_IMAGE_MIME_TYPES:
        raise ImagePreprocessError(f"Unsupported image type: {source_mime_type}")

    if normalized in HEIC_IMAGE_MIME_TYPES and not has_heic_support():
        raise ImagePreprocessError(
            "HEIC/HEIF images require the optional 'pillow-heif' package. "
            "Install it with: python3 -m pip install pillow-heif"
        )


def calculate_resized_dimensions(
    width: int,
    height: int,
    max_longest_side: int = MAX_LONGEST_SIDE,
) -> tuple[int, int]:
    longest_side = max(width, height)
    if longest_side <= max_longest_side:
        return width, height

    scale = max_longest_side / longest_side
    return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def convert_image_bytes_to_jpeg_data_url(
    raw_bytes: bytes,
    source_mime_type: str,
    max_longest_side: int = MAX_LONGEST_SIDE,
    jpeg_quality: int = JPEG_QUALITY,
) -> PreprocessedImage:
    ensure_decoder_support(source_mime_type)

    try:
        with Image.open(BytesIO(raw_bytes)) as source_image:
            image = ImageOps.exif_transpose(source_image)
            target_width, target_height = calculate_resized_dimensions(
                image.width,
                image.height,
                max_longest_side=max_longest_side,
            )

            if (target_width, target_height) != image.size:
                image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)

            rgb_image = _convert_to_rgb(image)

            buffer = BytesIO()
            rgb_image.save(
                buffer,
                format="JPEG",
                quality=jpeg_quality,
                optimize=True,
            )
    except UnidentifiedImageError as exc:
        raise ImagePreprocessError("Image bytes could not be decoded.") from exc
    except OSError as exc:
        normalized = normalize_mime_type(source_mime_type)
        if normalized in HEIC_IMAGE_MIME_TYPES:
            raise ImagePreprocessError(
                "HEIC/HEIF image conversion failed. "
                "Verify that 'pillow-heif' is installed and the uploaded file is a valid HEIC/HEIF image."
            ) from exc
        raise ImagePreprocessError("Image conversion failed.") from exc

    output_bytes = buffer.getvalue()
    encoded = base64.b64encode(output_bytes).decode("utf-8")
    return PreprocessedImage(
        data_url=f"data:{OUTPUT_IMAGE_MIME_TYPE};base64,{encoded}",
        output_bytes=output_bytes,
        source_mime_type=normalize_mime_type(source_mime_type),
        output_mime_type=OUTPUT_IMAGE_MIME_TYPE,
        width=target_width,
        height=target_height,
    )


def preprocess_data_url_image(
    data_url: str,
    max_longest_side: int = MAX_LONGEST_SIDE,
    jpeg_quality: int = JPEG_QUALITY,
) -> PreprocessedImage:
    mime_type, raw_bytes = split_data_url(data_url)
    return convert_image_bytes_to_jpeg_data_url(
        raw_bytes,
        source_mime_type=mime_type,
        max_longest_side=max_longest_side,
        jpeg_quality=jpeg_quality,
    )


def preprocess_images(
    images: list[str],
    max_longest_side: int = MAX_LONGEST_SIDE,
    jpeg_quality: int = JPEG_QUALITY,
) -> list[PreprocessedImage]:
    processed_images: list[PreprocessedImage] = []

    for image in images:
        if not image:
            continue

        processed_images.append(
            preprocess_data_url_image(
                image,
                max_longest_side=max_longest_side,
                jpeg_quality=jpeg_quality,
            )
        )

    if not processed_images:
        raise ImagePreprocessError("At least one valid image is required.")

    return processed_images


def _convert_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"}:
        background = Image.new("RGB", image.size, (255, 255, 255))
        alpha_image = image.convert("RGBA")
        background.paste(alpha_image, mask=alpha_image.getchannel("A"))
        return background

    if image.mode == "P":
        return _convert_to_rgb(image.convert("RGBA"))

    if image.mode != "RGB":
        return image.convert("RGB")

    return image
