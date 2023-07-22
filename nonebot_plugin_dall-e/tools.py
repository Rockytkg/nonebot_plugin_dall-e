from pathlib import Path
from nonebot.log import logger
from io import BytesIO
import aiohttp
from PIL import Image
import base64
import tempfile
import os


class DFAFilter:
    def __init__(self):
        self.keyword_chains = {}
        self.delimit = '\x00'
        self.load_keywords()

    def load_keywords(self):
        file_path = Path("data") / "违禁词.txt"
        try:
            with open(file_path, 'r', encoding='utf8') as file:
                for line in file:
                    stripped_line = line.strip()
                    if stripped_line:
                        self.add(stripped_line)
        except Exception as e:
            logger.error(f"DALL-E读取敏感词失败: {e}")

    def add(self, keyword):
        keyword = keyword.lower()
        chars = keyword.strip()
        if not chars:
            return
        level = self.keyword_chains
        for i in range(len(chars)):
            if chars[i] not in level:
                level[chars[i]] = {}
            level = level[chars[i]]
        level[self.delimit] = 0

    def parse(self, path):
        with open(path, encoding='utf-8') as f:
            for keyword in f:
                self.add(str(keyword).strip())

    def filter(self, message, repl="*"):
        message = str(message).lower()
        ret = []
        start = 0
        detected_keywords = []
        while start < len(message):
            if message[start] in self.keyword_chains:
                level = self.keyword_chains[message[start]]
                step_ins = 0
                for char in message[start + 1:]:
                    if char in level:
                        step_ins += 1
                        level = level[char]
                    else:
                        break

                if self.delimit in level and len(level) == 1:
                    ret.append(repl * (step_ins + 1))
                    detected_keywords.append(message[start:start + step_ins + 1])
                    start += step_ins
                else:
                    ret.append(message[start])
            else:
                ret.append(message[start])
            start += 1
        logger.info(f"DELL检测到敏感词: {detected_keywords}")
        return ''.join(ret)


async def get_img(img_url: str):
    logger.info(f"正在下载图片：{img_url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(img_url) as resp:
                result = await resp.read()
    except Exception as e:
        logger.error(f"图片下载失败，URL: {img_url}，错误：{e}")
        return None

    if not result:
        logger.error(f"图片下载结果为空，URL: {img_url}")
        return None

    logger.info(f"图片下载完成：{img_url}")
    return BytesIO(result)
