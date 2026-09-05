"""Native Strands BedrockModel Provider for Covenant."""

import logging
from typing import Any, Dict, List, Optional
import boto3
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import ClientError, BotoCoreError

from strands.models.bedrock import BedrockModel

from covenant.config import settings
from covenant.llm.provider import AbstractModelProvider, ChatMessage, LLMResponse

logger = logging.getLogger(__name__)


class BedrockModelProvider(AbstractModelProvider):
    """
    AWS Bedrock provider utilizing native Strands BedrockModel.
    Maintains Covenant's provider abstraction while delegating reasoning to Strands.
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        region_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        boto_session: Optional[boto3.Session] = None,
        boto_client_config: Optional[BotocoreConfig] = None,
        endpoint_url: Optional[str] = None,
    ):
        import os
        self.model_id = model_id or os.getenv("COVENANT_BEDROCK_MODEL_ID") or settings.bedrock_model_id
        if not self.model_id or not self.model_id.strip():
            raise ValueError(
                "Bedrock provider requires a non-empty model_id. "
                "Set COVENANT_BEDROCK_MODEL_ID or pass model_id explicitly."
            )

        self.region_name = (
            region_name
            or os.getenv("COVENANT_AWS_REGION")
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or settings.aws_region
        )
        if temperature is not None:
            self.temperature = float(temperature)
        elif os.getenv("COVENANT_BEDROCK_TEMPERATURE"):
            self.temperature = float(os.getenv("COVENANT_BEDROCK_TEMPERATURE"))
        else:
            self.temperature = settings.bedrock_temperature

        if max_tokens is not None:
            self.max_tokens = int(max_tokens)
        elif os.getenv("COVENANT_BEDROCK_MAX_TOKENS"):
            self.max_tokens = int(os.getenv("COVENANT_BEDROCK_MAX_TOKENS"))
        else:
            self.max_tokens = settings.bedrock_max_tokens

        self.endpoint_url = endpoint_url


        model_kwargs: Dict[str, Any] = {
            "model_id": self.model_id,
        }
        if self.temperature is not None:
            model_kwargs["temperature"] = float(self.temperature)
        if self.max_tokens is not None:
            model_kwargs["max_tokens"] = int(self.max_tokens)

        # Instantiate native strands BedrockModel
        # Uses standard AWS credential resolution chain (environment, IAM roles, ~/.aws/credentials)
        self.strands_model = BedrockModel(
            boto_session=boto_session,
            boto_client_config=boto_client_config,
            region_name=self.region_name,
            endpoint_url=self.endpoint_url,
            **model_kwargs,
        )

    @property
    def model_name(self) -> str:
        return f"bedrock/{self.model_id}"

    async def is_available(self) -> bool:
        """
        Check if Bedrock is reachable and permissible for this account.
        Returns False if offline, credentials missing, or blocked by account Error 002.
        """
        try:
            client = self.strands_model.client
            if not client:
                return False
            return True
        except (ClientError, BotoCoreError, Exception) as e:
            logger.warning(f"Bedrock availability check failed: {e}")
            return False

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Send messages to Bedrock through native Strands BedrockModel.
        """
        strands_messages = []
        system_prompt = None

        for m in messages:
            if m.role == "system":
                system_prompt = m.content
            else:
                strands_messages.append({
                    "role": m.role if m.role in ("user", "assistant") else "user",
                    "content": [{"text": m.content}],
                })

        if not strands_messages:
            strands_messages.append({"role": "user", "content": [{"text": "Hello"}]})

        # Update dynamic config if specified
        stream_kwargs: Dict[str, Any] = {}
        if temperature is not None:
            self.strands_model.update_config(temperature=temperature)
        if max_tokens is not None:
            self.strands_model.update_config(max_tokens=max_tokens)

        accumulated_text = []
        try:
            async for event in self.strands_model.stream(
                messages=strands_messages,
                system_prompt=system_prompt,
                **stream_kwargs,
            ):
                if "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"].get("delta", {})
                    if "text" in delta:
                        accumulated_text.append(delta["text"])
        except ClientError as e:
            err_msg = str(e)
            if "Error 002" in err_msg:
                logger.error(f"Bedrock access blocked by AWS account-level Error 002: {e}")
            raise

        full_content = "".join(accumulated_text)
        return LLMResponse(
            content=full_content,
            model_name=self.model_name,
            raw_response={"model_id": self.model_id, "region": self.region_name},
        )
