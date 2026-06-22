"""Re-extract and re-map images for all existing library items."""

import json
import os
import shutil

from pysbd import Segmenter

from extractors import (
    extract_url_with_images,
    extract_with_images,
    map_images_to_sentences,
)
from models import get_db, get_item, get_items, init_db, item_images_dir

segmenter = Segmenter(language="en", clean=False)


def reparse_all():
    init_db()
    summaries = get_items()
    print(f"Found {len(summaries)} items")

    for summary in summaries:
        item = get_item(summary["id"])
        item_id = item["id"]
        title = item["title"]
        source_type = item["source_type"]
        source_url = item.get("source_url")
        original_path = item.get("original_path")
        text_content = item.get("text_content", "")
        sentences = item["sentences"]

        print(f"\n[{item_id}] {title}")
        print(f"  type={source_type}, sentences={len(sentences)}")

        img_dir = item_images_dir(item_id)

        # Clean old images
        if os.path.isdir(img_dir):
            shutil.rmtree(img_dir)
        os.makedirs(img_dir, exist_ok=True)

        images = []

        if source_type == "article" and source_url:
            import urllib.request

            try:
                req = urllib.request.Request(
                    source_url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                result = extract_url_with_images(html, source_url, img_dir)
                if result and result.get("images"):
                    images = map_images_to_sentences(result["images"], text_content, sentences)
            except Exception as e:
                print(f"  Failed to re-fetch: {e}")

        elif source_type == "document" and original_path and os.path.isfile(original_path):
            result = extract_with_images(original_path, img_dir)
            if result and result.get("images"):
                images = map_images_to_sentences(result["images"], text_content, sentences)

        # Clean up empty image dir
        if not images and os.path.isdir(img_dir):
            try:
                shutil.rmtree(img_dir)
            except OSError:
                pass

        with get_db() as db:
            db.execute(
                "UPDATE items SET images = ?, updated_at = ? WHERE id = ?",
                (json.dumps(images), __import__("time").time(), item_id),
            )

        print(f"  -> {len(images)} images mapped")
        if images:
            positions = [img["after_sentence"] for img in images]
            print(f"  positions: {positions}")


if __name__ == "__main__":
    reparse_all()
