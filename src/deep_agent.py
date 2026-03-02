from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable, List

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

    def _estimate_complexity(self, question: str) -> str:
        text = question.strip().lower()
        word_count = len(text.split())

        complex_markers = [
            "so sánh",
            "chiến lược",
            "roadmap",
            "đánh giá",
            "phân tích",
            "rủi ro",
            "compliance",
            "tổng quan",
            "benchmark",
            "detailed",
            "compare",
            "strategy",
            "analysis",
            "trade-off",
        ]
        marker_hits = sum(1 for marker in complex_markers if marker in text)

        if word_count <= 9 and marker_hits == 0:
            return "simple"
        if word_count >= 22 or marker_hits >= 2:
            return "complex"
        return "medium"

    def _adaptive_limits(self, question: str, requested_max_subquestions: int) -> tuple[int, int, str]:
        complexity = self._estimate_complexity(question)

        if complexity == "simple":
            auto_subquestions = 1
            recursion_limit = 8
        elif complexity == "medium":
            auto_subquestions = 2
            recursion_limit = 14
        else:
            auto_subquestions = 4
            recursion_limit = 22

        selected_subquestions = max(1, min(requested_max_subquestions, auto_subquestions))
        return selected_subquestions, recursion_limit, complexity

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

    def _research_sub_question(self, sub_question: str, recursion_limit: int) -> str:
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
            config={"recursion_limit": recursion_limit},
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

    @staticmethod
    def _build_difficulty_header(
        complexity: str,
        selected_subquestions: int,
        recursion_limit: int,
    ) -> str:
        complexity_label = {
            "simple": "Dễ",
            "medium": "Trung bình",
            "complex": "Khó",
        }.get(complexity, complexity)

        return (
            "## Đánh giá câu hỏi\n"
            f"- Mức độ: **{complexity_label}**\n"
            f"- Số câu hỏi con dùng: **{selected_subquestions}**\n"
            f"- Độ sâu mỗi câu (recursion limit): **{recursion_limit}**\n"
            "- Chiến lược trả lời: **Tự động điều chỉnh theo độ khó**"
        )

    @staticmethod
    def _notify(progress_callback: Callable[[str], None] | None, message: str) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(message)
        except Exception:
            return

    def run(
        self,
        question: str,
        max_subquestions: int = 5,
        progress_callback: Callable[[str], None] | None = None,
        analysis_question: str | None = None,
    ) -> dict:
        effective_analysis_question = (analysis_question or question).strip()
        selected_subquestions, recursion_limit, complexity = self._adaptive_limits(
            effective_analysis_question,
            requested_max_subquestions=max_subquestions,
        )

        self._notify(
            progress_callback,
            (
                "🧭 Đã phân loại độ phức tạp câu hỏi: "
                f"{complexity} | subquestions={selected_subquestions} | recursion={recursion_limit}"
            ),
        )

        self._notify(progress_callback, "📝 Đang lập research plan...")
        plan = self._plan(question, max_subquestions=selected_subquestions)
        self._notify(
            progress_callback,
            f"✅ Plan xong, có {len(plan.sub_questions)} câu hỏi con. Bắt đầu research...",
        )
        artifacts: List[Artifact] = []

        for index, sub_question in enumerate(plan.sub_questions, start=1):
            self._notify(
                progress_callback,
                f"🔎 [{index}/{len(plan.sub_questions)}] Đang research: {sub_question}",
            )
            findings = self._research_sub_question(
                sub_question,
                recursion_limit=recursion_limit,
            )
            artifacts.append(Artifact(sub_question=sub_question, findings=findings))
            self._notify(
                progress_callback,
                f"✅ [{index}/{len(plan.sub_questions)}] Hoàn tất research.",
            )

        self._notify(progress_callback, "🧠 Đang tổng hợp kết quả cuối...")
        final_answer = self._synthesize(question, plan, artifacts)
        self._notify(progress_callback, "✅ Hoàn tất tổng hợp. Đang gửi kết quả...")
        difficulty_header = self._build_difficulty_header(
            complexity=complexity,
            selected_subquestions=selected_subquestions,
            recursion_limit=recursion_limit,
        )

        return {
            "plan": plan.model_dump(),
            "artifacts": [a.__dict__ for a in artifacts],
            "final_answer": f"{difficulty_header}\n\n{final_answer}",
            "depth_profile": {
                "complexity": complexity,
                "max_subquestions": selected_subquestions,
                "recursion_limit": recursion_limit,
            },
        }
