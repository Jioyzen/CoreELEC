#!/usr/bin/env python3
"""Regenerate the small offline glyph atlas; Pillow is only needed by authors."""
import argparse
import base64
import gzip
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TEXT = (
    '首次启动 · 正在部署离线组件请勿断电'
    '准备校验安装包解压文件插件服务程序保存配置完成桌面'
    '失败可重试查看系统日志已用时秒分钟个/0123456789%:()，。 '
)


def generate(source, destination):
    sizes = {}
    for size in (22, 28):
        font = ImageFont.truetype(str(source), size, index=2)
        glyphs = {}
        for char in sorted(set(TEXT)):
            left, top, right, bottom = font.getbbox(char)
            width, height = max(1, right-left), max(1, bottom-top)
            mask = Image.new('L', (width, height))
            ImageDraw.Draw(mask).text((-left, -top), char, font=font, fill=255)
            glyphs[char] = [round(font.getlength(char)), left, top, width, height,
                            base64.b64encode(mask.tobytes()).decode()]
        sizes[str(size)] = glyphs
    data = json.dumps({'format': 1, 'sizes': sizes}, ensure_ascii=False).encode()
    Path(destination).write_bytes(gzip.compress(data, mtime=0))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--font', required=True)
    parser.add_argument('--output', default=str(Path(__file__).with_name('font.json.gz')))
    args = parser.parse_args()
    generate(args.font, args.output)
