async def handle(ctx):
    if "插件测试" in ctx.text:
        await ctx.reply("插件系统已就位。")
        return True
    return False
