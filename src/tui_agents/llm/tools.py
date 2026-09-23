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
