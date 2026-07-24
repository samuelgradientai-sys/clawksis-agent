# Audio Spectrograms (songsee)

> Absorbed from `songsee` skill.

## Setup

```bash
go install github.com/steipete/songsee/cmd/songsee@latest
```

Optional: `ffmpeg` for formats beyond WAV/MP3.

## Usage

```bash
# Basic spectrogram
songsee track.mp3

# Save to file
songsee track.mp3 -o spectrogram.png

# Multi-panel visualization grid
songsee track.mp3 --viz spectrogram,mel,chroma,hpss,selfsim,loudness,tempogram,mfcc,flux

# Time slice
songsee track.mp3 --start 12.5 --duration 8 -o slice.jpg
```

## Visualization Types

`spectrogram`, `mel`, `chroma`, `hpss` (harmonic/percussive separation), `selfsim` (self-similarity), `loudness`, `tempogram`, `mfcc`, `flux` (spectral flux).
