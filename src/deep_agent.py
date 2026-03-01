from __future__ import annotations

from dataclasses import dataclass
import os
from typing import List

from langchain_tavily import TavilySearch
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field


class ResearchPlan(BaseModel):
    objective: str = Field(description="Mục tiêu nghiên cứu")
    sub_questions: List[str] = Field(description="Danh sách câu hỏi con cần xử lý")
    success_criteria: List[str] = Field(description="Tiêu chí để xem là đã trả lời tốt")


@dataclass
class Artifact:
    sub_question: str
    findings: str


class DeepResearchAgent:
    def __init__(self, model_name: str = "gpt-4o-mini", temperature: float = 0.0) -> None:
        if not os.getenv("TAVILY_API_KEY"):
            raise RuntimeError("Thiếu TAVILY_API_KEY. Hãy tạo file .env từ .env.example")

        self.model = ChatOpenAI(model=model_name, temperature=temperature)
        self.tools = [TavilySearch(max_results=5)]
        self.react_agent = create_react_agent(self.model, self.tools)

    def _plan(self, question: str, max_subquestions: int) -> ResearchPlan:
        planner = self.model.with_structured_output(ResearchPlan)
        system = (
            "Bạn là senior researcher. Hãy lập kế hoạch nghiên cứu sâu, rõ ràng, không lan man. "
            "Chia nhỏ vấn đề thành các câu hỏi con độc lập, ưu tiên câu có thể kiểm chứng được."
        )
        user = (
            f"Yêu cầu nghiên cứu: {question}\n"
            f"Số lượng câu hỏi con tối đa: {max_subquestions}\n"
            "Trả về đúng schema yêu cầu."
        )
        plan = planner.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        plan.sub_questions = plan.sub_questions[:max_subquestions]
        return plan

    def _research_sub_question(self, sub_question: str) -> str:
        prompt = (
            "Bạn là chuyên gia nghiên cứu web. "
            "Dùng tool tìm kiếm để lấy thông tin mới nhất và tóm tắt có dẫn nguồn (URL khi có).\n\n"
            f"Câu hỏi con: {sub_question}\n\n"
            "Đầu ra mong muốn:\n"
            "1) Kết luận ngắn\n"
            "2) 3-5 bằng chứng chính\n"
            "3) Nguồn tham khảo"
        )

        result = self.react_agent.invoke(
            {"messages": [("user", prompt)]},
            config={"recursion_limit": 25},
        )

        messages = result.get("messages", [])
        if not messages:
            return "Không thu được kết quả."

        final_message = messages[-1]
        return getattr(final_message, "content", str(final_message))

    def _synthesize(self, question: str, plan: ResearchPlan, artifacts: List[Artifact]) -> str:
        compiled = "\n\n".join(
            [f"[Câu hỏi con] {a.sub_question}\n{a.findings}" for a in artifacts]
        )

        system = (
            "Bạn là principal analyst. Hãy tổng hợp câu trả lời chất lượng cao, cấu trúc rõ ràng, "
            "nêu hạn chế dữ liệu và phần cần kiểm chứng thêm nếu có."
        )
        user = (
            f"Câu hỏi gốc: {question}\n\n"
            f"Mục tiêu: {plan.objective}\n"
            f"Tiêu chí thành công: {', '.join(plan.success_criteria)}\n\n"
            f"Tư liệu nghiên cứu:\n{compiled}\n\n"
            "Hãy trả lời theo định dạng markdown với các mục:\n"
            "- Executive summary\n"
            "- Detailed findings\n"
            "- Risks/uncertainties\n"
            "- Sources"
        )

        return self.model.invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        ).content

    def run(self, question: str, max_subquestions: int = 5) -> dict:
        plan = self._plan(question, max_subquestions=max_subquestions)
        artifacts: List[Artifact] = []

        for sub_question in plan.sub_questions:
            findings = self._research_sub_question(sub_question)
            artifacts.append(Artifact(sub_question=sub_question, findings=findings))

        final_answer = self._synthesize(question, plan, artifacts)

        return {
            "plan": plan.model_dump(),
            "artifacts": [a.__dict__ for a in artifacts],
            "final_answer": final_answer,
        }
