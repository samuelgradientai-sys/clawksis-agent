# WeTransfer Download via Browser

When a user shares a WeTransfer link (`we.tl/t-...`), follow these steps to download the file to the server.

## Steps

1. **Navigate** to the shortened link with `browser_navigate(url)`
   - It auto-redirects to `wetransfer.com/downloads/{transferId}/{securityHash}?...`

2. **Accept the cookie/terms dialog**
   - Click the "I agree" button (ref varies, usually labeled "I agree")
   - Wait for the page to load

3. **Find the download page**
   - Look for a heading "Your files are ready"
   - A "Download" button should be visible

4. **Click Download**
   - Click the "Download" button
   - The page will change to "Download completed"
   - The file is saved to the browser's download directory

5. **Locate the file**
   - Files land in `/root/Downloads/`
   - Find with: `find /root/Downloads -name "*.mp4" -mmin -10`
   - The filename is the original upload name (usually a long hash)

6. **Verify**
   - Check file type: `file /root/Downloads/filename.mp4`
   - Check video info: `ffprobe -v quiet -print_format json -show_format -show_streams /root/Downloads/filename.mp4`

## Pitfalls
- The browser downloads to /root/Downloads/, NOT to the terminal's working directory
- Multiple clicks create multiple copies: "file (1).mp4", "file (2).mp4"
- WeTransfer files expire after a few days — don't wait
- The download only works through the interactive browser session; curl/wget won't work due to JavaScript challenge and auth cookies
