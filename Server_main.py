import os
import json
import smtplib
import ast
import operator
import math
from datetime import datetime
from email.message import EmailMessage
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()
mcp = FastMCP("Server")

@mcp.tool()
async def send_email(to: str, subject: str, body: str, attachmentfilename: str) -> str:
    """
    发送邮件，支持带附件。
    arguments:
        to (str): 收件人邮箱地址
        subject (str): 邮件标题(默认为：机器发送)
        body (str): 邮件正文(默认为：您好)
        attachmentfilename (str): 保存的 Markdown 文件名（不含路径），若无附件则为字符串："noattach"
    return:
        (str) 邮件发送状态说明
    """
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 465))
    sender_email = os.getenv("EMAIL_USER")
    sender_pass = os.getenv("EMAIL_PASS")

    if attachmentfilename != "noattach":
        # 如果存在附件，则进一步检查地址合法性
        if not os.path.exists(attachmentfilename):
            return {"error": f"没找到该文件: {attachmentfilename}"}
    masage = EmailMessage()
    masage["Subject"] = subject
    masage["From"] = sender_email
    masage["To"] = to
    masage.set_content(body)

    # 添加附件并发送邮件
    if attachmentfilename != "noattach":
        try:
            with open(attachmentfilename, "rb") as f:
                file_data = f.read()
                file_name = os.path.basename(attachmentfilename)
                masage.add_attachment(file_data, maintype="application", subtype="octet-stream", filename=file_name)
        except Exception as e:
            return {"error": f"附件读取失败: {str(e)}"}
    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender_email, sender_pass)
            server.send_message(masage)
        return f"邮件已成功发送给 {to}"
    except Exception as e:
        return {"error": f"邮件发送失败: {str(e)}"}

@mcp.tool()
async def calculate(expression: str) -> str:
    """
    计算数学表达式。
    arguments:
        expression (str): 数学表达式，允许是复杂的，不允许进行数值比较，要求符号只能包括："+"、"-"、"*"、"/"、"**"、"("、")"，不包括">"、"<"。需要你整理好表达式，只调用一次函数就可以完成整体计算
    return:
        (str): 数学表达式的结果
    """
    allowed_operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
    }
    allowed_names = {
        k: getattr(math, k)
        for k in dir(math)
        if not k.startswith("__")
    }
    allowed_names.update({
        "pi": math.pi,
        "e": math.e,
    })

    def eval_expr(node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            if node.id in allowed_names:
                return allowed_names[node.id]
            raise ValueError(f"Unknown identifier: {node.id}")
        elif isinstance(node, ast.BinOp):
            left = eval_expr(node.left)
            right = eval_expr(node.right)
            if type(node.op) in allowed_operators:
                return allowed_operators[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -eval_expr(node.operand)
        elif isinstance(node, ast.Call):
            func = eval_expr(node.func)
            args = [eval_expr(arg) for arg in node.args]
            return func(*args)
        raise ValueError(f"Unsupported operation: {ast.dump(node)}")
    try:
        expression = expression.replace('^', '**').replace('×', '*').replace('÷', '/')
        parsed_expr = ast.parse(expression, mode='eval')
        result = eval_expr(parsed_expr.body)
        return str(result)
    except Exception as e:
        return {"error": f"表达式计算失败: {str(e)}"}

@mcp.tool()
async def get_time() -> str:
    """
    获取当前时间，或者当网页搜索涉及“今天”，“现在”时则需要该函数获取具体日期和时间
    arguments:
        None
    return:
        (str): 当前时间
    """
    current_time = datetime.now()
    formatted_time = current_time.strftime('%Y年%m月%d日 %H:%M:%S')
    return str(formatted_time)

if __name__ == "__main__":
    mcp.run(transport='stdio')

