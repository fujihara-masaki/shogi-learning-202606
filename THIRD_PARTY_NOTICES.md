# Third-party notices

## Shogi Images

The appearance themes use assets derived from the official Shogi Images
distributions “一文字駒”, “二文字駒”, “一文字駒（ダーク）”, “盤 - 木材（明）”,
“盤 - 木材（暖）”, and “盤 - ダーク”. The official
distribution page is <https://sunfish-shogi.github.io/shogi-images/> and describes
the materials as dedicated to the public domain under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).

- License/provenance review date: 2026-08-12
- Public/runtime assets: 93 files / 1,377,301 bytes, consisting of 90 PNG piece
  images and three processed PNG board textures
- Immutable processing sources: the three `board-original.png` files under
  `frontend/assets-source/shogi/boards/shogi-images-{light,warm,dark}/` are the
  official, unmodified 458x500 Shogi Images board PNGs (258,910 / 196,141 /
  7,111 bytes). They are retained only to make runtime processing reproducible.
- Runtime board modification: each corresponding
  `frontend/public/assets/shogi/boards/shogi-images-*/board.png` is generated
  from its immutable source with the original 9x9 grid lines and four star
  points removed; the 458x500 px dimensions and source texture are retained
- Piece modification: none; all 90 piece PNG files are unprocessed. The
  downloaded `futamoji.zip` and `hitomoji_dark.zip` archives had SHA-256
  `c2bfa0c41e42af5e92e5478716c8334bb17b3d8a940ba6a4b4bc01281c026510` and
  `dba5610aaa5250a220aae131f4464656baa18d97ad8bc201441ac9586172041a`
  respectively; archive-only overview images and SVGs are not redistributed.
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
