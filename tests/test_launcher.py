import unittest
from pathlib import Path
try:
    from launch import model_command
except ImportError:
    model_command = None


class LauncherTests(unittest.TestCase):
    def test_pinned_local_model_uses_offline_and_nvidia_device(self):
        self.assertIsNotNone(model_command, '本地启动器尚未实现')
        args = model_command(Path(__file__).resolve().parents[1])
        self.assertIn('--offline', args)
        self.assertEqual(args[args.index('--host')+1], '127.0.0.1')
        self.assertIn('Vulkan1', args)
        from planning.providers.registry import Registry
        registry = Registry(Path(__file__).resolve().parents[1])
        self.assertEqual(registry.defaults['chat'], 'qwen35-9b-q4')
        model = registry.models[registry.defaults['chat']]
        self.assertEqual(args[args.index('--alias') + 1], model['alias'])
        self.assertEqual(args[args.index('--port') + 1], model['endpoint'].rsplit(':', 1)[1])
        self.assertEqual(args[args.index('-c') + 1], str(model['context']))
        self.assertEqual(Path(args[args.index('-m') + 1]), Path(__file__).resolve().parents[1] / model['weights'])
        self.assertFalse(any(a.startswith('https://') for a in args))


if __name__ == '__main__':
    unittest.main()
