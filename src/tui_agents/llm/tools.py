COLLECTOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_papers",
            "description": "Search for research papers on a given topic using available sources",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for papers (e.g., 'diffusion models optimal transport')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 20,
                    },
                    "source": {
                        "type": "string",
                        "enum": ["arxiv", "semantic_scholar", "all"],
                        "description": "Source to search",
                        "default": "all",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

DISTILLER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_distillation",
            "description": "Save a distilled summary and analysis of a paper",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Comprehensive summary of the paper (2-3 paragraphs)",
                    },
                    "methodology": {
                        "type": "string",
                        "description": "Detailed description of the methodology and approach",
                    },
                    "contributions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Key contributions of the paper",
                    },
                    "limitations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Limitations and weaknesses identified in the paper",
                    },
                    "key_equations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Key mathematical equations (LaTeX format)",
                    },
                    "related_work": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Notable related work cited in the paper",
                    },
                },
                "required": ["summary", "methodology", "contributions"],
            },
        },
    },
]

IMPLEMENTER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_implementation",
            "description": "Save the generated implementation code",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Complete Python implementation code",
                    },
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Python package dependencies required",
                    },
                    "tests": {
                        "type": "string",
                        "description": "Pytest test cases for the implementation",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Explanation of the implementation approach and design decisions",
                    },
                },
                "required": ["code", "dependencies", "explanation"],
            },
        },
    },
]

PROTOTYPER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_prototype",
            "description": "Save a runnable prototype script",
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": "Complete runnable Python script that demonstrates the implementation",
                    },
                    "requirements": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "pip install requirements for the prototype",
                    },
                    "usage_instructions": {
                        "type": "string",
                        "description": "Instructions for running the prototype",
                    },
                    "expected_output": {
                        "type": "string",
                        "description": "Description of expected output/behavior",
                    },
                },
                "required": ["script", "requirements", "usage_instructions"],
            },
        },
    },
]

BENCHMARKER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_benchmark",
            "description": "Save benchmark results for an implementation",
            "parameters": {
                "type": "object",
                "properties": {
                    "metrics": {
                        "type": "object",
                        "description": "Dictionary of metric names to values",
                    },
                    "compared_to_baseline": {
                        "type": "boolean",
                        "description": "Whether results were compared against a baseline",
                    },
                    "passed_threshold": {
                        "type": "boolean",
                        "description": "Whether results passed the quality threshold",
                    },
                    "analysis": {
                        "type": "string",
                        "description": "Analysis of benchmark results and suggestions for improvement",
                    },
                },
                "required": ["metrics", "analysis"],
            },
        },
    },
]
