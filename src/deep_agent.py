from __future__ import annotations

from dataclasses import dataclass
import os
import random
from typing import Callable, List, Literal
from urllib.parse import unquote, urlparse
import requests
from bs4 import BeautifulSoup

from langchain_tavily import TavilySearch
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    PlaywrightTimeout = Exception


class ResearchPlan(BaseModel):
    objective: str = Field(description="Mục tiêu nghiên cứu")
    sub_questions: List[str] = Field(description="Danh sách câu hỏi con cần xử lý")
    success_criteria: List[str] = Field(description="Tiêu chí để xem là đã trả lời tốt")


@dataclass
class Artifact:
    sub_question: str
    findings: str


class QualityAssessment(BaseModel):
    score: int = Field(description="Điểm chất lượng từ 0 đến 100")
    verdict: Literal["pass", "fail"] = Field(description="Kết luận qua hay chưa qua quality gate")
    feedback: List[str] = Field(description="Danh sách góp ý để cải thiện câu trả lời")


class DeepResearchAgent:
    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        if not os.getenv("TAVILY_API_KEY"):
            raise RuntimeError("Thiếu TAVILY_API_KEY. Hãy tạo file .env từ .env.example")

        llm_kwargs: dict = {
            "model": model_name,
            "temperature": temperature,
        }
        if base_url and isinstance(base_url, str):
            llm_kwargs["base_url"] = base_url.strip()
        if api_key and isinstance(api_key, str):
            llm_kwargs["api_key"] = api_key.strip()

        self.model = ChatOpenAI(**llm_kwargs)
        self.tools = [TavilySearch(max_results=5), self._create_web_fetch_tool()]
        self.react_agent = create_react_agent(self.model, self.tools)

    @staticmethod
    def _create_web_fetch_tool():
        """Tạo tool để fetch và parse nội dung từ URL với Playwright fallback."""
        @tool
        def fetch_url(url: str) -> str:
            """Fetch và trích xuất text content từ một URL (hỗ trợ JavaScript rendering).
            
            Args:
                url: URL cần lấy nội dung (http/https)
            
            Returns:
                Clean text content từ webpage, hoặc thông báo lỗi nếu thất bại
            """
            timeout = int(os.getenv("WEB_FETCH_TIMEOUT", "15"))
            user_agent = os.getenv(
                "WEB_FETCH_USER_AGENT",
                "Mozilla/5.0 (compatible; WSDeepAgent/1.0)"
            )
            use_playwright = os.getenv("WEB_FETCH_USE_PLAYWRIGHT", "auto").lower()

            proxy_single = (os.getenv("WEB_FETCH_PROXY", "") or "").strip()
            proxy_list_raw = (os.getenv("WEB_FETCH_PROXY_LIST", "") or "").strip()
            proxy_rotate = (os.getenv("WEB_FETCH_PROXY_ROTATE", "true") or "true").strip().lower() == "true"

            proxy_pool = [item.strip() for item in proxy_list_raw.split(",") if item.strip()]

            if proxy_pool:
                selected_proxy = random.choice(proxy_pool) if proxy_rotate else proxy_pool[0]
            elif proxy_single:
                selected_proxy = proxy_single
            elif url.lower().startswith("https://"):
                selected_proxy = (os.getenv("HTTPS_PROXY", "") or os.getenv("https_proxy", "")).strip()
            else:
                selected_proxy = (os.getenv("HTTP_PROXY", "") or os.getenv("http_proxy", "")).strip()

            selected_proxy = selected_proxy or None

            def build_playwright_proxy(proxy_url: str | None) -> dict | None:
                if not proxy_url:
                    return None

                parsed = urlparse(proxy_url)
                if not parsed.scheme or not parsed.hostname:
                    return {"server": proxy_url}

                server = f"{parsed.scheme}://{parsed.hostname}"
                if parsed.port:
                    server = f"{server}:{parsed.port}"

                proxy_config: dict = {"server": server}
                if parsed.username:
                    proxy_config["username"] = unquote(parsed.username)
                if parsed.password:
                    proxy_config["password"] = unquote(parsed.password)

                return proxy_config
            
            # Thử requests trước cho trang tĩnh (nhanh hơn)
            if use_playwright != "always":
                try:
                    headers = {"User-Agent": user_agent}
                    proxies = (
                        {
                            "http": selected_proxy,
                            "https": selected_proxy,
                        }
                        if selected_proxy
                        else None
                    )
                    response = requests.get(
                        url,
                        headers=headers,
                        timeout=timeout,
                        proxies=proxies,
                    )
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.content, "lxml")
                    for script in soup(["script", "style", "nav", "footer"]):
                        script.decompose()
                    
                    text = soup.get_text(separator="\n", strip=True)
                    lines = [line.strip() for line in text.splitlines()]
                    text = "\n".join(line for line in lines if line)
                    
                    # Kiểm tra xem có đủ nội dung không (tránh trang JS-heavy trống)
                    if len(text) > 200 or use_playwright == "never":
                        max_chars = int(os.getenv("WEB_FETCH_MAX_CHARS", "50000"))
                        if len(text) > max_chars:
                            text = text[:max_chars] + f"\n\n[Truncated at {max_chars} chars]"
                        proxy_label = selected_proxy if selected_proxy else "none"
                        return f"URL: {url}\nMethod: requests\nProxy: {proxy_label}\n\n{text}"
                    
                except requests.RequestException:
                    pass  # Fallback to playwright
            
            # Fallback: dùng Playwright cho JS-rendered content
            if not PLAYWRIGHT_AVAILABLE:
                return (
                    f"Error: Trang {url} cần JavaScript rendering nhưng Playwright chưa cài.\n"
                    "Chạy: playwright install chromium"
                )
            
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context_kwargs = {"user_agent": user_agent}
                    playwright_proxy = build_playwright_proxy(selected_proxy)
                    if playwright_proxy:
                        context_kwargs["proxy"] = playwright_proxy

                    context = browser.new_context(**context_kwargs)
                    page = context.new_page()
                    
                    page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
                    page.wait_for_timeout(2000)  # Đợi JS render
                    
                    # Lấy text content
                    html = page.content()
                    browser.close()
                    
                    soup = BeautifulSoup(html, "lxml")
                    for script in soup(["script", "style", "nav", "footer"]):
                        script.decompose()
                    
                    text = soup.get_text(separator="\n", strip=True)
                    lines = [line.strip() for line in text.splitlines()]
                    text = "\n".join(line for line in lines if line)
                    
                    max_chars = int(os.getenv("WEB_FETCH_MAX_CHARS", "50000"))
                    if len(text) > max_chars:
                        text = text[:max_chars] + f"\n\n[Truncated at {max_chars} chars]"
                    
                    proxy_label = selected_proxy if selected_proxy else "none"
                    return f"URL: {url}\nMethod: playwright\nProxy: {proxy_label}\n\n{text}"
                    
            except PlaywrightTimeout:
                return f"Error: Timeout khi render {url} với Playwright (>{timeout}s)"
            except Exception as e:
                return f"Error: Lỗi khi fetch {url} với Playwright: {str(e)}"
        
        return fetch_url

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

    def _adaptive_limits(
        self,
        question: str,
        requested_max_subquestions: int,
        mode: Literal["auto", "fast", "balanced", "deep"],
    ) -> tuple[int, int, str]:
        if mode == "fast":
            selected_subquestions = max(1, min(requested_max_subquestions, 1))
            return selected_subquestions, 8, "simple"
        if mode == "balanced":
            selected_subquestions = max(1, min(requested_max_subquestions, 2))
            return selected_subquestions, 14, "medium"
        if mode == "deep":
            selected_subquestions = max(1, min(requested_max_subquestions, 4))
            return selected_subquestions, 24, "complex"

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

    def _evaluate_quality(self, question: str, answer: str) -> QualityAssessment:
        evaluator = self.model.with_structured_output(QualityAssessment)
        system = (
            "Bạn là quality reviewer cực kỳ nghiêm ngặt. "
            "Chấm điểm câu trả lời theo: độ đầy đủ, tính chính xác, rõ cấu trúc, có nêu rủi ro/giới hạn."
        )
        user = (
            f"Câu hỏi: {question}\n\n"
            f"Câu trả lời hiện tại:\n{answer}\n\n"
            "Trả về score (0-100), verdict (pass/fail), feedback dạng gạch đầu dòng ngắn."
        )
        quality = evaluator.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        quality.score = max(0, min(100, quality.score))
        if quality.score >= 70:
            quality.verdict = "pass"
        return quality

    def _refine_answer(self, question: str, answer: str, feedback: List[str]) -> str:
        system = (
            "Bạn là principal analyst. Hãy cải thiện câu trả lời theo feedback, "
            "giữ tính súc tích và đảm bảo các mục quan trọng rõ ràng."
        )
        user = (
            f"Câu hỏi: {question}\n\n"
            f"Câu trả lời hiện tại:\n{answer}\n\n"
            f"Feedback cần sửa: {chr(10).join(f'- {item}' for item in feedback)}\n\n"
            "Trả về bản final đã cải thiện."
        )
        return self.model.invoke([SystemMessage(content=system), HumanMessage(content=user)]).content

    def summarize_memory(self, previous_summary: str, turns_to_merge: List[dict]) -> str:
        if not turns_to_merge:
            return previous_summary

        turns_text = "\n\n".join(
            f"User: {item.get('user', '')}\nAssistant: {item.get('assistant', '')}"
            for item in turns_to_merge
        )
        system = (
            "Bạn là memory summarizer. Tóm tắt ngữ cảnh hội thoại dạng ngắn gọn, "
            "giữ lại intent, thông tin sở thích/ràng buộc của user, và quyết định quan trọng."
        )
        user = (
            f"Summary hiện tại:\n{previous_summary or '(chưa có)'}\n\n"
            f"Các lượt hội thoại mới cần gộp:\n{turns_text}\n\n"
            "Trả về summary đã cập nhật, tối đa 12 gạch đầu dòng."
        )
        return self.model.invoke([SystemMessage(content=system), HumanMessage(content=user)]).content

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
        include_difficulty_header: bool = True,
        mode: Literal["auto", "fast", "balanced", "deep"] = "auto",
        quality_gate_threshold: int = 70,
    ) -> dict:
        effective_analysis_question = (analysis_question or question).strip()
        selected_subquestions, recursion_limit, complexity = self._adaptive_limits(
            effective_analysis_question,
            requested_max_subquestions=max_subquestions,
            mode=mode,
        )

        self._notify(
            progress_callback,
            (
                "🧭 Đã phân loại độ phức tạp câu hỏi: "
                f"{complexity} | mode={mode} | subquestions={selected_subquestions} | recursion={recursion_limit}"
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

        self._notify(progress_callback, "🛡️ Đang chạy quality gate...")
        quality = self._evaluate_quality(question=question, answer=final_answer)
        threshold = max(1, min(100, quality_gate_threshold))
        if quality.score < threshold:
            self._notify(
                progress_callback,
                f"⚠️ Quality gate chưa đạt ({quality.score}/{threshold}). Đang refine câu trả lời...",
            )
            final_answer = self._refine_answer(
                question=question,
                answer=final_answer,
                feedback=quality.feedback,
            )
            quality = self._evaluate_quality(question=question, answer=final_answer)

        self._notify(
            progress_callback,
            f"✅ Quality gate: {quality.score}/100 ({quality.verdict}). Đang gửi kết quả...",
        )
        if include_difficulty_header:
            difficulty_header = self._build_difficulty_header(
                complexity=complexity,
                selected_subquestions=selected_subquestions,
                recursion_limit=recursion_limit,
            )
            final_answer = f"{difficulty_header}\n\n{final_answer}"

        return {
            "plan": plan.model_dump(),
            "artifacts": [a.__dict__ for a in artifacts],
            "final_answer": final_answer,
            "depth_profile": {
                "complexity": complexity,
                "mode": mode,
                "max_subquestions": selected_subquestions,
                "recursion_limit": recursion_limit,
            },
            "quality_gate": quality.model_dump(),
        }
