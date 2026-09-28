"""English page: the models write for the user in English; the checks stay the same."""
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from formula_rag.catalog import load_catalog
from planning.agents import planner, review
from planning.agents.requirements import RequirementsAgent
from planning.agents.role_model import Rewrite, english, for_language, in_chinese, output_language
from planning.workflow.task_service import TaskService, validate_command
from test_model_settings import ROOT, command


def in_english(run):
    token = output_language.set('en')
    try:
        return run()
    finally:
        output_language.reset(token)


class OutputLanguageTests(unittest.TestCase):
    def test_command_language_is_optional_and_checked(self):
        base = command('create')
        self.assertEqual(validate_command(dict(base, lang='en'))['lang'], 'en')
        self.assertNotIn('lang', validate_command(base))
        with self.assertRaises(ValueError) as caught:
            validate_command(dict(base, lang='fr'))
        self.assertEqual(str(caught.exception), 'INVALID_LANG')

    def test_prompts_and_caps_follow_the_language(self):
        self.assertEqual(for_language('answer：用中文直接回答', 'x'), 'answer：用中文直接回答')
        self.assertEqual((planner.caps(), review.limits()), ((20, 60), review.LIMITS))
        token = output_language.set('en')
        try:
            text = for_language('answer：用中文直接回答', 'answer 不超过 60 个英文词')
            self.assertNotIn('用中文', text)
            self.assertIn('一律用英文', text)
            self.assertIn('answer 不超过 60 个英文词', text)
            self.assertEqual((planner.caps(), review.limits()), ((60, 160), review.EN_LIMITS))
        finally:
            output_language.reset(token)

    def test_an_english_command_asks_every_role_for_english(self):
        prompts = {}

        def capture(selector, role, prompt, view, schema):
            prompts[role] = prompt
            raise OSError('offline')
        with tempfile.TemporaryDirectory() as tmp:
            service = TaskService(ROOT, Path(tmp) / 'p.sqlite')
            with patch('formula_rag.model.LocalSelector.__call__', side_effect=OSError('offline')), \
                 patch('planning.agents.role_model.LocalRoleSelector.__call__', capture):
                state = service.apply(command('create', mode='llm', lang='en'))['state']
                done = service.apply(command('confirm', event_id='e2', ver=state['state_version'], lang='en',
                                             review_hash=state['review']['review_hash']))['state']
        self.assertEqual(done['status'], 'COMPLETED')
        self.assertIn('一律用英文', prompts['compute_agent'])
        self.assertIn('一律用英文', prompts['validator_agent'])
        self.assertNotIn('用中文直接回答', prompts['validator_agent'])
        self.assertFalse(english())  # the command's language does not outlive it

    def test_english_prompts_drop_the_chinese_length_rules_and_examples(self):
        for prompt, swaps in ((planner.PROMPT, planner.EN_SWAPS), (review.PROMPT, review.EN_SWAPS)):
            for old, _ in swaps:
                self.assertIn(old, prompt)  # a reworded prompt must update its swaps
        text = in_english(lambda: for_language(planner.PROMPT, planner.EN_LIMITS, planner.EN_SWAPS))
        self.assertTrue(text.startswith('写给用户看的文字一律用英文'))
        self.assertNotIn('16 字', text)
        self.assertNotIn('由两站经纬度与高程算直线距离', text)
        self.assertNotIn('80 字', in_english(lambda: for_language(review.PROMPT, review.EN_WORDS, review.EN_SWAPS)))

    def test_chinese_text_is_told_apart_from_an_english_sentence_with_a_chinese_name(self):
        self.assertTrue(in_chinese('计算链路余量，并与 10dB 预留要求比较。'))
        self.assertFalse(in_chinese('Slant range from 东港站 to Site B'))
        self.assertFalse(in_chinese(None))

    def test_chinese_plan_text_on_the_english_page_is_asked_for_once_more_then_kept(self):
        cards = load_catalog(ROOT)
        request = dict(schema_version='1.0.0', task_id=str(uuid.uuid4()), revision=0, request_id=str(uuid.uuid4()),
                       raw_text='按自由空间基准，频率2GHz，距离1km，求路径损耗。', manual_parameters={}, condition=None, target=None)
        report = RequirementsAgent(ROOT, selector=False).run(request)
        english_plan = dict(steps=[dict(card='fspl_ghz', why='Path loss from frequency and distance')],
                            assessment=dict(verdict='ready', notes=[dict(kind='goal', text='Answers the path loss asked for.', refs=['target'])]))
        for output, calls_wanted in ((planner.proposal_for(report), 2), (english_plan, 1)):
            views = []

            def model(role, prompt, view, schema):
                views.append(view)
                return dict(output=output)
            plan, role = in_english(lambda: planner.PlanningAgent(model).run(request, report, cards))
            self.assertEqual(len(views), calls_wanted)
            self.assertEqual(plan['origin'], 'model')
        chinese = planner.proposal_for(report)['steps'][0]['why']
        plan, role = in_english(lambda: planner.PlanningAgent(lambda *a: dict(output=planner.proposal_for(report))).run(request, report, cards))
        self.assertEqual(role['diagnostics'][0]['code'], 'PLAN_LANGUAGE')
        self.assertEqual(plan['steps'][0]['why'], chinese)  # kept as written after the second try

    def test_chinese_review_text_on_the_english_page_is_asked_for_once_more(self):
        from planning.agents.calculation import propose_calculation
        from planning.services.calculation import execute, validate_result
        from planning.services.confirmation import confirm_review
        with tempfile.TemporaryDirectory() as tmp:
            draft = TaskService(ROOT, Path(tmp) / 'p.sqlite').apply(command('create'))['state']
        cards = load_catalog(ROOT)
        snapshot = confirm_review(draft['review'], cards)
        result = execute(snapshot, draft['review'], cards, propose_calculation(snapshot))
        facts = review.facts_for(result, snapshot, validate_result(result, snapshot))
        chinese = dict(decision='pass', answer='路径损耗为 98.42 dB。', steps=[], opinions=[])
        self.assertFalse(review.accept(chinese, facts)['hidden'])  # the Chinese page takes it
        with self.assertRaises(Rewrite) as caught:
            in_english(lambda: review.accept(chinese, facts))
        self.assertEqual((str(caught.exception), caught.exception.reason), ('REVIEW_LANGUAGE', 'language'))
        self.assertEqual(caught.exception.kept['answer'], chinese['answer'])
        self.assertFalse(in_english(lambda: review.accept(dict(chinese, answer='The path loss is 98.42 dB.'), facts))['hidden'])


if __name__ == '__main__':
    unittest.main()
