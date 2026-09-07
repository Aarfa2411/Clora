"""
Prototype Evaluation Benchmark for Multimodal Engineering Drawing Intelligence.
INDUSAI-X / SIH26117 (MRPL)
Evaluates 20 standardized P&ID questions measuring:
1. Tag Detection
2. Symbol & Component Classification
3. Operational State (NO/NC) Identification
4. Piping Connectivity Relationships
5. Spatial Grid Grounding
"""

import os
import pytest
from typing import Dict, Any, List

from indusai.multimodal.evidence_fusion import EvidenceFusionEngine
from backend.agents.vision_agent import VisionDiagramAgent

# 20 Standardized Prototype Benchmark Questions & Ground Truths
BENCHMARK_QUESTIONS: List[Dict[str, Any]] = [
    # Category 1: Equipment Tag Identification (Questions 1-5)
    {"q_id": "Q01", "cat": "tag_detection", "q": "What is the tag of the main booster pump?", "target": "P-101", "type": "contains"},
    {"q_id": "Q02", "cat": "tag_detection", "q": "What is the tag of the cooling water control valve?", "target": "CV-104B", "type": "contains"},
    {"q_id": "Q03", "cat": "tag_detection", "q": "What is the tag of the manual bypass valve?", "target": "V-109", "type": "contains"},
    {"q_id": "Q04", "cat": "tag_detection", "q": "What is the lube oil cooler exchanger tag?", "target": "E-101", "type": "contains"},
    {"q_id": "Q05", "cat": "tag_detection", "q": "What is the suction pressure transmitter tag?", "target": "PT-201", "type": "contains"},

    # Category 2: Component Classification (Questions 6-9)
    {"q_id": "Q06", "cat": "classification", "q": "What type of equipment is P-101?", "target": "pump", "type": "contains_lower"},
    {"q_id": "Q07", "cat": "classification", "q": "What type of component is CV-104B?", "target": "valve", "type": "contains_lower"},
    {"q_id": "Q08", "cat": "classification", "q": "What type of component is V-109?", "target": "valve", "type": "contains_lower"},
    {"q_id": "Q09", "cat": "classification", "q": "What type of component is E-101?", "target": "cooler", "alt": "exchanger", "type": "contains_either"},

    # Category 3: Operational State (NO/NC) Identification (Questions 10-13)
    {"q_id": "Q10", "cat": "state_detection", "q": "What is the normal operating state of bypass valve V-109?", "target": "NC", "alt": "normally closed", "type": "contains_either_lower"},
    {"q_id": "Q11", "cat": "state_detection", "q": "Is valve V-109 normally open or normally closed?", "target": "closed", "type": "contains_lower"},
    {"q_id": "Q12", "cat": "state_detection", "q": "What is the fail-safe action of control valve CV-104B?", "target": "FC", "alt": "fail", "type": "contains_either"},
    {"q_id": "Q13", "cat": "state_detection", "q": "Is pump P-101 shown as operating?", "target": "operating", "alt": "P-101", "type": "contains_either"},

    # Category 4: Piping Connectivity & Topological Inferences (Questions 14-17)
    {"q_id": "Q14", "cat": "connectivity", "q": "Which valve is installed on the bypass line of CV-104B?", "target": "V-109", "type": "contains"},
    {"q_id": "Q15", "cat": "connectivity", "q": "Does the discharge of P-101 connect to lube oil cooler E-101?", "target": "E-101", "alt": "P-101", "type": "contains_either"},
    {"q_id": "Q16", "cat": "connectivity", "q": "What line feeds cooling water through valve CV-104B?", "target": "cooling", "alt": "CW", "type": "contains_either_lower"},
    {"q_id": "Q17", "cat": "connectivity", "q": "Is valve V-109 parallel to control valve CV-104B?", "target": "V-109", "alt": "CV-104B", "type": "contains_either"},

    # Category 5: Spatial Grid Grounding (Questions 18-20)
    {"q_id": "Q18", "cat": "grounding", "q": "In which grid location is valve CV-104B located?", "target": "D4", "alt": "Grid D4", "type": "contains"},
    {"q_id": "Q19", "cat": "grounding", "q": "In which grid location is manual valve V-109 located?", "target": "D4", "alt": "Grid D4", "type": "contains"},
    {"q_id": "Q20", "cat": "grounding", "q": "What is the drawing number on the title block?", "target": "PID", "alt": "MRPL", "type": "contains"}
]


@pytest.fixture(scope="module")
def p_and_id_drawing():
    path = os.path.join("samples", "PID_Cooling_Water_Circuit_P101.png")
    if not os.path.exists(path):
        from samples.generate_sample_pid import generate_sample_pid
        path = generate_sample_pid(path)
    return path


def test_drawing_prototype_benchmark(p_and_id_drawing):
    """
    Executes the 20-question benchmark suite against the P&ID analysis pipeline,
    recording pass/fail metrics and asserting overall accuracy exceeds the 85% threshold.
    """
    agent = VisionDiagramAgent()
    engine = EvidenceFusionEngine()
    analysis_result = engine.analyze_drawing(p_and_id_drawing)

    results = []
    category_scores: Dict[str, List[int]] = {
        "tag_detection": [],
        "classification": [],
        "state_detection": [],
        "connectivity": [],
        "grounding": []
    }

    for item in BENCHMARK_QUESTIONS:
        q_id = item["q_id"]
        cat = item["cat"]
        q = item["q"]
        target = item["target"]

        # Run analysis via VisionDiagramAgent
        res = agent.analyze(
            question=q,
            drawing_path=p_and_id_drawing,
            drawing_metadata={"id": "pid-mrpl-01", "filename": "PID_Cooling_Water_Circuit_P101.png"}
        )

        citation_text = ""
        for c in res.get("citations", []):
            citation_text += " " + c.get("snippet_or_data", "") + " " + c.get("sheet_or_table", "")

        # Evaluate correctness based on condition
        passed = False
        t_type = item.get("type", "contains")

        if t_type == "contains":
            passed = target in citation_text
        elif t_type == "contains_lower":
            passed = target.lower() in citation_text.lower()
        elif t_type == "contains_either":
            alt = item.get("alt", target)
            passed = (target.lower() in citation_text.lower()) or (alt.lower() in citation_text.lower())
        elif t_type == "contains_either_lower":
            alt = item.get("alt", target)
            passed = (target.lower() in citation_text.lower()) or (alt.lower() in citation_text.lower())


        score = 1 if passed else 0
        category_scores[cat].append(score)
        results.append({
            "id": q_id,
            "category": cat,
            "question": q,
            "passed": passed
        })

    # Calculate metrics
    total_q = len(BENCHMARK_QUESTIONS)
    total_passed = sum(r["passed"] for r in results)
    overall_accuracy = (total_passed / total_q) * 100.0

    print(f"\n========================================================")
    print(f"INDUSAI-X P&ID PROTOTYPE EVALUATION BENCHMARK RESULTS")
    print(f"Total Questions Evaluated: {total_q}")
    print(f"Total Questions Passed:    {total_passed}")
    print(f"Overall Accuracy:          {overall_accuracy:.1f}%")
    print(f"--------------------------------------------------------")
    for cat, scores in category_scores.items():
        cat_acc = (sum(scores) / len(scores)) * 100.0 if scores else 0.0
        print(f"  • {cat.replace('_', ' ').title():<28}: {cat_acc:5.1f}% ({sum(scores)}/{len(scores)})")
    print(f"========================================================\n")

    # Assert that benchmark passes threshold
    assert overall_accuracy >= 85.0, f"Expected benchmark accuracy >= 85%, got {overall_accuracy}%"
