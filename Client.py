import asyncio
import os
import json
from typing import List
from contextlib import AsyncExitStack
from datetime import datetime
import re
from openai import OpenAI
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
load_dotenv()

class MCPClient:

    def __init__(self):
        """
        从环境变量中获取底层大模型的配置，使用 deepseek-chat 大模型
        需要创建多个服务端对话，所以使用字典来存
        """
        self.exit_stack = AsyncExitStack()
        self.deepseek_api_key = os.getenv("DASHSCOPE_API_KEY")
        self.base_url = os.getenv("BASE_URL")
        self.model = os.getenv("MODEL")
        self.client = OpenAI(api_key=self.deepseek_api_key, base_url=self.base_url)
        ## 连接多个服务端会话
        # server_id -> session, stdio, write
        self.sessions = {}
        ## 存储工具的映射关系 
        # name -> server_file_name
        self.tools_map = {}

    async def connect_to_server(self,server_id:str, server_path: str):
        """
        本项目都使用python，所以command设置为python即可，参数即为Server文件本身
        根据服务器参数，启动服务器进程并建立通信通道创建客户端会话，最后初始化会话
        """
        server_params = StdioServerParameters(
            command="python", 
            args=[server_path], 
            env=None,
        )
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        stdio, write = stdio_transport
        # MCP 客户端会话对象创建
        session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))
        await session.initialize()
        self.sessions[server_id] = {"session": session, "stdio":stdio, "write":write}
        # 更新工具的映射
        response = await session.list_tools()
        for tool in response.tools:
            print(f"工具名称：{tool.name}\t\t对应Server：{server_id}")
            self.tools_map[tool.name] = server_id


    async def query_match_tools(self, query: str) -> str:
        """
        根据 query 进行子任务拆分，并且为子任务分配工具
        按照生成的 tools 工作流执行 call_tool，并且保存到 massage 中
        以上步骤相当于为 query 提供了丰富的上下文，最后整体放入大模型中生成最终答案
        """
        messages = [{"role": "user", "content": query}]
        available_tools = []
        for tool_name, server_id in self.tools_map.items():
            session = self.sessions[server_id]["session"]
            response = await session.list_tools()
            for tool in response.tools:
                if tool.name == tool_name:
                    available_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "input_schema": tool.inputSchema
                        }
                    })
        ### 拆分子任务，并且为子任务分配工具
        tool_plan = await self.plan_tool_usage(query, available_tools)
        print(tool_plan)

        outputs_histoy = {}
        # 依次执行工具调用，并收集结果
        calltimes = 0
        for step in tool_plan:
            tool_name = step["name"]
            tool_args = step["arguments"]
            calltimes += 1 
            tool_info = {"name":tool_name, "arguments":tool_args}
            ## 用于判定调用的历史tool是否存在error，若存在，则当前tool直接加入到tool 流的尾部
            error_flag = False
            for key, val in tool_args.items():
                ## 针对串联工具的情况，需要记录之前使用过的工具得到的结果
                # 用 {{name}} 标识出，替换为之前使用过的工具得到的结果
                if isinstance(val, str) and "{{" in val and "}}" in val:
                    # 提取所有 {{ }} 的格式的引用并逐个替换
                    matches = re.findall(r"\{\{(.*?)\}\}", val)
                    for match in matches:
                        ref_key = match.strip()
                        resolved_val = outputs_histoy.get(ref_key, f"{{{{{ref_key}}}}}")
                        val = val.replace(f"{{{{{ref_key}}}}}", str(resolved_val))
                    # 再匹配一次，看是否还有 {{}}
                    matches = re.findall(r"\{\{(.*?)\}\}", val)
                    if matches:
                        error_flag = True
                        break
                    tool_args[key] = val
            ### 涉及文件路径的地方，在此处理，需要统一
            ## 由于只是 demo，所以全部暂存进相对目录 ./Test box/ 中
            ## 文件地址
            abs_file_path = "E:/Sysu MCP-Based Agent/mywork/Test box/"
            if self.tools_map.get(tool_name) == "Server_filesystem":
                if "file_name" not in tool_args:
                    tool_args["file_name"] = "temp.txt"
                # 当然，如果给定了绝对地址，也可以按照绝对地址进行文件操作，为了操作方便，就设定全在E盘
                if "E:/" not in tool_args["file_name"]:
                    tool_args["file_name"] = abs_file_path + tool_args["file_name"]
            ## email的附件地址：
            if tool_name == "send_email" and tool_args["attachmentfilename"] != "noattach":
                if "E:/" not in tool_args["attachmentfilename"]:
                    tool_args["attachmentfilename"] = abs_file_path + tool_args["attachmentfilename"]

            ## 用于判定调用的历史tool是否存在error，若存在，则当前tool直接加入到tool 流的尾部，维护各数据结构
            if error_flag:
                print(f"\nTool Call #{calltimes}: {tool_name} with {tool_args}")
                print("error")
                tool_plan.append(tool_info)
                continue
            
            ## 通过 tool_name 找到对应的 session
            server_id = self.tools_map.get(tool_name)
            session = self.sessions[server_id]["session"]
            print(f"\nTool Call #{calltimes}: {tool_name} with {tool_args}")
            result = await session.call_tool(tool_name, tool_args)

            ### 让大模型来判断query与result的关联程度
            judge_flag = "True"
            if tool_name != "calculate":
                judgement = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": ("你是一个判断能力很强的问题助手，擅长分析两段文本之间的关系。"
                                                    "现在需要你判定answer是否能够作为解决用户的query的上下文，或者answer是否与用户的query相关，或者answer是否对query的解决有帮助。"
                                                    "能作为上下文的answer可能是获取到的时间比如“2025年05月29日 10:00:26”，可能是与query相关的一段文本，比如可供query参考的资料，也可能是解决query过程中的阶段状态，比如文件创建、写入成功、邮件发送成功等状态，这些都能算是上下文"
                                                    "能作为上下文则回复“True”，否则回复“False”"
                                                    "不回复多余文字，直接输出True或者False即可")},
                        {"role": "user", "content": f"这是用户的query：“{query}”\n这是answer：{result.content[0].text}"}
                    ],
                )
                judge_flag = judgement.choices[0].message.content.strip()

            if "error" not in result.content[0].text and "Error" not in result.content[0].text and "False" not in judge_flag:
                messages.append({
                    "role": "assistant",
                    "content": "null",
                    "tool_calls": [{ 
                        "id": tool_name,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": f"{tool_args}"
                        }
                    }]
                })
                outputs_histoy[tool_name] = result.content[0].text
            
                if tool_name == "calculate":
                    calculate_prompt = "不使用latex或者markdown格式输出:"
                    output_text = calculate_prompt + result.content[0].text
                else:
                    output_text = result.content[0].text
            
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_name,
                    "content": output_text
                })
                #print(output_text)
            else:
                ## 出现error，则加入到tool流的末尾，重新执行
                # 由于是队列操作，所以如果存在链式调用，则全部重新依次加入到tool流的末尾，确保输出的完整性
                tool_plan.append(tool_info)
                #print(result.content[0].text)
                print("error")

        ## 最后再将以上内容作为上下文，调用 LLM 生成回复信息，并输出保存结果
        final_response = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        final_output = final_response.choices[0].message.content
        return final_output


    async def plan_tool_usage(self, query: str, tools: List[dict]) -> List[dict]:
        """
        使用prompt，让底层大模型根据query，从Server提供的tools中构造出一条json数组格式的tools chain，从而能够链式执行
        """
        tool_list_text = "\n".join([
            f"- {tool['function']['name']}: {tool['function']['description']}"
            for tool in tools
        ])
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system",
                "content": (
                    "你是一个有若干工具的智能任务规划助手，用户会给出自然语言请求\n"
                    "现在需要你根据你拥有的的工具，将用户的请求合理地拆分为若干子任务，从而可以将子任务使用对应的工具进行解决\n"
                    "可供你选择的工具如下（严格使用工具名称）：\n"
                    f"{tool_list_text}\n"
                    "你返回的内容应当是针对各个子问题所选择的工具，如果多个工具需要串联，后续步骤中可以使用 {{上一步工具名}} 占位。\n"
                    "返回格式：JSON 数组，每个对象包含 name 和 arguments 字段。\n"
                    "不要返回自然语言，不要使用未列出的工具名。")
                },
                {"role": "user", "content": query}
            ],
            stream=False
        )
        ## 提取出模型返回的 JSON 内容
        ## 并且匹配带```json或```的代码块
        content = response.choices[0].message.content.strip()
        pattern = r"```(?:json)?\n([\s\S]+?)\n```"  
        match = re.search(pattern, content)
        json_text = match.group(1) if match else content
        try:
            plan = json.loads(json_text)
            return plan if isinstance(plan, list) else []
        except Exception as e:
            print(f"工具调用链规划失败: {e}\n原始返回: {content}")
            return []

    async def cleanup(self):
        await self.exit_stack.aclose()

    async def chat_loop(self):
        """
        循环，维持会话，输入 quit 退出循环
        """
        while True:
            try:
                query = input("\n用户: ").strip()
                if query == 'quit':
                    break
                response = await self.query_match_tools(query)
                print(f"回答:\n{response}\n")
            except Exception as e:
                print(f"发生错误: {str(e)}")

async def main():
    client = MCPClient()
    print("MCP 客户端已启动！输入'quit'退出\n可使用的工具包括：")
    try:
        await client.connect_to_server("Server_main","E:\\Sysu MCP-Based Agent\\mywork\\Server_main.py")
        await client.connect_to_server("Server_filesystem","E:\\Sysu MCP-Based Agent\\mywork\\Server_filesystem.py")
        await client.connect_to_server("Server_web_brower","E:\\Sysu MCP-Based Agent\\mywork\\Server_web_brower.py")
        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())