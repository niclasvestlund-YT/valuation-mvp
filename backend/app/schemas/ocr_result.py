"""OCR result schema for cross-verification with Vision identification."""

from dataclasses import dataclass, field


@dataclass
class OcrResult:
    detected_text: list[str] = field(default_factory=list)
    detected_logos: list[str] = field(default_factory=list)
    detected_labels: list[str] = field(default_factory=list)
    web_entities: list[str] = field(default_factory=list)
    source: str = "none"
    raw_confidence: float = 0.0
    processing_time_ms: int = 0
    provider: str = "none"        # "google_vision" | "easyocr" | "none"
    text_found: bool = False      # True if OCR found any text

    @classmethod
    def empty(cls) -> "OcrResult":
        return cls()

    @property
    def has_text(self) -> bool:
        return bool(self.detected_text)

    @property
    def has_logos(self) -> bool:
        return bool(self.detected_logos)

    @property
    def all_text_lower(self) -> str:
        """All detected text joined and lowercased for matching."""
        return " ".join(self.detected_text).lower()

    @property
    def all_logos_lower(self) -> list[str]:
        return [logo.lower() for logo in self.detected_logos]
