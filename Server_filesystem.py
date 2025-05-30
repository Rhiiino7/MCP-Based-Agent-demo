import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Server")

@mcp.tool()
async def create_file(file_name: str, content: str) -> str:
    """
    创建文件
    arguments:
    	file_name (str): 文件名
    	content (str): 文件内容
    return: 
    	(str) 创建成功消息
    """
    try:
        with open(file_name, "w", encoding="utf-8") as file:
            file.write(content)
        return f"文件'{file_name}'创建成功"
    except Exception as e:
        return {"error": f"创建文件失败: {str(e)}"}

@mcp.tool()
async def read_file(file_name: str) -> str:
    """
    读取文件内容
    arguments: 
    	file_name (str): 文件名
    return: 
    	(str) 文件内容或错误消息
    """
    try:
        with open(file_name, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        return {"error": f"文件'{file_name}'未找到"}
    except Exception as e:
        return {"error": f"读取文件失败: {str(e)}"}

@mcp.tool()
async def write_file(file_name: str, content: str) -> str:
    """
    写入文件内容（覆盖原有内容）
    arguments:
    	file_name (str): 文件名
    	content (str): 文件内容
    return: 
    	(str) 写入成功消息
    """
    try:
        with open(file_name, "w", encoding="utf-8") as file:
            file.write(content)
        return f"文件'{file_name}'写入成功"
    except Exception as e:
        return {"error": f"写入文件失败: {str(e)}"}

@mcp.tool()
async def append_file(file_name: str, content: str) -> str:
    """
    向文件追加内容（不覆盖原有内容）
    arguments:
        file_name (str): 文件名
        content (str): 要追加的内容
    return:
        (str) 操作成功消息或错误消息
    """
    try:
        with open(file_name, "a", encoding="utf-8") as file:
            file.write(content)
        return f"内容已成功追加到文件'{file_name}'"
    except Exception as e:
        return {"error": f"写入文件失败: {str(e)}"}

@mcp.tool()
async def delete_file(file_name: str) -> str:
    """
    删除指定文件
    arguments:
        file_name (str): 要删除的文件名
    return:
        (str) 删除成功消息或错误消息
    """
    try:
        if not os.path.exists(file_name):
            return {"error": f"文件'{file_name}'不存在"}
        os.remove(file_name)
        return {"error": f"文件'{file_name}'删除成功"}
    except PermissionError:
        return {"error": f"无权限删除文件'{file_name}'"}
    except Exception as e:
        return {"error": f"删除文件失败: {str(e)}"}
    
if __name__ == "__main__":
    mcp.run(transport='stdio')