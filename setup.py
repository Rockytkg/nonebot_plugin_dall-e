from setuptools import setup, find_packages

setup(
    name="nonebot_plugin_dall-e",
    version="0.6",
    packages=find_packages(),
    install_requires=["nonebot2", "openai", "pillow", "aiohttp", "httpx", "nonebot-adapter-onebot"],

    author="Join-liu",
    author_email="2696916846@qq.com",
    description="""
    A nonebot2 plugin that uses a key pool and key polling technology to manage API calls effectively.
    It supports setting the maximum number of calls per minute for each key to break API rate limits. 
    In addition, it can filter out prompt words that users do not want to see.
    """.strip(),
    license="Apache License 2.0",
    keywords="nonebot2 plugin",
    url="https://github.com/Rockytkg/nonebot_plugin_dall-e",
)
