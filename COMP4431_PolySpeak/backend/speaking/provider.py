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
        raise ProviderError("The model response had an invalid format. Try again; this answer has not been submitted.") from exc
    if not isinstance(value, dict):
        raise ProviderError("The model did not return a valid structured response. Try again.")
    return value


class ModelProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, system: str, data: dict, *, json_mode: bool = True) -> Any:
        if not self.settings.api_key:
            raise ProviderError("Configure the Bailian API key in the local .env file, or choose offline demo mode.")
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
            raise ProviderError("The model returned an empty response. Try again later.")
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
            raise ProviderError("Could not connect to the model service. Check your network and the service address in .env.") from exc
        if response.status_code in (401, 403):
            raise ProviderError("The API key or model access is unavailable. Check your Bailian account and region.")
        if response.status_code == 429:
            raise ProviderError("The model service is rate-limited or has insufficient quota. Try again later and check your account.")
        if response.status_code >= 400:
            try:
                code = response.json().get("error", {}).get("code", str(response.status_code))
            except ValueError:
                code = str(response.status_code)
            raise ProviderError(f"Model service request failed ({code}). Check that the model name matches the service region.")
        try:
            value = response.json()
        except ValueError as exc:
            raise ProviderError("The model service returned no valid result. Try again later.") from exc
        if not isinstance(value, dict):
            raise ProviderError("The model service returned an unexpected result. Try again later.")
        return value

