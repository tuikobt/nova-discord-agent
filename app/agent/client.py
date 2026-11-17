"""Official SDK, fixed API origin, explicit retention and retry settings."""

from openai import AsyncOpenAI


class ResponsesClient:
    def __init__(self, config):
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.key, base_url="https://api.openai.com/v1", max_retries=0, timeout=30
        )

    async def respond(self, *, inputs, instructions, tools):
        return await self.client.responses.create(
            model=self.config.model,
            input=inputs,
            instructions=instructions,
            tools=tools,
            parallel_tool_calls=False,
            max_output_tokens=self.config.output_tokens,
            store=False,
        )

    async def close(self):
        await self.client.close()
