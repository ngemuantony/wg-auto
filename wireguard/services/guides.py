from dataclasses import dataclass
from django.template.loader import render_to_string
import markdown  # new import

@dataclass
class GuideContext:
    peer_name: str
    server_endpoint: str
    allowed_ips: str
    dns: str
    platform: str

class InstallationGuideService:
    """
    Generates step-by-step WireGuard installation guides
    per platform using Django templates.
    """

    SUPPORTED_PLATFORMS = [
        "android",
        "ios",
        "windows",
        "linux",
        "macos",
    ]

    @classmethod
    def generate(cls, context: GuideContext) -> str:
        if context.platform not in cls.SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform: {context.platform}")

        template = f"wireguard/guides/{context.platform}.md"

        # Render Markdown template as plain text first
        markdown_content = render_to_string(
            template,
            {
                "peer": context.peer_name,
                "endpoint": context.server_endpoint,
                "allowed_ips": context.allowed_ips,
                "dns": context.dns,
            },
        )

        # Convert Markdown to HTML
        html_content = markdown.markdown(
            markdown_content, 
            extensions=["fenced_code", "tables"]
        )

        return html_content
