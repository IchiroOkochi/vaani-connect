import os
from huggingface_hub import login


def load_hf_token() -> str:
    """Read Hugging Face token from environment variables."""
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
    if not token:
        raise ValueError(
            "HF token is missing. Set HF_TOKEN or HUGGINGFACE_HUB_TOKEN before starting the backend."
        )
    return token


def login_huggingface() -> str:
    """Login to Hugging Face Hub and return the active token."""
    token = load_hf_token()
    login(token=token)
    os.environ["HF_TOKEN"] = token
    os.environ["HUGGINGFACE_HUB_TOKEN"] = token
    return token
