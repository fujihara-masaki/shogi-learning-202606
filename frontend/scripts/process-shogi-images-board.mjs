import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const EXPECTED_SIZE = { width: 458, height: 500 };
const EXPECTED_SOURCE = {
  byteLength: 258_910,
  sha256: "641f3923c9091f365514693c0957ba9fc18f32d541229281addc15370f907294",
};
const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const sourceBoardPath = resolve(
  scriptDirectory,
  "../assets-source/shogi/boards/shogi-images-light/board-original.png",
);
const outputBoardPath = resolve(
  scriptDirectory,
  "../public/assets/shogi/boards/shogi-images-light/board.png",
);

// The source image has ten vertical and ten horizontal rule bands. Each range
// includes the dark rule and its antialiased edge pixels.
const verticalRuleBands = [
  [5, 7],
  [54, 57],
  [104, 106],
  [153, 156],
  [203, 205],
  [252, 255],
  [302, 304],
  [351, 354],
  [401, 403],
  [450, 453],
];
const horizontalRuleBands = [
  [5, 7],
  [59, 61],
  [113, 115],
  [167, 170],
  [221, 224],
  [275, 278],
  [330, 332],
  [384, 386],
  [438, 440],
  [492, 494],
];
const starCenters = [
  [154, 169],
  [303, 169],
  [154, 331],
  [303, 331],
];

const source = await readFile(sourceBoardPath);
const sourceSha256 = createHash("sha256").update(source).digest("hex");
if (source.byteLength !== EXPECTED_SOURCE.byteLength || sourceSha256 !== EXPECTED_SOURCE.sha256) {
  throw new Error(
    `Unexpected immutable source: ${source.byteLength} bytes / SHA-256 ${sourceSha256}`,
  );
}
const sourceUrl = `data:image/png;base64,${source.toString("base64")}`;
const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage();
  const result = await page.evaluate(
    async ({ sourceUrl, expectedSize, verticalRuleBands, horizontalRuleBands, starCenters }) => {
      const image = new Image();
      image.src = sourceUrl;
      await image.decode();

      if (image.naturalWidth !== expectedSize.width || image.naturalHeight !== expectedSize.height) {
        throw new Error(
          `Expected ${expectedSize.width}x${expectedSize.height}, got ${image.naturalWidth}x${image.naturalHeight}`,
        );
      }

      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext("2d", { alpha: true });
      if (!context) throw new Error("Canvas 2D context is unavailable");
      context.drawImage(image, 0, 0);

      const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
      const pixels = imageData.data;
      const offset = (x, y) => (y * canvas.width + x) * 4;

      const interpolate = (target, before, after, ratio) => {
        for (let channel = 0; channel < 4; channel += 1) {
          pixels[target + channel] = Math.round(
            pixels[before + channel] * (1 - ratio) + pixels[after + channel] * ratio,
          );
        }
      };

      const fillVertically = (left, right, top, bottom) => {
        const beforeY = top - 1;
        const afterY = bottom + 1;
        for (let x = left; x <= right; x += 1) {
          const before = offset(x, beforeY);
          const after = offset(x, afterY);
          for (let y = top; y <= bottom; y += 1) {
            interpolate(offset(x, y), before, after, (y - beforeY) / (afterY - beforeY));
          }
        }
      };

      const fillHorizontally = (left, right) => {
        const beforeX = left - 1;
        const afterX = right + 1;
        for (let y = 0; y < canvas.height; y += 1) {
          const before = offset(beforeX, y);
          const after = offset(afterX, y);
          for (let x = left; x <= right; x += 1) {
            interpolate(offset(x, y), before, after, (x - beforeX) / (afterX - beforeX));
          }
        }
      };

      // Wood grain runs predominantly vertically. Interpolating star patches
      // vertically continues that grain while removing only each small mark.
      for (const [centerX, centerY] of starCenters) {
        fillVertically(centerX - 5, centerX + 5, centerY - 5, centerY + 5);
      }
      for (const [left, right] of verticalRuleBands) fillHorizontally(left, right);
      for (const [top, bottom] of horizontalRuleBands) {
        fillVertically(0, canvas.width - 1, top, bottom);
      }

      context.putImageData(imageData, 0, 0);
      return {
        width: canvas.width,
        height: canvas.height,
        png: canvas.toDataURL("image/png").split(",", 2)[1],
      };
    },
    {
      sourceUrl,
      expectedSize: EXPECTED_SIZE,
      verticalRuleBands,
      horizontalRuleBands,
      starCenters,
    },
  );

  if (result.width !== EXPECTED_SIZE.width || result.height !== EXPECTED_SIZE.height) {
    throw new Error(`Processed image has unexpected dimensions: ${result.width}x${result.height}`);
  }

  await writeFile(outputBoardPath, Buffer.from(result.png, "base64"));
  console.log(
    `Processed ${sourceBoardPath} -> ${outputBoardPath} (${result.width}x${result.height})`,
  );
} finally {
  await browser.close();
}
