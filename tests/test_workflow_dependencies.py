"""Real dependency smoke tests; memory checkpoints do not prove durability."""
import unittest
from typing import TypedDict


class SmokeState(TypedDict):
    needs_input: bool
    answer: str


class WorkflowDependencyTests(unittest.TestCase):
    def test_stategraph_conditional_interrupt_resume(self):
        from langgraph.graph import StateGraph, START, END
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.types import Command, interrupt

        calls = []

        def propose(state):
            return {"answer": "proposal"}

        def ask(state):
            calls.append("entered")
            answer = interrupt({"question": "Provide missing input"})
            return {"answer": answer, "needs_input": False}

        builder = StateGraph(SmokeState)
        builder.add_node("propose", propose)
        builder.add_node("ask", ask)
        builder.add_edge(START, "propose")
        builder.add_conditional_edges("propose", lambda s: "ask" if s["needs_input"] else END)
        builder.add_edge("ask", END)
        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "dependency-smoke"}}
        paused = graph.invoke({"needs_input": True, "answer": ""}, config)
        self.assertEqual(paused["__interrupt__"][0].value["question"], "Provide missing input")
        resumed = graph.invoke(Command(resume="provided"), config)
        self.assertEqual(resumed["answer"], "provided")
        self.assertFalse(resumed["needs_input"])
        self.assertEqual(calls, ["entered", "entered"])
        direct = graph.invoke({"needs_input": False, "answer": ""}, {"configurable": {"thread_id": "direct"}})
        self.assertEqual(direct["answer"], "proposal")
        self.assertNotIn("__interrupt__", direct)

    def test_existing_ml_imports(self):
        import torch
        import transformers
        self.assertEqual(torch.__version__, "2.8.0+cpu")
        self.assertEqual(transformers.__version__, "4.57.6")
        self.assertEqual(torch.tensor([2, 3]).sum().item(), 5)


if __name__ == "__main__":
    unittest.main()
