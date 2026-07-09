"""Request models + param normalization for the screenshot endpoints."""
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class ScreenshotOptions(BaseModel):
    url: str
    width: Optional[int] = None
    height: Optional[int] = None
    type: Optional[str] = None  # jpeg | png
    quality: int = 80
    full_page: bool = False
    dark_mode: bool = False
    emulate_device: Optional[str] = None
    mobile: bool = False
    scale: Optional[float] = None
    delay: int = 0
    wait_until: str = "networkidle"
    timeout: int = 10000

    @field_validator("type")
    @classmethod
    def _type(cls, v):
        if v is not None and v.lower() not in ("jpeg", "png"):
            raise ValueError("type must be 'jpeg' or 'png'")
        return v

    @field_validator("quality")
    @classmethod
    def _quality(cls, v):
        if not 1 <= v <= 100:
            raise ValueError("quality must be 1-100")
        return v

    @field_validator("wait_until")
    @classmethod
    def _wait(cls, v):
        if v not in ("load", "networkidle", "domcontentloaded"):
            raise ValueError("wait_until must be load|networkidle|domcontentloaded")
        return v

    @field_validator("url")
    @classmethod
    def _url(cls, v):
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url must be a valid http(s) URL")
        return v

    def to_opts(self) -> dict[str, Any]:
        # Flatten to a plain dict, dropping unset optionals.
        out: dict[str, Any] = {"url": self.url}
        for k in ("width", "height", "type", "quality", "full_page",
                  "dark_mode", "emulate_device", "mobile", "scale",
                  "delay", "wait_until", "timeout"):
            val = getattr(self, k)
            if val is not None:
                out[k] = val
        return out


class BatchRequest(BaseModel):
    requests: list[ScreenshotOptions] = Field(..., min_length=1)

    @field_validator("requests")
    @classmethod
    def _len(cls, v):
        if len(v) > 10:
            raise ValueError("at most 10 requests per batch")
        return v


class AsyncRequest(BaseModel):
    url: str
    options: dict[str, Any] = Field(default_factory=dict)
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None

    @field_validator("url")
    @classmethod
    def _url(cls, v):
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url must be a valid http(s) URL")
        return v
