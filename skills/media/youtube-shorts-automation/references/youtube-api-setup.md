# YouTube Data API v3 — Upload Setup Guide

> Based on Google Cloud Console setup + youtube-upload CLI (tokland/youtube-upload) + official API docs. June 2026.

## 🏁 One-Time Setup

### 1. Create Google Cloud Project
1. Go to https://console.cloud.google.com/
2. Create new project
3. Navigate to APIs & Services → Library
4. Search and enable **YouTube Data API v3**

### 2. Create OAuth 2.0 Credentials
1. APIs & Services → Credentials
2. Create Credentials → OAuth 2.0 Client ID
3. Application type: **Desktop app**
4. Name: `youtube-upload` (or whatever)
5. Download JSON → save as `~/.client_secrets.json`

### 3. Install upload tool
```bash
# Option A: youtube-upload CLI (tokland)
pip3 install --upgrade google-api-python-client google-auth-oauthlib
git clone https://github.com/tokland/youtube-upload
cd youtube-upload && python3 setup.py install

# Option B: Custom Python script
pip3 install google-api-python-client google-auth-oauthlib
```

### 4. First upload (manual — generates refresh token)
```bash
youtube-upload \
  --client-secrets=~/.client_secrets.json \
  --title="Test video" \
  --description="Automated upload test" \
  --privacy="unlisted" \
  video.mp4
```
- First run opens a browser for OAuth consent
- After authorizing, credentials saved to `~/.youtube-upload-credentials.json`
- Subsequent runs use the refresh token automatically — no browser needed

## 🔄 Automated Upload (for cron)

Once the refresh token exists:

```bash
youtube-upload \
  --client-secrets=~/.client_secrets.json \
  --credentials-file=~/.youtube-upload-credentials.json \
  --title="Video Title" \
  --description="Description with links" \
  --tags="tag1,tag2" \
  --category="Education" \
  --privacy="public" \
  video.mp4
```

## 💸 Quota

| Request | Cost (units) |
|---------|:---:|
| Upload video | 1,600 |
| Fetch video details | 1 |
| Update metadata | 50 |
| **Quota (default daily)** | **10,000** |
| **Max uploads/day** | **~6** |

To request quota increase: Google Cloud Console → APIs & Services → Quotas → YouTube Data API v3 → Edit

## 🐛 Common Issues

| Issue | Fix |
|-------|-----|
| `401 Unauthorized` | Refresh token expired. Delete credentials file and re-authorize |
| `403 Forbidden (quota)` | Wait for reset (midnight PT) or request quota increase |
| `403 Forbidden (scope)` | Re-authorize with correct OAuth scope (youtube.upload) |
| `500/503` | Transient — retry with exponential backoff |
| Refresh token expired | Tokens expire after 6 months of inactivity. Schedule monthly "keepalive" |
| Multiple channels | youtube-upload will prompt to select channel on first auth |

## 📝 Video Requirements

| Format | Spec |
|--------|------|
| Shorts format | Vertical 9:16, 1080×1920, max 60s |
| Long-form | 16:9, 1920×1080, any length |
| Max file size | 256 GB |
| Max duration | 12 hours |
| Accepted formats | .mp4 (H.264), .mov, .avi, .wmv, .flv, .webm |
