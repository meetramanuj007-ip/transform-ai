import pytest
import asyncio
from pydantic import BaseModel

from app.services.llm.provider import GroqProvider

# Simple schema for testing

def SimpleSchemaFactory():
    class SimpleSchema(BaseModel):
        ok: bool
    return SimpleSchema

# Helper subclass to mock `complete` method
def make_provider(return_str: str):
    class MockProvider(GroqProvider):
        async def complete(self, *args, **kwargs):
            return return_str
    return MockProvider(api_key="dummy", model="dummy")

@pytest.mark.asyncio
async def test_extract_pure_json():
    provider = make_provider('{"ok": true}')
    schema = SimpleSchemaFactory()
    result = await provider.structured([{"role": "user", "content": "test"}], schema)
    assert result.ok is True

@pytest.mark.asyncio
async def test_extract_prefixed_json():
    provider = make_provider('Return {"ok": true}')
    schema = SimpleSchemaFactory()
    result = await provider.structured([{"role": "user", "content": "test"}], schema)
    assert result.ok is True

@pytest.mark.asyncio
async def test_extract_surrounding_text():
    provider = make_provider('Here is the JSON: {"ok": true}')
    schema = SimpleSchemaFactory()
    result = await provider.structured([{"role": "user", "content": "test"}], schema)
    assert result.ok is True

@pytest.mark.asyncio
async def test_extract_markdown_fence():
    provider = make_provider('```json\n{"ok": true}\n```')
    schema = SimpleSchemaFactory()
    result = await provider.structured([{"role": "user", "content": "test"}], schema)
    assert result.ok is True

@pytest.mark.asyncio
async def test_extract_nested_json():
    nested = '{"a": {"b": 1}, "c": [1,2], "ok": true}'
    provider = make_provider(nested)
    class NestedSchema(BaseModel):
        a: dict
        c: list
        ok: bool
    result = await provider.structured([{"role": "user", "content": "test"}], NestedSchema)
    assert result.ok is True
    assert result.a == {"b": 1}
    assert result.c == [1, 2]

@pytest.mark.asyncio
async def test_braces_inside_string():
    txt = '{"text": "{ not a JSON }", "ok": true}'
    provider = make_provider(txt)
    class TextSchema(BaseModel):
        text: str
        ok: bool
    result = await provider.structured([{"role": "user", "content": "test"}], TextSchema)
    assert result.ok is True
    assert result.text == "{ not a JSON }"

@pytest.mark.asyncio
async def test_invalid_response_raises():
    provider = make_provider('No JSON here')
    schema = SimpleSchemaFactory()
    with pytest.raises(RuntimeError):
        await provider.structured([{"role": "user", "content": "test"}], schema)

@pytest.mark.asyncio
async def test_multiple_json_sections():
    provider = make_provider('First {"ok": true} second {"ok": false}')
    schema = SimpleSchemaFactory()
    result = await provider.structured([{"role": "user", "content": "test"}], schema)
    # Should parse the first JSON object
    assert result.ok is True
