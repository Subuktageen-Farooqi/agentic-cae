"""Server-side AI Studio key authentication, explicit Developer API selection."""
from providers.vertex import VertexGeminiProvider


class GeminiDeveloperProvider(VertexGeminiProvider):
    def availability_issues(self):
        return [f"{name} is not configured" for name, value in (
            ("GEMINI_API_KEY", self.config.gemini_api_key),
            ("GEMINI_MODEL_ID", self.config.gemini_model_id)) if not value]

    def _new_client(self, genai, types):
        return genai.Client(vertexai=False, api_key=self.config.gemini_api_key,
            http_options=types.HttpOptions(timeout=self.config.worker_timeout_seconds * 1000,
                                          retry_options=types.HttpRetryOptions(attempts=1)))
