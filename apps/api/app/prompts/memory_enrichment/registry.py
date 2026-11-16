from dataclasses import dataclass

from app.prompts.memory_enrichment import v1, v1_1, v1_2, v1_3, v1_4


@dataclass(frozen=True)
class PromptDefinition:
    version: str
    instructions: str


CURRENT_PROMPT_VERSION = v1_4.PROMPT_VERSION

_PROMPTS = {
    prompt.PROMPT_VERSION: PromptDefinition(
        version=prompt.PROMPT_VERSION,
        instructions=prompt.INSTRUCTIONS,
    )
    for prompt in (v1, v1_1, v1_2, v1_3, v1_4)
}


def get_memory_enrichment_prompt(
    version: str | None = None,
) -> PromptDefinition:
    selected_version = version or CURRENT_PROMPT_VERSION

    try:
        return _PROMPTS[selected_version]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported memory enrichment prompt version: "
            f"{selected_version}"
        ) from exc