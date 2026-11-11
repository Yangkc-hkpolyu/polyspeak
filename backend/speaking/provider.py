import json
from typing import Any
import httpx

from .config import Settings


class ProviderError(RuntimeError):
    pass


def parse_json(text: str) -> dict:
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        value = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise ProviderError("模型回复的格式不正确，请重试。本轮回答尚未提交。") from exc
    if not isinstance(value, dict):
        raise ProviderError("模型没有返回有效的结构化结果，请重试。")
    return value


class ModelProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, system: str, data: dict, *, json_mode: bool = True) -> Any:
        if not self.settings.api_key:
            raise ProviderError("尚未配置百炼 API Key。请在本机 .env 配置，或选择明确标注的离线演示模式。")
        payload = {
            "model": self.settings.chat_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ],
            "temperature": 0.35,
            "max_tokens": 4000 if data.get("task") == "feedback" else 1100,
            "enable_thinking": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        result = await self.request(payload)
        text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not isinstance(text, str) or not text.strip():
            raise ProviderError("模型返回了空回复，请稍后重试。")
        return parse_json(text) if json_mode else text

    async def request(self, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=20)) as client:
                response = await client.post(
                    f"{self.settings.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.api_key}"},
                    json=payload,
                )
        except httpx.RequestError as exc:
            raise ProviderError("连接模型服务失败，请检查网络和 .env 中的服务地址。") from exc
        if response.status_code in (401, 403):
            raise ProviderError("API Key 或模型权限不可用，请检查百炼账户及地域。")
        if response.status_code == 429:
            raise ProviderError("模型服务当前限流或额度不足，请稍后重试并检查账户额度。")
        if response.status_code >= 400:
            try:
                code = response.json().get("error", {}).get("code", str(response.status_code))
            except ValueError:
                code = str(response.status_code)
            raise ProviderError(f"模型服务请求失败（{code}）。请确认模型名称与服务地域匹配。")
        try:
            value = response.json()
        except ValueError as exc:
            raise ProviderError("模型服务没有返回有效结果，请稍后重试。") from exc
        if not isinstance(value, dict):
            raise ProviderError("模型服务返回了异常结果，请稍后重试。")
        return value

