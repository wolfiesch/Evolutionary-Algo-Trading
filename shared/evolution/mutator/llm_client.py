"""
LLM client wrapper - provider-agnostic interface.

Supports OpenAI and Anthropic APIs with unified interface.
Default: OpenAI GPT-5 mini for cost efficiency.
"""
import os
import json
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


@dataclass
class LLMConfig:
    """LLM client configuration."""
    provider: LLMProvider
    model: str
    api_key: str
    max_tokens: int = 500  # Sufficient for JSON strategy responses
    temperature: float = 0.7
    log_dir: Optional[Path] = None  # For interaction logging

    @classmethod
    def from_env(cls, provider: LLMProvider = LLMProvider.OPENAI) -> "LLMConfig":
        """
        Create config from environment variables.

        Environment variables:
            OPENAI_API_KEY - for OpenAI
            ANTHROPIC_API_KEY - for Anthropic
        """
        if provider == LLMProvider.OPENAI:
            api_key = os.environ.get("OPENAI_API_KEY", "")
            model = "gpt-5-mini"  # GPT-5 mini - cost-effective for strategy generation
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            model = "claude-haiku-4-5-20251001"  # Haiku 4.5 - fast & cheap for JSON generation

        return cls(
            provider=provider,
            model=model,
            api_key=api_key,
        )


class LLMClient(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._log_file: Optional[Path] = None
        if config.log_dir:
            config.log_dir.mkdir(parents=True, exist_ok=True)
            self._log_file = config.log_dir / "llm_interactions.jsonl"

    @abstractmethod
    def _call_api(self, prompt: str) -> str:
        """Provider-specific API call. Override in subclasses."""
        pass

    def generate(self, prompt: str, context: Optional[dict] = None) -> str:
        """
        Send prompt and return response with logging.

        Args:
            prompt: The prompt to send
            context: Optional context for logging (strategy name, etc.)

        Returns:
            Raw response text from LLM
        """
        start_time = time.time()
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "provider": self.config.provider.value,
            "model": self.config.model,
            "context": context or {},
            "prompt_length": len(prompt),
        }

        try:
            response = self._call_api(prompt)
            elapsed = time.time() - start_time

            log_entry.update({
                "success": True,
                "response_length": len(response),
                "elapsed_seconds": round(elapsed, 2),
            })

            self._log_interaction(log_entry, prompt, response)
            return response

        except Exception as e:
            elapsed = time.time() - start_time
            log_entry.update({
                "success": False,
                "error": str(e),
                "elapsed_seconds": round(elapsed, 2),
            })
            self._log_interaction(log_entry, prompt, None)
            raise

    def _log_interaction(
        self,
        entry: dict,
        prompt: str,
        response: Optional[str]
    ) -> None:
        """Log interaction to file if configured."""
        if not self._log_file:
            return

        # Add prompt and response to entry
        full_entry = {
            **entry,
            "prompt": prompt[:1000] + "..." if len(prompt) > 1000 else prompt,
            "response": (response[:1000] + "..." if response and len(response) > 1000 else response),
        }

        try:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(full_entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to log LLM interaction: {e}")


class OpenAIClient(LLMClient):
    """OpenAI API implementation."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        """Lazy-initialize OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.config.api_key)
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        return self._client

    def _call_api(self, prompt: str) -> str:
        """Call OpenAI API."""
        client = self._get_client()

        # GPT-5.x models use reasoning tokens internally, need higher max_completion_tokens
        # to leave room for actual output after reasoning completes
        max_tokens = self.config.max_tokens
        if self.config.model.startswith("gpt-5"):
            # GPT-5 typically uses 200-500 tokens for reasoning, need buffer for output
            max_tokens = max(max_tokens, 2000)

        params = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": max_tokens,
        }

        # GPT-5.x models don't support custom temperature
        if not self.config.model.startswith("gpt-5"):
            params["temperature"] = self.config.temperature

        response = client.chat.completions.create(**params)

        return response.choices[0].message.content


class AnthropicClient(LLMClient):
    """Anthropic Claude API implementation."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        """Lazy-initialize Anthropic client."""
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.config.api_key)
            except ImportError:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
        return self._client

    def _call_api(self, prompt: str) -> str:
        """Call Anthropic API."""
        client = self._get_client()

        response = client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        return response.content[0].text


class GeminiClient(LLMClient):
    """Google Gemini API implementation."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._model = None

    def _get_model(self):
        """Lazy-initialize Gemini model."""
        if self._model is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.config.api_key)
                self._model = genai.GenerativeModel(self.config.model)
            except ImportError:
                raise ImportError("google-generativeai package not installed. Run: pip install google-generativeai")
        return self._model

    def _call_api(self, prompt: str) -> str:
        """Call Gemini API."""
        model = self._get_model()

        response = model.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
            }
        )

        return response.text


def create_llm_client(config: LLMConfig) -> LLMClient:
    """
    Factory function to create appropriate LLM client.

    Args:
        config: LLMConfig with provider, model, api_key

    Returns:
        LLMClient instance (OpenAIClient, AnthropicClient, or GeminiClient)
    """
    if config.provider == LLMProvider.OPENAI:
        return OpenAIClient(config)
    elif config.provider == LLMProvider.ANTHROPIC:
        return AnthropicClient(config)
    elif config.provider == LLMProvider.GEMINI:
        return GeminiClient(config)
    else:
        raise ValueError(f"Unknown provider: {config.provider}")


def create_default_client(log_dir: Optional[Path] = None) -> LLMClient:
    """
    Create default LLM client from environment.

    Priority: Anthropic > OpenAI > Gemini (Anthropic reliable, others have quota issues)

    Args:
        log_dir: Optional directory for logging interactions

    Returns:
        LLMClient instance
    """
    # Try Anthropic first (most reliable)
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-haiku-20241022",  # Haiku 3.5 - fast & cheap for JSON generation
            api_key=anthropic_key,
            log_dir=log_dir,
        )
        return AnthropicClient(config)

    # Try OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-5-mini",  # GPT-5 mini - cost-effective for strategy generation
            api_key=openai_key,
            log_dir=log_dir,
        )
        return OpenAIClient(config)

    # Try Gemini as last fallback
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        config = LLMConfig(
            provider=LLMProvider.GEMINI,
            model="gemini-2.0-flash",  # Gemini 2.0 Flash - reliable JSON output
            api_key=gemini_key,
            log_dir=log_dir,
        )
        return GeminiClient(config)

    raise ValueError(
        "No LLM API key found. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY environment variable."
    )


def create_analysis_client(log_dir: Optional[Path] = None) -> LLMClient:
    """
    Create a capable LLM client for strategy analysis.

    Uses Sonnet (Anthropic) or GPT-4o (OpenAI) for reasoning about
    why strategies work. Sonnet provides good analysis at reasonable cost.

    Priority: Anthropic Sonnet > OpenAI GPT-4o > Gemini Pro

    Args:
        log_dir: Optional directory for logging interactions

    Returns:
        LLMClient instance configured for analysis
    """
    # Try Anthropic Sonnet first (good reasoning, reasonable cost)
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",  # Sonnet 4 - good reasoning, cost-effective
            api_key=anthropic_key,
            max_tokens=2000,  # Analysis needs more tokens
            temperature=0.3,  # Lower temperature for analytical tasks
            log_dir=log_dir,
        )
        return AnthropicClient(config)

    # Try OpenAI GPT-5 for complex analysis
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-5-mini",  # GPT-5 mini - cost-effective for analysis
            api_key=openai_key,
            max_tokens=2000,
            log_dir=log_dir,
        )
        return OpenAIClient(config)

    # Try Gemini Pro as fallback
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        config = LLMConfig(
            provider=LLMProvider.GEMINI,
            model="gemini-2.5-pro",  # Gemini Pro - reasoning capable
            api_key=gemini_key,
            max_tokens=2000,
            temperature=0.3,
            log_dir=log_dir,
        )
        return GeminiClient(config)

    raise ValueError(
        "No LLM API key found. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY environment variable."
    )
