# Third-party notices

## Shogi Images

The appearance theme uses assets derived from the official Shogi Images
distributions “一文字駒（通常、非ゴシック）” and “盤 - 木材（明）”. The official
distribution page is <https://sunfish-shogi.github.io/shogi-images/> and describes
the materials as dedicated to the public domain under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).

- License/provenance review date: 2026-08-10
- Public/runtime assets: 31 files / 564,243 bytes, consisting of 30 PNG piece
  images and one processed PNG board texture
- Immutable processing source: `frontend/assets-source/shogi/boards/shogi-images-light/board-original.png`
  is the official, unmodified Shogi Images “盤 - 木材（明）” PNG (258,910 bytes).
  It is retained only to make the runtime board processing reproducible.
- Runtime board modification: `frontend/public/assets/shogi/boards/shogi-images-light/board.png`
  is generated from the immutable source with the original 9x9 grid lines and
  four star points removed; the 458x500 px dimensions and wood-grain texture are
  retained
- Piece modification: none; all 30 piece PNG files are unprocessed
- Attribution is not required by CC0; this notice is retained for provenance.

## `tokuhirom/tanuki-tsume-shogi`

This application can import tsume-shogi puzzle data from [`tokuhirom/tanuki-tsume-shogi`](https://github.com/tokuhirom/tanuki-tsume-shogi), specifically `puzzles/1.json`, `puzzles/3.json`, and `puzzles/5.json`.

- Copyright (c) 2026 tokuhirom
- Licensed under the MIT License

### MIT License

MIT License

Copyright (c) 2026 tokuhirom

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
