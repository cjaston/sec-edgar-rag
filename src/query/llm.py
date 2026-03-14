"""
Multi-provider LLM abstraction.

Supports OpenAI, Anthropic, and Google with a common interface.
The provider and model are configurable via env vars or the UI.
Eliza doesn't lock clients into one vendor — this demonstrates that philosophy.

Supports streaming mode for CLI output (text appears word-by-word).
"""

import sys
import time

from openai import OpenAI
import config


def _get_openai_client(api_key: str | None = None) -> OpenAI:
    return OpenAI(api_key=api_key or config.OPENAI_API_KEY)


def call_llm(
    messages: list[dict],
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    api_key: str | None = None,
    stream: bool = False,
) -> dict:
    """
    Call an LLM with the given messages. Returns a standardized response dict.

    Args:
        messages: List of {"role": "system"|"user", "content": "..."} dicts
        provider: "openai", "anthropic", or "google"
        model: Model name override
        temperature: Temperature override
        max_tokens: Max output tokens override
        api_key: API key override
        stream: If True, print tokens to stdout as they arrive

    Returns:
        {
            "provider": str,
            "model": str,
            "content": str (the response text),
            "input_tokens": int,
            "output_tokens": int,
        }
    """
    provider = provider or config.LLM_PROVIDER
    model = model or config.LLM_MODEL
    temperature = temperature if temperature is not None else config.LLM_TEMPERATURE
    max_tokens = max_tokens or config.LLM_MAX_TOKENS

    if provider == "openai":
        return _call_openai(messages, model, temperature, max_tokens, api_key, stream)
    elif provider == "anthropic":
        return _call_anthropic(messages, model, temperature, max_tokens, api_key, stream)
    elif provider == "google":
        return _call_google(messages, model, temperature, max_tokens, api_key)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def _call_openai(messages, model, temperature, max_tokens, api_key, stream=False):
    client = _get_openai_client(api_key)

    # Retry with backoff for rate limits
    for attempt in range(3):
        try:
            if stream:
                try:
                    response = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                        stream_options={"include_usage": True},
                    )
                except Exception as e:
                    err_str = str(e).lower()
                    if "request too large" in err_str or "must be reduced" in err_str or ("rate_limit" in err_str and "token" in err_str):
                        return {
                            "provider": "openai",
                            "model": model,
                            "content": f"[Error: Prompt too large for your OpenAI rate limit. Try a more specific question or switch to Anthropic provider.]\n\nDetails: {e}",
                            "input_tokens": 0,
                            "output_tokens": 0,
                        }
                    raise
                content = ""
                input_tokens = 0
                output_tokens = 0
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        text = chunk.choices[0].delta.content
                        content += text
                        sys.stdout.write(text)
                        sys.stdout.flush()
                    if chunk.usage:
                        input_tokens = chunk.usage.prompt_tokens
                        output_tokens = chunk.usage.completion_tokens
                print()  # newline after stream
                return {
                    "provider": "openai",
                    "model": model,
                    "content": content,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }
            else:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                break
        except Exception as e:
            err_str = str(e).lower()
            if "request too large" in err_str or "must be reduced" in err_str:
                raise
            if "rate_limit" in err_str or "429" in str(e):
                wait = 5 * (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
                if attempt == 2:
                    raise
            else:
                raise

    choice = response.choices[0]
    usage = response.usage
    return {
        "provider": "openai",
        "model": model,
        "content": choice.message.content,
        "input_tokens": usage.prompt_tokens,
        "output_tokens": usage.completion_tokens,
    }


def _call_anthropic(messages, model, temperature, max_tokens, api_key, stream=False):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key or config.ANTHROPIC_API_KEY)

    # Anthropic uses a separate system parameter, not a system message
    system_text = ""
    user_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_text = msg["content"]
        else:
            user_messages.append(msg)

    if stream:
        content = ""
        input_tokens = 0
        output_tokens = 0
        with client.messages.stream(
            model=model,
            system=system_text,
            messages=user_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ) as stream_resp:
            for text in stream_resp.text_stream:
                content += text
                sys.stdout.write(text)
                sys.stdout.flush()
        print()  # newline after stream
        usage = stream_resp.get_final_message().usage
        return {
            "provider": "anthropic",
            "model": model,
            "content": content,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        }

    response = client.messages.create(
        model=model,
        system=system_text,
        messages=user_messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return {
        "provider": "anthropic",
        "model": model,
        "content": response.content[0].text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def _call_google(messages, model, temperature, max_tokens, api_key):
    import google.generativeai as genai
    genai.configure(api_key=api_key or config.GOOGLE_API_KEY)
    gmodel = genai.GenerativeModel(model)

    # Google uses a single prompt string, not message array
    prompt = "\n\n".join(msg["content"] for msg in messages)
    response = gmodel.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) if hasattr(response, "usage_metadata") else 0
    output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) if hasattr(response, "usage_metadata") else 0

    return {
        "provider": "google",
        "model": model,
        "content": response.text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
