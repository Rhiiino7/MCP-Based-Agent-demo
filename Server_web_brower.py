import os
from typing import Dict, List
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from openai import OpenAI

load_dotenv()
mcp = FastMCP("Server")

GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"


async def google_search(query: str, num_results: int = 5) -> List[Dict[str, str]]:
    """
    用于在谷歌上搜索query相关的内容，并且返回一个结构化的结果
    该结果包含 num_results 个 url 中包含的信息 (title, link, snippet)
    """
    ## url 需要的其他参数，限制查询的范围为中文网页
    lang = "zh"
    country = "cn"
    if GOOGLE_SEARCH_API_KEY and GOOGLE_CSE_ID:
        async with httpx.AsyncClient() as client:
            url = f"https://www.googleapis.com/customsearch/v1?q={quote_plus(query)}&key={GOOGLE_SEARCH_API_KEY}&cx={GOOGLE_CSE_ID}&num={num_results}&lr=lang_{lang}&gl={country}"
            response = await client.get(url)
            if response.status_code == 200:
                results = response.json()
                structured_results = []
                for item in results.get("items", []):
                    structured_results.append({
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", "")
                    })
                return structured_results
            else:
                return [{"error": f"Google API error: {response.status_code} - {response.text}"}]
    else:
        print("Google search API or engine 存在问题")
        return [{"error": "Google API error"}]


async def extract_webpage_content(subquery: str, url: str, max_length: int = 2000) -> str:
    """
    从搜索中得到的结构化数据中进行提取和总结
    返回依据这些搜索结果和subquery总结的内容
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=10.0)
            
            if response.status_code != 200:
                return {"error": f"Failed to fetch URL: HTTP {response.status_code}"}
            soup = BeautifulSoup(response.text, 'html.parser')
            ## 把没用的内容除去，然后提取主要内容
            for element in soup(["script", "style", "nav", "footer", "iframe"]):
                element.decompose()
            main_content = soup.find("main") or soup.find("article") or soup
            text = " ".join(main_content.get_text().split())
            text = text[:max_length] if max_length > 0 else text
            try:
                deepseek_api_key = os.getenv("DASHSCOPE_API_KEY")
                base_url = os.getenv("BASE_URL")
                model = os.getenv("MODEL")
                client = OpenAI(api_key=deepseek_api_key, base_url=base_url)
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "你是一个总结能力很强的阅读助手，擅长根据需求，整理、总结材料"},
                        {"role": "user", "content": f"你要解决“{subquery}”这个问题，现在需要你以解决问题为目标，将以下web的内容整理、总结，不多于200字：{text}"}
                    ]
                )
                result = response.choices[0].message.content.strip()
            except Exception as e:
                result = str(e)
            return result
    except Exception as e:
        return {"error": f"网页处理出现错误: {str(e)}"}

@mcp.tool()
async def web_search(subquery: str, keyword: str, num_results: int) -> str:
    """
    使用谷歌搜索查询内容并自动整理，允许对查询到的内容进行摘要总结，如果不需要查询网页就能解决问题则不调用此工具
    arguments:
        subquery (str): 需要解决、查询、搜索、了解的问题（从用户的query中提取）
        keyword (str): 为解决subquery这个问题，需要在网页上查询的关键字（需要你自己总结提取）
        num_results (int): 搜索网页的个数（默认为3个，如果资料的需求量大，可以适当增加，不超过六个）
    return:
        (str): 查询的内容
    """
    # num_results = 3
    search_results = await google_search(keyword, num_results)
    
    if "error" in search_results[0]:
        return {"error": f"网页处理出现错误"}
    
    summaries = []
    for result in search_results:
        if "link" in result:
            content = await extract_webpage_content(subquery, result["link"])
            summaries.append(content)

    ## 将每个url的摘要进一步总结
    try:
        deepseek_api_key = os.getenv("DASHSCOPE_API_KEY")
        base_url = os.getenv("BASE_URL")
        model = os.getenv("MODEL")
        client = OpenAI(api_key=deepseek_api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个总结能力很强的阅读助手，擅长根据需求，整理、总结材料"},
                {"role": "user", "content": f"你要解决“{subquery}”这个问题，现在需要你以解决问题为目标，将以下材料整理总结，不能输出json等结构化文本，字数上限500字：{summaries}"}
            ],
        )
        summary = response.choices[0].message.content.strip()
        return summary
    except Exception as e:
        return {"error": f"总结处理出现错误: {str(e)}"}

if __name__ == "__main__":
    mcp.run(transport='stdio')