# OCR Image Text Extraction

## When to use

When the user sends an image (screenshot of a Teams assignment, a cover page, a document, etc.) and you need to extract the text from it to understand the task or recreate the document.

## Dependencies

```bash
uv pip install pytesseract Pillow
```

System dependency: `tesseract-ocr` (pre-installed on most Linux systems via `/usr/bin/tesseract`)

## Quick Script

```python
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter

img = Image.open('/path/to/image.jpg')

# Enhance for better OCR on dark/low-contrast images
img = img.convert('L')
img = ImageEnhance.Contrast(img).enhance(2.0)
img = img.filter(ImageFilter.SHARPEN)

# OCR with Spanish + English
text = pytesseract.image_to_string(img, lang='spa+eng', config='--psm 6')
print(text)
```

## PSM modes reference

| Mode | Use case |
|------|----------|
| `--psm 3` | Default: automatic page segmentation |
| `--psm 4` | Assume a single column of text |
| `--psm 6` | Assume a single uniform block of text (best for screenshots) |
| `--psm 11` | Sparse text (find as much text as possible) |

## Pitfalls

- Always enhance contrast before OCR on phone/Teams screenshots — they're often dark
- Always use `lang='spa+eng'` for Spanish documents mixed with English terms
- The `terminal()` tool works better than `execute_code` for OCR since it has direct file system access
- Save the enhanced image to check quality: `img.save('/tmp/enhanced.jpg')`
