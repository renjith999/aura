from dataclasses import dataclass

from app.prompts.memory_enrichment import v1


@dataclass(frozen=True)
class PromptDefinition:
    version: str
    instructions: str


CURRENT_PROMPT_VERSION = v1.PROMPT_VERSION

_PROMPTS = {
    v1.PROMPT_VERSION: PromptDefinition(
        version=v1.PROMPT_VERSION,
        instructions=v1.INSTRUCTIONS,
    )
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