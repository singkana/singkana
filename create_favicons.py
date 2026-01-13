#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
SingKANA ファビコン生成スクリプト

使用方法:
    python create_favicons.py <元画像のパス>

例:
    python create_favicons.py logo_512x512.png
    python create_favicons.py "C:/Users/SingKANA_β/logo.png"
"""

import sys
import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("エラー: Pillowがインストールされていません。")
    print("インストール: pip install Pillow")
    sys.exit(1)


def create_favicons(source_path: str, output_dir: str = "assets/favicon"):
    """
    元画像からファビコンファイルを生成
    
    Args:
        source_path: 元画像のパス（512x512推奨）
        output_dir: 出力ディレクトリ
    """
    # 元画像のパスを確認
    source = Path(source_path)
    if not source.exists():
        print(f"エラー: 元画像が見つかりません: {source_path}")
        sys.exit(1)
    
    # 出力ディレクトリを作成
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    
    print(f"元画像: {source_path}")
    print(f"出力先: {output_dir}")
    print()
    
    # 元画像を読み込み
    try:
        img = Image.open(source)
        print(f"元画像サイズ: {img.size[0]}x{img.size[1]}")
    except Exception as e:
        print(f"エラー: 画像を読み込めません: {e}")
        sys.exit(1)
    
    # 各サイズを作成
    sizes = {
        "favicon-16.png": 16,
        "favicon-32.png": 32,
        "apple-touch.png": 180,
    }
    
    print("生成中...")
    for filename, size in sizes.items():
        resized = img.resize((size, size), Image.Resampling.LANCZOS)
        output_path = output / filename
        resized.save(output_path, "PNG")
        print(f"  ✓ {filename} ({size}x{size})")
    
    # favicon.ico を作成（16x16 + 32x32 マルチ）
    ico_sizes = [16, 32]
    ico_images = []
    for size in ico_sizes:
        resized = img.resize((size, size), Image.Resampling.LANCZOS)
        ico_images.append(resized)
    
    ico_path = output / "favicon.ico"
    # ICO形式で保存（複数サイズを含む）
    ico_images[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ico_sizes]
    )
    print(f"  ✓ favicon.ico (16x16 + 32x32)")
    
    print()
    print("完了！以下のファイルが生成されました:")
    for filename in ["favicon.ico", "favicon-16.png", "favicon-32.png", "apple-touch.png"]:
        filepath = output / filename
        if filepath.exists():
            size = filepath.stat().st_size
            print(f"  - {filepath} ({size:,} bytes)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print()
        print("元画像のパスを指定してください:")
        print("  python create_favicons.py <画像のパス>")
        sys.exit(1)
    
    source_path = sys.argv[1]
    create_favicons(source_path)
