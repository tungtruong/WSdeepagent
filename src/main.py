from __future__ import annotations

import argparse
import json
import os

from dotenv import load_dotenv

from deep_agent import DeepResearchAgent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deep Agent với LangChain")
    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="Câu hỏi cần nghiên cứu sâu",
    )
    parser.add_argument(
        "--max-subquestions",
        type=int,
        default=5,
        help="Số lượng câu hỏi con tối đa",
    )
    parser.add_argument(
        "--print-artifacts",
        action="store_true",
        help="In cả kết quả trung gian của từng câu hỏi con",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    default_provider = os.getenv("DEFAULT_LLM_PROVIDER", "openai").strip().lower()
    if default_provider not in {"openai", "local"}:
        default_provider = "openai"

    if default_provider == "openai":
        openai_api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not openai_api_key:
            raise RuntimeError("Provider openai yêu cầu OPENAI_API_KEY trong .env")
        agent = DeepResearchAgent(
            model_name=model_name,
            base_url=None,
            api_key=openai_api_key,
        )
    else:
        local_llm_base_url = (os.getenv("LOCAL_LLM_BASE_URL") or "").strip()
        local_llm_api_key = (os.getenv("LOCAL_LLM_API_KEY") or "local").strip() or "local"
        if not local_llm_base_url:
            raise RuntimeError("Provider local yêu cầu LOCAL_LLM_BASE_URL trong .env")
        agent = DeepResearchAgent(
            model_name=model_name,
            base_url=local_llm_base_url,
            api_key=local_llm_api_key,
        )

    result = agent.run(args.query, max_subquestions=args.max_subquestions)

    print("\n=== PLAN ===")
    print(json.dumps(result["plan"], ensure_ascii=False, indent=2))

    if args.print_artifacts:
        print("\n=== ARTIFACTS ===")
        print(json.dumps(result["artifacts"], ensure_ascii=False, indent=2))

    print("\n=== FINAL ANSWER ===")
    print(result["final_answer"])


if __name__ == "__main__":
    main()
