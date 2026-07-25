from __future__ import annotations

from typing import Any

from tui_agents.llm.client import LLMClient
from tui_agents.storage.models import Implementation


ESTIMATOR_PROMPT = """You are analyzing a Python ML implementation to estimate its runtime.
Consider the following factors and make your best guess (does not need to be precise):

1. Model size: number of layers, hidden dimensions, parameter count
2. Dataset: is it synthetic (small), MNIST-scale (~60K samples), or larger?
3. Training: number of epochs, batch size
4. Hardware: this runs CPU-only in a Docker container (no GPU)
5. Output type: does it train from scratch, or just run inference/basic computation?

Respond with a JSON object:
- estimate_seconds: integer, best guess at runtime in seconds
- reasoning: string, brief explanation of your estimate (1-2 sentences)"""


class RuntimeEstimator:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def estimate(self, implementation: Implementation, prototype_code: str) -> dict[str, Any]:
        code_excerpt = implementation.code
        if len(code_excerpt) > 4000:
            code_excerpt = code_excerpt[:4000] + "\n# ... (truncated)"

        proto_excerpt = prototype_code
        if len(proto_excerpt) > 2000:
            proto_excerpt = proto_excerpt[:2000] + "\n# ... (truncated)"

        deps = ", ".join(implementation.dependencies[:10]) if implementation.dependencies else "none"

        user_prompt = f"""Implementation code:
```python
{code_excerpt}
```

Prototype code:
```python
{proto_excerpt}
```

Dependencies: {deps}

Estimate how long this will take to run CPU-only in Docker."""

        schema = {
            "type": "object",
            "properties": {
                "estimate_seconds": {"type": "integer", "description": "Estimated runtime in seconds"},
                "reasoning": {"type": "string", "description": "Brief explanation of the estimate"},
            },
            "required": ["estimate_seconds", "reasoning"],
        }

        try:
            result = await self.llm.chat_structured(
                system_prompt=ESTIMATOR_PROMPT,
                user_prompt=user_prompt,
                response_schema=schema,
                max_tokens=512,
            )
            if "error" in result:
                return {"estimate_seconds": 60, "reasoning": "Could not estimate; defaulting to 60s."}
            return result
        except Exception:
            return {"estimate_seconds": 60, "reasoning": "Could not estimate; defaulting to 60s."}
