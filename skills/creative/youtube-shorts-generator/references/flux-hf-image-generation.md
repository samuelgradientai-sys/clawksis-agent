# FLUX + HuggingFace Inference — Image Generation per Segment

## HuggingFace Inference Providers (free tier)
FLUX.1-dev via HF Inference Providers — includes a free tier.

### Token Setup
1. https://huggingface.co/settings/tokens
2. Create **fine-grained token** with `Make calls to Inference Providers` permission
3. URL pre-filled: `https://huggingface.co/settings/tokens/new?ownUserPermissions=inference.serverless.write&tokenType=fineGrained`

### API Call
```python
import requests
resp = requests.post(
    "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-dev",
    headers={"Authorization": f"Bearer {HF_TOKEN}"},
    json={"inputs": "A person with thoughtful expression, cinematic, photorealistic"},
    timeout=60
)
if resp.status_code == 200:
    with open("image.png", "wb") as f:
        f.write(resp.content)
```

### Best prompts for psychology Shorts
| Segment | Prompt |
|---|---|
| Hook | "A person having sudden realization, cinematic lighting, dramatic portrait" |
| Points | "Brain with glowing neural connections, scientific, dark background" |
| Points | "Two people in deep conversation, warm lighting, documentary style" |
| Points | "Abstract human behavior visualization, flowing lines, artistic" |
| Points | "Person meditating, calm atmosphere, soft lighting, photorealistic" |
| CTA | "Silhouette looking at horizon, sunrise, motivational, cinematic" |
