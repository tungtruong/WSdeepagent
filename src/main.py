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

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Thiếu OPENAI_API_KEY. Hãy tạo file .env từ .env.example")

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    args = parse_args()

    agent = DeepResearchAgent(model_name=model_name)
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
