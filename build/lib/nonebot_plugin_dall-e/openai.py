import asyncio
import openai
from pathlib import Path
from datetime import datetime
from collections import deque
from nonebot.log import logger
import tempfile
from io import BytesIO
from PIL import Image


class DALLEKeyManager:
    def __init__(self, usage_count_per_minute_key=3):
        # 从文件中读取key，并用双端队列管理
        keys = self.read_keys_from_file()
        self.keys = deque(keys)
        # 为每个key创建一个长度为3的队列，用于存储使用时间
        self.key_usage = {key: deque(maxlen=usage_count_per_minute_key) for key in keys}
        # 创建一个条件变量，用于等待key的释放
        self.condition = asyncio.Condition()

    @staticmethod
    def read_keys_from_file():
        # 生成文件路径
        key_file = Path("data") / "openai_key.txt"

        # 检查文件是否存在，如果不存在则创建文件
        if not key_file.exists():
            key_file.touch()

        with open(key_file, 'r', encoding="utf8") as f:
            keys = [line.strip() for line in f.readlines()]
        return keys

    async def get_key(self):
        # 循环直到获取一个可用的key
        while True:
            key = self.keys[0]
            timestamps = self.key_usage[key]

            # 如果key在最近一分钟内使用次数少于3次，就返回这个key
            if len(timestamps) < 3 or (datetime.now() - timestamps[0]).total_seconds() > 60:
                self.key_usage[key].append(datetime.now())
                self.keys.rotate(-1)
                return key

            # 否则，等待key的释放
            async with self.condition:
                await self.condition.wait()

    async def release_key(self, key):
        # 如果key在最近一分钟内没有被使用，就释放这个key
        if (datetime.now() - self.key_usage[key][-1]).total_seconds() > 60:
            async with self.condition:
                self.condition.notify_all()

    async def create_image(self, prompt=None, image=None, sizes=None):
        # 尝试所有的key，直到创建图像成功
        for _ in range(len(self.keys)):
            key = await self.get_key()
            logger.info(f"DALL-E使用key：{key}")
            logger.info(f"DALL-E使用提示：{prompt}, 大小：{sizes}")

            openai.api_key = key
            try:
                # 根据提示或者图像创建图像
                if prompt:
                    response = openai.Image.create(
                        prompt=prompt,
                        n=1,
                        size=sizes,
                    )
                else:
                    response = openai.Image.create_variation(
                        image=image,
                        n=1,
                        size=sizes,
                    )
                logger.success(f"DALL-E图像生成·成功：{response['data'][0]['url']}")
                return response["data"][0]["url"], True
            except Exception as e:
                logger.error(f"请求失败，尝试使用下一个key：{e}")
                await self.release_key(key)
                await asyncio.sleep(1)

        # 如果所有的key都已经尝试过，就返回错误消息
        return "所有的key都已经尝试过，请求失败。", False

    async def get_image(self, prompt, sizes):
        # 根据提示创建图像
        return await self.create_image(prompt=prompt, sizes=sizes)

    async def img_img(self, init_images: BytesIO, sizes):
        # 根据图像创建图像变体
        f = tempfile.mktemp(suffix='.png')
        raw_image = Image.open(init_images)
        raw_image.save(f, format='PNG')
        return await self.create_image(image=open(f, 'rb'), sizes=sizes)
