from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from loguru import logger

from models import AffiliateLink, Message, Product


@dataclass
class Repo:
    db_path: Path

    def _conn(self) -> sqlite3.Connection:
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def init(self) -> None:
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id_meli TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    image_url TEXT,
                    price REAL,
                    original_price REAL,
                    discount_pct REAL,
                    rating REAL,
                    reviews INTEGER,
                    free_shipping INTEGER,
                    seller TEXT,
                    category TEXT,
                    in_stock INTEGER,
                    collected_at TEXT
                );
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS links (
                    product_id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    affiliate_url TEXT NOT NULL,
                    short_url TEXT,
                    FOREIGN KEY(product_id) REFERENCES products(id_meli)
                );
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    product_id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    image_path TEXT,
                    FOREIGN KEY(product_id) REFERENCES products(id_meli)
                );
                """
            )

    def upsert_product(self, p: Product) -> None:
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO products (
                    id_meli, title, url, image_url, price, original_price, discount_pct, rating, reviews,
                    free_shipping, seller, category, in_stock, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id_meli) DO UPDATE SET
                    title=excluded.title,
                    url=excluded.url,
                    image_url=excluded.image_url,
                    price=excluded.price,
                    original_price=excluded.original_price,
                    discount_pct=excluded.discount_pct,
                    rating=excluded.rating,
                    reviews=excluded.reviews,
                    free_shipping=excluded.free_shipping,
                    seller=excluded.seller,
                    category=excluded.category,
                    in_stock=excluded.in_stock,
                    collected_at=excluded.collected_at;
                """,
                (
                    p.id_meli,
                    p.title,
                    str(p.url),
                    str(p.image_url) if p.image_url else None,
                    p.price,
                    p.original_price,
                    p.discount_pct,
                    p.rating,
                    p.reviews,
                    1 if p.free_shipping else 0,
                    p.seller,
                    p.category,
                    1 if (p.in_stock or False) else 0,
                    p.collected_at.isoformat(),
                ),
            )

    def upsert_link(self, product_id: str, link: AffiliateLink) -> None:
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO links (product_id, source_url, affiliate_url, short_url)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    source_url=excluded.source_url,
                    affiliate_url=excluded.affiliate_url,
                    short_url=excluded.short_url;
                """,
                (product_id, str(link.source_url), str(link.final_url), str(link.short_url) if link.short_url else None),
            )

    def upsert_message(self, msg: Message) -> None:
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO messages (product_id, text, image_path)
                VALUES (?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    text=excluded.text,
                    image_path=excluded.image_path;
                """,
                (msg.product_id, msg.text, msg.image_path),
            )

    def iter_products(self) -> list[dict]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT id_meli, title, url, image_url, price, original_price, discount_pct, rating, reviews, free_shipping, category
                FROM products
                ORDER BY collected_at DESC
                """
            ).fetchall()
        cols = [
            "id_meli",
            "title",
            "url",
            "image_url",
            "price",
            "original_price",
            "discount_pct",
            "rating",
            "reviews",
            "free_shipping",
            "category",
        ]
        return [dict(zip(cols, r)) for r in rows]

    def export_csv_json_messages(
        self, out_dir: Path, *, filename_prefix: str = "ofertas"
    ) -> tuple[Path, Path, Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        csv_path = out_dir / f"{filename_prefix}_{date_str}.csv"
        json_path = out_dir / f"{filename_prefix}_{date_str}.json"
        txt_path = out_dir / f"messages_{date_str}.txt"
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT p.id_meli, p.title, p.url, p.image_url, p.price, p.original_price, p.discount_pct,
                       p.rating, p.reviews, p.free_shipping, p.category, l.affiliate_url, l.short_url, m.text
                FROM products p
                LEFT JOIN links l ON l.product_id = p.id_meli
                LEFT JOIN messages m ON m.product_id = p.id_meli
                ORDER BY p.collected_at DESC;
                """
            ).fetchall()

        # CSV
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id_meli",
                    "title",
                    "url",
                    "image_url",
                    "price",
                    "original_price",
                    "discount_pct",
                    "rating",
                    "reviews",
                    "free_shipping",
                    "category",
                    "link_compartilhado",
                    "short_url",
                    "message",
                ]
            )
            for r in rows:
                writer.writerow([
                    r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10],
                    r[11] or "",  # affiliate_url (link compartilhado)
                    r[12] or "",  # short_url
                    r[13] or "",  # message
                ])

        # JSON
        json_records = [
            {
                "id_meli": r[0],
                "title": r[1],
                "url": r[2],
                "image_url": r[3],
                "price": r[4],
                "original_price": r[5],
                "discount_pct": r[6],
                "rating": r[7],
                "reviews": r[8],
                "free_shipping": bool(r[9]),
                "category": r[10],
                "link_compartilhado": r[11],  # affiliate_url (link compartilhado extraído)
                "short_url": r[12],
                "message": r[13],
            }
            for r in rows
        ]
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(json_records, f, ensure_ascii=False, indent=2)

        # messages.txt
        with txt_path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write((r[13] or "") + "\n\n")  # message está no índice 13 (após category)

        logger.info(f"Exportado: {csv_path} | {json_path} | {txt_path}")
        return csv_path, json_path, txt_path

    def fetch_products_with_links(self, *, limit: int = 50) -> list[dict]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT p.id_meli, p.title, p.url, p.image_url, p.price, p.original_price, p.discount_pct,
                       p.rating, p.reviews, p.free_shipping, p.category, l.affiliate_url, l.short_url
                FROM products p
                LEFT JOIN links l ON l.product_id = p.id_meli
                ORDER BY p.collected_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        cols = [
            "id_meli",
            "title",
            "url",
            "image_url",
            "price",
            "original_price",
            "discount_pct",
            "rating",
            "reviews",
            "free_shipping",
            "category",
            "link_compartilhado",  # affiliate_url (link compartilhado extraído)
            "short_url",
        ]
        return [dict(zip(cols, r)) for r in rows]
