"""LLM orchestration — resolution ladder, tool loop, response generation."""


async def handle_message(user_id: str, message: str) -> str:
    """Process a user message through the resolution ladder.

    Steps: cache -> Google Places -> web search -> pre-call check -> voice call.
    """
    # TODO: implement resolution ladder with Claude tool-calling loop
    raise NotImplementedError
