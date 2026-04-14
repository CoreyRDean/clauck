# Downloads as a landing zone, not a junk drawer

**Who:** Developer or researcher who downloads many files throughout the day

**Intent:** "When PDFs, images, installers, or datasets land in my Downloads folder, I want them categorized and described automatically. Ideally suggest where they should go. Don't move anything — just tell me what's there and what to do with it."

**Context:** ~/Downloads accumulates 50+ files a week. Most are never looked at again. Finding a specific download from two days ago means scrolling through a mess of `Screenshot 2025-...`, `document (3).pdf`, and random `.dmg` files. The user wants awareness of what's landing without having to check constantly.

**Success:** Within a minute of a download burst settling, a categorized report appears. Each file has a one-line description and a suggested destination. The user reviews the report at their convenience, not in real-time. Over time, the job (with session persistence) learns the user's patterns — PDFs from arxiv go to ~/Documents/papers, screenshots go to ~/Pictures, etc.
