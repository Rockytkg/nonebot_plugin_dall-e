import asyncio
import httpx
from pathlib import Path
from datetime import datetime
from collections import deque
from nonebot.log import logger
import tempfile
import aiofiles
from io import BytesIO
from PIL import Image


class DALLEKeyManager:
    def __init__(self, usage_count_per_minute_key=3, proxy=None):
        # 从文件中读取key，并用双端队列管理
        keys = self.read_keys_from_file()
        # 设置代理
        self.url = self.set_proxy(proxy)
        self.keys = deque(keys)
        # 为每个key创建一个长度为3的队列，用于存储使用时间
        self.key_usage = {key: deque(maxlen=usage_count_per_minute_key) for key in keys}
        # 创建一个条件变量，用于等待key的释放
        self.condition = asyncio.Condition()

    @staticmethod
    def set_proxy(proxy):
        if proxy is None:
            return "https://api.openai.com"
        return proxy.rstrip('/') if proxy.endswith('/') else proxy

    @staticmethod
    def read_keys_from_file():
        try:
            # 生成文件路径
            key_file = Path("data") / "openai_key.txt"
            with open(key_file, 'r', encoding="utf8") as f:
                keys = [line.strip() for line in f.readlines()]

            # 在控制台上打印成功读取了多少个key
            logger.success(f"DALL-E初始化成功: 成功读取了 {len(keys)} 个keys。")

            return keys
        except (FileNotFoundError, IOError) as e:
            # 处理文件找不到或读取错误的异常
            logger.error(f"DALL-E初始化失败:获取OpenAI Key出错,{e}")
            return []

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

    async def create_image(self, url, json=None, files=None, data=None):
        timeout = httpx.Timeout(10.0, read=30.0)  # 10秒连接超时，30秒读取超时
        # 尝试所有的key，直到创建图像成功
        for _ in range(len(self.keys)):
            key = await self.get_key()
            logger.info(f"DALL-E使用key：{key}")

            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        url=url,
                        headers={'Authorization': f'Bearer {key}'},
                        json=json,
                        data=data,
                        files=files
                    )
                logger.success(f"DALL-E图像生成·成功,任务ID：{resp.json()['created']}")
                return f"base64://{resp.json()['data'][0]['b64_json']}", True
            except Exception as e:
                logger.error(f"请求失败，尝试使用下一个key：{e}")
                await self.release_key(key)
                await asyncio.sleep(1)

        # 如果所有的key都已经尝试过，就返回错误消息
        return "所有的key都已经尝试过，请求失败。", False

    async def get_image(self, prompt, sizes):
        logger.info(f"DALL-E使用提示：{prompt}, 大小：{sizes}")
        data = {
            'prompt': prompt,
            'n': 1,
            'size': sizes,
            "response_format": "b64_json"
        }
        url = self.url + "/v1/images/generations"
        # 根据提示创建图像
        return await self.create_image(url=url, json=data)

    async def img_img(self, init_images: BytesIO, sizes):
        # 根据图像创建图像变体
        f = tempfile.mktemp(suffix='.png')
        raw_image = Image.open(init_images)
        raw_image.save(f, format='PNG')
        async with aiofiles.open(f, 'rb') as f:
            image_data = await f.read()
        # 构造请求数据
        data = {'n': 2, 'size': sizes, "response_format": "b64_json"}
        files = {'image': image_data}
        url = self.url + "/v1/images/variations"
        return await self.create_image(url=url, data=data, files=files)
