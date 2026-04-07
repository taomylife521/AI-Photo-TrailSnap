import logging
from typing import Dict, Any, List
from uuid import UUID
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langgraph.prebuilt import create_react_agent
from sqlalchemy.orm import Session

from app.core.config_manager import config_manager
from app.db.session import SessionLocal
from app.service.agent.tools import get_agent_tools
from app.crud.agent import get_messages_by_session, create_message
from app.schemas.agent import AgentMessageCreate

logger = logging.getLogger(__name__)

def get_session_history(db: Session, session_id: str) -> List[BaseMessage]:
    db_messages = get_messages_by_session(db, session_id, limit=100)
    messages = []
    for msg in db_messages:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))
        elif msg.role == "system":
            messages.append(SystemMessage(content=msg.content))
    return messages


def get_agent_executor(user_id: str, session_id: str, db: Session, connection_id: str = None, model_name: str = None):
    """
    完全适配 langgraph==1.1.3 的 Agent 初始化
    """
    user_config = config_manager.get_user_config(user_id, db)

    ai_settings = user_config.ai

    c_id = connection_id or ai_settings.analysis_connection_id
    m_name = model_name or ai_settings.analysis_model_name

    if not c_id or not m_name:
        raise ValueError("未配置智能分析模型，请在「系统设置 -> 智能分析」中配置连接和模型。")

    # Find connection
    connection = next((c for c in ai_settings.connections if c.id == c_id), None)
    if not connection:
        raise ValueError(f"未找到指定的 AI 连接配置: {c_id}")
        
    if not connection.enable:
        raise ValueError(f"选中的 AI 连接已禁用: {c_id}")

    if not connection.api_key:
        raise ValueError(f"选中的 AI 连接未配置 API Key: {c_id}")

    # 初始化 LLM
    llm = ChatOpenAI(
        model=m_name,
        api_key=connection.api_key,
        base_url=connection.api_base if connection.api_base else None,
        temperature=0.7,
        streaming=True
    )

    # 加载工具列表
    tools = get_agent_tools(user_id)

    # 获取当前时间
    import datetime
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")

    # 系统提示：通过 PromptTemplate 注入
    system_prompt = f"""你是一个名为 TrailSnap 的智能相册与旅行足迹助手。
今天是 {current_date}。
你的目标是帮助用户回忆他们的旅行、检索相册中的照片，并为他们提供有趣的内容（例如发朋友圈的文案）。在检索照片之前，你必须先根据用户的描述来初步缩小搜索范围，例如日期范围、地点、类型、标签、人物等，如果用户没有提供足够的信息，你可以要求用户进一步给出详细的描述。
你可以使用提供的工具来搜索照片和查看照片的详细数据，例如地址、景区、标签、人脸等。

【重要指令】：如果你需要展示照片给用户，请必须使用 Markdown 图片语法，并且 URL 格式必须为：
`![照片描述](/api/medias/照片ID/thumbnail)`
例如：
`![美丽的风景](/api/medias/123e4567-e89b-12d3-a456-426614174000/thumbnail)`

当你为用户准备了九宫格照片时，请在回答中直接用上述 Markdown 格式输出这 9 张照片。
当用户问“发生了什么事情”或“玩了哪些景点”时，你可以结合照片的描述(description)和一句话旁白(narrative)来丰富你的回答。
请使用友好、自然、有温度的中文与用户交流。
"""

    # 并通过手动构建 prompt 状态传入
    agent = create_react_agent(llm, tools)

    return agent, system_prompt


def chat_with_agent(user_id: str, session_id: str, user_input: str, db: Session, connection_id: str = None, model_name: str = None) -> str:
    """
    与 Agent 对话，维护上下文历史
    """
    agent, system_prompt = get_agent_executor(user_id, session_id, db, connection_id, model_name)
    messages = get_session_history(db, session_id)
    
    # 将 system_prompt 作为第一条消息传入，如果它不在历史中
    if not messages or not isinstance(messages[0], SystemMessage):
        messages.insert(0, SystemMessage(content=system_prompt))
        
    messages.append(HumanMessage(content=user_input))
    
    # Save user message to DB
    create_message(db, AgentMessageCreate(
        session_id=UUID(session_id),
        role="user",
        content=user_input,
    ))
    
    try:
        response = agent.invoke({"messages": messages})
        
        # 获取大模型的回复
        ai_message = response["messages"][-1].content

        # Save AI message to DB
        create_message(db, AgentMessageCreate(
            session_id=UUID(session_id),
            role="assistant",
            content=ai_message,
        ))

        return ai_message
    except Exception as e:
        logger.error(f"Agent 对话失败：{str(e)}", exc_info=True)
        return f"抱歉，处理你的请求时出错了：{str(e)}，请稍后重试。"

import json
from concurrent.futures import ThreadPoolExecutor
from app.db.session import SessionLocal

def generate_session_title_task(user_id: str, session_id: str, user_input: str):
    try:
        from app.core.config_manager import config_manager
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
        from app.crud.agent import get_session, update_session
        from app.schemas.agent import AgentSessionUpdate
        from uuid import UUID

        with SessionLocal() as db:
            if isinstance(user_id, str):
                user_id = UUID(user_id)
            user_config = config_manager.get_user_config(user_id, db)
            
            ai_settings = user_config.ai
            c_id = ai_settings.analysis_connection_id
            m_name = ai_settings.analysis_model_name
            
            if not c_id or not m_name:
                return None
                
            connection = next((c for c in ai_settings.connections if c.id == c_id), None)
            if not connection or not connection.enable or not connection.api_key:
                return None
                
            llm = ChatOpenAI(
                model=m_name,
                api_key=connection.api_key,
                base_url=connection.api_base if connection.api_base else None,
                temperature=0.7
            )
            
            prompt = f"请根据用户的第一个问题，生成一个非常简短的会话标题（不超过10个字）。只返回标题文本，不要包含任何标点符号或其他多余解释。\n用户问题：{user_input}"
            response = llm.invoke([HumanMessage(content=prompt)])
            title = response.content.strip()
            
            if title.startswith('"') and title.endswith('"'):
                title = title[1:-1]
            if title.startswith("'") and title.endswith("'"):
                title = title[1:-1]
                
            session = get_session(db, session_id)
            if session:
                update_session(db, session, AgentSessionUpdate(title=title))
                
            return title
    except Exception as e:
        logger.error(f"Failed to generate title: {e}")
        return None

def stream_chat_with_agent(user_id: str, session_id: str, user_input: str, db: Session, connection_id: str = None, model_name: str = None):
    """
    与 Agent 对话，并使用 SSE 流式返回大模型的回复
    """
    try:
        agent, system_prompt = get_agent_executor(user_id, session_id, db, connection_id, model_name)
        messages = get_session_history(db, session_id)

        if not messages or not isinstance(messages[0], SystemMessage):
            messages.insert(0, SystemMessage(content=system_prompt))

        messages.append(HumanMessage(content=user_input))

        # Save user message to DB
        create_message(db, AgentMessageCreate(
            session_id=UUID(session_id),
            role="user",
            content=user_input,
        ))

        full_response = ""
        import json
        
        # Check if it's the first message (1 system prompt + 1 user message = 2)
        is_first_message = len(messages) <= 2
        future_title = None
        executor = None
        if is_first_message:
            executor = ThreadPoolExecutor(max_workers=1)
            future_title = executor.submit(generate_session_title_task, user_id, session_id, user_input)
        
        # 使用 langgraph stream 模式
        for chunk, metadata in agent.stream({"messages": messages}, stream_mode="messages"):
            if chunk.type and metadata.get("langgraph_node") == "agent":
                content = chunk.content
                if isinstance(content, str) and content:
                    full_response += content
                    # yield SSE data
                    data = json.dumps({"content": content, "session_id": session_id})
                    yield f"data: {data}\n\n"

        if future_title:
            try:
                new_title = future_title.result(timeout=10) # wait at most 10 seconds
                if new_title:
                    data = json.dumps({"title": new_title, "session_id": session_id})
                    yield f"data: {data}\n\n"
            except Exception as e:
                logger.error(f"Wait for title generation timeout or error: {e}")
            finally:
                if executor:
                    executor.shutdown(wait=False)

        # Save AI message to DB
        if full_response:
            create_message(db, AgentMessageCreate(
                session_id=UUID(session_id),
                role="assistant",
                content=full_response,
            ))

        # 结束标志
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Agent 流式对话失败：{str(e)}", exc_info=True)
        import json
        error_msg = f"\n\n抱歉，处理你的请求时出错了：{str(e)}，请稍后重试。"
        data = json.dumps({"content": error_msg, "session_id": session_id})
        yield f"data: {data}\n\n"
        
        full_response += error_msg
        # Save partial AI message with error to DB
        create_message(db, AgentMessageCreate(
            session_id=UUID(session_id),
            role="assistant",
            content=full_response,
        ))
        
        yield "data: [DONE]\n\n"
