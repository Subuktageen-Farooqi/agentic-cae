"""Select authentication without falling back to another billable provider."""


def make_provider(config):
    if config.llm_provider == "gemini_developer":
        from providers.gemini_developer import GeminiDeveloperProvider
        return GeminiDeveloperProvider(config)
    from providers.vertex import VertexGeminiProvider
    return VertexGeminiProvider(config)
