from nonebot import get_driver, on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, PrivateMessageEvent, MessageSegment, GroupMessageEvent
from nonebot.adapters.onebot.v11.helpers import ImageURLs
from nonebot.params import CommandArg
from nonebot.rule import to_me
from enum import Enum
from nonebot.plugin import PluginMetadata
import asyncio
from typing import Optional
from nonebot.permission import SUPERUSER
from .openai import DALLEKeyManager
from .tools import *

__version__ = "0.6.0"
__plugin_meta__ = PluginMetadata(
    name="DALL-E绘图",
    description='使用DALL·E绘图',
    type="application",
    usage='',
    homepage="https://github.com/Rockytkg/nonebot_plugin_dall-e",
    supported_adapters={"~onebot.v11"},
    extra={
        "version": __version__,
        "author": "Agnes4m <2696916846@qq.com>",
    },
)

superusers = get_driver().config.superusers
dallkey = get_driver().config.dallkey
try:
    openai_proxy = get_driver().config.openai_proxy
except:
    openai_proxy = None


class Size(Enum):
    SMALL = '256x256'
    MEDIUM = '512x512'
    LARGE = '1024x1024'


size_mapping = {
    "小": Size.SMALL,
    "中": Size.MEDIUM,
    "大": Size.LARGE
}

# 全局变量，用于存储DALL·E的开关状态、图片尺寸，以及正在绘图的用户
drawing_users = {}  # 用于存储正在绘图的用户
DALLESwitchState = True  # 开关状态,默认关闭
DALLESwitchState_lock = asyncio.Lock()  # 用于保护DALLESwitchState
DALLEImageSize = Size.SMALL  # 图片尺寸，默认为256x256
DALLEImageSize_lock = asyncio.Lock()  # 用于保护DALLEImageSize
gfw = DFAFilter()  # 初始化敏感词过滤器
dalle = DALLEKeyManager(dallkey, openai_proxy)  # 实例化DALL·E绘图管理器
drawing_users_lock = asyncio.Lock()  # 用于绘图用户的锁

dall_drawing = on_command("开关绘图", aliases={"开启绘图", "关闭绘图"}, permission=SUPERUSER, priority=2,
                          block=True)


@dall_drawing.handle()
async def _(event: MessageEvent):
    global DALLESwitchState  # 在函数内部声明全局变量
    if isinstance(event, PrivateMessageEvent) and str(event.user_id) not in superusers:
        await dall_drawing.finish("私聊无法使用此功能")
    if isinstance(event, GroupMessageEvent):
        async with DALLESwitchState_lock:
            if not DALLESwitchState:
                DALLESwitchState = True
                await dall_drawing.finish("已开启绘图功能")
            else:
                DALLESwitchState = False
                await dall_drawing.finish("已关闭绘图功能")


dell_size = on_command("绘图尺寸", rule=to_me(), aliases={"尺寸"}, permission=SUPERUSER, priority=2, block=True)


@dell_size.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    global DALLEImageSize  # 在函数内部声明全局变量
    if isinstance(event, PrivateMessageEvent) and str(event.user_id) not in superusers:
        await dall_drawing.finish("私聊无法使用此功能")
    directives = arg.extract_plain_text()
    if directives in size_mapping:
        async with DALLEImageSize_lock:
            DALLEImageSize = size_mapping[directives]
        logger.success(f"已设置绘图尺寸为{DALLEImageSize.value}")
        await dell_size.finish(f"已设置绘图尺寸为{DALLEImageSize.value}")
    else:
        await dell_size.finish("参数错误，可选参数：小、中、大")


async def do_drawing(event: MessageEvent, arg: Optional[Message] = None, urls: Optional[ImageURLs] = None):
    user_id = str(event.user_id)
    async with drawing_users_lock:
        if isinstance(event, PrivateMessageEvent) and user_id not in superusers:
            await dall_drawing.finish("私聊无法使用此功能")

        # 检查是否用户已经在绘图
        if user_id in drawing_users:
            await dall_drawing.finish("你已经有一个绘图任务在进行中，请等待完成后再发起新的请求", at_sender=True)

        if not DALLESwitchState:
            await dall_drawing.finish("绘图功能未开启")

        # 把用户添加到绘图用户列表
        drawing_users[user_id] = True

    try:
        if urls is None and (arg is None or not arg):
            await dall_drawing.finish("请输入要绘制的内容")

        if urls is not None and (urls is None or len(urls) != 1):
            await dall_drawing.finish("您没有给出图片，或者您给出了多张图片")

        await dall_drawing.send("正在绘图，请稍等...", at_sender=True)

        # 调用DALL·E绘图
        if urls is not None:
            result, success = await dalle.img_img(await get_img(urls[0]), DALLEImageSize.value)
        else:
            # 过滤敏感词
            prompt = gfw.filter(arg.extract_plain_text())
            result, success = await dalle.get_image(prompt, DALLEImageSize.value)
    finally:
        # 无论成功或失败，都从绘图用户列表中删除
        async with drawing_users_lock:
            del drawing_users[user_id]

    response_message = MessageSegment.image(result) if success else "绘图失败，请重试"
    if not success:
        logger.error(f"DALL·E绘图失败: {result}")

    await dall_drawing.finish(response_message, at_sender=True)


dall_drawing = on_command("画", rule=to_me(), aliases={"draw"}, priority=2, block=True)


@dall_drawing.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    await do_drawing(event, arg)


dall_img_drawing = on_command("垫图", rule=to_me(), aliases={"img_draw"}, priority=2, block=True)


@dall_img_drawing.handle()
async def _(event: MessageEvent, urls=ImageURLs()):
    await do_drawing(event, urls=urls)
