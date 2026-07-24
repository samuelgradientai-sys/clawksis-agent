# SadTalker Avatar via Replicate (talking head)

## What it does
Takes a single portrait photo + audio WAV/MP3 → outputs a talking-head video with lip-sync.

## Replicate API
- Model: `cjwbw/sadtalker`
- Cost: ~$0.075 per video (~13 runs per $1)
- Predictions complete in ~54 seconds
- Requires billing setup: https://replicate.com/account/billing
- API key format: `r8_...`

## API Call
```python
import requests, time
REPLICATE_KEY=os.environ["REPLICATE_API_KEY"]

# Start prediction
r = requests.post("https://api.replicate.com/v1/predictions", 
    headers={"Authorization": f"Bearer {REPLICATE_KEY}"},
    json={
        "version": "cjwbw/sadtalker",
        "input": {
            "source_image": "https://.../photo.png",  # URL to portrait photo
            "driven_audio": "https://.../audio.wav"    # URL to audio file
        }
    })

# Poll for result
prediction_id = r.json()["id"]
for _ in range(30):
    time.sleep(3)
    r2 = requests.get(f"https://api.replicate.com/v1/predictions/{prediction_id}",
        headers={"Authorization": f"Bearer {REPLICATE_KEY}"})
    if r2.json()["status"] == "succeeded":
        print(f"Output: {r2.json()['output']}")
        break
```

## Known issues
- Replicate requires billing setup (no free tier for SadTalker)
- Account needs payment method even for $5 trial credits
- Alternative: run SadTalker locally on user's Radeon 8060S machine
